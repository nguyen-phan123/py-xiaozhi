"""Lắp ráp plugin và dịch vụ dùng chung (Plugin & Shared Services Wiring).

Tập trung: khởi tạo McpServer/MusicPlayer, đăng ký danh sách plugin, dọn dẹp resource pool, kênh truyền trực tiếp âm thanh.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.logging import get_logger

if TYPE_CHECKING:
    from src.bootstrap.container import ServiceContainer
    from src.bootstrap.protocols import PluginCommands, PluginContext

logger = get_logger()


def bind_shared_services(container: "ServiceContainer") -> None:
    """Tạo các dịch vụ dùng chung giữa các plugin (McpServer / MusicPlayer), chỉ do container nắm giữ.

    Không ghi vào singleton cấp module; plugin và MCP tool nhận cùng một instance qua dependency injection / closure.
    """
    from src.mcp.mcp_server import McpServer
    from src.mcp.tools.music.music_player import MusicPlayer

    if container.mcp_server is None:
        container.mcp_server = McpServer()

    if container.music_player is None:
        container.music_player = MusicPlayer()

    logger.debug("Dịch vụ dùng chung đã được tạo: McpServer, MusicPlayer")


def unbind_shared_services(container: "ServiceContainer") -> None:
    """Giải phóng tham chiếu dịch vụ dùng chung (được gọi ở giai đoạn cuối của resource pool)."""
    if container.music_player is not None:
        try:
            container.music_player.detach()
        except Exception as e:
            logger.debug(f"detach MusicPlayer thất bại: {e}", exc_info=True)
    if container.mcp_server is not None:
        try:
            container.mcp_server.detach()
        except Exception as e:
            logger.debug(f"detach McpServer thất bại: {e}", exc_info=True)
    container.music_player = None
    container.mcp_server = None


async def setup_plugins(
    container: "ServiceContainer",
    mode: str,
    ctx: "PluginContext",
    cmd: "PluginCommands",
) -> None:
    """Ràng buộc dịch vụ dùng chung, đăng ký và khởi tạo plugin, gắn dọn dẹp tài nguyên và kết nối trực tiếp âm thanh."""
    from src.plugins.audio import AudioPlugin
    from src.plugins.mcp import McpPlugin
    from src.plugins.shortcuts import ShortcutsPlugin
    from src.plugins.ui import UIPlugin
    from src.plugins.wake_word import WakeWordPlugin

    bind_shared_services(container)

    # Tạo instance các plugin (Audio công bố codec qua event, không inject MusicPlayer)
    audio_plugin = AudioPlugin()
    wake_word_plugin = WakeWordPlugin()
    ui_plugin = UIPlugin(mode=mode, task_manager=container.tasks)
    shortcuts_plugin = ShortcutsPlugin()
    mcp_plugin = McpPlugin(
        server=container.mcp_server,
        music_player=container.music_player,
    )

    container.plugins.register(
        mcp_plugin,
        audio_plugin,
        wake_word_plugin,
        ui_plugin,
        shortcuts_plugin,
    )

    await container.plugins.setup_all(ctx, cmd)

    register_cleanup_resources(container)

    # Thiết lập kênh truyền trực tiếp âm thanh (âm thanh TTS không qua EventBus để giảm độ trễ)
    if not audio_plugin.failed:
        container.protocol.set_audio_handler(audio_plugin.on_incoming_audio)


def register_cleanup_resources(container: "ServiceContainer") -> None:
    """Đăng ký hàm dọn dẹp của tất cả các module vào resource pool (đăng ký trước giải phóng sau)."""
    pool = container.resource_pool

    # Đăng ký đầu tiên = giải phóng cuối cùng: unbind dịch vụ dùng chung sau khi dọn dẹp plugin
    pool.register(
        "shared_services", lambda: unbind_shared_services(container)
    )

    # Giải phóng EventBus cuối cùng (đăng ký thứ hai)
    pool.register("event_bus", container.event_bus.clear)

    # Mỗi plugin tự đăng ký tài nguyên của mình
    for plugin in container.plugins._plugins:
        plugin.register_resources(pool)

    # Kết nối mạng
    pool.register("protocol", container.protocol.disconnect)

    # Tác vụ bất đồng bộ
    pool.register("tasks", container.tasks.cancel_all)
