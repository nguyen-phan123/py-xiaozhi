"""Backend phím tắt pynput.

Dùng cho các hệ thống Linux và Windows.
"""

import asyncio
import time
from typing import Callable, Optional, Set

from src.logging import get_logger

from .base import ShortcutBackend, ShortcutConfig

logger = get_logger()

try:
    from pynput import keyboard
except ImportError as e:
    raise ImportError(
        "pynput is required for keyboard shortcut support. "
        "Install with: pip install pynput"
    ) from e


class PynputShortcutBackend(ShortcutBackend):
    """Backend phím tắt pynput.

    Thích hợp cho các hệ thống Linux và Windows.
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        super().__init__(loop)
        self._listener = None
        self._pressed_keys: Set[str] = set()
        self._last_activity_time = 0.0
        self._health_check_task = None
        self._check_interval = 10.0  # Khoảng thời gian kiểm tra sức khỏe (giây)

        # Bảng ánh xạ ký tự điều khiển
        self._key_mapping = {
            "\x17": "w", "\x01": "a", "\x13": "s", "\x04": "d",
            "\x05": "e", "\x12": "r", "\x14": "t", "\x06": "f",
            "\x07": "g", "\x08": "h", "\x0a": "j", "\x0b": "k",
            "\x0c": "l", "\x1a": "z", "\x18": "x", "\x03": "c",
            "\x16": "v", "\x02": "b", "\x0e": "n", "\x0d": "m",
            "\x11": "q",
        }

    async def start(self) -> bool:
        """Bắt đầu lắng nghe phím tắt."""
        if self._running:
            return True

        try:
            self._listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._listener.start()
            self._running = True
            self._last_activity_time = time.time()

            # Khởi động kiểm tra sức khỏe
            self._start_health_check()

            logger.info("Đã khởi động lắng nghe phím tắt toàn cục pynput")
            return True
        except Exception as e:
            logger.error(f"Khởi động lắng nghe phím tắt pynput thất bại: {e}", exc_info=True)
            return False

    async def stop(self) -> None:
        """Dừng lắng nghe phím tắt."""
        self._running = False

        # Dừng kiểm tra sức khỏe
        if self._health_check_task:
            self._health_check_task.cancel()
            # concurrent.futures.Future không thể await trực tiếp, cần xử lý đặc biệt
            try:
                # Chờ Future hoàn thành (bỏ qua ngoại lệ hủy)
                self._health_check_task.result(timeout=1.0)
            except Exception as e:
                logger.debug(f"Health check Pynput timeout: {e}")
            self._health_check_task = None

        # Dừng listener
        if self._listener:
            try:
                self._listener.stop()
            except Exception as e:
                logger.warning(f"Lỗi khi dừng listener: {e}", exc_info=True)
            self._listener = None

        self._pressed_keys.clear()
        logger.info("Đã dừng lắng nghe phím tắt toàn cục pynput")

    def register(self, name: str, config: ShortcutConfig, callback: Callable) -> bool:
        """Đăng ký phím tắt."""
        self._shortcuts[name] = config
        self._callbacks[name] = callback
        logger.info(f"Đã đăng ký phím tắt: {name} -> {config.modifier}+{config.key}")
        return True

    def unregister(self, name: str) -> bool:
        """Hủy đăng ký phím tắt."""
        if name not in self._shortcuts:
            return False

        del self._shortcuts[name]
        if name in self._callbacks:
            del self._callbacks[name]

        logger.info(f"Đã hủy đăng ký phím tắt: {name}")
        return True

    def _on_key_press(self, key) -> None:
        """Callback khi nhấn phím."""
        if not self._running:
            return

        self._last_activity_time = time.time()
        key_name = self._get_key_name(key)
        if not key_name:
            return

        self._pressed_keys.add(key_name)
        self._check_shortcuts()

    def _on_key_release(self, key) -> None:
        """Callback khi nhả phím."""
        if not self._running:
            return

        self._last_activity_time = time.time()
        key_name = self._get_key_name(key)
        if not key_name:
            return

        self._pressed_keys.discard(key_name)

    def _get_key_name(self, key) -> Optional[str]:
        """Lấy tên phím bấm."""
        try:
            if hasattr(key, "name"):
                name = key.name
                # Chuẩn hóa tên phím bổ trợ (modifier)
                if name in ("ctrl_l", "ctrl_r"):
                    return "ctrl"
                if name in ("alt_l", "alt_r"):
                    return "alt"
                if name in ("shift_l", "shift_r"):
                    return "shift"
                if name == "cmd":
                    return "cmd"
                if name == "esc":
                    return "escape"
                if name == "enter":
                    return "return"
                return name.lower()
            elif hasattr(key, "char") and key.char:
                char = key.char
                if char == "\n":
                    return "return"
                if char in self._key_mapping:
                    return self._key_mapping[char]
                return char.lower()
        except Exception as e:
            logger.debug(f"Ánh xạ phím thất bại: {e}")
        return None

    def _check_shortcuts(self) -> None:
        """Kiểm tra xem có kích hoạt phím tắt không."""
        if not self._shortcuts:
            return

        # Kiểm tra trạng thái phím bổ trợ
        ctrl = any(k in self._pressed_keys for k in ("ctrl", "control"))
        alt = any(k in self._pressed_keys for k in ("alt", "option"))
        shift = "shift" in self._pressed_keys
        cmd = "cmd" in self._pressed_keys

        for name, config in self._shortcuts.items():
            if self._match_shortcut(config, ctrl, alt, shift, cmd):
                logger.debug(f"Kích hoạt phím tắt: {name}")
                self._run_callback(name)

    def _match_shortcut(
        self, config: ShortcutConfig, ctrl: bool, alt: bool, shift: bool, cmd: bool
    ) -> bool:
        """Kiểm tra xem có khớp với cấu hình phím tắt không."""
        modifier = config.modifier.lower()

        # Kiểm tra phím bổ trợ
        if modifier == "ctrl" and not ctrl:
            return False
        if modifier == "alt" and not alt:
            return False
        if modifier == "shift" and not shift:
            return False
        if modifier == "cmd" and not cmd:
            return False

        # Kiểm tra phím chính
        return config.key.lower() in {k.lower() for k in self._pressed_keys}

    def _start_health_check(self) -> None:
        """Khởi động task kiểm tra sức khỏe."""
        if self._loop:
            self._health_check_task = asyncio.run_coroutine_threadsafe(
                self._health_check_loop(), self._loop
            )

    async def _health_check_loop(self) -> None:
        """Vòng lặp kiểm tra sức khỏe."""
        while self._running:
            await asyncio.sleep(self._check_interval)

            if not self._running:
                break

            # Kiểm tra xem listener có còn đang chạy không
            if self._listener and not self._listener.is_alive():
                logger.warning("Listener pynput đã dừng, đang thử khởi động lại...")
                await self._restart_listener()

    async def _restart_listener(self) -> None:
        """Khởi động lại listener."""
        try:
            # Dừng listener cũ
            if self._listener:
                try:
                    self._listener.stop()
                except Exception as e:
                    logger.debug(f"Dừng listener Pynput thất bại: {e}")
                self._listener = None

            # Chờ một khoảng ngắn
            await asyncio.sleep(0.5)

            # Tạo listener mới
            self._listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._listener.start()
            self._pressed_keys.clear()
            logger.info("Khởi động lại listener pynput thành công")
        except Exception as e:
            logger.error(f"Khởi động lại listener pynput thất bại: {e}", exc_info=True)
