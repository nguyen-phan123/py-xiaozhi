import asyncio
import json
import logging
import ssl

import websockets

from src.constants.constants import AudioConfig
from src.logging import get_logger
from src.protocols.protocol import Protocol
from src.utils.config_manager import get_config

# Máy chủ có thể dùng chứng chỉ tự ký, tạm thời bỏ qua xác minh chứng chỉ client
# để tránh lỗi kết nối do chứng chỉ SSL không chuẩn trong môi trường thực tế
ssl_context = ssl._create_unverified_context()

logger = get_logger()


class WebsocketProtocol(Protocol):
    def __init__(self):
        super().__init__()
        # Lấy instance của ConfigManager
        self.config = get_config()
        self.websocket = None
        self.connected = False
        self.hello_received = None  # Đặt là None khi khởi tạo
        # Tham chiếu tác vụ xử lý tin nhắn, tiện cho việc hủy khi đóng
        self._message_task = None

        self.WEBSOCKET_URL = self.config.get_config(
            "SYSTEM_OPTIONS.NETWORK.WEBSOCKET_URL"
        )
        access_token = self.config.get_config(
            "SYSTEM_OPTIONS.NETWORK.WEBSOCKET_ACCESS_TOKEN"
        )
        device_id = self.config.get_config("SYSTEM_OPTIONS.DEVICE_ID")
        client_id = self.config.get_config("SYSTEM_OPTIONS.CLIENT_ID")

        self.HEADERS = {
            "Authorization": f"Bearer {access_token}",
            "Protocol-Version": "1",
            "Device-Id": device_id,  # Lấy địa chỉ MAC của thiết bị
            "Client-Id": client_id,
        }

    async def connect(self) -> bool:
        """
        Kết nối đến máy chủ WebSocket.
        """
        if self._is_closing:
            logger.warning("Kết nối đang đóng, hủy lần thử kết nối mới")
            return False

        try:
            # Tạo Event khi kết nối, đảm bảo trong đúng event loop
            self.hello_received = asyncio.Event()

            # Xác định xem có nên dùng SSL không
            current_ssl_context = None
            if self.WEBSOCKET_URL.startswith("wss://"):
                current_ssl_context = ssl_context

            # Thiết lập kết nối WebSocket (tương thích các phiên bản Python khác nhau)
            try:
                # Cách viết mới (trong Python 3.11+)
                self.websocket = await websockets.connect(
                    uri=self.WEBSOCKET_URL,
                    ssl=current_ssl_context,
                    additional_headers=self.HEADERS,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=10,
                    open_timeout=5,
                    max_size=10 * 1024 * 1024,
                    compression=None,
                    proxy=None,
                )
            except TypeError:
                # Cách viết cũ (trong các phiên bản Python cũ hơn)
                self.websocket = await websockets.connect(
                    self.WEBSOCKET_URL,
                    ssl=current_ssl_context,
                    extra_headers=self.HEADERS,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=10,
                    open_timeout=5,
                    max_size=10 * 1024 * 1024,
                    compression=None,
                )

            # Khởi động vòng lặp xử lý tin nhắn (lưu tham chiếu task, có thể hủy khi đóng)
            self._message_task = asyncio.create_task(self._message_handler())

            # Khởi động giám sát kết nối
            self._start_connection_monitor()

            # Gửi tin nhắn hello của client
            hello_message = {
                "type": "hello",
                "version": 1,
                "features": {
                    "mcp": True,
                },
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",
                    "sample_rate": AudioConfig.INPUT_SAMPLE_RATE,
                    "channels": AudioConfig.CHANNELS,
                    "frame_duration": AudioConfig.FRAME_DURATION,
                },
            }
            await self.send_text(json.dumps(hello_message))

            # Đợi phản hồi hello từ máy chủ
            try:
                await asyncio.wait_for(self.hello_received.wait(), timeout=10.0)
                self.connected = True
                self._reconnect_attempts = 0  # Đặt lại số lần thử kết nối lại
                logger.info("Đã kết nối đến server WebSocket")

                # Thông báo thay đổi trạng thái kết nối
                if self._on_connection_state_changed:
                    self._on_connection_state_changed(True, "Kết nối thành công")

                return True
            except asyncio.TimeoutError:
                logger.error("Chờ phản hồi hello từ server quá thời gian (timeout)")
                await self._do_cleanup()
                if self._on_network_error:
                    await self._on_network_error("Hết thời gian chờ phản hồi")
                return False

        except Exception as e:
            logger.error(f"Kết nối WebSocket thất bại: {e}", exc_info=True)
            await self._do_cleanup()
            if self._on_network_error:
                await self._on_network_error(f"Không thể kết nối đến server: {str(e)}")
            return False

    # ============ Triển khai template method ============

    @property
    def _monitor_interval(self) -> float:
        """Khoảng thời gian kiểm tra giám sát kết nối WSS (giây)."""
        return 5.0

    def _is_connected(self) -> bool:
        """Kiểm tra kết nối WebSocket có còn sống hay không."""
        if not self.websocket:
            return False
        return self.websocket.close_code is None

    async def _do_cleanup(self):
        """Dọn dẹp tài nguyên đặc thù của giao thức WebSocket.

        Dọn dẹp tác vụ xử lý tin nhắn, tác vụ heartbeat, kết nối WebSocket và timestamp heartbeat.
        Không chịu trách nhiệm hủy tác vụ giám sát kết nối (lớp cơ sở _handle_connection_loss đảm nhận).
        """
        # Hủy tác vụ xử lý tin nhắn
        if self._message_task and not self._message_task.done():
            self._message_task.cancel()
            try:
                await self._message_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"Ngoại lệ khi chờ hủy tác vụ tin nhắn: {e}")
        self._message_task = None

        # Đóng kết nối WebSocket
        if self.websocket and self.websocket.close_code is None:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(f"Lỗi khi đóng kết nối WebSocket: {e}", exc_info=True)

        self.websocket = None

    def get_connection_info(self) -> dict:
        """Lấy thông tin kết nối WSS.

        Returns:
            dict: Dictionary chứa thông tin trạng thái kết nối, số lần kết nối lại, v.v.
        """
        info = super().get_connection_info()
        info.update(
            {
                "connected": self.connected,
                "websocket_closed": (
                    self.websocket.close_code is not None if self.websocket else True
                ),
                "websocket_url": self.WEBSOCKET_URL,
            }
        )
        return info

    async def _message_handler(self):
        """
        Xử lý tin nhắn WebSocket nhận được.
        """
        try:
            async for message in self.websocket:
                if self._is_closing:
                    break

                try:
                    if isinstance(message, str):
                        try:
                            data = json.loads(message)
                            msg_type = data.get("type")
                            if msg_type == "hello":
                                # Xử lý tin nhắn hello từ máy chủ
                                await self._handle_server_hello(data)
                            else:
                                if self._on_incoming_json:
                                    self._on_incoming_json(data)
                        except json.JSONDecodeError as e:
                            logger.error(f"Tin nhắn JSON không hợp lệ: {message}, lỗi: {e}", exc_info=True)
                    elif isinstance(message, bytes):
                        # Tin nhắn nhị phân, có thể là âm thanh
                        if self._on_incoming_audio:
                            self._on_incoming_audio(message)
                except Exception as e:
                    # Xử lý lỗi của từng tin nhắn đơn lẻ nhưng tiếp tục xử lý các tin nhắn khác
                    logger.error(f"Lỗi khi xử lý tin nhắn: {e}", exc_info=True)
                    continue

        except asyncio.CancelledError:
            logger.debug("Tác vụ xử lý tin nhắn đã bị hủy")
            return
        except websockets.ConnectionClosedOK as e:
            if not self._is_closing:
                logger.info(f"Kết nối WebSocket đã được server đóng bình thường: {e}")
                await self._handle_connection_loss(
                    f"Server đóng kết nối: {e.code}", clean=True
                )
        except websockets.ConnectionClosedError as e:
            if not self._is_closing:
                logger.info(f"Kết nối WebSocket bị đóng do lỗi: {e}")
                await self._handle_connection_loss(f"Lỗi kết nối: {e.code} {e.reason}")
        except websockets.InvalidState as e:
            logger.error(f"Trạng thái WebSocket không hợp lệ: {e}", exc_info=True)
            await self._handle_connection_loss("Trạng thái kết nối bất thường")
        except ConnectionResetError:
            logger.warning("Kết nối bị reset")
            await self._handle_connection_loss("Kết nối bị reset")
        except OSError as e:
            logger.error(f"Lỗi I/O mạng: {e}", exc_info=True)
            await self._handle_connection_loss("Lỗi I/O mạng")
        except Exception as e:
            logger.error(f"Ngoại lệ vòng lặp xử lý tin nhắn: {e}", exc_info=True)
            await self._handle_connection_loss(f"Xử lý message xảy ra ngoại lệ: {str(e)}")

    async def send_audio(self, data: bytes):
        """
        Gửi dữ liệu âm thanh.
        """
        if not self.is_audio_channel_opened():
            return

        try:
            await self.websocket.send(data)
        except websockets.ConnectionClosedOK as e:
            # Máy chủ thu hồi phiên bình thường (như đóng sau khi TTS kết thúc), không coi là lỗi mạng
            logger.info(f"Kết nối đã được server đóng bình thường khi gửi âm thanh: {e}")
            await self._handle_connection_loss(
                f"Server đóng kết nối khi gửi âm thanh: {e.code}", clean=True
            )
        except websockets.ConnectionClosedError as e:
            logger.warning(f"Kết nối bị đóng bất thường khi gửi âm thanh: {e}")
            await self._handle_connection_loss(f"Gửi âm thanh thất bại: {e.code} {e.reason}")
        except Exception as e:
            logger.error(f"Gửi dữ liệu âm thanh thất bại: {e}", exc_info=True)
            # Không gọi callback lỗi mạng ở đây, hãy để bộ xử lý kết nối xử lý
            await self._handle_connection_loss(f"Gửi âm thanh xảy ra ngoại lệ: {str(e)}")

    async def send_text(self, message: str):
        """
        Gửi tin nhắn văn bản.
        """
        if not self.websocket or self._is_closing:
            logger.warning("WebSocket chưa kết nối hoặc đang đóng, không thể gửi tin nhắn")
            return

        try:
            close_code = self.websocket.close_code
        except Exception:
            close_code = None
        if close_code is not None:
            # 1000/1001/1005 được coi là đóng bình thường (máy chủ thu hồi phiên)
            clean = close_code in (1000, 1001, 1005)
            logger.log(
                logging.INFO if clean else logging.WARNING,
                f"WebSocket đã đóng (code={close_code}), bỏ qua gửi văn bản",
            )
            if self.connected:
                await self._handle_connection_loss(
                    f"Gửi văn bản thất bại: Kết nối đã đóng {close_code}", clean=clean
                )
            return

        try:
            await self.websocket.send(message)
        except websockets.ConnectionClosedOK as e:
            # Máy chủ thu hồi phiên bình thường, không coi là lỗi mạng
            logger.info(f"Kết nối đã được server đóng bình thường khi gửi văn bản: {e}")
            if self.connected and not self._is_closing:
                await self._handle_connection_loss(
                    f"Server đóng kết nối khi gửi văn bản: {e.code}", clean=True
                )
        except websockets.ConnectionClosedError as e:
            logger.warning(f"Kết nối bị đóng bất thường khi gửi văn bản: {e}")
            if self.connected and not self._is_closing:
                await self._handle_connection_loss(
                    f"Lỗi gửi văn bản: {e.code} {e.reason}"
                )
        except Exception as e:
            logger.error(f"Gửi tin nhắn văn bản thất bại: {e}", exc_info=True)
            if self.connected and not self._is_closing:
                await self._handle_connection_loss(f"Gửi văn bản xảy ra ngoại lệ: {str(e)}")

    def is_audio_channel_opened(self) -> bool:
        """Kiểm tra kênh âm thanh đã mở hay chưa.

        Kiểm tra chính xác hơn trạng thái kết nối, bao gồm trạng thái thực tế của WebSocket
        """
        if not self.websocket or not self.connected or self._is_closing:
            return False

        # Kiểm tra trạng thái thực tế của WebSocket
        try:
            return self.websocket.close_code is None
        except Exception:
            return False

    async def open_audio_channel(self) -> bool:
        """Thiết lập kết nối WebSocket.

        Nếu chưa kết nối thì tạo kết nối WebSocket mới
        Returns:
            bool: Kết nối có thành công hay không
        """
        if not self.is_audio_channel_opened():
            return await self.connect()
        return True

    async def _handle_server_hello(self, data: dict):
        """
        Xử lý tin nhắn hello từ máy chủ.
        """
        try:
            # Xác thực phương thức truyền tải
            transport = data.get("transport")
            if not transport or transport != "websocket":
                logger.error(f"Phương thức truyền tải không được hỗ trợ: {transport}")
                return

            # Thiết lập event nhận hello
            self.hello_received.set()

            # Thông báo kênh âm thanh đã mở
            if self._on_audio_channel_opened:
                await self._on_audio_channel_opened()

            logger.info("Xử lý tin nhắn hello từ server thành công")

        except Exception as e:
            logger.error(f"Lỗi khi xử lý tin nhắn hello từ server: {e}", exc_info=True)
            if self._on_network_error:
                await self._on_network_error(f"Xử lý phản hồi từ server thất bại: {str(e)}")

    async def close_audio_channel(self):
        """
        Đóng kênh âm thanh.
        """
        self._is_closing = True

        try:
            self.connected = False

            # Hủy tác vụ giám sát kết nối (lớp cơ sở quản lý)
            await self._cancel_monitor_task()

            # Dọn dẹp đặc thù theo giao thức
            await self._do_cleanup()

            if self._on_audio_channel_closed:
                await self._on_audio_channel_closed()

        except Exception as e:
            logger.error(f"Đóng kênh âm thanh thất bại: {e}", exc_info=True)
        finally:
            self._is_closing = False
