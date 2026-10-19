import asyncio
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

from src.constants.constants import AudioConfig
from src.logging import get_logger
from src.utils.resource_finder import get_ffmpeg_path, get_ffprobe_path

logger = get_logger()

_SUBPROCESS_KW = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)

# 本地路径或 http(s) 流
AudioSource = str | Path


def is_http_url(source: AudioSource) -> bool:
    text = str(source).strip()
    return text.startswith("http://") or text.startswith("https://")


def _source_label(source: AudioSource) -> str:
    if is_http_url(source):
        host = urlparse(str(source)).hostname or "http"
        return f"stream:{host}"
    path = Path(source)
    return path.name


def _ffmpeg_header_args(headers: Mapping[str, str] | None) -> list[str]:
    """拼给 ffmpeg 的 -headers / -user_agent（HTTP 源常用）."""
    if not headers:
        return []
    args: list[str] = []
    ua = None
    lines: list[str] = []
    for key, value in headers.items():
        if not value:
            continue
        if key.lower() == "user-agent":
            ua = str(value)
            continue
        lines.append(f"{key}: {value}")
    if lines:
        blob = "".join(f"{line}\r\n" for line in lines)
        args.extend(["-headers", blob])
    if ua:
        args.extend(["-user_agent", ua])
    return args


class MusicDecoder:
    """只负责把音源解成 PCM；缓存预取不走这里（避免和播放进度绑死）."""

    @staticmethod
    async def get_duration(
        source: AudioSource,
        headers: Mapping[str, str] | None = None,
    ) -> float:
        """ffprobe 取时长；source 可以是本地文件或 http(s) URL."""
        try:
            ffprobe = get_ffprobe_path()
            try:
                check = await asyncio.create_subprocess_exec(
                    ffprobe,
                    "-version",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **_SUBPROCESS_KW,
                )
                await check.wait()
            except FileNotFoundError:
                logger.warning(
                    "ffprobe không khả dụng (không tìm thấy libs/ffmpeg tích hợp và PATH hệ thống không có ffprobe), "
                    f"không thể lấy thời lượng âm thanh. Đường dẫn đã thử: {ffprobe}"
                )
                return 0
            except OSError as e:
                logger.warning(f"Khởi động ffprobe thất bại: {ffprobe}: {e}", exc_info=True)
                return 0

            cmd = [ffprobe, "-v", "error"]
            if is_http_url(source):
                cmd.extend(_ffmpeg_header_args(headers))
            cmd.extend(
                [
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(source),
                ]
            )

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_SUBPROCESS_KW
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                duration_str = stdout.decode("utf-8").strip()
                duration = float(duration_str)
                logger.debug(f"Phân tích thời lượng âm thanh: {duration:.2f}s ({_source_label(source)})")
                return duration
            else:
                error_msg = stderr.decode("utf-8", errors="ignore")
                logger.warning(f"ffprobe lấy thời lượng thất bại: {error_msg}")
                return 0

        except Exception as e:
            logger.warning(f"Phân tích thời lượng âm thanh thất bại: {e}", exc_info=True)
            return 0

    def __init__(self, sample_rate: int = 24000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._process: subprocess.Process | None = None
        self._decode_task: asyncio.Task | None = None
        self._stopped = False

    async def start_decode(
        self,
        source: AudioSource,
        output_queue: asyncio.Queue,
        start_position: float = 0.0,
        headers: Mapping[str, str] | None = None,
        cache_path: Path | None = None,
    ) -> bool:
        """开始解码。source 为本地路径或 http(s)。

        cache_path 已废弃忽略：缓存由后台按网速 copy，不跟播放进度绑。
        """
        _ = cache_path
        http = is_http_url(source)
        if not http:
            path = Path(source)
            if not path.exists():
                logger.error(f"Tệp âm thanh không tồn tại: {path}")
                return False
            source = path

        self._stopped = False

        try:
            ffmpeg = get_ffmpeg_path()
            try:
                result = await asyncio.create_subprocess_exec(
                    ffmpeg,
                    "-version",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **_SUBPROCESS_KW,
                )
                await result.wait()
                if result.returncode not in (0, None):
                    logger.error(
                        f"FFmpeg không thể khởi động (exit code {result.returncode}): {ffmpeg}. "
                        "Bản cài đặt nên tích hợp sẵn binary; nếu vẫn thất bại vui lòng phản hồi phiên bản và nền tảng. "
                        "Nếu chạy từ nguồn vui lòng chạy ./scripts/bundle_ffmpeg.sh hoặc cài đặt ffmpeg hệ thống"
                    )
                    return False
            except FileNotFoundError:
                logger.error(
                    "FFmpeg không khả dụng: không tìm thấy libs/ffmpeg/<plat>/<arch>/ffmpeg tích hợp, "
                    f"và PATH hệ thống cũng không có. Đường dẫn đã thử: {ffmpeg}. "
                    "Người dùng bản cài đặt không cần cài FFmpeg riêng; nếu vẫn thất bại, "
                    "vui lòng tải lại gói cài đặt đầy đủ. Nếu chạy từ nguồn vui lòng cài ffmpeg hoặc chạy "
                    "./scripts/bundle_ffmpeg.sh"
                )
                return False
            except OSError as e:
                logger.error(
                    f"Khởi động FFmpeg thất bại (có thể thiếu thư viện động): {ffmpeg}: {e}",
                    exc_info=True,
                )
                return False

            cmd = [ffmpeg]

            if http:
                cmd.extend(
                    [
                        "-reconnect",
                        "1",
                        "-reconnect_streamed",
                        "1",
                        "-reconnect_delay_max",
                        "5",
                    ]
                )
                cmd.extend(_ffmpeg_header_args(headers))

            if start_position > 0.1:
                cmd.extend(["-ss", f"{start_position:.3f}"])

            cmd.extend(
                [
                    "-i",
                    str(source),
                    "-f",
                    "s16le",
                    "-ar",
                    str(self.sample_rate),
                    "-ac",
                    str(self.channels),
                    "-loglevel",
                    "error",
                    "-",
                ]
            )

            self._process = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_SUBPROCESS_KW
            )

            self._decode_task = asyncio.create_task(self._read_pcm_stream(output_queue))

            position_info = f" from {start_position:.1f}s" if start_position > 0 else ""
            mode = "luồng" if http else "tập tin"
            logger.info(
                f"Bắt đầu giải mã âm thanh ({mode}): {_source_label(source)}{position_info} "
                f"[{self.sample_rate}Hz, {self.channels}ch]"
            )
            return True

        except Exception as e:
            logger.error(f"Khởi động giải mã âm thanh thất bại: {e}", exc_info=True)
            return False

    async def _read_pcm_stream(self, output_queue: asyncio.Queue):
        frame_duration_ms = AudioConfig.FRAME_DURATION
        frame_size_samples = int(self.sample_rate * (frame_duration_ms / 1000))
        frame_size_bytes = frame_size_samples * 2 * self.channels
        logger.info(
            f"Tham số decoder: kích thước khung={frame_size_samples} mẫu, "
            f"{frame_size_bytes} byte, {frame_duration_ms}ms"
        )

        eof_reached = False
        frame_count = 0

        try:
            while not self._stopped:
                chunk = await self._process.stdout.read(frame_size_bytes)

                if not chunk:
                    duration_decoded = frame_count * frame_duration_ms / 1000
                    logger.info(
                        f"Giải mã âm thanh hoàn tất, tổng cộng {frame_count} khung, thời lượng khoảng {duration_decoded:.1f}s"
                    )

                    if self._process:
                        try:
                            await asyncio.wait_for(self._process.wait(), timeout=2.0)
                        except (asyncio.TimeoutError, Exception):
                            pass
                        try:
                            stderr_output = await self._process.stderr.read()
                            if stderr_output:
                                err = stderr_output.decode("utf-8", errors="ignore")
                                if err.strip():
                                    logger.warning(f"FFmpeg: {err.strip()[:300]}")
                        except Exception as e:
                            logger.debug(f"Đọc stderr của FFmpeg thất bại: {e}")

                    eof_reached = True
                    break

                frame_count += 1

                audio_array_int16 = np.frombuffer(chunk, dtype=np.int16)
                audio_array = audio_array_int16.astype(np.float32) / 32768.0

                if self.channels > 1:
                    audio_array = audio_array.reshape(-1, self.channels)

                # 节拍完全由下游背压决定：queue 满则在 put 处等位
                # （AudioCodec.write_pcm_direct 按缓冲水位放行）。
                # 不再用「墙钟-起播时刻」限速——暂停期间墙钟照走，
                # 恢复后会误判落后而全速灌数据，把播放队列冲爆。
                await output_queue.put(audio_array)

        except asyncio.CancelledError:
            logger.debug("Tác vụ giải mã đã bị hủy")
        except Exception as e:
            logger.error(f"Đọc luồng PCM thất bại: {e}", exc_info=True)
        finally:
            if eof_reached:
                try:
                    await output_queue.put(None)
                except Exception as e:
                    logger.debug(f"Gửi tín hiệu EOF thất bại: {e}")

    async def stop(self):
        if self._stopped:
            return

        self._stopped = True
        logger.debug("Dừng bộ giải mã âm thanh")

        if self._decode_task and not self._decode_task.done():
            self._decode_task.cancel()
            try:
                await self._decode_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Ngoại lệ tác vụ giải mã: {e}", exc_info=True)

        proc = self._process
        self._process = None
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception as e:
                    logger.debug(f"Buộc kết thúc FFmpeg thất bại: {e}")
            except ProcessLookupError:
                pass
            except Exception as e:
                if str(e).strip():
                    logger.debug(f"Kết thúc tiến trình FFmpeg: {e}")

    def is_running(self) -> bool:
        return (
            not self._stopped
            and self._process is not None
            and self._process.returncode is None
        )

    async def wait_completion(self):
        if self._decode_task and not self._decode_task.done():
            try:
                await self._decode_task
            except Exception as e:
                logger.error(f"Chờ giải mã hoàn tất thất bại: {e}", exc_info=True)
