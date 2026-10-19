"""Quản lý giao thức (ProtocolManager).

Đóng gói các thao tác giao thức truyền thông, chuyển tiếp thông điệp qua EventBus.
Dữ liệu âm thanh đi qua kênh truyền trực tiếp (hàng đợi có giới hạn + single consumer), tránh dồn ứ tác vụ create_task trên từng frame.
"""

import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from src.constants.constants import ListeningMode
from src.core.event_bus import EventBus, Events
from src.logging import get_logger

if TYPE_CHECKING:
    from src.core.task_manager import TaskManager
    from src.protocols.protocol import Protocol

logger = get_logger()

# Loại callback âm thanh
AudioCallback = Callable[[bytes], Awaitable[None]]

# Hàng đợi có giới hạn cho âm thanh đến: khi đầy sẽ loại bỏ khung cũ nhất, tránh làm quá tải event loop bởi các tác vụ
_INCOMING_AUDIO_QUEUE_SIZE = 64


class ProtocolTransport:
    """Chịu trách nhiệm tạo giao thức và quản lý kết nối."""

    def __init__(
        self,
        event_bus: EventBus,
        task_manager: Optional["TaskManager"] = None,
    ):
        self._event_bus = event_bus
        self._task_manager = task_manager
        self._protocol: Optional["Protocol"] = None
        self._connect_lock = asyncio.Lock()
        self._incoming_audio_handler: Optional[AudioCallback] = None

        # Hàng đợi âm thanh có giới hạn + single consumer (thay thế create_task trên từng gói tin)
        self._audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(
            maxsize=_INCOMING_AUDIO_QUEUE_SIZE
        )
        self._audio_consumer_task: Optional[asyncio.Task] = None
        self._audio_consumer_running = False

    def set_task_manager(self, task_manager: "TaskManager") -> None:
        """Inject TaskManager (có thể liên kết lại sau khi container khởi tạo)."""
        self._task_manager = task_manager

    @property
    def protocol(self) -> Optional["Protocol"]:
        return self._protocol

    def set_protocol(self, protocol_type: str) -> None:
        logger.debug(f"Thiết lập loại giao thức: {protocol_type}")

        if protocol_type == "mqtt":
            from src.protocols.mqtt_protocol import MqttProtocol

            self._protocol = MqttProtocol(asyncio.get_running_loop())
        else:
            from src.protocols.websocket_protocol import WebsocketProtocol

            self._protocol = WebsocketProtocol()

        self._setup_callbacks()
        self._ensure_audio_consumer()

    def set_audio_handler(self, handler: Optional[AudioCallback]) -> None:
        self._incoming_audio_handler = handler
        self._ensure_audio_consumer()

    def _setup_callbacks(self) -> None:
        if not self._protocol:
            return

        self._protocol.on_network_error(self._on_network_error)
        self._protocol.on_incoming_json(self._on_incoming_json)
        self._protocol.on_incoming_audio(self._on_incoming_audio)
        self._protocol.on_audio_channel_opened(self._on_audio_channel_opened)
        self._protocol.on_audio_channel_closed(self._on_audio_channel_closed)

    def _spawn(self, coro: Awaitable, name: str) -> None:
        """Ưu tiên chạy qua TaskManager; nếu không thì dùng create_task cục bộ và ghi log ngoại lệ."""
        if self._task_manager is not None:
            task = self._task_manager.spawn(coro, name=name)
            if task is None:
                # Đang đóng: đóng coroutine chưa được lên lịch để tránh cảnh báo
                if asyncio.iscoroutine(coro):
                    coro.close()
            return

        try:
            task = asyncio.create_task(coro, name=name)

            def _on_done(t: asyncio.Task) -> None:
                if t.cancelled():
                    return
                exc = t.exception()
                if exc:
                    logger.error(f"Tác vụ {name} kết thúc bất thường: {exc}", exc_info=exc)

            task.add_done_callback(_on_done)
        except Exception as e:
            logger.error(f"Tạo tác vụ {name} thất bại: {e}", exc_info=True)
            if asyncio.iscoroutine(coro):
                coro.close()

    def _ensure_audio_consumer(self) -> None:
        """Đảm bảo consumer âm thanh đến đang chạy (idempotent)."""
        if self._audio_consumer_running:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return

        self._audio_consumer_running = True
        if self._task_manager is not None:
            self._audio_consumer_task = self._task_manager.spawn(
                self._audio_consumer_loop(), name="protocol:audio_consumer"
            )
        else:
            self._audio_consumer_task = asyncio.create_task(
                self._audio_consumer_loop(), name="protocol:audio_consumer"
            )

        if self._audio_consumer_task is None:
            self._audio_consumer_running = False
            return

        def _on_done(t: asyncio.Task) -> None:
            self._audio_consumer_running = False
            self._audio_consumer_task = None
            if t.cancelled():
                return
            # TaskManager.spawn đã ghi log ngoại lệ; ghi thêm log khi create_task cục bộ
            if self._task_manager is None:
                exc = t.exception()
                if exc:
                    logger.error(f"Consumer âm thanh kết thúc bất thường: {exc}", exc_info=exc)

        self._audio_consumer_task.add_done_callback(_on_done)

    async def _audio_consumer_loop(self) -> None:
        """Single consumer xử lý tuần tự âm thanh đến, tránh bùng nổ tác vụ trên từng frame."""
        while True:
            data = await self._audio_queue.get()
            if data is None:
                # Poison pill: thoát
                return
            try:
                if self._incoming_audio_handler:
                    await self._incoming_audio_handler(data)
                else:
                    await self._event_bus.emit(Events.INCOMING_AUDIO, data)
            except Exception as e:
                logger.error(f"Xử lý âm thanh đến thất bại: {e}", exc_info=True)

    def _enqueue_audio(self, data: bytes) -> None:
        """Đưa vào hàng đợi có giới hạn: nếu đầy, loại bỏ khung cũ nhất rồi mới đưa khung mới nhất vào."""
        try:
            self._audio_queue.put_nowait(data)
            return
        except asyncio.QueueFull:
            pass

        # Loại bỏ khung cũ nhất
        try:
            self._audio_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            self._audio_queue.put_nowait(data)
        except asyncio.QueueFull:
            logger.warning("Hàng đợi âm thanh đến vẫn đầy, loại bỏ khung hiện tại")

    async def _stop_audio_consumer(self) -> None:
        """Dừng consumer và làm trống hàng đợi."""
        if self._audio_consumer_task and not self._audio_consumer_task.done():
            try:
                self._audio_queue.put_nowait(None)
            except asyncio.QueueFull:
                # Khi hàng đợi đầy, ép giải phóng một vị trí để đặt poison pill
                try:
                    self._audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    self._audio_queue.put_nowait(None)
                except asyncio.QueueFull:
                    self._audio_consumer_task.cancel()

            try:
                await self._audio_consumer_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"Ngoại lệ khi chờ consumer âm thanh thoát: {e}")

        self._audio_consumer_task = None
        self._audio_consumer_running = False

        # Dọn sạch các phần tử còn sót lại
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _on_network_error(self, error_message: str = None) -> None:
        if error_message:
            logger.error(f"Lỗi mạng: {error_message}")
        await self._event_bus.emit(Events.NETWORK_ERROR, error_message)

    def _on_incoming_json(self, json_data: dict) -> None:
        self._spawn(
            self._event_bus.emit(Events.INCOMING_JSON, json_data),
            name="protocol:incoming_json",
        )

    def _on_incoming_audio(self, data: bytes) -> None:
        try:
            self._ensure_audio_consumer()
            self._enqueue_audio(data)
        except Exception as exc:
            logger.warning(f"Phân phối dữ liệu âm thanh thất bại: {exc}", exc_info=True)

    async def _on_audio_channel_opened(self) -> None:
        logger.info("Kênh giao thức đã mở")
        await self._event_bus.emit(Events.AUDIO_CHANNEL_OPENED)
        await self._event_bus.emit(Events.PROTOCOL_CONNECTED, self._protocol)

    async def _on_audio_channel_closed(self) -> None:
        logger.info("Kênh giao thức đã đóng")
        await self._event_bus.emit(Events.AUDIO_CHANNEL_CLOSED)
        await self._event_bus.emit(Events.PROTOCOL_DISCONNECTED)

    def is_audio_channel_opened(self) -> bool:
        try:
            return bool(self._protocol and self._protocol.is_audio_channel_opened())
        except Exception:
            logger.debug("Ngoại lệ khi kiểm tra trạng thái kênh âm thanh", exc_info=True)
            return False

    async def connect(self, timeout: float = 12.0) -> bool:
        if self.is_audio_channel_opened():
            return True

        if not self._protocol:
            logger.error("Giao thức chưa được khởi tạo")
            return False

        async with self._connect_lock:
            if self.is_audio_channel_opened():
                return True

            try:
                opened = await asyncio.wait_for(
                    self._protocol.open_audio_channel(),
                    timeout=timeout,
                )
                if not opened:
                    logger.error("Kết nối giao thức thất bại")
                    return False

                logger.info("Kết nối giao thức đã được thiết lập")
                return True

            except asyncio.TimeoutError:
                logger.error("Kết nối giao thức quá thời gian chờ")
                return False
            except Exception as e:
                logger.error(f"Kết nối giao thức gặp lỗi ngoại lệ: {e}", exc_info=True)
                return False

    async def disconnect(self) -> None:
        if self._protocol:
            try:
                await self._protocol.close_audio_channel()
            except Exception as e:
                logger.error(f"Đóng giao thức thất bại: {e}", exc_info=True)
        await self._stop_audio_consumer()


class ProtocolGateway:
    """Gateway chịu trách nhiệm gửi tin nhắn."""

    def __init__(self, transport: ProtocolTransport):
        self._transport = transport

    async def send_audio(self, data: bytes) -> None:
        protocol = self._transport.protocol
        if protocol and self._transport.is_audio_channel_opened():
            await protocol.send_audio(data)
        else:
            logger.debug("Kênh âm thanh chưa mở, bỏ qua gửi dữ liệu âm thanh")

    async def send_text(self, text: str) -> None:
        protocol = self._transport.protocol
        if protocol:
            await protocol.send_text(text)

    async def send_start_listening(self, mode: ListeningMode) -> None:
        protocol = self._transport.protocol
        if protocol and self._transport.is_audio_channel_opened():
            await protocol.send_start_listening(mode)
        else:
            logger.warning("Kênh âm thanh chưa mở, bỏ qua send_start_listening")

    async def send_stop_listening(self) -> None:
        protocol = self._transport.protocol
        if protocol and self._transport.is_audio_channel_opened():
            await protocol.send_stop_listening()
        else:
            logger.debug("Kênh âm thanh chưa mở, bỏ qua send_stop_listening")

    async def send_abort_speaking(self, reason: str = None) -> None:
        protocol = self._transport.protocol
        if protocol:
            await protocol.send_abort_speaking(reason)

    async def send_wake_word_detected(self, wake_word: str) -> None:
        protocol = self._transport.protocol
        if protocol and self._transport.is_audio_channel_opened():
            await protocol.send_wake_word_detected(wake_word)
        else:
            logger.warning("Kênh âm thanh chưa mở, bỏ qua send_wake_word_detected")

    async def send_iot_descriptors(self, descriptors) -> None:
        protocol = self._transport.protocol
        if protocol:
            await protocol.send_iot_descriptors(descriptors)

    async def send_iot_states(self, states) -> None:
        protocol = self._transport.protocol
        if protocol:
            await protocol.send_iot_states(states)

    async def send_mcp_message(self, payload) -> None:
        protocol = self._transport.protocol
        if protocol:
            await protocol.send_mcp_message(payload)


class ProtocolManager:
    """Cung cấp giao diện thống nhất ra bên ngoài, bên trong kết hợp Transport + Gateway."""

    def __init__(
        self,
        event_bus: EventBus,
        task_manager: Optional["TaskManager"] = None,
    ):
        self._transport = ProtocolTransport(event_bus, task_manager=task_manager)
        self._gateway = ProtocolGateway(self._transport)

    def set_task_manager(self, task_manager: "TaskManager") -> None:
        self._transport.set_task_manager(task_manager)

    @property
    def protocol(self) -> Optional["Protocol"]:
        return self._transport.protocol

    def set_protocol(self, protocol_type: str) -> None:
        self._transport.set_protocol(protocol_type)

    def set_audio_handler(self, handler: Optional[AudioCallback]) -> None:
        self._transport.set_audio_handler(handler)

    def is_audio_channel_opened(self) -> bool:
        return self._transport.is_audio_channel_opened()

    async def connect(self, timeout: float = 12.0) -> bool:
        return await self._transport.connect(timeout)

    async def disconnect(self) -> None:
        await self._transport.disconnect()

    async def send_audio(self, data: bytes) -> None:
        await self._gateway.send_audio(data)

    async def send_text(self, text: str) -> None:
        await self._gateway.send_text(text)

    async def send_start_listening(self, mode: ListeningMode) -> None:
        await self._gateway.send_start_listening(mode)

    async def send_stop_listening(self) -> None:
        await self._gateway.send_stop_listening()

    async def send_abort_speaking(self, reason: str = None) -> None:
        await self._gateway.send_abort_speaking(reason)

    async def send_wake_word_detected(self, wake_word: str) -> None:
        await self._gateway.send_wake_word_detected(wake_word)

    async def send_iot_descriptors(self, descriptors) -> None:
        await self._gateway.send_iot_descriptors(descriptors)

    async def send_iot_states(self, states) -> None:
        await self._gateway.send_iot_states(states)

    async def send_mcp_message(self, payload) -> None:
        await self._gateway.send_mcp_message(payload)
