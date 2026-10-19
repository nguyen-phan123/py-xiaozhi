import asyncio
import json

from src.constants.constants import AbortReason, ListeningMode
from src.logging import get_logger

logger = get_logger()


class Protocol:
    def __init__(self):
        self.session_id = ""
        # Khởi tạo hàm callback là None
        self._on_incoming_json = None
        self._on_incoming_audio = None
        self._on_audio_channel_opened = None
        self._on_audio_channel_closed = None
        self._on_network_error = None
        # Thêm callback thay đổi trạng thái kết nối
        self._on_connection_state_changed = None
        self._on_reconnecting = None

        # Trạng thái kết nối và tự động kết nối lại (dùng chung, chuyển từ lớp con lên)
        self._is_closing = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5  # Mặc định thử kết nối lại 5 lần
        self._auto_reconnect_enabled = False  # Mặc định tắt tự động kết nối lại
        self._connection_monitor_task = None

    def on_incoming_json(self, callback):
        """
        Thiết lập hàm callback nhận tin nhắn JSON.
        """
        self._on_incoming_json = callback

    def on_incoming_audio(self, callback):
        """
        Thiết lập hàm callback nhận dữ liệu âm thanh.
        """
        self._on_incoming_audio = callback

    def on_audio_channel_opened(self, callback):
        """
        Thiết lập hàm callback khi kênh âm thanh mở.
        """
        self._on_audio_channel_opened = callback

    def on_audio_channel_closed(self, callback):
        """
        Thiết lập hàm callback khi kênh âm thanh đóng.
        """
        self._on_audio_channel_closed = callback

    def on_network_error(self, callback):
        """
        Thiết lập hàm callback xử lý lỗi mạng.
        """
        self._on_network_error = callback

    def on_connection_state_changed(self, callback):
        """Thiết lập hàm callback khi trạng thái kết nối thay đổi.

        Args:
            callback: Hàm callback, nhận các tham số (connected: bool, reason: str)
        """
        self._on_connection_state_changed = callback

    def on_reconnecting(self, callback):
        """Thiết lập hàm callback cho các lần thử kết nối lại.

        Args:
            callback: Hàm callback, nhận các tham số (attempt: int, max_attempts: int)
        """
        self._on_reconnecting = callback

    async def send_text(self, message):
        """
        Phương thức trừu tượng gửi tin nhắn văn bản, cần được triển khai trong lớp con.
        """
        raise NotImplementedError("Phương thức send_text phải do lớp con triển khai")

    async def send_audio(self, data: bytes):
        """
        Phương thức trừu tượng gửi dữ liệu âm thanh, cần được triển khai trong lớp con.
        """
        raise NotImplementedError("Phương thức send_audio phải do lớp con triển khai")

    def is_audio_channel_opened(self) -> bool:
        """
        Phương thức trừu tượng kiểm tra kênh âm thanh có mở hay không, cần được triển khai trong lớp con.
        """
        raise NotImplementedError("Phương thức is_audio_channel_opened phải do lớp con triển khai")

    async def open_audio_channel(self) -> bool:
        """
        Phương thức trừu tượng mở kênh âm thanh, cần được triển khai trong lớp con.
        """
        raise NotImplementedError("Phương thức open_audio_channel phải do lớp con triển khai")

    async def close_audio_channel(self):
        """
        Phương thức trừu tượng đóng kênh âm thanh, cần được triển khai trong lớp con.
        """
        raise NotImplementedError("Phương thức close_audio_channel phải do lớp con triển khai")

    async def send_abort_speaking(self, reason):
        """
        Gửi tin nhắn hủy bỏ giọng nói (abort speaking).
        """
        message = {"session_id": self.session_id, "type": "abort"}
        if reason == AbortReason.WAKE_WORD_DETECTED:
            message["reason"] = "wake_word_detected"
        await self.send_text(json.dumps(message))

    async def send_wake_word_detected(self, wake_word):
        """
        Gửi tin nhắn phát hiện từ đánh thức (wake word).
        """
        message = {
            "session_id": self.session_id,
            "type": "listen",
            "state": "detect",
            "text": wake_word,
        }
        await self.send_text(json.dumps(message))

    async def send_start_listening(self, mode):
        """
        Gửi tin nhắn bắt đầu lắng nghe.
        """
        mode_map = {
            ListeningMode.REALTIME: "realtime",
            ListeningMode.AUTO_STOP: "auto",
            ListeningMode.MANUAL: "manual",
        }
        message = {
            "session_id": self.session_id,
            "type": "listen",
            "state": "start",
            "mode": mode_map[mode],
        }
        await self.send_text(json.dumps(message))

    async def send_stop_listening(self):
        """
        Gửi tin nhắn dừng lắng nghe.
        """
        message = {"session_id": self.session_id, "type": "listen", "state": "stop"}
        await self.send_text(json.dumps(message))

    async def send_iot_descriptors(self, descriptors):
        """
        Gửi thông tin mô tả thiết bị IoT.
        """
        try:
            # Phân tích dữ liệu descriptor
            if isinstance(descriptors, str):
                descriptors_data = json.loads(descriptors)
            else:
                descriptors_data = descriptors

            # Kiểm tra xem có phải là mảng không
            if not isinstance(descriptors_data, list):
                logger.error("IoT descriptors should be an array")
                return

            # Gửi tin nhắn riêng cho từng descriptor
            for i, descriptor in enumerate(descriptors_data):
                if descriptor is None:
                    logger.error(f"Failed to get IoT descriptor at index {i}")
                    continue

                message = {
                    "session_id": self.session_id,
                    "type": "iot",
                    "update": True,
                    "descriptors": [descriptor],
                }

                try:
                    await self.send_text(json.dumps(message))
                except Exception as e:
                    logger.error(
                        f"Failed to send JSON message for IoT descriptor "
                        f"at index {i}: {e}"
                    )
                    continue

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse IoT descriptors: {e}", exc_info=True)
            return

    async def send_iot_states(self, states):
        """
        Gửi thông tin trạng thái thiết bị IoT.
        """
        if isinstance(states, str):
            states_data = json.loads(states)
        else:
            states_data = states

        message = {
            "session_id": self.session_id,
            "type": "iot",
            "update": True,
            "states": states_data,
        }
        await self.send_text(json.dumps(message))

    async def send_mcp_message(self, payload):
        """
        Gửi tin nhắn MCP.
        """
        if isinstance(payload, str):
            payload_data = json.loads(payload)
        else:
            payload_data = payload

        message = {
            "session_id": self.session_id,
            "type": "mcp",
            "payload": payload_data,
        }

        await self.send_text(json.dumps(message))

    # ============ Kiểm tra trạng thái kết nối (template method, lớp con triển khai) ============

    def _is_connected(self) -> bool:
        """Kiểm tra kết nối có còn hoạt động hay không.

        Lớp con bắt buộc phải triển khai phương thức này, trả về trạng thái sức khỏe của kết nối giao thức hiện tại.

        Returns:
            bool: Trả về True nếu kết nối còn sống, ngược lại trả về False
        """
        raise NotImplementedError("Phương thức _is_connected phải do lớp con triển khai")

    # ============ Dọn dẹp đặc thù theo giao thức (template method, lớp con triển khai) ============

    async def _do_cleanup(self):
        """Dọn dẹp tài nguyên đặc thù của giao thức (không bao gồm trạng thái dùng chung và tác vụ giám sát).

        Khi lớp con triển khai phương thức này cần:
        - Đóng kết nối mạng đặc thù của giao thức (socket / websocket / mqtt client v.v.)
        - Hủy tác vụ nền đặc thù của giao thức (heartbeat, xử lý tin nhắn v.v.)
        - Đặt lại timestamp/trạng thái đặc thù của giao thức

        Không thực hiện trong phương thức này:
        - Đặt self.connected = False (lớp cơ sở _handle_connection_loss đảm nhận)
        - Hủy self._connection_monitor_task (lớp cơ sở _handle_connection_loss đảm nhận)
        """
        raise NotImplementedError("Phương thức _do_cleanup phải do lớp con triển khai")

    # ============ Giám sát kết nối (dùng chung, lớp con có thể override _monitor_interval) ============

    @property
    def _monitor_interval(self) -> float:
        """Khoảng thời gian kiểm tra giám sát kết nối (giây), lớp con có thể override."""
        return 5.0

    def _start_connection_monitor(self):
        """Khởi động tác vụ nền giám sát sức khỏe kết nối."""
        if (
            self._connection_monitor_task is None
            or self._connection_monitor_task.done()
        ):
            self._connection_monitor_task = asyncio.create_task(
                self._connection_monitor()
            )

    async def _connection_monitor(self):
        """Coroutine giám sát trạng thái sức khỏe kết nối.

        Lặp lại kiểm tra giá trị trả về của self._is_connected(),
        nếu phát hiện mất kết nối thì gọi self._handle_connection_loss().
        """
        try:
            while not self._is_closing:
                await asyncio.sleep(self._monitor_interval)

                if not self._is_connected():
                    logger.warning("Phát hiện kết nối đã bị ngắt")
                    await self._handle_connection_loss("Kiểm tra kết nối thất bại")
                    break

        except asyncio.CancelledError:
            logger.debug("Tác vụ giám sát kết nối đã bị hủy")
        except Exception as e:
            logger.error(f"Ngoại lệ giám sát kết nối: {e}", exc_info=True)

    # ============ Tự động kết nối lại (dùng chung) ============

    def enable_auto_reconnect(self, enabled: bool = True, max_attempts: int = 5):
        """Bật hoặc tắt tính năng tự động kết nối lại.

        Args:
            enabled: Có bật tự động kết nối lại hay không
            max_attempts: Số lần thử kết nối lại tối đa
        """
        self._auto_reconnect_enabled = enabled
        if enabled:
            self._max_reconnect_attempts = max_attempts
            logger.info(f"Bật tự động kết nối lại, số lần thử tối đa: {max_attempts}")
        else:
            self._max_reconnect_attempts = 0
            logger.info("Tắt tự động kết nối lại")

    async def _handle_connection_loss(self, reason: str, *, clean: bool = False):
        """Xử lý mất kết nối (logic dùng chung).

        Quy trình:
        1. Cập nhật trạng thái kết nối
        2. Hủy tác vụ giám sát kết nối
        3. Gọi _do_cleanup() của lớp con để dọn dẹp tài nguyên đặc thù
        4. Thông báo cho observer (thay đổi trạng thái, đóng kênh âm thanh)
        5. Quyết định có tự động kết nối lại hay không dựa trên cấu hình

        Args:
            clean: Đóng bình thường từ phía máy chủ (như kết thúc phiên). Chỉ thu hồi kênh,
                   không kích hoạt kết nối lại tự động, cũng không báo cáo lỗi mạng.
        """
        if clean:
            logger.info(f"Kết nối đã được server đóng bình thường: {reason}")
        else:
            logger.warning(f"Mất kết nối: {reason}")

        was_connected = self.connected
        self.connected = False

        # Hủy tác vụ giám sát kết nối
        await self._cancel_monitor_task()

        # Thông báo thay đổi trạng thái kết nối
        if self._on_connection_state_changed and was_connected:
            try:
                self._on_connection_state_changed(False, reason)
            except Exception as e:
                logger.error(f"Gọi callback thay đổi trạng thái kết nối thất bại: {e}", exc_info=True)

        # Gọi dọn dẹp đặc thù theo giao thức của lớp con
        await self._do_cleanup()

        # Thông báo đóng kênh âm thanh
        if self._on_audio_channel_closed:
            try:
                await self._on_audio_channel_closed()
            except Exception as e:
                logger.error(f"Gọi callback đóng kênh âm thanh thất bại: {e}", exc_info=True)

        # Máy chủ đóng bình thường: kết thúc phiên không coi là sự cố, không kết nối lại và không báo lỗi,
        # mở lại open_audio_channel theo nhu cầu trong lần tương tác kế tiếp
        if clean:
            return

        # Quyết định có thử tự động kết nối lại hay không dựa theo cấu hình
        if (
            not self._is_closing
            and self._auto_reconnect_enabled
            and self._reconnect_attempts < self._max_reconnect_attempts
        ):
            await self._attempt_reconnect(reason)
        else:
            if self._on_network_error:
                if (
                    self._auto_reconnect_enabled
                    and self._reconnect_attempts >= self._max_reconnect_attempts
                ):
                    await self._on_network_error(f"Mất kết nối và thử kết nối lại thất bại: {reason}")
                else:
                    await self._on_network_error(f"Mất kết nối: {reason}")

    async def _attempt_reconnect(self, original_reason: str):
        """Thử tự động kết nối lại (logic dùng chung).

        Sử dụng chiến lược exponential backoff, gọi connect() của lớp con để thực hiện kết nối thực tế.
        """
        self._reconnect_attempts += 1

        # Thông báo bắt đầu kết nối lại
        if self._on_reconnecting:
            try:
                self._on_reconnecting(
                    self._reconnect_attempts, self._max_reconnect_attempts
                )
            except Exception as e:
                logger.error(f"Gọi callback kết nối lại thất bại: {e}", exc_info=True)

        logger.info(
            f"Đang thử tự động kết nối lại ({self._reconnect_attempts}/{self._max_reconnect_attempts})"
        )

        # Chờ exponential backoff, tối đa 30 giây
        await asyncio.sleep(min(self._reconnect_attempts * 2, 30))

        try:
            success = await self.connect()
            if success:
                logger.info("Tự động kết nối lại thành công")
                if self._on_connection_state_changed:
                    self._on_connection_state_changed(True, "Kết nối lại thành công")
            else:
                logger.warning(
                    f"Tự động kết nối lại thất bại ({self._reconnect_attempts}/{self._max_reconnect_attempts})"
                )
                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    if self._on_network_error:
                        await self._on_network_error(
                            f"Kết nối lại thất bại, đã đạt số lần thử tối đa: {original_reason}"
                        )
        except Exception as e:
            logger.error(f"Lỗi trong quá trình kết nối lại: {e}", exc_info=True)
            if self._reconnect_attempts >= self._max_reconnect_attempts:
                if self._on_network_error:
                    await self._on_network_error(f"Ngoại lệ khi kết nối lại: {str(e)}")

    async def _cancel_monitor_task(self):
        """Hủy và chờ tác vụ giám sát kết nối hoàn tất."""
        if self._connection_monitor_task and not self._connection_monitor_task.done():
            self._connection_monitor_task.cancel()
            try:
                await self._connection_monitor_task
            except asyncio.CancelledError:
                pass

    def get_connection_info(self) -> dict:
        """Lấy thông tin kết nối (triển khai ở lớp cơ sở, lớp con có thể mở rộng).

        Returns:
            dict: Dictionary chứa thông tin trạng thái kết nối, số lần kết nối lại, v.v.
        """
        return {
            "is_closing": self._is_closing,
            "auto_reconnect_enabled": self._auto_reconnect_enabled,
            "reconnect_attempts": self._reconnect_attempts,
            "max_reconnect_attempts": self._max_reconnect_attempts,
        }
