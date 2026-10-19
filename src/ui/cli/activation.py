"""CLI模式设备激活流程."""

from datetime import datetime

from src.constants.system import SystemConstants
from src.logging import get_logger
from src.ui.shared.activation import BaseActivation

logger = get_logger()


class CliActivation(BaseActivation):
    """CLI模式设备激活处理器.

    继承 BaseActivation，仅覆盖终端输出的展示方法。
    """

    def __init__(self, activation_service, init_result: dict):
        super().__init__(activation_service, init_result)

    async def run(self) -> bool:
        self._print_header()

        if not self.needs_activation():
            self._log("Thiết bị đã được kích hoạt, không cần thao tác thêm")
            self._print_success()
            return True

        self._print_device_info()
        try:
            return await self._core_activate()
        except KeyboardInterrupt:
            self._log("\nNgười dùng đã hủy quy trình kích hoạt")
            return False

    # ---- BaseActivation 展示方法 ----

    def _show_code(self, data: dict) -> None:
        self._print_activation_info(data)

    def _show_result(self, success: bool) -> None:
        if success:
            self._print_success()
        else:
            self._print_failure()

    def _show_error(self, msg: str) -> None:
        self._log(msg)

    # ---- 终端展示辅助方法 ----

    def _print_header(self):
        print("\n" + "=" * 60)
        print(f"{SystemConstants.APP_DISPLAY_NAME} - Kích hoạt thiết bị")
        print("=" * 60)

    def _print_device_info(self):
        """打印设备信息."""
        serial = self._service.get_serial_number() or "--"
        mac = self._service.get_mac_address() or "--"
        status = self._service.get_activation_status()

        print("\nThông tin thiết bị:")
        print(f"  Số seri: {serial}")
        print(f"  Địa chỉ MAC: {mac}")

        local = status.get("local_activated", False)
        server = status.get("server_activated", False)
        consistent = status.get("status_consistent", True)

        if not consistent:
            status_text = "Cần kích hoạt lại" if local and not server else "Đã tự động sửa"
        else:
            status_text = "Đã kích hoạt" if local else "Chưa kích hoạt"

        print(f"  Trạng thái: {status_text}")

    def _print_activation_info(self, data: dict):
        """打印激活信息."""
        code = data.get("code", "------")
        message = data.get("message", "Vui lòng truy cập xiaozhi.me để nhập mã xác thực")

        print("\n" + "-" * 60)
        print("Thông tin kích hoạt")
        print("-" * 60)
        print(f"Mã xác thực: {' '.join(code)}")
        print(f"Hướng dẫn: {message}")
        print("-" * 60)
        print("\nCác bước kích hoạt:")
        print("  1. Mở trình duyệt và truy cập xiaozhi.me")
        print("  2. Đăng nhập vào tài khoản của bạn")
        print("  3. Chọn thêm thiết bị mới")
        print(f"  4. Nhập mã xác thực: {code}")
        print("  5. Xác nhận thêm thiết bị")

    def _print_success(self):
        print("\n" + "=" * 60)
        print("Kích hoạt thiết bị thành công!")
        print("=" * 60)
        print("Thiết bị đã được thêm vào tài khoản của bạn")
        print(f"Đang khởi động {SystemConstants.APP_DISPLAY_NAME}...")
        print("=" * 60 + "\n")

    def _print_failure(self):
        print("\n" + "=" * 60)
        print("Kích hoạt thiết bị thất bại")
        print("=" * 60)
        print("Nguyên nhân có thể:")
        print("  - Kết nối mạng không ổn định")
        print("  - Mã xác thực sai hoặc đã hết hạn")
        print("  - Máy chủ tạm thời không khả dụng")
        print("\nGiải pháp:")
        print("  - Kiểm tra lại kết nối mạng")
        print("  - Chạy lại ứng dụng để lấy mã xác thực mới")
        print("  - Đảm bảo nhập chính xác mã xác thực")
        print("=" * 60 + "\n")

    def _log(self, message: str):
        """打印带时间戳的日志."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        logger.info(message)
