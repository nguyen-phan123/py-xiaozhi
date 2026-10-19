"""Module plugin phím tắt.

Cung cấp hỗ trợ phím tắt toàn cục đa nền tảng:
- macOS: Sử dụng Quartz Event Tap (PyObjC)
- Linux/Windows: Sử dụng pynput
"""

import asyncio
import sys
from typing import TYPE_CHECKING, Callable, Dict, Optional

from src.constants.constants import AbortReason
from src.logging import get_logger
from src.plugins.base import Plugin
from src.utils.config_manager import get_config

from .base import ShortcutBackend, ShortcutConfig

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext

logger = get_logger()

__all__ = ["ShortcutBackend", "ShortcutConfig", "ShortcutsPlugin", "create_backend"]


def create_backend(
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> Optional[ShortcutBackend]:
    """Tạo backend phím tắt phù hợp với nền tảng hiện tại.

    Args:
        loop: Event loop asyncio

    Returns:
        Instance backend phím tắt, trả về None nếu không thể tạo
    """
    if sys.platform == "darwin":
        # macOS: Ưu tiên sử dụng Quartz Event Tap
        try:
            from .macos_backend import MacOSShortcutBackend

            logger.info("Sử dụng backend macOS Quartz Event Tap")
            return MacOSShortcutBackend(loop)
        except ImportError as e:
            logger.warning(f"Không thể tải backend macOS: {e}", exc_info=True)
            logger.info("Fallback về backend pynput")
            # Fallback về pynput
            try:
                from .pynput_backend import PynputShortcutBackend

                return PynputShortcutBackend(loop)
            except ImportError as e2:
                logger.error(f"Không thể tải backend pynput: {e2}")
                return None
    else:
        # Linux/Windows: Sử dụng pynput
        try:
            from .pynput_backend import PynputShortcutBackend

            logger.info("Sử dụng backend pynput")
            return PynputShortcutBackend(loop)
        except ImportError as e:
            logger.error(f"Không thể tải backend pynput: {e}", exc_info=True)
            return None


class _CmdAdapter:
    """Adapter lệnh phím tắt."""

    def __init__(self, cmd: "PluginCommands", ctx: "PluginContext"):
        self._cmd = cmd
        self._ctx = ctx

    async def toggle_chat_state(self):
        try:
            await self._cmd.connect_protocol()
            from src.constants.constants import ListeningMode

            mode = (
                ListeningMode.REALTIME
                if self._ctx.get_config().get_config("AEC_OPTIONS.ENABLED", True)
                else ListeningMode.AUTO_STOP
            )
            await self._cmd.start_listening(mode)
        except Exception as e:
            logger.error(f"Chuyển đổi trạng thái đối thoại thất bại: {e}", exc_info=True)

    async def abort_speaking(self, reason):
        try:
            await self._cmd.abort_speaking(reason)
        except Exception as e:
            logger.error(f"Ngắt đối thoại thất bại: {e}", exc_info=True)


class ShortcutsPlugin(Plugin):
    """Plugin phím tắt."""

    name = "shortcuts"
    priority = 70  # Mức độ ưu tiên thấp nhất, phụ thuộc vào UIPlugin

    # Hằng số tên phím tắt
    MANUAL_PRESS = "MANUAL_PRESS"
    AUTO_TOGGLE = "AUTO_TOGGLE"
    ABORT = "ABORT"
    MODE_TOGGLE = "MODE_TOGGLE"
    WINDOW_TOGGLE = "WINDOW_TOGGLE"

    def __init__(self) -> None:
        super().__init__()
        self._backend: Optional[ShortcutBackend] = None
        self._adapter: Optional[_CmdAdapter] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._event_bus = None
        self._config = get_config()
        self._shortcuts_config: Dict = {}
        self._enabled = True

    async def setup(self, ctx: "PluginContext", cmd: "PluginCommands") -> None:
        await super().setup(ctx, cmd)
        self._adapter = _CmdAdapter(cmd, ctx)
        self._loop = asyncio.get_running_loop()
        self._event_bus = ctx.event_bus

        # Tải cấu hình
        self._load_config()

        # Tạo backend
        self._backend = create_backend(self._loop)
        if not self._backend:
            logger.warning("Không thể tạo backend phím tắt, tính năng phím tắt sẽ không khả dụng")

        # Đăng ký sự kiện thay đổi cấu hình
        from src.core.event_bus import Events

        ctx.event_bus.on(Events.CONFIG_CHANGED, self._on_config_changed)

    def _load_config(self) -> None:
        """Tải cấu hình phím tắt."""
        self._shortcuts_config = self._config.get_config("SHORTCUTS", {}) or {}
        self._enabled = bool(self._shortcuts_config.get("ENABLED", True))

    async def _on_config_changed(self, data=None) -> None:
        """Tải lại khi cấu hình thay đổi."""
        logger.info("ShortcutsPlugin: Nhận được sự kiện thay đổi cấu hình, đang tải lại cấu hình")
        self.reload_from_config()

    async def start(self) -> None:
        """Khởi chạy plugin."""
        if not self._enabled:
            logger.info("Tính năng phím tắt đã bị vô hiệu hóa")
            return

        if not self._backend:
            logger.warning("Backend phím tắt không khả dụng")
            return

        # Đăng ký phím tắt
        self._register_shortcuts()

        # Khởi động backend
        success = await self._backend.start()
        if success:
            logger.info("Plugin phím tắt đã khởi động")
        else:
            logger.error("Khởi động backend phím tắt thất bại")

    def _register_shortcuts(self) -> None:
        """Đăng ký tất cả phím tắt."""
        if not self._backend:
            return

        shortcut_handlers = {
            self.MANUAL_PRESS: self._handle_manual_press,
            self.AUTO_TOGGLE: self._handle_auto_toggle,
            self.ABORT: self._handle_abort,
            self.MODE_TOGGLE: self._handle_mode_toggle,
            self.WINDOW_TOGGLE: self._handle_window_toggle,
        }

        for name, handler in shortcut_handlers.items():
            cfg = self._shortcuts_config.get(name, {}) or {}
            modifier = str(cfg.get("modifier", "ctrl")).lower()
            key = str(cfg.get("key", "")).lower()

            if not key:
                continue

            config = ShortcutConfig(
                modifier=modifier,
                key=key,
                description=cfg.get("description", ""),
            )

            self._backend.register(name, config, handler)

    def _handle_manual_press(self) -> None:
        """Xử lý phím tắt nhấn thủ công - sử dụng sự kiện UI_MANUAL_TOGGLE."""
        if not self._event_bus or not self._loop:
            return

        from src.core.event_bus import Events

        asyncio.run_coroutine_threadsafe(
            self._event_bus.emit(Events.UI_MANUAL_TOGGLE), self._loop
        )

    def _handle_auto_toggle(self) -> None:
        """Xử lý phím tắt chuyển đổi đối thoại tự động."""
        if not self._adapter or not self._loop:
            return

        asyncio.run_coroutine_threadsafe(
            self._adapter.toggle_chat_state(), self._loop
        )

    def _handle_abort(self) -> None:
        """Xử lý phím tắt ngắt lời."""
        if not self._adapter or not self._loop:
            return

        asyncio.run_coroutine_threadsafe(
            self._adapter.abort_speaking(AbortReason.NONE), self._loop
        )

    def _handle_mode_toggle(self) -> None:
        """Xử lý phím tắt chuyển đổi chế độ."""
        if not self._event_bus or not self._loop:
            return

        from src.core.event_bus import Events

        asyncio.run_coroutine_threadsafe(
            self._event_bus.emit(Events.UI_AUTO_TOGGLE), self._loop
        )

    def _handle_window_toggle(self) -> None:
        """Xử lý phím tắt ẩn/hiện cửa sổ."""
        if not self._event_bus or not self._loop:
            return

        from src.core.event_bus import Events

        asyncio.run_coroutine_threadsafe(
            self._event_bus.emit(Events.UI_TOGGLE_WINDOW), self._loop
        )

    async def stop(self) -> None:
        """Dừng plugin."""
        if self._backend:
            await self._backend.stop()

    def register_resources(self, pool) -> None:
        backend = self._backend
        if backend:
            pool.register("shortcuts.backend", backend.stop)

    def reload_from_config(self) -> None:
        """Tải lại từ cấu hình."""
        self._load_config()

        if not self._backend:
            return

        # Hủy đăng ký tất cả phím tắt
        self._backend.unregister_all()

        if self._enabled:
            # Đăng ký lại
            self._register_shortcuts()
            logger.info("Cấu hình phím tắt đã được tải lại")
        else:
            logger.info("Tính năng phím tắt đã bị vô hiệu hóa")
