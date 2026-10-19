"""EventBus 桥接器 - Python 信号与 QML 信号双向转换."""

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from src.core.event_bus import EventBus, Events
from src.logging import get_logger

logger = get_logger()


class EventBridge(QObject):
    """EventBus 与 QML 的双向桥接.

    QML → Python: QML 调用 slot，slot 内部 emit EventBus 事件
    Python → QML: EventBus 事件触发 Python Signal，QML 连接该 Signal

    设备激活由独立 GuiActivation 窗口处理，主界面桥接不再承载激活信号。
    """

    # ========== Python → QML 信号 ==========

    # 窗口控制
    showWindow = Signal()
    hideWindow = Signal()
    showSettingsWindow = Signal()  # 显示设置窗口

    # ========== 构造 ==========

    def __init__(self, event_bus: EventBus, task_manager=None, parent: QObject | None = None):
        super().__init__(parent)
        self._event_bus = event_bus
        self._task_manager = task_manager

    def _emit_event(self, event: str, data=None):
        """安全地发射 EventBus 事件，在 Qt 主线程中调度到 asyncio loop."""
        if self._task_manager is None:
            logger.error("EventBridge: TaskManager chưa được inject, không thể phát sự kiện")
            return

        def do_emit():
            try:
                task_name = f"bridge:{event.split('.')[-1]}" if '.' in event else f"bridge:{event}"
                self._task_manager.spawn(self._event_bus.emit(event, data), name=task_name)
            except Exception as e:
                logger.warning(
                    f"EventBridge: Phát sự kiện {event} thất bại: {e}",
                    exc_info=True,
                )

        # 使用 QTimer.singleShot 确保在 Qt 事件循环中执行
        QTimer.singleShot(0, do_emit)

    # ========== QML → Python (Slots) ==========

    @Slot()
    def onButtonPress(self):
        """手动模式按钮按下."""
        logger.debug("EventBridge: Nút được nhấn")
        self._emit_event(Events.UI_BUTTON_PRESS)

    @Slot()
    def onButtonRelease(self):
        """手动模式按钮释放."""
        logger.debug("EventBridge: Nút được nhả")
        self._emit_event(Events.UI_BUTTON_RELEASE)

    @Slot()
    def onManualToggle(self):
        """手动模式录音切换（点击开始/停止）."""
        logger.debug("EventBridge: Chuyển đổi ghi âm thủ công")
        self._emit_event(Events.UI_MANUAL_TOGGLE)

    @Slot()
    def onAutoToggle(self):
        """自动模式切换."""
        logger.debug("EventBridge: Chuyển đổi chế độ tự động")
        self._emit_event(Events.UI_AUTO_TOGGLE)

    @Slot()
    def onAutoStart(self):
        """自动模式：开始或停止对话."""
        logger.debug("EventBridge: Bắt đầu/dừng đối thoại chế độ tự động")
        self._emit_event(Events.UI_AUTO_START)

    @Slot()
    def onAbort(self):
        """中断请求."""
        logger.debug("EventBridge: Yêu cầu ngắt")
        self._emit_event(Events.UI_ABORT_REQUEST)

    @Slot(str)
    def onSendText(self, text: str):
        """发送文本."""
        if text.strip():
            logger.debug(f"EventBridge: Gửi văn bản: {text[:20]}...")
            from src.ui.shared.events import UISendTextRequest
            self._emit_event(Events.UI_SEND_TEXT, UISendTextRequest(text=text))

    @Slot()
    def onQuitRequest(self):
        """退出请求."""
        logger.info("EventBridge: Yêu cầu thoát")
        self._emit_event(Events.UI_QUIT_REQUEST)

    @Slot()
    def onOpenSettings(self):
        """打开设置窗口 - 直接发射信号到 QML."""
        logger.debug("EventBridge: Mở cửa sổ cài đặt")
        self.showSettingsWindow.emit()
