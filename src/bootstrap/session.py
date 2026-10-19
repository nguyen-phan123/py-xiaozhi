"""Điều khiển phiên hội thoại: State machine nghe/nói và gửi tin qua giao thức.

Tách biệt với SessionActions phía UI (nút bấm/chế độ): ở đây chỉ chịu trách nhiệm về logic phiên hội thoại cấp ứng dụng như connect /
listen / abort / TTS loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.constants.constants import DeviceState, ListeningMode
from src.core.event_bus import Events
from src.logging import get_logger

if TYPE_CHECKING:
    from src.core.event_bus import EventBus
    from src.core.protocol_manager import ProtocolManager
    from src.core.state_manager import StateManager
    from src.plugins.manager import PluginManager

logger = get_logger()


class ConversationSession:
    """Bộ điều khiển phiên hội thoại cấp ứng dụng."""

    def __init__(
        self,
        state: "StateManager",
        protocol: "ProtocolManager",
        plugins: "PluginManager",
        event_bus: Optional["EventBus"] = None,
    ) -> None:
        self.state = state
        self.protocol = protocol
        self.plugins = plugins
        self._event_bus = event_bus
        self._aborted = False
        # Kết nối lại cấu hình MCP tool v.v.: sau khi mở kênh thì giữ IDLE, không tự động chuyển sang lắng nghe
        self._keep_idle_on_channel_open = False

    # -------------------------
    # Đăng ký sự kiện
    # -------------------------
    def bind_events(self, event_bus: "EventBus") -> None:
        """Đăng ký các sự kiện liên quan đến giao thức/trạng thái (có thể gọi lặp lại, lấy lần gọi cuối làm chuẩn)."""
        self._event_bus = event_bus
        event_bus.on(Events.AUDIO_CHANNEL_OPENED, self._on_audio_channel_opened)
        event_bus.on(Events.AUDIO_CHANNEL_CLOSED, self._on_audio_channel_closed)
        event_bus.on(Events.INCOMING_JSON, self._on_incoming_json)
        # Lưu ý: INCOMING_AUDIO đi qua kênh truyền trực tiếp, không qua EventBus nữa
        event_bus.on(Events.NETWORK_ERROR, self._on_network_error)
        event_bus.on(Events.DEVICE_STATE_CHANGED, self._on_device_state_changed)
        event_bus.on(
            Events.PROTOCOL_RECONNECT_REQUEST, self._on_protocol_reconnect_request
        )

    # -------------------------
    # Bộ xử lý sự kiện
    # -------------------------
    async def _on_audio_channel_opened(self, _=None) -> None:
        if self._keep_idle_on_channel_open:
            self._keep_idle_on_channel_open = False
            self.state.set_keep_listening(False)
            await self.state.set_device_state(DeviceState.IDLE)
            logger.info("Kênh giao thức đã mở (kết nối lại cấu hình): giữ trạng thái chờ, không vào lắng nghe")
            return
        await self.state.set_device_state(DeviceState.LISTENING)

    async def _on_audio_channel_closed(self, _=None) -> None:
        await self.state.set_device_state(DeviceState.IDLE)

    async def _on_network_error(self, error_message: str = None) -> None:
        """Lỗi mạng: Dừng lắng nghe liên tục và reset trạng thái thiết bị về IDLE."""
        self.state.set_keep_listening(False)
        try:
            if not self.state.is_idle():
                await self.state.set_device_state(DeviceState.IDLE)
        except Exception as e:
            logger.error(f"Khôi phục trạng thái thiết bị sau lỗi mạng thất bại: {e}", exc_info=True)

    async def _on_device_state_changed(self, data: dict) -> None:
        new_state = data.get("new_state")
        if new_state:
            await self.plugins.notify_device_state_changed(new_state)
            if new_state == DeviceState.LISTENING:
                self._aborted = False

    async def _on_incoming_json(self, json_data: dict) -> None:
        try:
            msg_type = json_data.get("type") if isinstance(json_data, dict) else None
            logger.info(f"Nhận tin nhắn JSON: type={msg_type}")

            if msg_type == "tts":
                state = json_data.get("state")
                if state == "start":
                    await self._handle_tts_start()
                elif state == "stop":
                    await self._handle_tts_stop()

            await self.plugins.notify_incoming_json(json_data)

        except Exception as e:
            logger.error(f"Xử lý tin nhắn JSON thất bại: {e}", exc_info=True)

    async def _handle_tts_start(self) -> None:
        if (
            self.state.keep_listening
            and self.state.listening_mode == ListeningMode.REALTIME
        ):
            await self.state.set_device_state(DeviceState.LISTENING)
        else:
            await self.state.set_device_state(DeviceState.SPEAKING)

    async def _handle_tts_stop(self) -> None:
        # Nếu vẫn tiếp tục nghe thì cố gắng gửi listen trước, rồi mới xóa queue và đổi trạng thái
        if not self.state.keep_listening:
            await self.state.set_device_state(DeviceState.IDLE)
            return

        # realtime thường vẫn đang trong trạng thái listen, không cần gửi lại
        if self.state.listening_mode != ListeningMode.REALTIME:
            if self.protocol.is_audio_channel_opened():
                try:
                    await self.protocol.send_start_listening(self.state.listening_mode)
                except Exception as e:
                    logger.warning(
                        f"Lắng nghe lại sau khi kết thúc TTS thất bại: {e}",
                        exc_info=True,
                    )
            else:
                logger.warning("TTS kết thúc nhưng kênh giao thức đã đóng, bỏ qua lắng nghe lại")

        try:
            audio_plugin = self.plugins.get_plugin("audio")
            if audio_plugin and audio_plugin.codec:
                await audio_plugin.codec.clear_audio_queue()
        except Exception as e:
            logger.warning(f"Xóa hàng đợi âm thanh thất bại: {e}", exc_info=True)

        await self.state.set_device_state(DeviceState.LISTENING)

    # -------------------------
    # Phương thức thao tác
    # -------------------------
    async def connect_protocol(self) -> bool:
        if self.protocol.is_audio_channel_opened():
            return True

        opened = await self.protocol.connect()
        if opened:
            await self.plugins.notify_protocol_connected(self.protocol.protocol)
        return opened

    async def _on_protocol_reconnect_request(self, _=None) -> None:
        """Danh sách MCP tool thay đổi sau khi lưu cài đặt: nếu đã kết nối thì ngắt và kết nối lại để server list lại.

        Chỉ làm mới giao thức / góc nhìn công cụ, không khôi phục phiên lắng nghe (tránh vào trạng thái «đang lắng nghe» sau khi lưu cài đặt).
        """
        try:
            if not self.protocol.is_audio_channel_opened():
                logger.info("Cấu hình công cụ MCP đã cập nhật (hiện chưa kết nối, có hiệu lực lần kết nối tới)")
                return
            logger.info("Cấu hình công cụ MCP đã cập nhật, đang kết nối lại giao thức…")
            # Ngắt ngữ nghĩa nghe/nói đang diễn ra để tránh giữ keep_listening sau khi kết nối lại
            self.state.set_keep_listening(False)
            self._aborted = False
            self._keep_idle_on_channel_open = True
            try:
                await self.protocol.disconnect()
                ok = await self.connect_protocol()
            except Exception:
                self._keep_idle_on_channel_open = False
                raise
            if ok:
                # Bảo hiểm kép: nếu thứ tự callback OPENED bất thường, vẫn kéo về IDLE
                if not self.state.is_idle():
                    await self.state.set_device_state(DeviceState.IDLE)
                logger.info("Kết nối lại giao thức thành công (tools/list mới sẽ có hiệu lực khi bắt tay, giữ trạng thái chờ)")
            else:
                self._keep_idle_on_channel_open = False
                logger.warning("Kết nối lại giao thức thất bại, vui lòng kết nối lại thủ công")
        except Exception as e:
            self._keep_idle_on_channel_open = False
            logger.error(f"Kết nối lại giao thức thất bại: {e}", exc_info=True)

    async def start_listening(self, mode: ListeningMode) -> None:
        ok = await self.connect_protocol()
        if not ok:
            return

        self.state.set_listening_mode(mode)
        self.state.set_keep_listening(mode != ListeningMode.MANUAL)
        await self.protocol.send_start_listening(mode)
        await self.state.set_device_state(DeviceState.LISTENING)

    async def stop_listening(self) -> None:
        self.state.set_keep_listening(False)
        await self.protocol.send_stop_listening()
        await self.state.set_device_state(DeviceState.IDLE)

    async def start_listening_manual(self) -> None:
        ok = await self.connect_protocol()
        if not ok:
            return

        self.state.set_keep_listening(False)

        if self.state.is_speaking():
            logger.info("Đang phát giọng nói, gửi lệnh ngắt")
            await self.protocol.send_abort_speaking(None)
            await self.state.set_device_state(DeviceState.IDLE)

        await self.protocol.send_start_listening(ListeningMode.MANUAL)
        await self.state.set_device_state(DeviceState.LISTENING)

    async def stop_listening_manual(self) -> None:
        await self.protocol.send_stop_listening()
        await self.state.set_device_state(DeviceState.IDLE)

    async def start_auto_conversation(self) -> None:
        ok = await self.connect_protocol()
        if not ok:
            return

        mode = (
            ListeningMode.REALTIME
            if self.state.aec_enabled
            else ListeningMode.AUTO_STOP
        )
        self.state.set_listening_mode(mode)
        self.state.set_keep_listening(True)

        await self.protocol.send_start_listening(mode)
        await self.state.set_device_state(DeviceState.LISTENING)

    async def abort_speaking(self, reason: str) -> None:
        # Khi cuộc hội thoại tự động vẫn đang tiếp tục nghe, ngắt lời xong quay về listening chứ đừng dừng ở idle
        if self._aborted:
            logger.debug(f"Đã hủy bỏ trước đó, bỏ qua yêu cầu trùng lặp: {reason}")
            return

        logger.info(f"Hủy bỏ phát giọng nói: {reason}")
        self._aborted = True
        self.state.set_aborted(True)
        try:
            if self.protocol.is_audio_channel_opened():
                await self.protocol.send_abort_speaking(reason)
        except Exception as e:
            logger.warning(f"Gửi abort thất bại: {e}", exc_info=True)

        if self.state.keep_listening:
            if self.state.listening_mode != ListeningMode.REALTIME:
                if self.protocol.is_audio_channel_opened():
                    try:
                        await self.protocol.send_start_listening(
                            self.state.listening_mode
                        )
                    except Exception as e:
                        logger.warning(
                            f"Lắng nghe lại sau khi ngắt thất bại: {e}",
                            exc_info=True,
                        )
            await self.state.set_device_state(DeviceState.LISTENING)
            self._aborted = False
            self.state.set_aborted(False)
            logger.debug("Đã khôi phục lắng nghe liên tục sau khi ngắt")
        else:
            await self.state.set_device_state(DeviceState.IDLE)
