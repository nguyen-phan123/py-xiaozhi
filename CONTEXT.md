# Py-Xiaozhi Domain Context

Cross-platform AI voice assistant client communicating with Xiaozhi protocol backend.

## Language

**Chờ lệnh**:
Device is connected, idle, and waiting for user wake word or input command.
_Avoid_: 待命, Rảnh rỗi, Đang nghỉ

**Kích hoạt**:
The onboarding process binding the device to the user account using serial number and code.
_Avoid_: 激活, Đăng ký, Cấp quyền

**Mã xác thực**:
The numeric verification code displayed during onboarding to enter on the web console.
_Avoid_: 验证码, Mã kích hoạt, OTP, Verification pin

## Architecture & Decisions
- [ADR-0001: Cơ chế Giả lập Phần cứng ESP32](docs/adr/0001-esp32-hardware-simulation.md)
- [ADR-0002: Kiến trúc ActivationService Facade](docs/adr/0002-activation-service-facade.md)
- [ADR-0003: Quản lý Định danh Thiết bị và Lưu trữ eFuse](docs/adr/0003-device-identity-efuse-storage.md)



