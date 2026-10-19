# 系统常量定义
from enum import Enum


class InitializationStage(Enum):
    """
    初始化阶段枚举.
    """

    DEVICE_FINGERPRINT = "Giai đoạn 1: Chuẩn bị định danh thiết bị"
    CONFIG_MANAGEMENT = "Giai đoạn 2: Khởi tạo quản lý cấu hình"
    OTA_CONFIG = "Giai đoạn 3: Lấy cấu hình OTA"
    ACTIVATION = "Giai đoạn 4: Quy trình kích hoạt"


class SystemConstants:
    """
    系统常量.
    """

    # 应用信息
    APP_NAME = "py-xiaozhi"  # 程序标识名（ASCII，用于目录、配置、bundle_id）
    APP_DISPLAY_NAME = "Xiaozhi"  # 显示名称（用于窗口标题、Launchpad、安装器 UI）
    APP_VERSION = "2.1.2"
    BOARD_TYPE = "bread-compact-wifi"

    # 默认超时设置
    DEFAULT_TIMEOUT = 10
    ACTIVATION_MAX_RETRIES = 60
    ACTIVATION_RETRY_INTERVAL = 5

    # 文件名常量
    CONFIG_FILE = "config.json"
    EFUSE_FILE = "efuse.json"
