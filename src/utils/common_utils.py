"""
通用工具函数集合模块.

包含浏览器操作、剪贴板、验证码提取等通用工具函数。
"""

import re
import webbrowser
from typing import Optional

from src.logging import get_logger

logger = get_logger()


def open_url(url: str) -> bool:
    """打开网页链接."""
    try:
        success = webbrowser.open(url)
        if success:
            logger.info(f"Đã mở trang web thành công: {url}")
        else:
            logger.warning(f"Không thể mở trang web: {url}")
        return success
    except Exception as e:
        logger.error(f"Lỗi khi mở trang web: {e}", exc_info=True)
        return False


def copy_to_clipboard(text: str) -> bool:
    """复制文本到剪贴板."""
    try:
        import pyperclip

        pyperclip.copy(text)
        logger.info(f'Văn bản "{text}" đã được sao chép vào clipboard')
        return True
    except ImportError:
        logger.warning("Chưa cài đặt module pyperclip, không thể sao chép vào clipboard")
        return False
    except Exception as e:
        logger.error(f"Lỗi khi sao chép vào clipboard: {e}", exc_info=True)
        return False


def extract_verification_code(text: str) -> Optional[str]:
    """从文本中提取验证码."""
    try:
        # 激活相关关键词列表
        activation_keywords = [
            "登录",
            "控制面板",
            "激活",
            "验证码",
            "绑定设备",
            "添加设备",
            "输入验证码",
            "输入",
            "面板",
            "xiaozhi.me",
            "激活码",
        ]

        # 检查文本是否包含激活相关关键词
        has_activation_keyword = any(keyword in text for keyword in activation_keywords)

        if not has_activation_keyword:
            logger.debug(f"Văn bản không chứa từ khóa kích hoạt, bỏ qua trích xuất mã xác thực: {text}")
            return None

        # 更精确的验证码匹配模式
        patterns = [
            r"验证码[：:]\s*(\d{6})",
            r"输入验证码[：:]\s*(\d{6})",
            r"输入\s*(\d{6})",
            r"验证码\s*(\d{6})",
            r"激活码[：:]\s*(\d{6})",
            r"(\d{6})[，,。.]",
            r"[，,。.]\s*(\d{6})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                code = match.group(1)
                logger.info(f"Đã trích xuất mã xác thực từ văn bản: {code}")
                return code

        # 通用模式匹配
        match = re.search(r"((?:\d\s*){6,})", text)
        if match:
            code = "".join(match.group(1).split())
            if len(code) == 6 and code.isdigit():
                logger.info(f"Đã trích xuất mã xác thực từ văn bản (chế độ chung): {code}")
                return code

        logger.warning(f"Không tìm thấy mã xác thực trong văn bản: {text}")
        return None
    except Exception as e:
        logger.error(f"Lỗi khi trích xuất mã xác thực: {e}", exc_info=True)
        return None


def handle_verification_code(text: str) -> None:
    """处理验证码：提取并复制到剪贴板."""
    code = extract_verification_code(text)
    if code:
        copy_to_clipboard(code)
