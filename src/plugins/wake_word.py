"""Plugin từ đánh thức (wake word).

Phát hiện từ đánh thức và kích hoạt cuộc trò chuyện.
"""

from typing import TYPE_CHECKING, Optional

from src.constants.constants import AbortReason
from src.logging import get_logger
from src.plugins.base import Plugin

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext

logger = get_logger()


class WakeWordPlugin(Plugin):
    name = "wake_word"
    priority = 30
    requires = ["audio"]

    def __init__(self) -> None:
        super().__init__()
        self.detector = None

    @property
    def _audio_plugin(self):
        """Lấy AudioPlugin thông qua dependency injection."""
        return self.get_dep("audio")

    async def setup(self, ctx: "PluginContext", cmd: "PluginCommands") -> None:
        await super().setup(ctx, cmd)
        # Đăng ký sự kiện thay đổi cấu hình (nhẹ, chưa tải model)
        from src.core.event_bus import Events
        ctx.event_bus.on(Events.CONFIG_CHANGED, self._on_config_changed)

    async def _on_config_changed(self, data=None):
        """Tải lại mô hình từ đánh thức khi cấu hình thay đổi."""
        logger.info("WakeWordPlugin: Nhận được sự kiện thay đổi cấu hình, đang tải lại mô hình từ đánh thức")
        await self.reload_model()

    async def start(self) -> None:
        try:
            # Trì hoãn việc tải mô hình đến giai đoạn start(), tránh xung đột với DLL PortAudio trong setup()
            if self.detector is None:
                from src.audio_processing.wake_word_detect import WakeWordDetector

                self.detector = WakeWordDetector()
                if not await self.detector.initialize():
                    logger.info("Bộ nhận diện từ đánh thức chưa bật hoặc khởi tạo thất bại")
                    self.detector = None
                    return
                self.detector.on_detected(self._on_detected)
                self.detector.on_error = self._on_error

            if not self._audio_plugin or not self._audio_plugin.codec:
                logger.warning("Không tìm thấy audio_codec, không thể khởi động nhận diện từ đánh thức")
                return
            await self.detector.start(self._audio_plugin.codec)
        except ImportError as e:
            logger.error(f"Không thể import bộ nhận diện từ đánh thức: {e}", exc_info=True)
            self.detector = None
        except Exception as e:
            logger.error(f"Khởi động bộ nhận diện từ đánh thức thất bại: {e}", exc_info=True)

    async def stop(self) -> None:
        if self.detector:
            try:
                await self.detector.stop()
            except Exception as e:
                logger.warning(f"Dừng bộ nhận diện từ đánh thức thất bại: {e}", exc_info=True)

    def register_resources(self, pool) -> None:
        detector = self.detector
        if detector:
            pool.register("wake_word.detector", detector.shutdown)

    async def reload_model(self, model_path: Optional[str] = None) -> bool:
        """Hot-reload mô hình từ đánh thức.

        Args:
            model_path: Đường dẫn mô hình mới (vd: "models/en"). Nếu là None, đọc từ cấu hình.

        Returns:
            Liệu có tải lại thành công không
        """
        if not self.detector:
            logger.warning("Bộ nhận diện chưa khởi tạo, không thể hot-reload")
            return False

        try:
            return await self.detector.reload(model_path)
        except Exception as e:
            logger.error(f"Hot-reload mô hình từ đánh thức thất bại: {e}", exc_info=True)
            return False

    async def _on_detected(self, wake_word, full_text):
        """
        Callback khi phát hiện từ đánh thức.
        """
        try:
            if self._ctx.is_speaking():
                await self._cmd.abort_speaking(AbortReason.WAKE_WORD_DETECTED)
                if self._audio_plugin and self._audio_plugin.codec:
                    await self._audio_plugin.codec.clear_audio_queue()
            else:
                # Khởi động hội thoại tự động
                await self._cmd.connect_protocol()
                from src.constants.constants import ListeningMode

                mode = (
                    ListeningMode.REALTIME
                    if self._ctx.get_config().get_config("AEC_OPTIONS.ENABLED", True)
                    else ListeningMode.AUTO_STOP
                )
                await self._cmd.start_listening(mode)
        except Exception as e:
            logger.error(f"Xử lý nhận diện từ đánh thức thất bại: {e}", exc_info=True)

    async def _on_error(self, error):
        """
        Callback lỗi khi phát hiện từ đánh thức.
        """
        logger.error(f"Lỗi nhận diện từ đánh thức: {error}", exc_info=True)
