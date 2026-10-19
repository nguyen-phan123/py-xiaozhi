"""Tạo UI kích hoạt theo chế độ chạy (đối xứng với create_viewport)."""

from typing import Any


def create_activation_ui(mode: str, activation_service, init_result: dict) -> Any:
    """gui → GuiActivation；tui/cli/gpio → CliActivation.

    Args:
        mode: Chế độ chạy
        activation_service: Instance của ActivationService
        init_result: Kết quả initialize() (tránh gọi initialize lặp lại)
    """
    normalized = (mode or "cli").lower()
    if normalized == "gui":
        from src.ui.gui import GuiActivation

        return GuiActivation(activation_service, init_result)

    # tui / cli / gpio: Giai đoạn kích hoạt dùng tương tác terminal đơn giản
    from src.ui.cli import CliActivation

    return CliActivation(activation_service, init_result)
