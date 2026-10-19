"""Cơ chế kiểm tra sức khỏe khởi động và chiến lược giáng cấp âm thanh (Health Check & Audio Degradation).

Độc lập với logic phiên làm việc: chỉ dựa vào tập hợp plugin thất bại và biến môi trường để quyết định exit hay tiếp tục ở chế độ giáng cấp (degraded).
"""

from __future__ import annotations

import os
from typing import Optional, Protocol

# Thoát trực tiếp khi khởi động thất bại, tránh zombie wait_shutdown
CRITICAL_PLUGINS = ("ui",)
# audio mặc định là then chốt; khi XIAOZHI_DEGRADED_AUDIO=1 thất bại chỉ giáng cấp chứ không exit
AUDIO_CRITICAL = True

DEGRADED_AUDIO_NOTICE = (
    "Giáng cấp: Âm thanh không khả dụng (không có mic/loa). Trang cài đặt vẫn hoạt động, vui lòng khởi động lại sau khi sửa thiết bị."
)


class _PluginHealth(Protocol):
    def is_failed(self, name: str) -> bool: ...


def audio_is_fatal() -> bool:
    """Kiểm tra lỗi audio có dẫn đến thoát tiến trình hay không.

    - XIAOZHI_DISABLE_AUDIO=1: Chủ động vô hiệu hóa, không coi là thất bại
    - XIAOZHI_DEGRADED_AUDIO=1: Thất bại sẽ giáng cấp tiếp tục (UI/cài đặt khả dụng)
    - Mặc định: Lỗi audio sẽ exit 1
    """
    if os.getenv("XIAOZHI_DISABLE_AUDIO") == "1":
        return False
    if os.getenv("XIAOZHI_DEGRADED_AUDIO") == "1":
        return False
    return AUDIO_CRITICAL


def check_critical_plugins(plugins: _PluginHealth) -> Optional[str]:
    """Kiểm tra các plugin then chốt (critical plugins) có khả dụng hay không.

    Returns:
        Mô tả lỗi; trả về None khi tất cả đều hoạt động bình thường
    """
    failed: list[str] = []
    for name in CRITICAL_PLUGINS:
        if plugins.is_failed(name):
            failed.append(name)

    if audio_is_fatal() and plugins.is_failed("audio"):
        failed.append("audio")

    if not failed:
        return None

    hints = []
    if "audio" in failed:
        hints.append(
            "Để debug không có âm thanh, có thể đặt XIAOZHI_DISABLE_AUDIO=1; "
            "hoặc đặt XIAOZHI_DEGRADED_AUDIO=1 để tiếp tục ở chế độ không mic (UI/cài đặt vẫn khả dụng)."
        )
    return (
        f"Plugin then chốt khởi động thất bại: {', '.join(failed)}. "
        "Ứng dụng sẽ thoát để tránh chạy không tải (zombie)."
        + (" " + " ".join(hints) if hints else "")
    )
