"""Định nghĩa giao thức interface (Protocol Interface Definitions).

Định nghĩa hợp đồng (contract) giữa plugin, cửa sổ giao diện và dịch vụ cốt lõi, thực hiện ghép lỏng (loose coupling).
"""

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol

if TYPE_CHECKING:
    from src.constants.constants import DeviceState, ListeningMode


class PluginContext(Protocol):
    """Context chỉ đọc mà plugin có thể truy cập.

    Plugin lấy trạng thái ứng dụng qua interface này nhưng không thể trực tiếp sửa đổi trạng thái.
    """

    def get_device_state(self) -> "DeviceState":
        """
        Lấy trạng thái thiết bị hiện tại.
        """
        ...

    def get_listening_mode(self) -> "ListeningMode":
        """
        Lấy chế độ lắng nghe hiện tại.
        """
        ...

    def is_listening(self) -> bool:
        """
        Kiểm tra xem có đang lắng nghe hay không.
        """
        ...

    def is_speaking(self) -> bool:
        """
        Kiểm tra xem có đang nói hay không.
        """
        ...

    def is_idle(self) -> bool:
        """
        Kiểm tra xem có đang ở trạng thái rảnh (IDLE) hay không.
        """
        ...

    def is_audio_channel_opened(self) -> bool:
        """
        Kiểm tra kênh âm thanh đã mở hay chưa.
        """
        ...

    def should_capture_audio(self) -> bool:
        """
        Kiểm tra có nên thu âm thanh hay không.
        """
        ...

    def is_keep_listening(self) -> bool:
        """
        Kiểm tra có duy trì lắng nghe liên tục hay không.
        """
        ...

    def get_config(self) -> Any:
        """
        Lấy bộ quản lý cấu hình (ConfigManager).
        """
        ...


class PluginCommands(Protocol):
    """Các lệnh mà plugin có thể thực thi.

    Plugin thực hiện các thao tác qua interface này, logic cụ thể do core service triển khai.
    """

    async def start_listening(self, mode: "ListeningMode") -> None:
        """
        Bắt đầu lắng nghe.
        """
        ...

    async def stop_listening(self) -> None:
        """
        Dừng lắng nghe.
        """
        ...

    async def abort_speaking(self, reason: str) -> None:
        """
        Ngắt đầu ra giọng nói.
        """
        ...

    async def send_audio(self, data: bytes) -> None:
        """
        Gửi dữ liệu âm thanh.
        """
        ...

    async def send_text(self, text: str) -> None:
        """
        Gửi tin nhắn văn bản.
        """
        ...

    async def send_wake_word_detected(self, text: str) -> None:
        """
        Gửi văn bản đã phát hiện (từ đánh thức hoặc input của người dùng).
        """
        ...

    async def send_mcp_message(self, payload: str) -> None:
        """
        Gửi thông điệp MCP (tự động đóng gói định dạng).
        """
        ...

    async def connect_protocol(self) -> bool:
        """
        Kết nối kênh giao thức.
        """
        ...

    def spawn(self, coro: Awaitable[Any], name: str) -> Any:
        """
        Tạo tác vụ bất đồng bộ (async task).
        """
        ...

    def schedule_command_nowait(self, fn: Callable, *args, **kwargs) -> None:
        """
        Lập lịch lệnh (non-blocking).
        """
        ...

    def request_shutdown(self) -> None:
        """
        Yêu cầu đóng ứng dụng.
        """
        ...


class EventHandler(Protocol):
    """
    Giao thức cho EventHandler.
    """

    async def __call__(self, data: Any = None) -> None:
        """
        Xử lý sự kiện.
        """
        ...


class EventBusProtocol(Protocol):
    """Giao thức EventBus.

    Dùng cho giao tiếp tách rời (decoupled) giữa các component.
    """

    def on(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        """
        Đăng ký handler xử lý sự kiện.
        """
        ...

    def off(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        """
        Xóa handler xử lý sự kiện.
        """
        ...

    async def emit(self, event: str, data: Any = None) -> None:
        """
        Kích hoạt sự kiện.
        """
        ...
