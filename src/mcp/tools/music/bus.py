"""MusicPlayer 与 EventBus 的桥：订阅控制事件、发射状态/歌词.

持有 PlaybackEngine 引用；控制请求通过 MusicPlayer 公开方法转发
（便于测试 monkeypatch player.stop 等）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.tools.music.music_player import MusicPlayer
    from src.mcp.tools.music.playback import PlaybackEngine

logger = get_logger()


class MusicEventBridge:
    def __init__(self, engine: "PlaybackEngine", player: "MusicPlayer") -> None:
        self._engine = engine
        self._player = player
        self.event_bus = None
        self.plugin_ctx = None

    async def on_audio_codec_changed(self, codec=None) -> None:
        """EventBus：AudioPlugin 发布 codec 就绪/清除.

        EventBus 在 data 为 None 时无参调用 handler，故 codec 必须有默认值。
        """
        if codec is None:
            if self._engine.is_playing:
                try:
                    # 经 player 转发，测试可 monkeypatch player.stop
                    await self._player.stop()
                except Exception as e:
                    logger.debug(f"Dừng phát trước khi xóa codec thất bại: {e}", exc_info=True)
            if self._engine.decoder:
                try:
                    await self._engine.decoder.stop()
                except Exception as e:
                    logger.debug(f"Dừng decoder trước khi xóa codec thất bại: {e}", exc_info=True)
                self._engine.decoder = None
            self._engine.audio_codec = None
            logger.debug("AudioCodec của MusicPlayer đã được xóa")
            return

        self._engine.audio_codec = codec
        logger.info("Đã thiết lập AudioCodec cho MusicPlayer")

    def set_event_bus(self, event_bus, plugin_ctx=None) -> None:
        from src.core.event_bus import Events

        self.unsubscribe()
        self.event_bus = event_bus
        self.plugin_ctx = plugin_ctx
        if event_bus:
            event_bus.on(Events.MUSIC_PAUSE_REQUEST, self._on_pause_request)
            event_bus.on(Events.MUSIC_RESUME_REQUEST, self._on_resume_request)
            event_bus.on(Events.AUDIO_CODEC_CHANGED, self.on_audio_codec_changed)
            logger.info("MusicPlayer đã kết nối đến EventBus")

    def unsubscribe(self) -> None:
        if not self.event_bus:
            return
        try:
            from src.core.event_bus import Events

            self.event_bus.off(Events.MUSIC_PAUSE_REQUEST, self._on_pause_request)
            self.event_bus.off(Events.MUSIC_RESUME_REQUEST, self._on_resume_request)
            self.event_bus.off(Events.AUDIO_CODEC_CHANGED, self.on_audio_codec_changed)
        except Exception as e:
            logger.debug(f"MusicPlayer hủy đăng ký EventBus thất bại: {e}")

    def detach(self) -> None:
        self.unsubscribe()
        self.event_bus = None
        self.plugin_ctx = None
        self._engine.audio_codec = None
        self._engine.cancel_prefetch()
        logger.debug("MusicPlayer đã detach liên kết runtime")

    async def emit_state_change(
        self,
        state: str,
        song_name: str | None = None,
        position: float | None = None,
    ) -> None:
        if not self.event_bus:
            return
        try:
            from src.core.event_bus import Events

            from .events import MusicStateData

            eng = self._engine
            data = MusicStateData(
                state=state,
                song=song_name or eng.current_song,
                position=position if position is not None else eng.current_position,
                duration=eng.total_duration,
                pause_source=eng.pause_source if state == "paused" else None,
            )
            await self.event_bus.emit(Events.MUSIC_STATE_CHANGED, data)
            logger.debug(f"Gửi sự kiện thay đổi trạng thái nhạc: {state}")
        except Exception as e:
            logger.debug(f"Gửi sự kiện trạng thái thất bại: {e}")

    async def emit_lyrics_update(self, lyrics_text: str, time_sec: float = 0) -> None:
        if not self.event_bus:
            return
        try:
            from src.core.event_bus import Events

            from .events import MusicLyricsData

            data = MusicLyricsData(
                text=lyrics_text,
                time_sec=time_sec,
                song_id=self._engine.song_id,
            )
            await self.event_bus.emit(Events.MUSIC_LYRICS_UPDATE, data)
        except Exception as e:
            logger.debug(f"Gửi sự kiện lời bài hát thất bại: {e}")

    async def _on_pause_request(self, data: Any) -> None:
        try:
            from .events import MusicControlRequest

            if isinstance(data, MusicControlRequest):
                source = data.source
            elif isinstance(data, dict):
                source = data.get("source", "external")
            else:
                source = "external"

            eng = self._engine
            if eng.is_playing and not eng.paused:
                logger.info(f"Nhận yêu cầu tạm dừng, nguồn: {source}")
                await self._player.pause(source=source)
        except Exception as e:
            logger.error(f"Xử lý yêu cầu tạm dừng thất bại: {e}", exc_info=True)

    async def _on_resume_request(self, data: Any) -> None:
        try:
            from .events import MusicControlRequest

            if isinstance(data, MusicControlRequest):
                source = data.source
            elif isinstance(data, dict):
                source = data.get("source", "external")
            else:
                source = None

            eng = self._engine
            if eng.is_playing and eng.paused:
                if source is None or eng.pause_source == source:
                    logger.info(f"Nhận yêu cầu tiếp tục, nguồn: {source}")
                    await self._player.resume()
        except Exception as e:
            logger.error(f"Xử lý yêu cầu tiếp tục thất bại: {e}", exc_info=True)
