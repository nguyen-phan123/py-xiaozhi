"""Plugin cơ sở.

Sử dụng interface PluginContext và PluginCommands để tương tác với các service lõi.
"""

import asyncio
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext
    from src.core.resource_pool import ResourcePool


class Plugin:
    """Lớp cơ sở cho plugin.

    Plugin lấy trạng thái thông qua PluginContext, thực thi thao tác thông qua PluginCommands.

    Thuộc tính:
        name: Tên plugin, dùng cho khai báo phụ thuộc và ghi log
        priority: Mức độ ưu tiên, giá trị càng nhỏ càng ưu tiên cao (phạm vi: 1-100)
        requires: Danh sách tên plugin phụ thuộc, PluginManager sẽ tự động tiêm vào

    Cách dùng:
        class MyPlugin(Plugin):
            name = "my_plugin"
            priority = 50
            requires = ["audio"]  # Khai báo phụ thuộc vào AudioPlugin

            async def setup(self, ctx, cmd):
                await super().setup(ctx, cmd)
                # self.deps["audio"] có thể lấy instance AudioPlugin
    """

    name: str = "plugin"
    priority: int = 50  # Mức độ ưu tiên, giá trị càng nhỏ càng ưu tiên cao (phạm vi: 1-100)
    requires: List[str] = []  # Danh sách tên plugin phụ thuộc

    def __init__(self) -> None:
        self._started = False
        self._failed = False
        self._ctx: "PluginContext" = None
        self._cmd: "PluginCommands" = None
        self._deps: dict[str, "Plugin"] = {}  # Các instance plugin được tiêm phụ thuộc

    @property
    def ctx(self) -> "PluginContext":
        """
        Lấy context của plugin.
        """
        return self._ctx

    @property
    def cmd(self) -> "PluginCommands":
        """
        Lấy interface lệnh của plugin.
        """
        return self._cmd

    @property
    def deps(self) -> dict[str, "Plugin"]:
        """Lấy các instance plugin phụ thuộc."""
        return self._deps

    @property
    def failed(self) -> bool:
        """Plugin đã bị đánh dấu thất bại hay chưa (setup/start thất bại hoặc dependency thất bại)."""
        return self._failed

    def mark_failed(self) -> None:
        """Đánh dấu plugin thất bại, các bước start/notify tiếp theo sẽ bị bỏ qua."""
        self._failed = True

    def get_dep(self, name: str) -> Optional["Plugin"]:
        """Lấy plugin phụ thuộc theo tên chỉ định."""
        return self._deps.get(name)

    def _inject_dependency(self, name: str, plugin: "Plugin"):
        """Tiêm plugin phụ thuộc (được gọi bởi PluginManager)."""
        self._deps[name] = plugin

    async def setup(self, ctx: "PluginContext", cmd: "PluginCommands") -> None:
        """Giai đoạn chuẩn bị plugin.

        Args:
            ctx: Context của plugin (truy cập trạng thái ở chế độ chỉ đọc)
            cmd: Interface lệnh của plugin (thực thi thao tác)
        """
        self._ctx = ctx
        self._cmd = cmd
        await asyncio.sleep(0)

    async def start(self) -> None:
        """
        Khởi chạy plugin (thường được gọi sau khi kết nối giao thức được thiết lập).
        """
        self._started = True
        await asyncio.sleep(0)

    async def on_protocol_connected(self, protocol: Any) -> None:
        """
        Thông báo sau khi kênh giao thức được thiết lập.
        """
        await asyncio.sleep(0)

    async def on_incoming_json(self, message: Any) -> None:
        """
        Thông báo khi nhận được tin nhắn JSON.
        """
        await asyncio.sleep(0)

    async def on_incoming_audio(self, data: bytes) -> None:
        """
        Thông báo khi nhận được dữ liệu âm thanh.
        """
        await asyncio.sleep(0)

    async def on_device_state_changed(self, state: Any) -> None:
        """
        Thông báo thay đổi trạng thái thiết bị.
        """
        await asyncio.sleep(0)

    async def stop(self) -> None:
        """
        Dừng plugin.
        """
        self._started = False
        await asyncio.sleep(0)

    def register_resources(self, pool: "ResourcePool") -> None:
        """
        Đăng ký hàm dọn dẹp vào pool tài nguyên. Lớp con ghi đè phương thức này để đăng ký tài nguyên cần giải phóng.
        Tài nguyên được giải phóng theo thứ tự ngược lại lúc đăng ký, đăng ký trước sẽ giải phóng sau.

        Args:
            pool: Instance của pool tài nguyên
        """
        pass
