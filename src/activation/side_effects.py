"""Tác dụng phụ của mã xác thực kích hoạt: Clipboard và phát âm thanh."""

from __future__ import annotations

from typing import Optional

from src.logging import get_logger

logger = get_logger()


def apply_code_side_effects(code: str, message: Optional[str] = None) -> None:
    """Log + clipboard + phát âm; không chịu trách nhiệm hiển thị văn bản CLI/GUI."""
    if not code:
        return
    msg = message or "Vui lòng nhập mã xác thực trên bảng điều khiển"
    logger.info(f"Thông báo kích hoạt: {msg}")
    logger.info(f"Mã xác thực: {code}")

    text = f".Vui lòng đăng nhập vào bảng điều khiển để thêm thiết bị, nhập mã xác thực: {' '.join(code)}..."
    try:
        from src.utils.common_utils import handle_verification_code

        handle_verification_code(text)
    except Exception as e:
        logger.debug(f"Sao chép mã xác thực thất bại: {e}")

    try:
        from src.utils.activation_announcer import announce_activation_code

        announce_activation_code(code, locale="zh-CN")
    except Exception as e:
        logger.debug(f"Phát thông báo mã xác thực thất bại: {e}")


def announce_code(code: str) -> None:
    """Chỉ phát âm (dùng khi thử lại trong polling)."""
    if not code:
        return
    from src.utils.activation_announcer import announce_activation_code

    announce_activation_code(code, locale="zh-CN")
