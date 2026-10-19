# ADR-0003: Quản lý Định danh Thiết bị và Lưu trữ eFuse

## Bối cảnh (Context)
Trong vi điều khiển ESP32, thông tin định danh và khóa bí mật được ghi chết vào các thanh ghi eFuse (One-Time Programmable) và phân vùng NVS (Non-Volatile Storage). `py-xiaozhi` chạy trên PC và SBC, cần một cơ chế tương đương để lưu trữ bền vững Serial Number, MAC address, HMAC Key và trạng thái kích hoạt mà không bị lỗi hỏng dữ liệu khi gặp sự cố ngắt nguồn.

Trước đây, file `efuse.json` lưu trữ lồng đối tượng `device_fingerprint` phức tạp, gây khó khăn cho việc validate, không thể di chuyển linh hoạt và dễ bị lỗi parse khi thay đổi card mạng.

## Quyết định Kiến trúc (Decisions)

### 1. Chuẩn hóa Cấu trúc Phẳng (Flat Schema)
File `efuse.json` chỉ duy trì duy nhất 4 trường phẳng:
- `mac_address`: Địa chỉ MAC card mạng chính (chuẩn hóa `xx:xx:xx:xx:xx:xx`).
- `serial_number`: Mã số định danh thiết bị theo định dạng `SN-{hash8}-{mac_clean}`.
- `hmac_key`: Khóa bí mật dùng để ký xác thực challenge với server.
- `activation_status`: Giá trị boolean lưu trạng thái kích hoạt cục bộ.

Tất cả các trường phụ hoặc cấu trúc lồng cũ (`device_fingerprint`) sẽ bị tự động bóc tách và loại bỏ trong hàm `_normalize_efuse_dict()`.

### 2. Tách biệt Bộ nhớ Thu thập và Bộ nhớ Lưu trữ
- **`generate_fresh_fingerprint()`**: Chỉ thu thập tức thời trong RAM (`psutil`, `machineid`, `platform.node()`) khi cần tạo mới hoặc bổ sung trường thiếu; tuyệt đối không ghi cả khối fingerprint vào file đĩa.
- **Cache RAM (`_efuse_cache`)**: Lưu dữ liệu đã chuẩn hóa trong bộ nhớ để phục vụ các lần đọc sau, giảm thiểu I/O đọc đĩa lặp lại.

### 3. Ghi đĩa Nguyên tử (Atomic Write)
Để ngăn ngừa tình trạng file json bị rỗng (0 bytes) hoặc hỏng cú pháp (corrupted) khi ứng dụng bị tắt đột ngột:
- Dữ liệu luôn được ghi ra file tạm thời: `efuse.tmp`.
- Sử dụng hàm nguyên tử `os.replace(tmp, self._efuse_file)` của hệ điều hành để ghi đè an toàn.

### 4. Cơ chế Ký số HMAC Xác thực
Khi server gửi mã thách thức `challenge`, hàm `generate_hmac_signature(challenge)` sử dụng thuật toán HMAC-SHA256 với `hmac_key` để tạo chữ ký hex chứng minh tính danh thực của thiết bị.

## Hậu quả & Đánh đổi (Consequences)
- **Tích cực**:
  - Dữ liệu định danh gọn gàng, tương thích 100% với các test case phục hồi lỗi (`test_resilience_fixes.py`).
  - An toàn tuyệt đối trước sự cố crash đĩa hoặc ngắt điện.
- **Tiêu cực**:
  - Việc clone toàn bộ thư mục `config/efuse.json` sang máy tính khác sẽ khiến máy mới bị nhận diện trùng lặp danh tính (cần xóa file để tạo lại nếu muốn reset thiết bị mới).
