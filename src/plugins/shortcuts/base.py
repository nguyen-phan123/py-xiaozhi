"""Lớp cơ sở trừu tượng cho backend phím tắt."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from src.logging import get_logger

logger = get_logger()


@dataclass
class ShortcutConfig:
    """Cấu hình phím tắt."""

    modifier: str  # ctrl, alt, shift, cmd
    key: str  # Phím bấm
    description: str = ""


class ShortcutBackend(ABC):
    """Lớp cơ sở trừu tượng cho backend phím tắt.

    Định nghĩa các interface mà tất cả các backend phím tắt phải hiện thực.
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        self._loop = loop
        self._running = False
        self._shortcuts: Dict[str, ShortcutConfig] = {}
        self._callbacks: Dict[str, Callable] = {}

    @abstractmethod
    async def start(self) -> bool:
        """Bắt đầu lắng nghe phím tắt.

        Returns:
            Có khởi động thành công hay không
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Dừng lắng nghe phím tắt."""
        pass

    @abstractmethod
    def register(self, name: str, config: ShortcutConfig, callback: Callable) -> bool:
        """Đăng ký phím tắt.

        Args:
            name: Tên phím tắt
            config: Cấu hình phím tắt
            callback: Hàm callback (không có tham số)

        Returns:
            Có đăng ký thành công hay không
        """
        pass

    @abstractmethod
    def unregister(self, name: str) -> bool:
        """Hủy đăng ký phím tắt.

        Args:
            name: Tên phím tắt

        Returns:
            Có hủy đăng ký thành công hay không
        """
        pass

    def unregister_all(self) -> None:
        """Hủy đăng ký tất cả phím tắt."""
        for name in list(self._shortcuts.keys()):
            self.unregister(name)

    @property
    def is_running(self) -> bool:
        """Có đang chạy hay không."""
        return self._running

    def _run_callback(self, name: str) -> None:
        """Thực thi hàm callback (thread-safe).

        Args:
            name: Tên phím tắt
        """
        if name not in self._callbacks:
            return

        callback = self._callbacks[name]
        if self._loop and self._loop.is_running():
            if asyncio.iscoroutinefunction(callback):
                asyncio.run_coroutine_threadsafe(callback(), self._loop)
            else:
                self._loop.call_soon_threadsafe(callback)
        else:
            # Không có event loop, gọi trực tiếp
            if asyncio.iscoroutinefunction(callback):
                logger.warning(f"Không thể gọi callback bất đồng bộ {name}, không có event loop")
            else:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Callback phím tắt {name} thực thi thất bại: {e}", exc_info=True)
