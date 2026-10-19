"""Quản lý plugin.

Quản lý vòng đời plugin, hỗ trợ khai báo phụ thuộc và sắp xếp topo.
"""

from typing import TYPE_CHECKING, Any, List, Optional

from src.logging import get_logger

from .base import Plugin

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext

logger = get_logger()


class PluginManager:
    """Trình quản lý plugin.

    Nhiệm vụ:
    - Sắp xếp topo theo quan hệ phụ thuộc
    - Tự động tiêm dependency cho plugin
    - Broadcast thống nhất setup/start/stop
    - Cô lập lỗi, một plugin thất bại không ảnh hưởng đến plugin khác
    - Đánh dấu thất bại + bỏ qua downstream khi dependency thất bại
    """

    def __init__(self) -> None:
        self._plugins: List[Plugin] = []
        self._by_name: dict[str, Plugin] = {}
        self._sorted: bool = False

    def register(self, *plugins: Plugin) -> None:
        """Đăng ký plugin.

        Ban đầu sắp xếp theo priority, sau này khi setup_all sẽ sắp xếp theo topo dependency.
        """
        sorted_plugins = sorted(plugins, key=lambda p: getattr(p, "priority", 50))
        for p in sorted_plugins:
            if p not in self._plugins:
                self._plugins.append(p)
                try:
                    name = getattr(p, "name", None)
                    if isinstance(name, str) and name:
                        self._by_name[name] = p
                except Exception as e:
                    logger.error(f"Đăng ký plugin thất bại: {e}", exc_info=True)
        self._sorted = False

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Lấy instance plugin theo tên."""
        return self._by_name.get(name)

    def is_failed(self, name: str) -> bool:
        """Kiểm tra plugin có bị thất bại không (chưa đăng ký được coi là thất bại)."""
        plugin = self._by_name.get(name)
        return plugin is None or plugin.failed

    def failed_plugins(self) -> List[str]:
        """Trả về danh sách tên tất cả plugin đã thất bại."""
        return [
            p.name
            for p in self._plugins
            if getattr(p, "name", None) and p.failed
        ]

    def _dependencies_ok(self, plugin: Plugin) -> bool:
        """Kiểm tra xem các dependency được plugin khai báo có khả dụng không (đã đăng ký và chưa thất bại)."""
        requires = getattr(plugin, "requires", []) or []
        for dep_name in requires:
            dep = self._by_name.get(dep_name)
            if dep is None:
                logger.warning(
                    f"Plugin {getattr(plugin, 'name', 'unknown')} phụ thuộc {dep_name} chưa được đăng ký"
                )
                return False
            if dep.failed:
                logger.warning(
                    f"Plugin {getattr(plugin, 'name', 'unknown')} phụ thuộc {dep_name} đã thất bại, bỏ qua"
                )
                return False
        return True

    def _active_plugins(self) -> List[Plugin]:
        """Danh sách các plugin chưa bị thất bại."""
        return [p for p in self._plugins if not p.failed]

    def _topological_sort(self) -> List[Plugin]:
        """Sắp xếp topo danh sách plugin, đảm bảo dependency được khởi tạo trước plugin phụ thuộc vào nó.

        Returns:
            Danh sách plugin sau khi sắp xếp

        Raises:
            ValueError: Tồn tại phụ thuộc vòng (circular dependency)
        """
        # Xây dựng đồ thị phụ thuộc
        in_degree: dict[str, int] = {}
        dependents: dict[str, List[str]] = {}  # dependents: được ai phụ thuộc vào

        for p in self._plugins:
            name = getattr(p, "name", "")
            if name:
                in_degree[name] = 0
                dependents[name] = []

        for p in self._plugins:
            name = getattr(p, "name", "")
            requires = getattr(p, "requires", []) or []
            for dep in requires:
                if dep in self._by_name:
                    in_degree[name] = in_degree.get(name, 0) + 1
                    dependents[dep].append(name)
                else:
                    logger.warning(f"Plugin {name} khai báo phụ thuộc {dep} chưa đăng ký, bỏ qua")

        # Thuật toán Kahn
        queue = [name for name, degree in in_degree.items() if degree == 0]
        result: List[Plugin] = []

        while queue:
            # Chọn node có in-degree bằng 0 với priority nhỏ nhất
            queue.sort(
                key=lambda n: getattr(self._by_name.get(n), "priority", 50)
            )
            current = queue.pop(0)
            plugin = self._by_name.get(current)
            if plugin:
                result.append(plugin)

            for dependent in dependents.get(current, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len([p for p in self._plugins if getattr(p, "name", "")]):
            raise ValueError("Tồn tại phụ thuộc vòng giữa các plugin")

        # Thêm các plugin không có name vào cuối danh sách
        unnamed = [p for p in self._plugins if not getattr(p, "name", "")]
        result.extend(unnamed)

        return result

    def _inject_dependencies(self) -> None:
        """Tiêm các dependency đã khai báo cho từng plugin."""
        for p in self._plugins:
            requires = getattr(p, "requires", []) or []
            for dep_name in requires:
                dep_plugin = self._by_name.get(dep_name)
                if dep_plugin:
                    p._inject_dependency(dep_name, dep_plugin)
                    logger.debug(f"Inject dependency: {p.name} <- {dep_name}")

    async def setup_all(self, ctx: "PluginContext", cmd: "PluginCommands") -> None:
        """Khởi tạo tất cả các plugin.

        Khởi tạo theo thứ tự sau khi sắp xếp topo, tự động tiêm dependency.
        Plugin bị lỗi setup hoặc lỗi dependency sẽ bị mark_failed và bỏ qua các vòng đời tiếp theo.

        Args:
            ctx: Context của plugin
            cmd: Interface lệnh của plugin
        """
        # Sắp xếp topo
        if not self._sorted:
            try:
                self._plugins = self._topological_sort()
                self._sorted = True
                logger.info(
                    f"Sắp xếp topo plugin hoàn tất: {[p.name for p in self._plugins if hasattr(p, 'name')]}"
                )
            except ValueError as e:
                logger.error(f"Sắp xếp plugin thất bại: {e}", exc_info=True)
                # Fallback về sắp xếp theo mức độ ưu tiên (priority)
                self._plugins.sort(key=lambda p: getattr(p, "priority", 50))

        # Tiêm dependency
        self._inject_dependencies()

        # Khởi tạo
        for p in list(self._plugins):
            name = getattr(p, "name", "unknown")
            if p.failed:
                continue
            if not self._dependencies_ok(p):
                p.mark_failed()
                logger.error(f"Plugin {name} bị bỏ qua setup do dependency thất bại")
                continue
            try:
                await p.setup(ctx, cmd)
            except Exception as e:
                p.mark_failed()
                logger.error(f"Plugin {name} setup thất bại: {e}", exc_info=True)

    async def start_all(self) -> None:
        """Khởi chạy tất cả các plugin chưa thất bại."""
        for p in list(self._plugins):
            if p.failed:
                continue
            if not self._dependencies_ok(p):
                p.mark_failed()
                logger.error(
                    f"Plugin {getattr(p, 'name', 'unknown')} bị bỏ qua start do dependency thất bại"
                )
                continue
            try:
                await p.start()
            except Exception as e:
                p.mark_failed()
                logger.error(
                    f"Plugin {getattr(p, 'name', 'unknown')} start thất bại: {e}",
                    exc_info=True,
                )

    async def notify_protocol_connected(self, protocol: Any) -> None:
        """Thông báo giao thức đã kết nối."""
        for p in self._active_plugins():
            try:
                if p.on_protocol_connected:
                    await p.on_protocol_connected(protocol)
            except Exception as e:
                logger.error(
                    f"Plugin {getattr(p, 'name', 'unknown')} on_protocol_connected thất bại: {e}",
                    exc_info=True,
                )

    async def notify_incoming_json(self, message: Any) -> None:
        """Thông báo nhận được tin nhắn JSON."""
        for p in self._active_plugins():
            try:
                await p.on_incoming_json(message)
            except Exception as e:
                logger.error(
                    f"Plugin {getattr(p, 'name', 'unknown')} on_incoming_json thất bại: {e}",
                    exc_info=True,
                )

    async def notify_incoming_audio(self, data: bytes) -> None:
        """Thông báo nhận được dữ liệu âm thanh."""
        for p in self._active_plugins():
            try:
                await p.on_incoming_audio(data)
            except Exception as e:
                logger.error(
                    f"Plugin {getattr(p, 'name', 'unknown')} on_incoming_audio thất bại: {e}",
                    exc_info=True,
                )

    async def notify_device_state_changed(self, state: Any) -> None:
        """Thông báo thay đổi trạng thái thiết bị."""
        for p in self._active_plugins():
            try:
                await p.on_device_state_changed(state)
            except Exception as e:
                logger.error(
                    f"Plugin {getattr(p, 'name', 'unknown')} on_device_state_changed thất bại: {e}",
                    exc_info=True,
                )

    async def stop_all(self) -> None:
        """Dừng tất cả các plugin (theo thứ tự ngược lại; plugin thất bại vẫn thử stop để dọn dẹp tài nguyên)."""
        for p in reversed(self._plugins):
            try:
                await p.stop()
            except Exception as e:
                logger.error(
                    f"Plugin {getattr(p, 'name', 'unknown')} stop thất bại: {e}",
                    exc_info=True,
                )
