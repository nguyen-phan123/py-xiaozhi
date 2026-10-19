"""Backend phím tắt macOS.

Sử dụng RegisterEventHotKey của Carbon API để đăng ký hotkey toàn cục.
Cơ chế này sử dụng cùng API tầng dưới như globalShortcut của Electron.
"""

import asyncio
import sys
from typing import Callable, Dict, Optional

from src.logging import get_logger

from .base import ShortcutBackend, ShortcutConfig

logger = get_logger()

# Kiểm tra xem có đang chạy trên macOS không
if sys.platform != "darwin":
    raise ImportError("macOS backend only works on macOS")

try:
    import Quartz
except ImportError as e:
    raise ImportError(
        "PyObjC is required for macOS hotkey support. "
        "Install with: pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa"
    ) from e


# Bảng ánh xạ mã phím ảo của Carbon
# https://developer.apple.com/library/archive/technotes/tn2450/_index.html
KEYCODE_MAP = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04,
    "g": 0x05, "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09,
    "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E, "r": 0x0F,
    "y": 0x10, "t": 0x11, "1": 0x12, "2": 0x13, "3": 0x14,
    "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18, "9": 0x19,
    "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E,
    "o": 0x1F, "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23,
    "l": 0x25, "j": 0x26, "'": 0x27, "k": 0x28, ";": 0x29,
    "\\": 0x2A, ",": 0x2B, "/": 0x2C, "n": 0x2D, "m": 0x2E,
    ".": 0x2F, "`": 0x32, " ": 0x31, "space": 0x31,
    "return": 0x24, "enter": 0x24, "tab": 0x30, "escape": 0x35, "esc": 0x35,
    "delete": 0x33, "backspace": 0x33,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76,
    "f5": 0x60, "f6": 0x61, "f7": 0x62, "f8": 0x64,
    "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
    "up": 0x7E, "down": 0x7D, "left": 0x7B, "right": 0x7C,
    "home": 0x73, "end": 0x77, "pageup": 0x74, "pagedown": 0x79,
}

# Mặt nạ phím bổ trợ (modifier)
MODIFIER_MAP = {
    "cmd": Quartz.kCGEventFlagMaskCommand,
    "command": Quartz.kCGEventFlagMaskCommand,
    "ctrl": Quartz.kCGEventFlagMaskControl,
    "control": Quartz.kCGEventFlagMaskControl,
    "alt": Quartz.kCGEventFlagMaskAlternate,
    "option": Quartz.kCGEventFlagMaskAlternate,
    "shift": Quartz.kCGEventFlagMaskShift,
}


class MacOSShortcutBackend(ShortcutBackend):
    """Backend phím tắt macOS.

    Sử dụng Quartz Event Tap để lắng nghe sự kiện hotkey toàn cục.
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        super().__init__(loop)
        self._tap = None
        self._run_loop_source = None
        self._hotkey_ids: Dict[str, int] = {}  # name -> hotkey_id
        self._registered_hotkeys: Dict[int, str] = {}  # hotkey_id -> name
        self._next_hotkey_id = 1
        self._monitor_thread = None
        self._pressed_modifiers = 0
        self._check_interval = 5.0  # Khoảng thời gian kiểm tra sức khỏe (giây)
        self._health_check_task = None

    async def start(self) -> bool:
        """Bắt đầu lắng nghe phím tắt."""
        if self._running:
            return True

        try:
            # Tạo bộ lắng nghe sự kiện
            self._create_event_tap()
            self._running = True

            # Bắt đầu kiểm tra sức khỏe
            self._start_health_check()

            logger.info("Đã khởi động lắng nghe phím tắt toàn cục macOS (Quartz Event Tap)")
            return True
        except Exception as e:
            logger.error(f"Khởi động lắng nghe phím tắt macOS thất bại: {e}", exc_info=True)
            return False

    def _create_event_tap(self):
        """Tạo Quartz Event Tap."""
        # Lắng nghe sự kiện nhấn phím
        event_mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) |
            Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
        )

        # ListenOnly: Không chặn luồng sự kiện, Ctrl+C / phím tắt hệ thống vẫn truyền bình thường đến terminal
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            event_mask,
            self._event_callback,
            None,
        )

        if self._tap is None:
            raise RuntimeError(
                "Không thể tạo Event Tap. Vui lòng đảm bảo đã cấp quyền Trợ năng (Accessibility):\n"
                "Cài đặt hệ thống → Quyền riêng tư & Bảo mật → Trợ năng"
            )

        # Thêm tap vào run loop hiện tại
        self._run_loop_source = Quartz.CFMachPortCreateRunLoopSource(
            None, self._tap, 0
        )
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(),
            self._run_loop_source,
            Quartz.kCFRunLoopCommonModes,
        )
        Quartz.CGEventTapEnable(self._tap, True)

    def _event_callback(self, proxy, event_type, event, refcon):
        """Hàm callback sự kiện."""
        try:
            if event_type == Quartz.kCGEventKeyDown:
                # Lấy keycode và modifier
                keycode = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventKeycode
                )
                flags = Quartz.CGEventGetFlags(event)

                # Kiểm tra xem có khớp với hotkey đã đăng ký không
                self._check_hotkey(keycode, flags)

            elif event_type == Quartz.kCGEventFlagsChanged:
                # Cập nhật trạng thái phím bổ trợ
                self._pressed_modifiers = Quartz.CGEventGetFlags(event)

        except Exception as e:
            logger.error(f"Lỗi callback sự kiện: {e}", exc_info=True)

        return event

    def _check_hotkey(self, keycode: int, flags: int) -> None:
        """Kiểm tra xem có khớp với hotkey đã đăng ký không."""
        for name, config in self._shortcuts.items():
            # Lấy keycode mong đợi
            expected_keycode = KEYCODE_MAP.get(config.key.lower())
            if expected_keycode is None:
                continue

            if keycode != expected_keycode:
                continue

            # Kiểm tra phím bổ trợ
            expected_modifier = MODIFIER_MAP.get(config.modifier.lower(), 0)
            if expected_modifier == 0:
                continue

            # Kiểm tra xem modifier có khớp không (chỉ kiểm tra modifier mong đợi có được nhấn)
            if flags & expected_modifier:
                logger.debug(f"Kích hoạt phím tắt: {name}")
                self._run_callback(name)

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
                logger.debug(f"Health check macOS timeout: {e}")
            self._health_check_task = None

        # Gỡ bỏ event tap
        if self._tap:
            Quartz.CGEventTapEnable(self._tap, False)
            if self._run_loop_source:
                Quartz.CFRunLoopRemoveSource(
                    Quartz.CFRunLoopGetCurrent(),
                    self._run_loop_source,
                    Quartz.kCFRunLoopCommonModes,
                )
            self._tap = None
            self._run_loop_source = None

        logger.info("Đã dừng lắng nghe phím tắt toàn cục macOS")

    def register(self, name: str, config: ShortcutConfig, callback: Callable) -> bool:
        """Đăng ký phím tắt."""
        # Xác thực keycode
        if config.key.lower() not in KEYCODE_MAP:
            logger.warning(f"Phím không được hỗ trợ: {config.key}")
            return False

        # Xác thực modifier
        if config.modifier.lower() not in MODIFIER_MAP:
            logger.warning(f"Phím bổ trợ (modifier) không được hỗ trợ: {config.modifier}")
            return False

        self._shortcuts[name] = config
        self._callbacks[name] = callback

        hotkey_id = self._next_hotkey_id
        self._next_hotkey_id += 1
        self._hotkey_ids[name] = hotkey_id
        self._registered_hotkeys[hotkey_id] = name

        logger.info(f"Đã đăng ký phím tắt: {name} -> {config.modifier}+{config.key}")
        return True

    def unregister(self, name: str) -> bool:
        """Hủy đăng ký phím tắt."""
        if name not in self._shortcuts:
            return False

        del self._shortcuts[name]
        del self._callbacks[name]

        if name in self._hotkey_ids:
            hotkey_id = self._hotkey_ids[name]
            del self._hotkey_ids[name]
            if hotkey_id in self._registered_hotkeys:
                del self._registered_hotkeys[hotkey_id]

        logger.info(f"Đã hủy đăng ký phím tắt: {name}")
        return True

    def _start_health_check(self):
        """Khởi động task kiểm tra sức khỏe."""
        if self._loop:
            self._health_check_task = asyncio.run_coroutine_threadsafe(
                self._health_check_loop(), self._loop
            )

    async def _health_check_loop(self):
        """Kiểm tra sức khỏe: Nếu bị tắt thì thử re-enable; thất bại chỉ ghi warning, tránh tạo lại dồn dập cản trở thoát ứng dụng."""
        consecutive_fail = 0
        max_warn_streak = 3  # Số lần thất bại liên tiếp vượt quá mức này sẽ giảm tần suất log

        while self._running:
            try:
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break

            if not self._running:
                break

            if not self._tap:
                continue

            try:
                if Quartz.CGEventTapIsEnabled(self._tap):
                    consecutive_fail = 0
                    continue
            except Exception:
                # tap đã mất hiệu lực
                consecutive_fail += 1
            else:
                # Chỉ re-enable, không stop/start toàn bộ tree (tạo lại sẽ xung đột với CFRunLoop/tín hiệu)
                try:
                    Quartz.CGEventTapEnable(self._tap, True)
                    if Quartz.CGEventTapIsEnabled(self._tap):
                        if consecutive_fail > 0:
                            logger.info("Kích hoạt lại Event Tap thành công")
                        consecutive_fail = 0
                        continue
                except Exception as e:
                    logger.debug(f"Ngoại lệ CGEventTapEnable: {e}")

                consecutive_fail += 1

            if consecutive_fail <= max_warn_streak:
                logger.warning(
                    "Event Tap vẫn không khả dụng (%s lần). "
                    "Vui lòng kiểm tra: Cài đặt hệ thống → Quyền riêng tư & Bảo mật → Trợ năng. "
                    "Phím tắt có thể tạm thời mất tác dụng; Ctrl+C vẫn có thể thoát.",
                    consecutive_fail,
                )
            elif consecutive_fail % 12 == 0:
                # Khoảng mỗi phút một lần, tránh làm tràn log
                logger.warning(
                    "Event Tap tiếp tục không khả dụng (đã kiểm tra %s lần), bỏ qua việc buộc tạo lại",
                    consecutive_fail,
                )
