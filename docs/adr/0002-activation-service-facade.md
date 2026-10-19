# ADR-0002: Kiến trúc ActivationService Facade

## Bối cảnh (Context)
Trong các phiên bản trước, quy trình kích hoạt thiết bị bị phân tán giữa các module singleton độc lập (`ActivationService.get_instance()`, `ConfigManager.get_instance()`), dẫn tới việc tồn lưu state bẩn giữa các lần chạy, rò rỉ bộ nhớ khi hủy container và gây khó khăn cho việc viết unit test.

Để chuẩn hóa theo nguyên tắc Dependency Injection và Modular Architecture, `ActivationService` được tái cấu trúc thành một Facade hợp nhất không dùng singleton.

## Quyết định Kiến trúc (Decisions)

### 1. Triệt tiêu Singleton, Dùng Async Factory
- Khởi tạo bắt buộc qua phương thức bất đồng bộ: `await ActivationService.create()`.
- Mỗi instance quản lý vòng đời riêng, không chia sẻ biến toàn cục, an toàn cho kiểm thử và tái tạo container khi ứng dụng chạy nhiều mode (GUI, CLI, TUI, GPIO).

### 2. Thiết kế Pattern Facade Gom 4 Subsystem
`ActivationService` đóng gói 4 thành phần nội bộ:
1. **`DeviceIdentity`** (`src/activation/identity.py`): Đọc/ghi `efuse.json` mô phỏng eFuse ESP32, quản lý MAC address và Serial Number.
2. **`OtaConfigClient`** (`src/activation/ota.py`): Giao tiếp OTA server để lấy endpoint kết nối (WebSocket / MQTT) và cấu hình runtime.
3. **`ActivationHttpClient`** (`src/activation/client.py`): Polling server, gửi challenge và mã xác thực 6 số để đổi lấy token phiên.
4. **`Side Effects`** (`src/activation/side_effects.py`): Xử lý sao chép mã vào clipboard và phát âm thanh thông báo qua TTS.

### 3. Cơ chế Hòa giải Trạng thái Kích hoạt (State Reconciliation)
Hàm `_analyze_activation_status()` so khớp giữa trạng thái lưu cục bộ (`local_activated`) và xác nhận từ máy chủ (`server_activated`):

| Local | Server | Cần UI | Hành vi |
|---|---|---|---|
| False | False | True | Thiết bị mới chưa đăng ký → Hiển thị UI kích hoạt |
| True | True | False | Trạng thái nhất quán hợp lệ → Bỏ qua kích hoạt, vào thẳng app |
| False | True | False | Cục bộ mất dữ liệu nhưng server đã nhận → Tự động cập nhật `efuse.json` |
| True | False | True / Fallback | Server thu hồi quyền → Buộc tái kích hoạt nếu có mã mới |

### 4. Quản lý Tác vụ Bất đồng bộ và Khả năng Hủy (Cancellable)
- Lưu vết tác vụ polling qua `self._activation_task = asyncio.current_task()`.
- Cho phép UI gọi `cancel_activation()` ngắt ngay lập tức khi người dùng đóng cửa sổ hoặc ngắt ứng dụng (`Ctrl+C`), dọn dẹp cờ `_is_activating` trong khối `finally`.

## Hậu quả & Đánh đổi (Consequences)
- **Tích cực**:
  - Giao diện người dùng (GUI/CLI/TUI) chỉ cần gọi một API duy nhất (`await service.initialize()`, `await service.activate()`).
  - Trạng thái rõ ràng, dễ viết mock/stub cho unit test.
- **Tiêu cực**:
  - Khởi tạo async yêu cầu caller phải nằm trong event loop đang chạy (`create()` thay vì `__init__` đồng bộ thông thường).
