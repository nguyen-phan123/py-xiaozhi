"""歌词拉取、解析，以及按播放进度取当前句."""

from __future__ import annotations

import asyncio
from typing import Any

import requests

from src.logging import get_logger

logger = get_logger()

# (时间秒, 文本)
LyricLine = tuple[float, str]

# 过滤掉作词/作曲这类信息行
_METADATA_PREFIXES = (
    "作词",
    "作曲",
    "编曲",
    "制作",
    "演唱",
    "原唱",
    "翻唱",
)


def lyric_at(
    lyrics: list[LyricLine], current_time: float, *, lead: float = 0.5
) -> tuple[int, str] | None:
    """按当前播放时间找该显示哪句歌词.

    返回 (下标, 文本)；没有歌词返回 None。
    """
    if not lyrics:
        return None

    next_lyric_index = None
    for i, (time_sec, _) in enumerate(lyrics):
        if time_sec > current_time - lead:
            next_lyric_index = i
            break

    if next_lyric_index is not None and next_lyric_index > 0:
        idx = next_lyric_index - 1
    elif next_lyric_index is None:
        idx = len(lyrics) - 1
    else:
        idx = 0

    return idx, lyrics[idx][1]


def format_lyric_display(
    text: str, position: float, duration: float
) -> str:
    """拼 UI 上用的歌词行，例如 [00:12/03:45] 歌词内容."""
    return f"[{_fmt(position)}/{_fmt(duration)}] {text}"


def _fmt(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes:02d}:{secs:02d}"


def parse_kuwo_lrc_list(lrc_list: list[dict]) -> tuple[list[LyricLine], int]:
    """解析酷我返回的 lrclist.

    返回 (歌词列表, 被过滤的信息行数量).
    """
    lyrics: list[LyricLine] = []
    filtered = 0
    for item in lrc_list:
        time_str = item.get("time", "")
        text = (item.get("lineLyric") or "").strip()
        if not text or not time_str:
            continue
        try:
            time_sec = float(time_str)
        except (ValueError, TypeError):
            continue
        if text.startswith(_METADATA_PREFIXES):
            filtered += 1
            continue
        lyrics.append((time_sec, text))
    return lyrics, filtered


async def fetch_kuwo_lyrics(
    song_id: str,
    *,
    lyrics_url: str,
    headers: dict[str, Any] | None = None,
) -> list[LyricLine]:
    """从酷我接口拉歌词并解析."""
    try:
        logger.info(f"Lấy lời bài hát: ID={song_id}")
        response = await asyncio.to_thread(
            requests.get,
            lyrics_url,
            params={"musicId": song_id},
            headers=headers or {},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != 200:
            logger.info("Bài hát này tạm thời chưa có lời")
            return []

        lrc_list = data.get("data", {}).get("lrclist", [])
        if not lrc_list:
            logger.warning("Không lấy được dữ liệu lời bài hát")
            return []

        lyrics, filtered = parse_kuwo_lrc_list(lrc_list)
        logger.info(
            f"Lấy lời bài hát thành công, tổng cộng {len(lyrics)} dòng (lọc {filtered} dòng metadata)"
        )
        return lyrics
    except Exception as e:
        logger.error(f"Lấy lời bài hát thất bại: {e}", exc_info=True)
        return []
