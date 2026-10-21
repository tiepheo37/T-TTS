"""backend/audio_player.py — BỘ PHÁT ÂM THANH NATIVE WINDOWS (WAV & MP3)
===================================================================
Sử dụng Windows winmm.dll (Media Control Interface - MCI) tích hợp sẵn trong mọi bản Windows.
Hoạt động 100% offline, không cần ffmpeg lúc phát, không cần trình duyệt, không làm treo UI.
Hỗ trợ đầy đủ: Play, Pause, Resume, Stop, Seek, Get Position, Get Duration.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional


class NativeAudioPlayer:
    """Trình phát âm thanh Windows MCI hỗ trợ cả tệp WAV và MP3."""

    def __init__(self):
        self._lock = threading.RLock()
        self._current_file: Optional[str] = None
        self._is_paused = False
        self._alias = "TTTS_NativePlayer"
        self._mci = None
        if sys.platform == "win32":
            try:
                self._mci = ctypes.windll.winmm.mciSendStringW
            except Exception:
                self._mci = None

    def _send_cmd(self, cmd: str) -> tuple[int, str]:
        if not self._mci:
            return -1, ""
        buf = ctypes.create_unicode_buffer(256)
        ret = self._mci(cmd, buf, 255, 0)
        return ret, buf.value

    def play(self, file_path: str | Path) -> bool:
        """Mở và phát file âm thanh (WAV hoặc MP3)."""
        p = Path(file_path).resolve()
        if not p.is_file():
            return False

        with self._lock:
            # Đóng phiên phát trước nếu có
            self.stop()

            # Dùng short path để tránh lỗi đường dẫn có khoảng trắng hoặc ký tự đặc biệt
            short_path = self._get_short_path_name(str(p))

            # Mở tệp qua MCI
            ret, _ = self._send_cmd(f'open "{short_path}" type mpegvideo alias {self._alias}')
            if ret != 0:
                # Thử mở lại không chỉ định type (dành cho WAV PCM)
                ret, _ = self._send_cmd(f'open "{short_path}" alias {self._alias}')

            if ret != 0:
                # Phương án dự phòng bằng winsound cho WAV nếu MCI gặp trở ngại
                if str(p).lower().endswith(".wav"):
                    try:
                        import winsound
                        winsound.PlaySound(str(p), winsound.SND_FILENAME | winsound.SND_ASYNC)
                        self._current_file = str(p)
                        self._is_paused = False
                        return True
                    except Exception:
                        pass
                return False

            # Đặt định dạng thời gian là milliseconds
            self._send_cmd(f"set {self._alias} time format milliseconds")
            # Bắt đầu phát
            ret, _ = self._send_cmd(f"play {self._alias} from 0")
            if ret == 0:
                self._current_file = str(p)
                self._is_paused = False
                return True
            return False

    def pause(self) -> bool:
        """Tạm dừng phát."""
        with self._lock:
            if not self._current_file:
                return False
            ret, _ = self._send_cmd(f"pause {self._alias}")
            if ret == 0:
                self._is_paused = True
                return True
            return False

    def resume(self) -> bool:
        """Tiếp tục phát sau khi tạm dừng."""
        with self._lock:
            if not self._current_file:
                return False
            ret, _ = self._send_cmd(f"resume {self._alias}")
            if ret == 0:
                self._is_paused = False
                return True
            return False

    def stop(self) -> bool:
        """Dừng hoàn toàn và giải phóng tài nguyên."""
        with self._lock:
            if sys.platform == "win32":
                try:
                    import winsound
                    winsound.PlaySound(None, winsound.SND_PURGE)
                except Exception:
                    pass
            self._send_cmd(f"stop {self._alias}")
            self._send_cmd(f"close {self._alias}")
            self._current_file = None
            self._is_paused = False
            return True

    def is_playing(self) -> bool:
        """Kiểm tra âm thanh có đang phát hay không."""
        with self._lock:
            if not self._current_file or self._is_paused:
                return False
            ret, mode = self._send_cmd(f"status {self._alias} mode")
            return ret == 0 and mode.lower() == "playing"

    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def state(self) -> str:
        if self._is_paused:
            return "paused"
        if self.is_playing():
            return "playing"
        return "stopped"


    def get_position_ms(self) -> int:
        """Lấy vị trí phát hiện tại (milliseconds)."""
        with self._lock:
            if not self._current_file:
                return 0
            ret, pos_str = self._send_cmd(f"status {self._alias} position")
            if ret == 0 and pos_str.isdigit():
                return int(pos_str)
            return 0

    def get_duration_ms(self) -> int:
        """Lấy tổng thời lượng của tệp âm thanh (milliseconds)."""
        with self._lock:
            if not self._current_file:
                return 0
            ret, dur_str = self._send_cmd(f"status {self._alias} length")
            if ret == 0 and dur_str.isdigit():
                return int(dur_str)
            return 0

    def seek_ms(self, pos_ms: int) -> bool:
        """Tua tới vị trí thời gian xác định."""
        with self._lock:
            if not self._current_file:
                return False
            pos = max(0, int(pos_ms))
            ret, _ = self._send_cmd(f"seek {self._alias} to {pos}")
            if not self._is_paused:
                self._send_cmd(f"play {self._alias}")
            return ret == 0

    def _get_short_path_name(self, long_name: str) -> str:
        """Lấy đường dẫn 8.3 short path trên Windows để đảm bảo tương thích 100% với MCI."""
        if sys.platform != "win32":
            return long_name
        try:
            buf = ctypes.create_unicode_buffer(512)
            ret = ctypes.windll.kernel32.GetShortPathNameW(long_name, buf, 512)
            if ret > 0 and buf.value:
                return buf.value
        except Exception:
            pass
        return long_name


# Singleton audio player
audio_player = NativeAudioPlayer()
