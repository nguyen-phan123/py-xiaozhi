"""Bộ quản lý trạng thái (StateManager).

Quản lý tập trung trạng thái thiết bị, phát thông báo thay đổi trạng thái qua EventBus.
"""

import asyncio
from typing import TYPE_CHECKING

from src.constants.constants import DeviceState, ListeningMode
from src.core.event_bus import EventBus, Events
from src.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger()


class StateManager:
    """Bộ quản lý trạng thái thiết bị.

    Trách nhiệm:
    - Quản lý trạng thái thiết bị (IDLE, LISTENING, SPEAKING)
    - Quản lý chế độ lắng nghe (REALTIME, AUTO_STOP, MANUAL)
    - Quản lý trạng thái phiên (keep_listening, aec_enabled)
    - Phát thông báo thay đổi trạng thái qua EventBus

    Cách dùng:
        state = StateManager(event_bus)

        # Thiết lập trạng thái (sẽ tự động broadcast)
        await state.set_device_state(DeviceState.LISTENING)

        # Đọc trạng thái
        if state.is_listening():
            ...
    """

    def __init__(self, event_bus: EventBus, aec_enabled: bool = True):
        self._event_bus = event_bus
        self._lock = asyncio.Lock()

        # Trạng thái thiết bị
        self._device_state: DeviceState = DeviceState.IDLE

        # Cấu hình AEC
        self._aec_enabled: bool = aec_enabled

        # Chế độ lắng nghe: quyết định chế độ mặc định dựa trên cấu hình AEC
        self._listening_mode: ListeningMode = (
            ListeningMode.REALTIME if aec_enabled else ListeningMode.AUTO_STOP
        )

        # Trạng thái phiên làm việc
        self._keep_listening: bool = False

        # Cờ hủy bỏ (aborted)
        self._aborted: bool = False

    # -------------------------
    # Trạng thái thiết bị
    # -------------------------
    @property
    def device_state(self) -> DeviceState:
        """
        Lấy trạng thái thiết bị hiện tại.
        """
        return self._device_state

    async def set_device_state(self, state: DeviceState) -> None:
        """Thiết lập trạng thái thiết bị.

        Args:
            state: Trạng thái thiết bị mới

        Nếu trạng thái thay đổi, sẽ phát thông báo qua EventBus.
        """
        async with self._lock:
            if self._device_state == state:
                return

            old_state = self._device_state
            self._device_state = state
            logger.info(f"Thay đổi trạng thái thiết bị: {old_state} -> {state}")

            # Đặt lại cờ hủy bỏ
            if state == DeviceState.LISTENING:
                self._aborted = False

        # Broadcast ngoài lock để tránh deadlock
        await self._event_bus.emit(
            Events.DEVICE_STATE_CHANGED,
            {"old_state": old_state, "new_state": state},
        )

    def is_idle(self) -> bool:
        """
        Kiểm tra xem có đang ở trạng thái rảnh (IDLE) hay không.
        """
        return self._device_state == DeviceState.IDLE

    def is_listening(self) -> bool:
        """
        Kiểm tra xem có đang lắng nghe hay không.
        """
        return self._device_state == DeviceState.LISTENING

    def is_speaking(self) -> bool:
        """
        Kiểm tra xem có đang nói hay không.
        """
        return self._device_state == DeviceState.SPEAKING

    # -------------------------
    # Chế độ lắng nghe
    # -------------------------
    @property
    def listening_mode(self) -> ListeningMode:
        """
        Lấy chế độ lắng nghe hiện tại.
        """
        return self._listening_mode

    def set_listening_mode(self, mode: ListeningMode) -> None:
        """
        Thiết lập chế độ lắng nghe.
        """
        self._listening_mode = mode
        logger.debug(f"Chế độ lắng nghe được đặt thành: {mode}")

    # -------------------------
    # Trạng thái phiên làm việc
    # -------------------------
    @property
    def keep_listening(self) -> bool:
        """
        Kiểm tra xem có giữ trạng thái lắng nghe liên tục không.
        """
        return self._keep_listening

    def set_keep_listening(self, value: bool) -> None:
        """
        Thiết lập trạng thái lắng nghe liên tục.
        """
        self._keep_listening = value
        logger.debug(f"Lắng nghe liên tục: {value}")

    @property
    def aec_enabled(self) -> bool:
        """
        Kiểm tra AEC có đang bật không.
        """
        return self._aec_enabled

    # -------------------------
    # Trạng thái hủy bỏ
    # -------------------------
    @property
    def aborted(self) -> bool:
        """
        Kiểm tra xem đã bị hủy bỏ hay chưa.
        """
        return self._aborted

    def set_aborted(self, value: bool) -> None:
        """
        Thiết lập trạng thái hủy bỏ.
        """
        self._aborted = value

    # -------------------------
    # Truy vấn trạng thái kết hợp
    # -------------------------
    def should_capture_audio(self) -> bool:
        """Kiểm tra có nên thu âm thanh hay không.

        Cần thu âm trong các trường hợp sau:
        1. Đang lắng nghe và chưa bị hủy bỏ
        2. Đang nói, nhưng bật AEC và giữ lắng nghe liên tục ở chế độ real-time
        """
        if self._device_state == DeviceState.LISTENING and not self._aborted:
            return True

        return (
            self._device_state == DeviceState.SPEAKING
            and self._aec_enabled
            and self._keep_listening
            and self._listening_mode == ListeningMode.REALTIME
        )

    def get_snapshot(self) -> dict:
        """Lấy snapshot trạng thái.

        Trả về dictionary chứa tất cả trạng thái hiện tại, dùng cho debug và logging.
        """
        return {
            "device_state": self._device_state,
            "listening_mode": self._listening_mode,
            "keep_listening": self._keep_listening,
            "aec_enabled": self._aec_enabled,
            "aborted": self._aborted,
        }
