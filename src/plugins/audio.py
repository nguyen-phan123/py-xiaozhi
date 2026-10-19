"""Plugin Audio.

Chịu trách nhiệm thu âm, mã hóa, phát và gửi âm thanh.
AudioCodec được phát qua Events.AUDIO_CODEC_CHANGED, không liên kết trực tiếp với MusicPlayer.
"""

import asyncio
import os
from typing import TYPE_CHECKING

from src.audio_codecs.audio_codec import AudioCodec
from src.logging import get_logger
from src.plugins.base import Plugin

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext

logger = get_logger()

MAX_CONCURRENT_AUDIO_SENDS = 4


class AudioPlugin(Plugin):
    name = "audio"
    priority = 10  # Mức độ ưu tiên cao nhất, các plugin khác phụ thuộc vào audio_codec

    def __init__(self) -> None:
        super().__init__()
        self.codec: AudioCodec | None = None
        self._send_sem = asyncio.Semaphore(MAX_CONCURRENT_AUDIO_SENDS)
        self._in_silence_period = False

    async def setup(self, ctx: "PluginContext", cmd: "PluginCommands") -> None:
        await super().setup(ctx, cmd)

        if os.getenv("XIAOZHI_DISABLE_AUDIO") == "1":
            logger.warning("XIAOZHI_DISABLE_AUDIO=1, audio plugin chạy ở chế độ bị vô hiệu hóa")
            return

        try:
            self.codec = AudioCodec()
            await self.codec.initialize()
            self.codec.set_encoded_callback(self._on_encoded_audio)

            from src.core.event_bus import Events

            ctx.event_bus.on(Events.CONFIG_CHANGED, self._on_config_changed)
            ctx.event_bus.on(
                Events.AUDIO_DEVICES_REFRESH_REQUEST, self._on_devices_refresh_request
            )
            # codec được phát lại trong start(): MusicPlayer đăng ký EventBus trong McpPlugin.setup

        except Exception as e:
            logger.error(f"Khởi tạo audio plugin thất bại: {e}", exc_info=True)
            self.codec = None
            self.mark_failed()
            raise

    async def start(self) -> None:
        await super().start()
        if self.codec and not self.failed:
            await self._publish_audio_codec(self.codec)

    async def _publish_audio_codec(self, codec) -> None:
        """Phát instance AudioCodec hoặc None tới các subscriber (như MusicPlayer)."""
        if not self._ctx or not self._ctx.event_bus:
            logger.warning(
                "Không thể phát AUDIO_CODEC_CHANGED: PluginContext / EventBus chưa sẵn sàng"
            )
            return
        from src.core.event_bus import Events

        try:
            await self._ctx.event_bus.emit(Events.AUDIO_CODEC_CHANGED, codec)
        except Exception as e:
            logger.warning(f"Phát AUDIO_CODEC_CHANGED thất bại: {e}", exc_info=True)

    async def _on_config_changed(self, data=None):
        """Tải lại thiết bị âm thanh khi cấu hình thay đổi (bao gồm quét lại PortAudio)."""
        if self.codec:
            logger.info("AudioPlugin: Nhận được sự kiện thay đổi cấu hình, đang tải lại thiết bị âm thanh")
            await self.codec.reload_devices(reenumerate=True)

    async def _on_devices_refresh_request(self, data=None):
        """Trang cài đặt yêu cầu làm mới danh sách thiết bị: Dừng luồng → Quét lại → Mở lại luồng.

        payload có thể là asyncio.Future, sau khi hoàn thành sẽ gọi set_result(kết quả list_audio_devices).
        """
        from src.utils.audio_utils import list_audio_devices, refresh_portaudio_devices

        future = data if isinstance(data, asyncio.Future) else None
        result = {"input": [], "output": []}
        try:
            if self.codec:
                # Chỉ sau khi dừng luồng mới có thể _terminate PortAudio an toàn
                self.codec.stop_streams_for_enumeration()
                refresh_portaudio_devices(reinitialize=True)
                result = list_audio_devices(include_virtual=True)
                # Mở lại luồng theo cấu hình hiện tại (khớp tên có thể trỏ tới index mới)
                ok = await self.codec.reload_devices(reenumerate=False)
                if not ok:
                    logger.error("AudioPlugin: Mở lại luồng âm thanh sau khi làm mới thiết bị thất bại")
            else:
                # Khi không có codec (vô hiệu hóa audio) vẫn cố gắng liệt kê thiết bị để trang cài đặt hiển thị
                refresh_portaudio_devices(reinitialize=True)
                result = list_audio_devices(include_virtual=True)
            logger.info(
                "AudioPlugin: Làm mới thiết bị hoàn tất "
                f"in={len(result.get('input', []))} out={len(result.get('output', []))}"
            )
        except Exception as e:
            logger.error(f"AudioPlugin: Làm mới thiết bị thất bại: {e}", exc_info=True)
        finally:
            if future is not None and not future.done():
                future.set_result(result)

    async def on_device_state_changed(self, state):
        """
        Xử lý khi trạng thái thiết bị thay đổi.
        """
        if not self.codec:
            return

        from src.constants.constants import DeviceState

        if state == DeviceState.LISTENING:
            self._in_silence_period = True
            try:
                await asyncio.sleep(0.2)
            finally:
                self._in_silence_period = False

    async def on_incoming_json(self, message) -> None:
        """
        Xử lý sự kiện TTS.
        """
        if not isinstance(message, dict):
            return

        try:
            if message.get("type") == "tts":
                state = message.get("state")
                if state == "start":
                    if self._music_parallel_enabled():
                        logger.debug("TTS bắt đầu (chế độ song song): nhạc tiếp tục phát, tự động giảm âm lượng")
                    else:
                        await self._pause_music_for_tts()
                elif state == "stop":
                    # Chế độ song song cũng gửi khôi phục: phương án dự phòng khi bài hát phát trong lúc TTS bị tạm dừng bởi TTS
                    await self._resume_music_after_tts()
        except Exception as e:
            logger.error(f"Xử lý sự kiện TTS thất bại: {e}", exc_info=True)

    def _music_parallel_enabled(self) -> bool:
        """Xác định phát song song: Khi AEC engine sẵn sàng và cấu hình cho phép, TTS không tạm dừng nhạc.

        Khi engine bị bypass (thiếu thư viện/tự vô hiệu hóa do lỗi liên tiếp) sẽ tự động fallback về chiến lược tạm dừng,
        tránh việc phát song song không có khử tiếng vọng làm hỏng nhận dạng giọng nói.
        """
        try:
            config = self._ctx.get_config()
            if not bool(config.get_config("AEC_OPTIONS.MUSIC_PARALLEL", True)):
                return False
            return bool(self.codec and self.codec.aec_active)
        except Exception:
            return False

    async def on_incoming_audio(self, data: bytes) -> None:
        """
        Nhận và phát dữ liệu âm thanh.
        """
        if self.codec:
            try:
                await self.codec.write_audio(data)
            except Exception as e:
                logger.debug(f"Ghi dữ liệu âm thanh thất bại: {e}")

    async def _pause_music_for_tts(self):
        """Tạm dừng nhạc khi TTS bắt đầu (TTS/nhạc chia queue trộn âm riêng, không mất khung hình; phần nhạc còn lại giảm dần tự nhiên)."""
        try:
            from src.core.event_bus import Events
            from src.mcp.tools.music.events import MusicControlRequest

            logger.info("TTS bắt đầu, gửi yêu cầu tạm dừng nhạc")
            await self._ctx.event_bus.emit(
                Events.MUSIC_PAUSE_REQUEST, MusicControlRequest(source="tts")
            )
        except Exception as e:
            logger.warning(f"Gửi yêu cầu tạm dừng nhạc thất bại: {e}", exc_info=True)

    async def _resume_music_after_tts(self):
        """Khôi phục nhạc sau khi TTS kết thúc (trong chế độ song song chỉ mang tính dự phòng, phần lớn thời gian không thực sự tạm dừng)."""
        try:
            from src.core.event_bus import Events
            from src.mcp.tools.music.events import MusicControlRequest

            log = logger.debug if self._music_parallel_enabled() else logger.info
            log("TTS phát xong, gửi yêu cầu tiếp tục phát nhạc")
            await self._ctx.event_bus.emit(
                Events.MUSIC_RESUME_REQUEST, MusicControlRequest(source="tts")
            )
        except Exception as e:
            logger.error(f"Gửi yêu cầu tiếp tục phát nhạc thất bại: {e}", exc_info=True)

    def register_resources(self, pool) -> None:
        codec = self.codec
        if codec:

            async def _cleanup():
                """Dọn dẹp hoàn toàn audio codec: thông báo subscriber xóa codec trước, sau đó close."""
                import gc

                try:
                    # Music khi nhận được None sẽ tự động stop; việc detach hoàn toàn do mcp/container đảm nhận
                    await self._publish_audio_codec(None)
                except Exception as e:
                    logger.debug(f"Phát xóa codec thất bại: {e}", exc_info=True)
                gc.collect()
                await codec.close()

            pool.register("audio.codec", _cleanup)

    def _on_encoded_audio(self, encoded_data: bytes) -> None:
        """
        Callback mã hóa âm thanh (được gọi từ audio thread).
        """
        try:
            if not self._cmd:
                return
            self._cmd.schedule_command_nowait(self._send_audio_async, encoded_data)
        except Exception as e:
            logger.error(f"Điều phối gửi âm thanh thất bại: {e}", exc_info=True)

    async def _send_audio_async(self, encoded_data: bytes) -> None:
        """
        Gửi dữ liệu âm thanh bất đồng bộ.
        """
        async with self._send_sem:
            try:
                if not self._ctx.is_audio_channel_opened():
                    return
                if self._should_send_microphone_audio():
                    await self._cmd.send_audio(encoded_data)
            except Exception as e:
                logger.error(f"Gửi dữ liệu âm thanh thất bại: {e}", exc_info=True)

    def _should_send_microphone_audio(self) -> bool:
        """
        Kiểm tra xem có nên gửi âm thanh microphone không.
        """
        try:
            if self._in_silence_period:
                return False
            return self._ctx.should_capture_audio()
        except Exception as e:
            logger.warning(
                f"Kiểm tra có gửi âm thanh mic thất bại, mặc định không gửi: {e}", exc_info=True
            )
            return False
