"""TUI 设置：配置字段定义与读写（接 ConfigManager + CONFIG_CHANGED）."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.logging import get_logger
from src.utils.config_manager import get_config

logger = get_logger()


@dataclass(frozen=True)
class SettingField:
    """一个可编辑配置项."""

    path: str
    label: str
    kind: str = "str"  # str | int | bool | choice
    choices: tuple[str, ...] = ()
    help: str = ""


# 第一期：系统 / 音频 / 摄像头 / 唤醒词
SETTING_SECTIONS: list[tuple[str, list[SettingField]]] = [
    (
        "Hệ thống",
        [
            SettingField(
                "SYSTEM_OPTIONS.NETWORK.OTA_VERSION_URL",
                "OTA URL",
                help="Địa chỉ OTA / cấu hình kích hoạt",
            ),
            SettingField(
                "SYSTEM_OPTIONS.NETWORK.WEBSOCKET_URL",
                "WebSocket URL",
                help="Địa chỉ dịch vụ WebSocket",
            ),
            SettingField(
                "SYSTEM_OPTIONS.DEVICE_ID",
                "ID thiết bị",
                help="Device-Id (thường là MAC)",
            ),
            SettingField(
                "SYSTEM_OPTIONS.CLIENT_ID",
                "ID máy khách",
                help="Client-Id",
            ),
        ],
    ),
    (
        "Âm thanh",
        [
            SettingField(
                "AUDIO_DEVICES.input_device_name",
                "Thiết bị đầu vào",
                help="Khớp microphone theo tên (ID thay đổi sau khi cắm rút)",
            ),
            SettingField(
                "AUDIO_DEVICES.output_device_name",
                "Thiết bị đầu ra",
                help="Khớp loa/tai nghe theo tên",
            ),
            SettingField(
                "AUDIO_DEVICES.opus_output_sample_rate",
                "Tần số mẫu Opus",
                kind="choice",
                choices=("24000", "16000"),
                help="Chính thức 24000 / Bên thứ ba 16000",
            ),
            SettingField(
                "AUDIO_DEVICES.frame_duration",
                "Độ dài khung ms",
                kind="choice",
                choices=("20", "40", "60"),
                help="20 độ trễ thấp / 60 CPU thấp",
            ),
        ],
    ),
    (
        "Camera",
        [
            SettingField(
                "CAMERA.backend",
                "Backend thu hình",
                kind="choice",
                choices=("auto", "opencv", "picamera2"),
                help="auto ưu tiên OpenCV, thất bại chuyển Pi CSI",
            ),
            SettingField(
                "CAMERA.device",
                "Đường dẫn thiết bị",
                help="Ví dụ /dev/video0; ưu tiên hơn index",
            ),
            SettingField(
                "CAMERA.camera_index",
                "Index thiết bị",
                kind="int",
                help="Chỉ số số nguyên OpenCV",
            ),
            SettingField(
                "CAMERA.frame_width",
                "Chiều rộng",
                kind="int",
            ),
            SettingField(
                "CAMERA.frame_height",
                "Chiều cao",
                kind="int",
            ),
        ],
    ),
    (
        "Từ đánh thức",
        [
            SettingField(
                "WAKE_WORD_OPTIONS.USE_WAKE_WORD",
                "Bật từ đánh thức",
                kind="bool",
            ),
            SettingField(
                "WAKE_WORD_OPTIONS.WAKE_WORD",
                "Từ đánh thức",
                help="Ví dụ: Xin chào Xiaozhi",
            ),
            SettingField(
                "WAKE_WORD_OPTIONS.WAKE_WORD_LANG",
                "Ngôn ngữ",
                kind="choice",
                choices=("zh", "en"),
            ),
        ],
    ),
]


def load_setting_values() -> dict[str, str]:
    """读取当前配置为字符串表（path -> 显示值）."""
    cfg = get_config()
    values: dict[str, str] = {}
    for _section, fields in SETTING_SECTIONS:
        for f in fields:
            raw = cfg.get_config(f.path, "")
            if f.kind == "bool":
                values[f.path] = "true" if bool(raw) else "false"
            elif raw is None:
                values[f.path] = ""
            else:
                values[f.path] = str(raw)
    return values


def parse_field_value(field: SettingField, text: str) -> Any:
    """把输入框字符串转成配置值."""
    s = (text or "").strip()
    if field.kind == "int":
        if s == "":
            return 0
        return int(s)
    if field.kind == "bool":
        return s.lower() in ("1", "true", "yes", "on", "có", "bật", "đúng", "dung", "co", "bat", "是")
    if field.kind == "choice":
        if field.choices and s not in field.choices:
            # 仍写入用户值，由上层校验提示
            return s
        if field.path.endswith("opus_output_sample_rate") or field.path.endswith(
            "frame_duration"
        ):
            try:
                return int(s)
            except ValueError:
                return s
        return s
    return s


def save_settings(values: dict[str, str]) -> tuple[bool, str]:
    """批量写配置并落盘.

    Returns:
        (ok, message)
    """
    cfg = get_config()
    updates: dict[str, Any] = {}
    try:
        for _section, fields in SETTING_SECTIONS:
            for f in fields:
                if f.path not in values:
                    continue
                updates[f.path] = parse_field_value(f, values[f.path])
        if not updates:
            return True, "Không có thay đổi"
        ok = cfg.update_configs(updates)
        if not ok:
            return False, "Lưu thất bại (lỗi ghi đĩa)"
        logger.info(f"TUI đã lưu {len(updates)} mục cấu hình")
        return True, f"Đã lưu {len(updates)} mục"
    except Exception as e:
        logger.error(f"TUI lưu cấu hình thất bại: {e}", exc_info=True)
        return False, f"Lưu thất bại: {e}"
