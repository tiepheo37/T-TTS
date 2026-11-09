"""backend/recorder.py — BỘ THU ÂM MICROPHONE TÍCH HỢP CHO T-TTS v3.0
=====================================================================
Thu âm trực tiếp từ Micro máy tính bằng sounddevice & soundfile.
Chạy trong QThread nền, tự động chuẩn hóa sang định dạng WAV 16-bit PCM 44.1kHz,
phát tín hiệu đếm giây thời gian thực lên giao diện.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, List, Dict, Any

import numpy as np
from PySide6.QtCore import QThread, Signal


def get_available_mics() -> List[Dict[str, Any]]:
    """Lấy danh sách các thiết bị thu âm Micro khả dụng."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        results = []
        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                results.append({
                    "index": idx,
                    "name": dev.get("name", f"Microphone {idx}"),
                    "channels": dev.get("max_input_channels", 1),
                })
        return results
    except Exception:
        return []


class MicRecorderThread(QThread):
    """Tiểu trình thu âm Micro thời gian thực."""

    tick = Signal(float)  # Số giây đã thu âm (ví dụ: 5.4s)
    finished = Signal(str, float)  # (saved_path, duration_sec)
    error = Signal(str)

    def __init__(
        self,
        save_path: str | Path,
        device_index: Optional[int] = None,
        sample_rate: int = 44100,
    ):
        super().__init__()
        self.save_path = Path(save_path).resolve()
        self.device_index = device_index
        self.sample_rate = sample_rate
        self._is_recording = False
        self._stop_requested = False
        self._frames: list[np.ndarray] = []

    def request_stop(self):
        """Yêu cầu dừng thu âm an toàn từ luồng giao diện."""
        self._stop_requested = True

    def run(self):
        try:
            import sounddevice as sd
            import soundfile as sf
        except ImportError as e:
            self.error.emit(f"Thiếu thư viện thu âm: {e}")
            return

        # Kiểm tra thiết bị
        try:
            mics = get_available_mics()
            if not mics:
                self.error.emit(
                    "Không tìm thấy thiết bị Microphone nào đang kết nối với máy tính.\n"
                    "Vui lòng cắm Micro hoặc sử dụng tệp ghi âm có sẵn."
                )
                return

            dev_id = self.device_index
            if dev_id is None:
                # Tìm thiết bị đầu vào đầu tiên
                dev_id = mics[0]["index"]

            self._frames = []
            self._is_recording = True
            self._stop_requested = False

            def _audio_callback(indata, frame_count, time_info, status):
                if self._is_recording and not self._stop_requested:
                    self._frames.append(indata.copy())

            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=dev_id,
                callback=_audio_callback,
            )

            start_time = time.time()
            with stream:
                while not self._stop_requested:
                    self.msleep(100)
                    elapsed = time.time() - start_time
                    self.tick.emit(round(elapsed, 1))

            self._is_recording = False

            if not self._frames:
                self.error.emit("Không ghi nhận được dữ liệu âm thanh nào từ Micro.")
                return

            # Nối và chuẩn hóa
            all_samples = np.concatenate(self._frames, axis=0)
            if all_samples.ndim > 1:
                all_samples = all_samples.flatten()

            total_duration = len(all_samples) / float(self.sample_rate)
            if total_duration < 1.0:
                self.error.emit(
                    f"Thời lượng thu âm quá ngắn ({total_duration:.1f}s). Vui lòng thu âm ít nhất 3 giây."
                )
                return

            # Lưu ra file WAV 16-bit PCM
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(self.save_path), all_samples, self.sample_rate, subtype="PCM_16")

            self.finished.emit(str(self.save_path), round(total_duration, 2))

        except Exception as e:
            self._is_recording = False
            self.error.emit(f"Lỗi khi thu âm từ Micro: {e}")
