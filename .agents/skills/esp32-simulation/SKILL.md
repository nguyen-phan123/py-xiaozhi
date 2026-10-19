---
name: esp32-simulation
description: Reference guidelines and architectural patterns for simulating ESP32 hardware peripherals, protocols, and identity in py-xiaozhi.
---

# ESP32 Hardware Emulation Skill

<goal>
Guide agents and developers in maintaining fidelity when simulating ESP32 embedded hardware behavior, protocols, and identity in the py-xiaozhi Python client.
</goal>

<context>
`py-xiaozhi` is a Python-based client that emulates an ESP32 microcontroller running the `xiaozhi-esp32` C++/ESP-IDF firmware. It communicates with the Xiaozhi backend servers via specialized protocols and emulates physical hardware chips and memory storage without requiring real embedded hardware.
</context>

<constraints>
- Keep `config/efuse.json` schema strictly flat with four fields: `mac_address`, `serial_number`, `hmac_key`, `activation_status`.
- Never persist raw hardware fingerprint blobs into persistent files.
- Write files using atomic replace via temporary files to avoid data corruption on unexpected process shutdown.
- Maintain dual-channel networking: MQTT TLS for control signaling, UDP for audio data streaming.
- Retain binary packet header structure for AES-CTR encryption to ensure packet compatibility with ESP-IDF firmware specifications.
- Adhere to the canonical vocabulary in `CONTEXT.md` (e.g., "Mã xác thực", "Kích hoạt", "Chờ lệnh").
</constraints>

<steps>
1. Identity and eFuse emulation (`src/activation/identity.py`):
   - Read system network interface MAC or fallback MAC.
   - Format serial number with `SN-{hash8}-{mac_clean}`.
   - Store credentials in `config/efuse.json` using atomic write (`efuse.tmp` followed by `os.replace`).
   - Use HMAC-SHA256 with `hmac_key` to sign challenge strings requested by the backend.

2. Network protocols and cryptography (`src/protocols/`):
   - Maintain MQTT TLS connection on port `8883` or WebSocket connection with firmware-equivalent headers (`Device-Id`, `Client-Id`, `Authorization`).
   - Package UDP audio packets with AES-CTR encrypted binary frames: `prefix (4 hex)` + `payload length (4 hex)` + `base nonce (16 hex)` + `sequence counter (8 hex)`.

3. Audio pipeline processing (`src/audio_codecs/`):
   - Standardize audio stream format to PCM 16kHz, mono, 16-bit.
   - Use Opus codec with 20ms to 60ms frame sizes to simulate hardware codecs (ES8388 or AC101).
   - Apply WebRTC APM for Acoustic Echo Cancellation (AEC) and noise suppression.

4. Physical peripheral emulation (`src/ui/gpio/`):
   - Provide GPIO abstraction for single-board computers (Raspberry Pi).
   - Simulate Boot and Action buttons as well as LED status indicators.

5. Verification and activation workflow (`src/activation/`):
   - Implement verification code exchange against backend OTA services following the firmware API lifecycle.
</steps>

<done_when>
All ESP32 hardware abstractions preserve protocol compatibility with Xiaozhi backend servers, avoid state corruption under unexpected process termination, and adhere to canonical vocabulary standards.
</done_when>
