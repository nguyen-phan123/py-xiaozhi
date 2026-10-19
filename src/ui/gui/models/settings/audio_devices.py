"""音频设备枚举、选择与测试."""

from __future__ import annotations

import asyncio
import time

import numpy as np
import sounddevice as sd
from PySide6.QtCore import Slot

from src.logging import get_logger

logger = get_logger()


class SettingsAudioDevicesMixin:
    # ========== 音频设备设置 ==========

    def _apply_device_lists(self, devices: dict) -> None:
        """用枚举结果填充输入/输出列表并通知 QML."""
        self._input_devices = list(devices.get("input") or [])
        self._output_devices = list(devices.get("output") or [])
        self._audio_devices_loaded = True
        logger.debug(
            f"Đã tải {len(self._input_devices)} thiết bị đầu vào, "
            f"{len(self._output_devices)} thiết bị đầu ra"
        )
        self.devicesChanged.emit()

    def _load_audio_devices(self, force: bool = False):
        """加载可用的音频设备列表（普通枚举，不重初始化 PortAudio）.

        Args:
            force: True 时强制重新枚举（打开设置时）
        """
        if self._audio_devices_loaded and not force:
            return
        try:
            from src.utils.audio_utils import list_audio_devices

            devices = list_audio_devices(include_virtual=True)
            self._apply_device_lists(devices)
        except Exception as e:
            logger.error(f"Tải thiết bị âm thanh thất bại: {e}", exc_info=True)
            self._input_devices = []
            self._output_devices = []

    @Slot(result=list)
    def getInputDevices(self) -> list:
        """获取输入设备列表（首次调用时再枚举）."""
        self._load_audio_devices()
        return [d["name"] for d in self._input_devices]

    @Slot(result=list)
    def getOutputDevices(self) -> list:
        """获取输出设备列表（首次调用时再枚举）."""
        self._load_audio_devices()
        return [d["name"] for d in self._output_devices]

    @Slot()
    def refreshDevices(self):
        """热刷新设备列表（停流 → PortAudio 重枚举 → 再开流）.

        运行中后连蓝牙时，需经 AudioPlugin 先停流再 ``refresh_portaudio_devices``。
        无 EventBus 时降级为本地普通枚举。
        """
        if getattr(self, "_audio_devices_refreshing", False):
            self.statusMessage.emit("Đang làm mới thiết bị…")
            return

        event_bus = getattr(self, "_event_bus", None)
        task_manager = getattr(self, "_task_manager", None)

        if event_bus is None or task_manager is None:
            logger.warning("SettingsModel: Không có EventBus/TaskManager, chuyển sang liệt kê thiết bị cục bộ")
            self._load_audio_devices(force=True)
            self.statusMessage.emit(
                "Đã làm mới danh sách thiết bị (chưa điều phối luồng âm thanh)"
            )
            return

        self._audio_devices_refreshing = True
        self.statusMessage.emit("Đang làm mới thiết bị âm thanh (sẽ ngắt tạm thời mic/loa)…")

        async def _refresh():
            from src.core.event_bus import Events
            from src.utils.audio_utils import list_audio_devices

            # Future 作 payload：AudioPlugin 在 handler 里 set_result(设备列表)
            # emit 会 await 所有 handler，返回时 future 通常已完成
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            await event_bus.emit(Events.AUDIO_DEVICES_REFRESH_REQUEST, fut)
            if fut.done():
                result = fut.result()
            else:
                logger.warning("AudioPlugin chưa hoàn thành Future làm mới thiết bị, dùng liệt kê cục bộ dự phòng")
                result = list_audio_devices(include_virtual=True)
                if not fut.done():
                    fut.set_result(result)
            return result if isinstance(result, dict) else {"input": [], "output": []}

        def _on_task_done(task: asyncio.Task):
            def _apply():
                try:
                    if task.cancelled():
                        devices = {"input": [], "output": []}
                    else:
                        exc = task.exception()
                        if exc is not None:
                            logger.error(f"Tác vụ làm mới thiết bị gặp ngoại lệ: {exc}", exc_info=exc)
                            devices = {"input": [], "output": []}
                        else:
                            devices = task.result()
                except Exception as e:
                    logger.error(f"Đọc kết quả làm mới thất bại: {e}", exc_info=True)
                    devices = {"input": [], "output": []}
                try:
                    if not isinstance(devices, dict):
                        devices = {"input": [], "output": []}
                    self._apply_device_lists(devices)
                    n_in = len(self._input_devices)
                    n_out = len(self._output_devices)
                    self.statusMessage.emit(
                        f"Đã làm mới danh sách thiết bị (Đầu vào {n_in} / Đầu ra {n_out})"
                    )
                finally:
                    self._audio_devices_refreshing = False

            self._schedule_ui(_apply)

        try:
            task = task_manager.spawn(_refresh(), name="ui:audio_devices_refresh")
            if task is None:
                self._audio_devices_refreshing = False
                self._load_audio_devices(force=True)
                self.statusMessage.emit("Ứng dụng đang đóng, đã liệt kê cục bộ")
                return
            task.add_done_callback(_on_task_done)
        except Exception as e:
            self._audio_devices_refreshing = False
            logger.error(f"Không thể lập lịch làm mới thiết bị: {e}", exc_info=True)
            self._load_audio_devices(force=True)
            self.statusMessage.emit(f"Làm mới thiết bị thất bại, đã liệt kê cục bộ: {e}")

    def _schedule_ui(self, fn) -> None:
        """把回调丢回 Qt 主线程（spawn 的 done 可能在 loop 线程）."""
        try:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, fn)
        except Exception:
            try:
                fn()
            except Exception as e:
                logger.error(f"UI callback thất bại: {e}", exc_info=True)

    def _get_selectedInputIndex(self) -> int:
        """获取当前选中的输入设备索引."""
        current_id = self._get_value("AUDIO_DEVICES.input_device_id", -1)
        current_name = self._get_value("AUDIO_DEVICES.input_device_name", "")

        # 优先按设备名称匹配
        if current_name:
            for i, d in enumerate(self._input_devices):
                if d["raw_name"] == current_name:
                    return i

        # 其次按设备ID匹配
        for i, d in enumerate(self._input_devices):
            if d["index"] == current_id:
                return i
        return 0

    def _set_selectedInputIndex(self, index: int):
        """设置选中的输入设备."""
        if 0 <= index < len(self._input_devices):
            device = self._input_devices[index]
            self._set_value("AUDIO_DEVICES.input_device_id", device["index"])
            self._set_value("AUDIO_DEVICES.input_device_name", device["raw_name"])
            self._set_value("AUDIO_DEVICES.input_sample_rate", device["sample_rate"])
            self._set_value("AUDIO_DEVICES.input_channels", min(device["channels"], 1))
            logger.info(f"Chọn thiết bị đầu vào: {device['name']}")

    def _get_selectedOutputIndex(self) -> int:
        """获取当前选中的输出设备索引."""
        current_id = self._get_value("AUDIO_DEVICES.output_device_id", -1)
        current_name = self._get_value("AUDIO_DEVICES.output_device_name", "")

        # 优先按设备名称匹配
        if current_name:
            for i, d in enumerate(self._output_devices):
                if d["raw_name"] == current_name:
                    return i

        # 其次按设备ID匹配
        for i, d in enumerate(self._output_devices):
            if d["index"] == current_id:
                return i
        return 0

    def _set_selectedOutputIndex(self, index: int):
        """设置选中的输出设备."""
        if 0 <= index < len(self._output_devices):
            device = self._output_devices[index]
            self._set_value("AUDIO_DEVICES.output_device_id", device["index"])
            self._set_value("AUDIO_DEVICES.output_device_name", device["raw_name"])
            self._set_value("AUDIO_DEVICES.output_sample_rate", device["sample_rate"])
            self._set_value("AUDIO_DEVICES.output_channels", min(device["channels"], 2))
            logger.info(f"Chọn thiết bị đầu ra: {device['name']}")

    # 设备信息显示
    def _get_inputDeviceInfo(self) -> str:
        idx = self._get_selectedInputIndex()
        if 0 <= idx < len(self._input_devices):
            d = self._input_devices[idx]
            return f"Tần số mẫu: {d['sample_rate']}Hz, Kênh: {d['channels']}"
        return "Chưa chọn thiết bị"

    def _get_outputDeviceInfo(self) -> str:
        idx = self._get_selectedOutputIndex()
        if 0 <= idx < len(self._output_devices):
            d = self._output_devices[idx]
            return f"Tần số mẫu: {d['sample_rate']}Hz, Kênh: {d['channels']}"
        return "Chưa chọn thiết bị"

    # Opus 输出采样率
    def _get_opusOutputSampleRate(self) -> int:
        return self._get_value("AUDIO_DEVICES.opus_output_sample_rate", 24000)

    def _set_opusOutputSampleRate(self, value: int):
        self._set_value("AUDIO_DEVICES.opus_output_sample_rate", value)

    # 音频帧长度
    def _get_frameDuration(self) -> int:
        return self._get_value("AUDIO_DEVICES.frame_duration", 20)

    def _set_frameDuration(self, value: int):
        if value in [20, 40, 60]:
            self._set_value("AUDIO_DEVICES.frame_duration", value)

    # 音频测试
    @Slot()
    def testInputDevice(self):
        """测试输入设备（录音）."""
        if self._testing_input:
            return

        idx = self._get_selectedInputIndex()
        if idx < 0 or idx >= len(self._input_devices):
            self.statusMessage.emit("Vui lòng chọn thiết bị đầu vào trước")
            return

        device = self._input_devices[idx]
        self._testing_input = True
        self.statusMessage.emit("Bắt đầu kiểm tra ghi âm...")

        self._run_worker(
            self._do_input_test,
            device,
            name="settings:input_test",
            test_kind="input",
            clear_flags=lambda: setattr(self, "_testing_input", False),
        )

    def _do_input_test(self, device: dict):
        """执行录音测试（异常由 _run_worker 兜底）."""
        device_id = device["index"]
        sample_rate = device["sample_rate"]
        duration = 3

        self.statusMessage.emit(f"Vui lòng nói vào microphone ({duration} giây)...")
        time.sleep(1)

        recording = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            device=device_id,
            dtype=np.float32,
        )
        sd.wait()

        max_amplitude = np.max(np.abs(recording))

        if max_amplitude < 0.001:
            self.statusMessage.emit("[Thất bại] Không phát hiện tín hiệu âm thanh")
            self.testComplete.emit("input", False)
        elif max_amplitude > 0.8:
            self.statusMessage.emit("[Cảnh báo] Tín hiệu âm thanh quá tải")
            self.testComplete.emit("input", True)
        else:
            self.statusMessage.emit(f"[Thành công] Kiểm tra ghi âm đạt (Âm lượng: {max_amplitude:.1%})")
            self.testComplete.emit("input", True)

    @Slot()
    def testOutputDevice(self):
        """测试输出设备（播放）."""
        if self._testing_output:
            return

        idx = self._get_selectedOutputIndex()
        if idx < 0 or idx >= len(self._output_devices):
            self.statusMessage.emit("Vui lòng chọn thiết bị đầu ra trước")
            return

        device = self._output_devices[idx]
        self._testing_output = True
        self.statusMessage.emit("Bắt đầu kiểm tra phát âm...")

        self._run_worker(
            self._do_output_test,
            device,
            name="settings:output_test",
            test_kind="output",
            clear_flags=lambda: setattr(self, "_testing_output", False),
        )

    def _do_output_test(self, device: dict):
        """执行播放测试（异常由 _run_worker 兜底）."""
        device_id = device["index"]
        sample_rate = device["sample_rate"]
        duration = 2.0
        frequency = 440

        self.statusMessage.emit("Đang phát âm kiểm tra 440Hz...")
        time.sleep(0.5)

        t = np.linspace(0, duration, int(sample_rate * duration))
        audio = 0.3 * np.sin(2 * np.pi * frequency * t)

        fade_samples = int(0.1 * sample_rate)
        audio[:fade_samples] *= np.linspace(0, 1, fade_samples)
        audio[-fade_samples:] *= np.linspace(1, 0, fade_samples)

        sd.play(audio, samplerate=sample_rate, device=device_id)
        sd.wait()

        self.statusMessage.emit("[Thành công] Kiểm tra phát âm hoàn tất")
        self.testComplete.emit("output", True)
