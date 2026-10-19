"""Chuyển đổi thao tác phím, gửi văn bản, chuyển chế độ trên giao diện thành lệnh giao thức."""

from typing import TYPE_CHECKING

from src.constants.constants import AbortReason, DeviceState, ListeningMode
from src.core.event_bus import Events
from src.logging import get_logger

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext
    from src.plugins.ui_presenter import UiPresenter

logger = get_logger()


class SessionActions:
    """Các thao tác liên quan đến hội thoại."""

    def __init__(
        self,
        ctx: "PluginContext",
        cmd: "PluginCommands",
        presenter: "UiPresenter",
    ) -> None:
        self._ctx = ctx
        self._cmd = cmd
        self._ui = presenter
        self._manual_recording = False
        self._auto_mode = False
        # Ở chế độ tự động, kiểm tra xem đã bắt đầu cuộc hội thoại chưa (nút hiển thị "Dừng hội thoại")
        self._auto_session_active = False

    @property
    def auto_mode(self) -> bool:
        return self._auto_mode

    @property
    def auto_session_active(self) -> bool:
        return self._auto_session_active

    @property
    def manual_recording(self) -> bool:
        return self._manual_recording

    def subscribe(self, bus) -> None:
        bus.on(Events.UI_BUTTON_PRESS, self.press)
        bus.on(Events.UI_BUTTON_RELEASE, self.release)
        bus.on(Events.UI_MANUAL_TOGGLE, self.manual_toggle)
        bus.on(Events.UI_AUTO_TOGGLE, self.auto_toggle)
        bus.on(Events.UI_AUTO_START, self.auto_session_toggle)
        bus.on(Events.UI_ABORT_REQUEST, self.abort)
        bus.on(Events.UI_SEND_TEXT, self.send_text_from_event)
        bus.on(Events.UI_QUIT_REQUEST, self.request_shutdown)
        logger.info("SessionActions đã đăng ký các sự kiện thao tác người dùng trên UI")

    def on_device_state_changed(self, state) -> None:
        # Đặt lại nút nếu quá trình ghi âm thủ công bị thoát khỏi trạng thái listening
        if state != DeviceState.LISTENING and self._manual_recording:
            self._manual_recording = False
            if not self._auto_mode:
                self._ui.set_button_text("Nhấn giữ để nói")

        if self._auto_mode and state == DeviceState.IDLE and self._auto_session_active:
            self._auto_session_active = False
            self._ui.set_button_text("Bắt đầu hội thoại")
        elif self._auto_mode and state in (DeviceState.LISTENING, DeviceState.SPEAKING):
            if not self._auto_session_active:
                self._auto_session_active = True
            self._ui.set_button_text("Dừng hội thoại")

    async def request_shutdown(self, _data=None) -> None:
        self._cmd.request_shutdown()

    def _listen_mode(self) -> ListeningMode:
        if not self._auto_mode:
            return ListeningMode.MANUAL
        aec = self._ctx.get_config().get_config("AEC_OPTIONS.ENABLED", True)
        return ListeningMode.REALTIME if aec else ListeningMode.AUTO_STOP

    async def _ensure_listen_session(self) -> bool:
        # Nếu rảnh rỗi mà gọi detect ngay, server thường bị mất gói; cần chuyển sang nghe trước rồi gửi
        if self._ctx.is_listening() or self._ctx.is_speaking():
            return True
        if not await self._cmd.connect_protocol():
            logger.warning("Không thể thiết lập kết nối giao thức, hủy thao tác phiên")
            return False
        mode = self._listen_mode()
        await self._cmd.start_listening(mode)
        if self._auto_mode:
            self._auto_session_active = True
            self._ui.set_button_text("Dừng hội thoại")
        logger.debug(f"Đã mở phiên listen: mode={mode}")
        return True

    async def send_text_from_event(self, data) -> None:
        if hasattr(data, "text"):
            text = data.text
        elif isinstance(data, dict):
            text = data.get("text", "")
        elif isinstance(data, str):
            text = data
        else:
            logger.warning(f"Dữ liệu văn bản gửi không hợp lệ: {type(data)}")
            return
        await self.send_text(text)

    async def send_text(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return

        logger.info(f"Gửi văn bản: {text[:40]}{'...' if len(text) > 40 else ''}")

        if self._ctx.is_speaking():
            await self._cmd.abort_speaking(AbortReason.USER_INTERRUPTION)

        if not await self._ensure_listen_session():
            return

        await self._cmd.send_wake_word_detected(text)

    async def press(self, _data=None) -> None:
        await self._cmd.connect_protocol()
        await self._cmd.start_listening(ListeningMode.MANUAL)

    async def release(self, _data=None) -> None:
        await self._cmd.stop_listening()

    async def manual_toggle(self, _data=None) -> None:
        if not self._manual_recording:
            self._manual_recording = True
            logger.debug("Chế độ thủ công: Bắt đầu ghi âm")
            self._ui.set_button_text("Gửi")
            await self._cmd.connect_protocol()
            await self._cmd.start_listening(ListeningMode.MANUAL)
        else:
            self._manual_recording = False
            logger.debug("Chế độ thủ công: Dừng ghi âm và gửi")
            self._ui.set_button_text("Nhấn giữ để nói")
            await self._cmd.stop_listening()

    async def auto_toggle(self, _data=None) -> None:
        # Chỉ chuyển đổi giữa tự động/thủ công, không tự động bắt đầu nghe
        self._auto_mode = not self._auto_mode
        if not self._auto_mode:
            self._auto_session_active = False
        if self._auto_mode and self._manual_recording:
            self._manual_recording = False
        self._ui.set_auto_mode(self._auto_mode)
        logger.debug(f"Chuyển đổi chế độ: {'Tự động' if self._auto_mode else 'Thủ công'}")

    async def auto_session_toggle(self, _data=None) -> None:
        # Nút chính: Bắt đầu hội thoại / Dừng hội thoại
        if self._auto_session_active or self._ctx.is_listening() or self._ctx.is_speaking():
            await self._stop_auto_session()
            return

        if not await self._ensure_listen_session():
            return
        logger.debug("Chế độ tự động: Bắt đầu đối thoại")

    async def _stop_auto_session(self) -> None:
        # Trước tiên gọi stop để xóa keep_listening, sau đó gọi abort để tránh việc bị kéo lại vào nghe tiếp sau khi ngắt
        try:
            if self._ctx.is_speaking():
                await self._cmd.stop_listening()
                await self._cmd.abort_speaking(AbortReason.USER_INTERRUPTION)
            else:
                await self._cmd.stop_listening()
        finally:
            self._auto_session_active = False
            self._ui.set_button_text("Bắt đầu hội thoại")
            logger.debug("Chế độ tự động: Dừng đối thoại")

    async def abort(self, _data=None) -> None:
        await self._cmd.abort_speaking(AbortReason.USER_INTERRUPTION)
