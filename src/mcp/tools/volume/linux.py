"""Linux 音量后端（pactl / wpctl / amixer）."""

from __future__ import annotations

import re
import shutil
import subprocess

from src.logging import get_logger

logger = get_logger()

DEFAULT_VOLUME = 70


def _run_command(
    cmd: list[str], *, check: bool = False
) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=check)
    except Exception as e:
        logger.debug(f"Thực thi lệnh thất bại {' '.join(cmd)}: {e}")
        return None


class LinuxVolumeBackend:
    def __init__(self) -> None:
        self.linux_tool: str | None = None
        self._init()

    def _init(self) -> None:
        for tool in ("pactl", "wpctl", "amixer"):
            if shutil.which(tool):
                self.linux_tool = tool
                break

        if not self.linux_tool:
            logger.error("Không tìm thấy công cụ điều khiển âm lượng Linux khả dụng (pactl/wpctl/amixer)")
            raise Exception("未找到可用的Linux音量控制工具")

        logger.debug(f"Khởi tạo điều khiển âm lượng Linux thành công, sử dụng: {self.linux_tool}")

    def get_volume(self) -> int:
        tool = self.linux_tool
        if tool == "pactl":
            return self._get_pactl()
        if tool == "wpctl":
            return self._get_wpctl()
        if tool == "amixer":
            return self._get_amixer()
        return DEFAULT_VOLUME

    def set_volume(self, volume: int) -> None:
        tool = self.linux_tool
        if tool == "pactl":
            self._set_pactl(volume)
        elif tool == "wpctl":
            self._set_wpctl(volume)
        elif tool == "amixer":
            self._set_amixer(volume)

    def _get_pactl(self) -> int:
        try:
            result = _run_command(["pactl", "list", "sinks"])
            if result and result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "Volume:" in line:
                        match = re.search(r"(\d+)%", line)
                        if match:
                            volume = int(match.group(1))
                            logger.debug(f"Lấy âm lượng qua pactl thành công: {volume}%")
                            return volume
                logger.warning("Không tìm thấy thông tin âm lượng trong output của pactl")
            else:
                logger.warning(
                    f"Thực thi lệnh pactl thất bại: {result.returncode if result else 'None'}"
                )
        except Exception as e:
            logger.warning(f"Lấy âm lượng qua pactl thất bại: {e}", exc_info=True)
        return DEFAULT_VOLUME

    def _set_pactl(self, volume: int) -> None:
        try:
            result = _run_command(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"]
            )
            if result and result.returncode == 0:
                logger.debug(f"Đặt âm lượng qua pactl thành công: {volume}%")
            else:
                logger.warning(
                    f"Đặt âm lượng qua pactl thất bại: {result.returncode if result else 'None'}"
                )
        except Exception as e:
            logger.warning(f"Đặt âm lượng qua pactl thất bại: {e}", exc_info=True)

    def _get_wpctl(self) -> int:
        try:
            result = _run_command(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
            if result and result.returncode == 0:
                match = re.search(r"(\d+\.?\d*)", result.stdout)
                if match:
                    volume = int(float(match.group(1)) * 100)
                    logger.debug(f"Lấy âm lượng qua wpctl thành công: {volume}%")
                    return volume
                logger.warning(f"Không thể phân tích định dạng output của wpctl: {result.stdout}")
            else:
                logger.warning(
                    f"Thực thi lệnh wpctl thất bại: {result.returncode if result else 'None'}"
                )
        except Exception as e:
            logger.warning(f"Lấy âm lượng qua wpctl thất bại: {e}", exc_info=True)
        return DEFAULT_VOLUME

    def _set_wpctl(self, volume: int) -> None:
        try:
            result = _run_command(
                [
                    "wpctl",
                    "set-volume",
                    "@DEFAULT_AUDIO_SINK@",
                    f"{volume / 100.0:.2f}",
                ]
            )
            if result and result.returncode == 0:
                logger.debug(f"Đặt âm lượng qua wpctl thành công: {volume}%")
            else:
                logger.warning(
                    f"Đặt âm lượng qua wpctl thất bại: {result.returncode if result else 'None'}"
                )
        except Exception as e:
            logger.warning(f"Đặt âm lượng qua wpctl thất bại: {e}", exc_info=True)

    def _get_amixer(self) -> int:
        try:
            result = _run_command(["amixer", "get", "Master"])
            if result and result.returncode == 0:
                match = re.search(r"\[(\d+)%\]", result.stdout)
                if match:
                    volume = int(match.group(1))
                    logger.debug(f"Lấy âm lượng qua amixer thành công: {volume}%")
                    return volume
                logger.warning(f"Không thể phân tích định dạng output của amixer: {result.stdout}")
            else:
                logger.warning(
                    f"Thực thi lệnh amixer thất bại: {result.returncode if result else 'None'}"
                )
        except Exception as e:
            logger.warning(f"Lấy âm lượng qua amixer thất bại: {e}", exc_info=True)
        return DEFAULT_VOLUME

    def _set_amixer(self, volume: int) -> None:
        try:
            result = _run_command(["amixer", "sset", "Master", f"{volume}%"])
            if result and result.returncode == 0:
                logger.debug(f"Đặt âm lượng qua amixer thành công: {volume}%")
            else:
                logger.warning(
                    f"Đặt âm lượng qua amixer thất bại: {result.returncode if result else 'None'}"
                )
        except Exception as e:
            logger.warning(f"Đặt âm lượng qua amixer thất bại: {e}", exc_info=True)
