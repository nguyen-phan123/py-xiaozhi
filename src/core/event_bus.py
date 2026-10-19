"""EventBus (Hệ thống điều phối sự kiện).

Cung cấp cơ chế giao tiếp tách rời (decoupled) giữa các component.
"""

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from src.logging import get_logger

logger = get_logger()


# Tên sự kiện được định nghĩa trước
class Events:
    """
    Hằng số sự kiện được định nghĩa trước.
    """

    # Trạng thái thiết bị
    DEVICE_STATE_CHANGED = "device_state_changed"

    # Liên quan đến giao thức
    PROTOCOL_CONNECTED = "protocol_connected"
    PROTOCOL_DISCONNECTED = "protocol_disconnected"
    INCOMING_JSON = "incoming_json"
    INCOMING_AUDIO = "incoming_audio"

    # Lỗi mạng
    NETWORK_ERROR = "network_error"

    # Kênh âm thanh
    AUDIO_CHANNEL_OPENED = "audio_channel_opened"
    AUDIO_CHANNEL_CLOSED = "audio_channel_closed"
    # Vòng đời AudioCodec (AudioPlugin → MusicPlayer v.v. đăng ký lắng nghe, tránh set trực tiếp)
    AUDIO_CODEC_CHANGED = "audio_codec_changed"
    # Yêu cầu liệt kê lại thiết bị âm thanh (làm mới trang cài đặt; cần dừng stream trước rồi PortAudio reinit)
    # payload: asyncio.Future tùy chọn, khi hoàn thành set_result(list|dict|None)
    AUDIO_DEVICES_REFRESH_REQUEST = "audio_devices_refresh_request"

    # Vòng đời ứng dụng
    APP_SHUTDOWN = "app_shutdown"
    # Thông báo cấp hệ thống (banner chế độ giáng cấp v.v., payload: str)
    SYSTEM_NOTICE = "system_notice"

    # Sự kiện trình phát nhạc
    MUSIC_STATE_CHANGED = "music_state_changed"  # Thay đổi trạng thái phát
    MUSIC_LYRICS_UPDATE = "music_lyrics_update"  # Cập nhật lời bài hát
    MUSIC_PROGRESS_UPDATE = "music_progress_update"  # Cập nhật tiến độ phát

    # Lệnh điều khiển nhạc (điều khiển MusicPlayer từ bên ngoài)
    MUSIC_PAUSE_REQUEST = "music_pause_request"  # Yêu cầu tạm dừng (như TTS)
    MUSIC_RESUME_REQUEST = "music_resume_request"  # Yêu cầu tiếp tục

    # Thao tác UI (Giao diện → Plugin)
    UI_BUTTON_PRESS = "ui_button_press"  # Thủ công: Nhấn nút
    UI_BUTTON_RELEASE = "ui_button_release"  # Thủ công: Thả nút
    UI_MANUAL_TOGGLE = "ui_manual_toggle"  # Thủ công: Bấm một cái để bắt đầu/kết thúc ghi âm
    UI_AUTO_TOGGLE = "ui_auto_toggle"  # Chuyển đổi tự động/thủ công
    UI_AUTO_START = "ui_auto_start"  # Tự động: Bắt đầu/dừng đối thoại
    UI_ABORT_REQUEST = "ui_abort_request"  # Ngắt lời (abort)
    UI_SEND_TEXT = "ui_send_text"  # Gửi văn bản
    UI_QUIT_REQUEST = "ui_quit_request"  # Thoát ứng dụng
    UI_OPEN_SETTINGS = "ui_open_settings"  # Mở cài đặt
    UI_TOGGLE_WINDOW = "ui_toggle_window"  # Ẩn/hiện cửa sổ chính (GUI)

    # Sự kiện thay đổi cấu hình
    CONFIG_CHANGED = "config_changed"  # Cấu hình đã thay đổi (cần hot-reload)
    # Sau khi thay đổi danh sách MCP tool: ngắt và kết nối lại giao thức để server gọi lại tools/list
    PROTOCOL_RECONNECT_REQUEST = "protocol_reconnect_request"


# Tập hợp tên sự kiện đã biết: cảnh báo qua warning khi on/emit sai chính tả (hỗ trợ debug)
_KNOWN_EVENTS: frozenset[str] = frozenset(
    v for k, v in vars(Events).items() if not k.startswith("_") and isinstance(v, str)
)


class EventBus:
    """EventBus (Hệ thống điều phối sự kiện).

    Hỗ trợ xử lý sự kiện bất đồng bộ, thực hiện giao tiếp ghép lỏng (loose coupling) giữa các component.

    Cách dùng:
        bus = EventBus()

        # Đăng ký handler
        async def on_state_changed(state):
            print(f"State: {state}")

        bus.on(Events.DEVICE_STATE_CHANGED, on_state_changed)

        # Kích hoạt sự kiện
        await bus.emit(Events.DEVICE_STATE_CHANGED, DeviceState.LISTENING)

        # Xóa handler
        bus.off(Events.DEVICE_STATE_CHANGED, on_state_changed)
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable[..., Awaitable[None]]]] = defaultdict(
            list
        )

    @staticmethod
    def _warn_if_unknown(event: str, action: str) -> None:
        if event not in _KNOWN_EVENTS:
            logger.warning(
                f"EventBus: {action} tên sự kiện không xác định {event!r} (có thể viết sai chính tả; "
                "vui lòng dùng hằng số Events.*)"
            )

    def on(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        """Đăng ký handler xử lý sự kiện.

        Args:
            event: Tên sự kiện
            handler: Hàm xử lý bất đồng bộ (async handler)
        """
        self._warn_if_unknown(event, "đăng ký")
        if handler not in self._handlers[event]:
            self._handlers[event].append(handler)
            logger.debug(f"EventBus: Đăng ký handler {handler.__name__} -> {event}")

    def off(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        """Xóa handler xử lý sự kiện.

        Args:
            event: Tên sự kiện
            handler: Hàm xử lý cần xóa
        """
        if handler in self._handlers[event]:
            self._handlers[event].remove(handler)
            logger.debug(f"EventBus: Xóa handler {handler.__name__} <- {event}")

    def clear(self, event: str = None) -> None:
        """Xóa các handler xử lý sự kiện.

        Args:
            event: Tên sự kiện, nếu là None sẽ xóa toàn bộ
        """
        if event is None:
            self._handlers.clear()
            logger.debug("EventBus: Xóa tất cả handler")
        elif event in self._handlers:
            self._handlers[event].clear()
            logger.debug(f"EventBus: Xóa tất cả handler của sự kiện {event}")

    async def emit(self, event: str, data: Any = None) -> None:
        """Kích hoạt sự kiện.

        Gọi đồng thời tất cả các handler đã đăng ký.

        Args:
            event: Tên sự kiện
            data: Dữ liệu sự kiện
        """
        handlers = list(self._handlers.get(event, []))
        if not handlers:
            # Khi không có người đăng ký vẫn nhắc nhở nếu tên sự kiện không xác định, tránh mất dấu lỗi chính tả
            self._warn_if_unknown(event, "kích hoạt")
            return

        logger.debug(f"EventBus: Kích hoạt sự kiện {event}, {len(handlers)} handler")

        # Thực thi đồng thời tất cả handler
        tasks = []
        for handler in handlers:
            try:
                tasks.append(self._safe_call(handler, data))
            except Exception as e:
                logger.error(
                    f"EventBus: Tạo tác vụ cho {handler.__name__} thất bại: {e}",
                    exc_info=True,
                )

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def emit_sequential(self, event: str, data: Any = None) -> None:
        """Kích hoạt sự kiện tuần tự.

        Gọi lần lượt các handler theo thứ tự đăng ký.

        Args:
            event: Tên sự kiện
            data: Dữ liệu sự kiện
        """
        handlers = list(self._handlers.get(event, []))
        for handler in handlers:
            await self._safe_call(handler, data)

    async def _safe_call(
        self, handler: Callable[..., Awaitable[None]], data: Any
    ) -> None:
        """
        Gọi handler an toàn, bắt và xử lý ngoại lệ.
        """
        try:
            if data is None:
                await handler()
            else:
                await handler(data)
        except Exception as e:
            logger.error(
                f"EventBus: Handler {handler.__name__} thực thi gặp ngoại lệ: {e}",
                exc_info=True,
            )

    def has_handlers(self, event: str) -> bool:
        """
        Kiểm tra sự kiện có handler nào hay không.
        """
        return bool(self._handlers.get(event))

    def handler_count(self, event: str) -> int:
        """
        Lấy số lượng handler của một sự kiện.
        """
        return len(self._handlers.get(event, []))
