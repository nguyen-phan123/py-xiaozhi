#!/usr/bin/env python3
"""
watch_protocol.py — script độc lập để "nhìn thấy" giao thức Xiaozhi trần trụi.

Không import gì từ src/ của py-xiaozhi — chỉ dùng thư viện `websockets` để tự
kết nối, gửi hello y hệt client thật, rồi in ra mọi message JSON server gửi
về. Mục đích: hiểu giao thức trước khi lặn vào đọc code.

Cách dùng:
    1. Đã chạy py-xiaozhi và kích hoạt thành công ít nhất một lần
       (để có config.json với WEBSOCKET_URL/TOKEN thật).
    2. Đóng app py-xiaozhi lại (chỉ một client được giữ session cùng lúc).
    3. Chạy: uv run python watch_protocol.py
       (chạy trong venv của py-xiaozhi để có sẵn thư viện `websockets`)

Trong lúc script chạy:
    - Gõ một dòng bất kỳ rồi Enter: script gửi dòng đó như một message
      "listen/detect" (giống cơ chế báo phát hiện từ khoá đánh thức) để
      bạn thử xem server phản ứng ra sao khi không có audio thật đi kèm.
    - Mọi message JSON server gửi về được in ra ngay, kèm nhãn thời gian.
    - Frame audio (nhị phân) chỉ in độ dài, không giải mã (không cần opus).
    - Ctrl+C để thoát.
"""

from __future__ import annotations

import asyncio
import json
import platform
import ssl
import sys
import time
import uuid
from pathlib import Path


def default_config_path() -> Path:
    """Đường dẫn config.json mặc định theo platformdirs, không phụ thuộc thư viện đó."""
    system = platform.system()
    home = Path.home()
    if system == "Darwin":
        base = home / "Library" / "Application Support" / "py-xiaozhi"
    elif system == "Windows":
        import os

        base = Path(os.environ.get("LOCALAPPDATA", home)) / "py-xiaozhi"
    else:
        base = home / ".local" / "share" / "py-xiaozhi"
    return base / "config" / "config.json"


def load_connection_info(config_path: Path) -> dict:
    if not config_path.exists():
        sys.exit(
            f"Không thấy config.json ở: {config_path}\n"
            "Hãy chạy 'uv run python main.py --mode cli' ít nhất một lần và "
            "kích hoạt thành công trước, hoặc truyền đường dẫn config bằng "
            "tham số dòng lệnh: python watch_protocol.py /path/to/config.json"
        )
    data = json.loads(config_path.read_text(encoding="utf-8"))
    net = data["SYSTEM_OPTIONS"]["NETWORK"]
    device_id = data["SYSTEM_OPTIONS"].get("DEVICE_ID")
    client_id = data["SYSTEM_OPTIONS"].get("CLIENT_ID")
    url = net.get("WEBSOCKET_URL")
    token = net.get("WEBSOCKET_ACCESS_TOKEN")
    if not url:
        sys.exit(
            "config.json chưa có WEBSOCKET_URL — thiết bị có thể chưa kích hoạt "
            "xong. Chạy 'uv run python main.py --mode cli' để hoàn tất kích hoạt trước."
        )
    return {
        "url": url,
        "token": token or "test-token",
        "device_id": device_id or "00:00:00:00:00:00",
        "client_id": client_id or str(uuid.uuid4()),
    }


def ts() -> str:
    return time.strftime("%H:%M:%S")


def pretty(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


async def receiver(ws):
    """In ra mọi message server gửi về."""
    try:
        async for message in ws:
            if isinstance(message, (bytes, bytearray)):
                print(f"\n[{ts()}] ⬅ AUDIO nhị phân, {len(message)} byte (frame Opus)")
            else:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    print(f"\n[{ts()}] ⬅ (không parse được JSON): {message}")
                    continue
                mtype = data.get("type")
                print(f"\n[{ts()}] ⬅ JSON type={mtype}")
                print(pretty(data))
            print("\n> ", end="", flush=True)
    except Exception as e:
        print(f"\n[{ts()}] Kết nối đóng/lỗi trong lúc nhận: {e}")


async def sender(ws, session_id_holder: dict):
    """Đọc từng dòng bàn phím, gửi như message 'listen/detect'."""
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        text = line.strip()
        if not text:
            continue
        msg = {
            "session_id": session_id_holder.get("session_id", ""),
            "type": "listen",
            "state": "detect",
            "text": text,
        }
        print(f"[{ts()}] ➡ Gửi thử: {pretty(msg)}")
        await ws.send(json.dumps(msg))


async def main():
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_config_path()
    info = load_connection_info(config_path)

    print(f"Đọc config từ: {config_path}")
    print(f"WEBSOCKET_URL = {info['url']}")
    print(f"DEVICE_ID     = {info['device_id']}")
    print(f"CLIENT_ID     = {info['client_id']}\n")

    try:
        import websockets
    except ImportError:
        sys.exit(
            "Thiếu thư viện 'websockets'. Chạy script này bằng:\n"
            "  uv run python watch_protocol.py\n"
            "(trong thư mục py-xiaozhi, để dùng đúng venv đã cài)"
        )

    headers = {
        "Authorization": f"Bearer {info['token']}",
        "Protocol-Version": "1",
        "Device-Id": info["device_id"],
        "Client-Id": info["client_id"],
    }

    ssl_context = None
    if info["url"].startswith("wss://"):
        ssl_context = ssl._create_unverified_context()

    session_id_holder: dict = {"session_id": ""}

    print("Đang kết nối...")
    try:
        async with websockets.connect(
            info["url"],
            additional_headers=headers,
            ssl=ssl_context,
            open_timeout=10,
        ) as ws:
            print("Đã mở WebSocket. Gửi hello...\n")

            hello = {
                "type": "hello",
                "version": 1,
                "features": {"mcp": True},
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",
                    "sample_rate": 16000,
                    "channels": 1,
                    "frame_duration": 20,
                },
            }
            print(f"[{ts()}] ➡ Gửi hello:")
            print(pretty(hello))
            await ws.send(json.dumps(hello))

            # Chờ server hello để lấy session_id (nếu có) rồi mới cho gõ.
            first = await ws.recv()
            if isinstance(first, str):
                data = json.loads(first)
                print(f"\n[{ts()}] ⬅ Server hello:")
                print(pretty(data))
                if data.get("session_id"):
                    session_id_holder["session_id"] = data["session_id"]

            print(
                "\nĐã bắt tay xong. Gõ một câu bất kỳ rồi Enter để thử gửi "
                "(không có audio thật đi kèm, chỉ để xem server phản ứng "
                "thế nào). Ctrl+C để thoát.\n"
            )
            print("> ", end="", flush=True)

            await asyncio.gather(receiver(ws), sender(ws, session_id_holder))

    except KeyboardInterrupt:
        print("\nĐã thoát.")
    except Exception as e:
        print(f"\nLỗi kết nối: {e}")


if __name__ == "__main__":
    asyncio.run(main())
