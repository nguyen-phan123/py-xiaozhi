# ADR-0001: Cơ chế Giả lập Phần cứng ESP32 trong py-xiaozhi

## Bối cảnh (Context)
Server Xiaozhi ban đầu được thiết kế để phục vụ thiết bị phần cứng nhúng dựa trên vi điều khiển ESP32 (firmware `xiaozhi-esp32` bằng C++/ESP-IDF). `py-xiaozhi` là client thuần Python chạy trên hệ điều hành máy tính (macOS, Linux, Windows) và máy tính đơn bo (Raspberry Pi), đóng vai trò giả lập hoàn chỉnh một thiết bị ESP32 để kết nối liền mạch vào hệ sinh thái Xiaozhi.

## Quyết định Kiến trúc (Decisions)

### 1. Giả lập Bộ nhớ eFuse & Định danh phần cứng
- **Vị trí**: `src/activation/identity.py`
- **Lưu trữ**: File `efuse.json` lưu 4 trường cốt lõi: `mac_address`, `device_id`, `client_id`, `token`.
- **Cơ chế**: Thay vì đọc trực tiếp OTP/eFuse chip silicon của ESP32, ứng dụng đọc địa chỉ MAC thật của card mạng (hoặc fallback MAC ảo) và serialize/deserialize vào `efuse.json`, mô phỏng phân vùng NVS (Non-Volatile Storage) của ESP-IDF.

### 2. Giả lập Giao thức & Mã hóa Nhị phân (Protocol & Crypto)
- **Vị trí**: `src/protocols/mqtt_udp.py`, `src/protocols/mqtt_crypto.py`, `src/protocols/websocket_protocol.py`
- **Cơ chế**:
  - **MQTT + UDP**: Tách kênh JSON điều khiển (MQTT port 8883/TLS) và kênh stream âm thanh (UDP).
  - **Mã hóa AES-CTR**: Giả lập định dạng gói tin nhị phân của ESP32 firmware:
    - Fixed prefix (4 hex) + Payload length (4 hex) + Nonce gốc (16 hex) + Sequence Counter (8 hex).
  - **WebSocket**: Thiết lập handshake với HTTP Headers tương đương firmware ESP32 (`Device-Id`, `Client-Id`, `Authorization`).

### 3. Giả lập Pipeline Âm thanh Phần cứng (Audio Pipeline)
- **Vị trí**: `src/audio_codecs/opus_codec.py`, `src/audio_codecs/audio_buffer.py`
- **Cơ chế**:
  - Định dạng chuẩn: PCM 16kHz, mono 16-bit.
  - Encoder/Decoder Opus mô phỏng phần cứng codec (ES8388 / AC101) truyền nhận audio frame kích thước 20ms - 60ms.
  - Xử lý AEC (Acoustic Echo Cancellation) mô phỏng DSP phần cứng qua thư viện WebRTC APM.

### 4. Giả lập Phím bấm & Đèn LED Vật lý (GPIO)
- **Vị trí**: `src/ui/gpio/input.py`, `src/ui/gpio/manager.py`
- **Cơ chế**: Dành riêng cho SBC Linux (Raspberry Pi) điều khiển qua chân GPIO, mô phỏng nút ấn Boot/Action và LED trạng thái giống hệt bo mạch ESP32 thật.

### 5. Quy trình Kích hoạt & OTA
- **Vị trí**: `src/activation/ota.py`, `src/activation/service.py`
- **Cơ chế**: Thực hiện bắt tay xác thực mã 6 số (Verification Code) với backend OTA server theo chuẩn API mà firmware ESP32 sử dụng.

## Hậu quả & Đánh đổi (Consequences)
- **Tích cực**:
  - Tận dụng 100% hệ sinh thái backend Xiaozhi mà không cần sửa đổi server.
  - Dễ dàng chạy trên PC, Mac, server không màn hình hoặc Raspberry Pi.
- **Tiêu cực**:
  - Không thể biên dịch hay nạp trực tiếp code Python này vào vi điều khiển ESP32 vật lý.
  - Cần cài đặt các native library phụ thuộc (libopus, portaudio, webrtc-apm).
