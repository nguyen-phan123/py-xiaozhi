"""Textual App：仪表盘 + 设置屏."""

from __future__ import annotations

from collections.abc import Callable

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from src.constants.system import SystemConstants
from src.logging import get_logger
from src.ui.tui.settings_data import (
    SETTING_SECTIONS,
    load_setting_values,
    save_settings,
)

logger = get_logger()


class SettingsScreen(ModalScreen[bool]):
    """配置编辑弹层；返回 True 表示已保存."""

    BINDINGS = [
        Binding("escape", "cancel", "Hủy", show=True),
    ]

    CSS = """
    SettingsScreen {
        align: center middle;
    }
    #settings-dialog {
        width: 90%;
        max-width: 100;
        height: 85%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #settings-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #settings-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    .field-row {
        height: auto;
        margin-bottom: 1;
    }
    .field-label {
        width: 20;
        color: $text-muted;
        padding-top: 1;
    }
    .field-input {
        width: 1fr;
    }
    #settings-actions {
        height: 3;
        align: right middle;
        margin-top: 1;
    }
    #settings-status {
        color: $accent;
        height: 1;
        margin-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._values = load_setting_values()

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("Cài đặt", id="settings-title")
            yield Static(
                "Chỉnh sửa rồi nhấn「Lưu」để ghi đĩa và áp dụng | Esc Hủy | "
                "Trường choice vui lòng điền giá trị hợp lệ (xem gợi ý)",
                id="settings-hint",
            )
            with TabbedContent():
                for section_name, fields in SETTING_SECTIONS:
                    with TabPane(section_name):
                        with VerticalScroll():
                            for f in fields:
                                with Horizontal(classes="field-row"):
                                    yield Label(f.label, classes="field-label")
                                    current = self._values.get(f.path, "")
                                    placeholder = f.help or f.path
                                    if f.kind == "choice" and f.choices:
                                        placeholder = f"Tùy chọn: {', '.join(f.choices)}"
                                    elif f.kind == "bool":
                                        placeholder = "true / false"
                                    yield Input(
                                        value=current,
                                        placeholder=placeholder,
                                        id=f"fld-{f.path.replace('.', '-')}",
                                        classes="field-input",
                                    )
            yield Static("", id="settings-status")
            with Horizontal(id="settings-actions"):
                yield Button("Hủy", id="btn-cancel", variant="default")
                yield Button("Lưu", id="btn-save", variant="primary")

    def _collect_values(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for _section, fields in SETTING_SECTIONS:
            for f in fields:
                wid = f"fld-{f.path.replace('.', '-')}"
                try:
                    w = self.query_one(f"#{wid}", Input)
                    out[f.path] = w.value
                except Exception:
                    out[f.path] = self._values.get(f.path, "")
        return out

    @on(Button.Pressed, "#btn-cancel")
    def on_cancel_btn(self) -> None:
        self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#btn-save")
    def on_save_btn(self) -> None:
        values = self._collect_values()
        ok, msg = save_settings(values)
        try:
            self.query_one("#settings-status", Static).update(msg)
        except Exception:
            pass
        if ok:
            self.dismiss(True)


class XiaozhiTuiApp(App[None]):
    """小智 TUI 主应用."""

    TITLE = SystemConstants.APP_DISPLAY_NAME
    SUB_TITLE = "TUI"
    CSS = """
    Screen {
        layout: vertical;
    }
    #status-panel {
        height: auto;
        max-height: 8;
        border: solid $primary;
        margin: 0 1;
        padding: 0 1;
    }
    #status-line {
        text-style: bold;
    }
    #meta-line {
        color: $text-muted;
    }
    #log-panel {
        height: 1fr;
        border: solid $accent;
        margin: 0 1;
    }
    #input-row {
        height: 3;
        margin: 0 1 1 1;
    }
    #cmd-input {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit_app", "Thoát", show=True, priority=True),
        Binding("f2", "open_settings", "Cài đặt", show=True),
        Binding("f1", "show_help", "Trợ giúp", show=True),
    ]

    status_text: reactive[str] = reactive("Chờ lệnh")
    connected: reactive[bool] = reactive(False)
    auto_mode: reactive[bool] = reactive(False)
    chat_text: reactive[str] = reactive("")
    music_line: reactive[str] = reactive("")
    emotion: reactive[str] = reactive("neutral")

    def __init__(
        self,
        on_command: Callable[[str], None] | None = None,
        on_settings_saved: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._on_command = on_command
        self._on_settings_saved = on_settings_saved
        self._log_handler_installed = False
        self._tui_log_handler = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="status-panel"):
            yield Static("Trạng thái: Chờ lệnh", id="status-line")
            yield Static("Kết nối: Chưa kết nối | Chế độ: Thủ công | Biểu cảm: neutral", id="meta-line")
            yield Static("Hội thoại: —", id="chat-line")
            yield Static("Âm nhạc: —", id="music-line")
        yield RichLog(id="log-panel", highlight=True, markup=True, max_lines=500)
        with Horizontal(id="input-row"):
            yield Input(
                placeholder=(
                    "Nhập văn bản gửi | r hội thoại | x ngắt lời | s cài đặt | q thoát | h trợ giúp"
                ),
                id="cmd-input",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#cmd-input", Input).focus()
        self._install_log_handler()
        self._refresh_status_widgets()
        self.write_log(
            f"[bold cyan]{SystemConstants.APP_DISPLAY_NAME} TUI[/]  "
            "F2 Cài đặt · F1 Trợ giúp · Ctrl+C Thoát"
        )

    def watch_status_text(self, _value: str) -> None:
        self._refresh_status_widgets()

    def watch_connected(self, _value: bool) -> None:
        self._refresh_status_widgets()

    def watch_auto_mode(self, _value: bool) -> None:
        self._refresh_status_widgets()

    def watch_chat_text(self, _value: str) -> None:
        self._refresh_status_widgets()

    def watch_music_line(self, _value: str) -> None:
        self._refresh_status_widgets()

    def watch_emotion(self, _value: str) -> None:
        self._refresh_status_widgets()

    def _refresh_status_widgets(self) -> None:
        try:
            conn = "Đã kết nối" if self.connected else "Chưa kết nối"
            mode = "Tự động" if self.auto_mode else "Thủ công"
            self.query_one("#status-line", Static).update(f"Trạng thái: {self.status_text}")
            self.query_one("#meta-line", Static).update(
                f"Kết nối: {conn} | Chế độ: {mode} | Biểu cảm: {self.emotion}"
            )
            self.query_one("#chat-line", Static).update(
                f"Hội thoại: {self.chat_text or '—'}"
            )
            self.query_one("#music-line", Static).update(
                f"Âm nhạc: {self.music_line or '—'}"
            )
        except Exception:
            pass

    def write_log(self, message: str) -> None:
        try:
            self.query_one("#log-panel", RichLog).write(message)
        except Exception:
            pass

    @on(Input.Submitted, "#cmd-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = (event.value or "").strip()
        event.input.value = ""
        if text:
            self._dispatch_command(text)

    def _dispatch_command(self, text: str) -> None:
        raw = text.strip()
        key = raw.lower()
        if key.startswith("/"):
            key = key[1:]

        if key in ("s", "settings", "set"):
            self.action_open_settings()
            return
        if key in ("h", "help", "?"):
            self.action_show_help()
            return
        if key in ("q", "quit", "exit"):
            self.action_quit_app()
            return

        if self._on_command:
            if key in ("r", "x") and raw.startswith("/"):
                self._on_command(key)
            else:
                self._on_command(raw)

    def action_show_help(self) -> None:
        self.write_log(
            "[bold cyan]Trợ giúp[/]\n"
            "  Văn bản → Gửi cho trợ lý\n"
            "  r → Bắt đầu/Dừng hội thoại\n"
            "  x → Ngắt lời\n"
            "  s / F2 → Cài đặt\n"
            "  q / Ctrl+C → Thoát\n"
            "  h / F1 → Trợ giúp"
        )

    def action_open_settings(self) -> None:
        def _done(saved: bool | None) -> None:
            if saved:
                self.write_log("[green]Cấu hình đã lưu, đang áp dụng nóng…[/]")
                if self._on_settings_saved:
                    try:
                        self._on_settings_saved()
                    except Exception as e:
                        logger.error(f"Callback lưu cài đặt thất bại: {e}", exc_info=True)
                        self.write_log(f"[red]Áp dụng nóng thất bại: {e}[/]")

        self.push_screen(SettingsScreen(), _done)

    def action_quit_app(self) -> None:
        if self._on_command:
            self._on_command("q")
        self.exit()

    def _install_log_handler(self) -> None:
        if self._log_handler_installed:
            return
        import logging

        app = self

        class TuiLogHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                try:
                    msg = self.format(record)
                    app.call_from_thread(app.write_log, msg)
                except Exception:
                    pass

        handler = TuiLogHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"
            )
        )
        handler.setLevel(logging.INFO)
        root = logging.getLogger()
        for h in list(root.handlers):
            if isinstance(h, logging.StreamHandler) and not isinstance(
                h, logging.FileHandler
            ):
                try:
                    root.removeHandler(h)
                except Exception:
                    pass
        root.addHandler(handler)
        self._tui_log_handler = handler
        self._log_handler_installed = True

    def uninstall_log_handler(self) -> None:
        if not self._log_handler_installed:
            return
        import logging

        h = self._tui_log_handler
        if h is not None:
            try:
                logging.getLogger().removeHandler(h)
            except Exception:
                pass
        self._log_handler_installed = False
        self._tui_log_handler = None
