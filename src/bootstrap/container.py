"""Service Container (Bộ chứa dịch vụ).

Tích hợp các dịch vụ cốt lõi, đóng vai trò điều phối trung tâm của ứng dụng; session/health check/wiring/adapters đã được tách thành các sub-module.
"""

from src.bootstrap.adapters import PluginCommandsAdapter, PluginContextAdapter
from src.bootstrap.health import (
    DEGRADED_AUDIO_NOTICE,
    audio_is_fatal,
    check_critical_plugins,
)
from src.bootstrap.plugin_wiring import setup_plugins
from src.bootstrap.protocols import PluginCommands, PluginContext
from src.bootstrap.session import ConversationSession
from src.core.event_bus import EventBus, Events
from src.core.protocol_manager import ProtocolManager
from src.core.resource_pool import ResourcePool
from src.core.state_manager import StateManager
from src.core.task_manager import TaskManager
from src.logging import get_logger
from src.plugins.manager import PluginManager
from src.utils.config_manager import get_config

logger = get_logger()


class ServiceContainer:
    """Service Container (Bộ chứa dịch vụ).

    Nắm giữ các dịch vụ cốt lõi và ConversationSession, điều phối vòng đời run / shutdown.
    Các thao tác hội thoại đi qua ``self.session``; kiểm tra sức khỏe đi qua module ``health``.
    """

    def __init__(self):
        logger.debug("Khởi tạo ServiceContainer")

        self.config = get_config()

        try:
            aec_enabled = bool(self.config.get_config("AEC_OPTIONS.ENABLED", True))
        except Exception:
            aec_enabled = True

        self.event_bus = EventBus()
        self.state = StateManager(self.event_bus, aec_enabled=aec_enabled)
        self.tasks = TaskManager()
        # Protocol incoming tasks chạy qua TaskManager, tránh fire-and-forget
        self.protocol = ProtocolManager(self.event_bus, task_manager=self.tasks)
        self.plugins = PluginManager()
        self.resource_pool = ResourcePool()

        # Các dịch vụ dùng chung giữa các plugin do container nắm giữ (bind khi khởi động, unbind khi đóng)
        self.mcp_server = None
        self.music_player = None

        # Điều khiển phiên hội thoại (nghe/nói/ngắt lời/TTS loop)
        self.session = ConversationSession(
            state=self.state,
            protocol=self.protocol,
            plugins=self.plugins,
            event_bus=self.event_bus,
        )

        self._plugin_context: PluginContextAdapter | None = None
        self._plugin_commands: PluginCommandsAdapter | None = None

        self._mode: str = "cli"
        self._shutting_down = False
        # Chạy ở chế độ audio giáng cấp (XIAOZHI_DEGRADED_AUDIO=1 và audio thất bại)
        self._degraded_audio = False

    # -------------------------
    # Tạo adapter
    # -------------------------
    def create_plugin_context(self) -> PluginContext:
        if not self._plugin_context:
            self._plugin_context = PluginContextAdapter(self)
        return self._plugin_context

    def create_plugin_commands(self) -> PluginCommands:
        if not self._plugin_commands:
            self._plugin_commands = PluginCommandsAdapter(self)
        return self._plugin_commands

    # -------------------------
    # Vòng đời
    # -------------------------
    async def run(self, *, protocol: str = "websocket", mode: str = "gui") -> int:
        logger.info(f"Khởi động ServiceContainer, protocol={protocol}, mode={mode}")
        self._mode = mode

        try:
            self.tasks.initialize()
            self.protocol.set_task_manager(self.tasks)
            self.protocol.set_protocol(protocol)

            self.session.bind_events(self.event_bus)

            ctx = self.create_plugin_context()
            cmd = self.create_plugin_commands()

            await setup_plugins(self, mode, ctx, cmd)
            await self.plugins.start_all()

            # Chốt kiểm tra sức khỏe plugin then chốt: thất bại sẽ thoát ngay, cấm chạy silent zombie
            health_error = check_critical_plugins(self.plugins)
            if health_error:
                logger.error(health_error)
                return 1

            # Audio thất bại nhưng cho phép giáng cấp: ghi log/banner thông báo, tiếp tục chạy UI
            if self.plugins.is_failed("audio") and not audio_is_fatal():
                logger.warning(DEGRADED_AUDIO_NOTICE)
                self._degraded_audio = True
                try:
                    await self.event_bus.emit(
                        Events.SYSTEM_NOTICE, DEGRADED_AUDIO_NOTICE
                    )
                except Exception as e:
                    logger.debug(f"Phát sự kiện thông báo hạ cấp thất bại: {e}", exc_info=True)

            await self.plugins.notify_device_state_changed(self.state.device_state)

            await self.tasks.wait_shutdown()
            return 0

        except Exception as e:
            logger.error(f"Chạy ứng dụng thất bại: {e}", exc_info=True)
            return 1
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Đóng ứng dụng, giải phóng tập trung tất cả tài nguyên qua resource pool theo thứ tự ngược."""
        if self._shutting_down:
            logger.debug("ServiceContainer đang trong quá trình đóng, bỏ qua")
            return
        self._shutting_down = True
        logger.info("Đang đóng ServiceContainer...")

        try:
            await self.resource_pool.shutdown()
            logger.info("Đóng ServiceContainer hoàn tất")
        except Exception as e:
            logger.error(f"Lỗi khi đóng ServiceContainer: {e}", exc_info=True)
        finally:
            if self._mode == "gui":
                try:
                    from PySide6.QtWidgets import QApplication

                    if QApplication.instance():
                        logger.debug("Thoát ứng dụng Qt")
                        QApplication.quit()
                except Exception as e:
                    logger.debug(f"Lỗi khi thoát ứng dụng Qt: {e}")
