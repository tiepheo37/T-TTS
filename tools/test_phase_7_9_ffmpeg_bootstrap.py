"""tools/test_phase_7_9_ffmpeg_bootstrap.py — KIỂM THỬ KHỞI TẠO TẬP TRUNG FFMPEG
=============================================================================
PHASE 7.9: FFMPEG GLOBAL INITIALIZATION & AUDIO ENVIRONMENT CLEANUP
T-TTS v3.0.1 — Trợ lý Giọng nói Quân đội
Tác giả: Nguyễn Văn Tiệp

Bao gồm 8 ca kiểm thử:
1. test_01_ffmpeg_path_valid: File tồn tại, quyền thực thi, version string.
2. test_02_initialization_idempotent: Gọi nhiều lần không duplicate PATH.
3. test_03_pydub_converter_assigned: AudioSegment.converter & ffmpeg hợp lệ.
4. test_04_startup_zero_runtime_warning: Khởi động subprocess độc lập 0 cảnh báo.
5. test_05_wav_to_mp3_conversion: Mã hóa WAV -> MP3 bằng ffmpeg.
6. test_06_mp3_to_audiosegment_loading: Giải mã MP3 an toàn qua load_audio_segment_safe.
7. test_07_audio_concatenation_and_ducking: Ghép timeline và ducking nhiều track.
8. test_08_missing_ffmpeg_graceful_handling: Xử lý an toàn khi thiếu binary, không crash.
"""

from __future__ import annotations

import os
import sys
import shutil
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import numpy as np

# Đảm bảo khởi tạo bootstrap trước các import pydub
from backend.ffmpeg_bootstrap import (
    initialize_ffmpeg,
    is_ffmpeg_ready,
    get_ffmpeg_path,
    get_ffmpeg_status,
)
from backend.audio_utils import (
    save_wav,
    wav_to_mp3,
    load_audio_segment_safe,
    get_audio_duration_safe,
)


class TestPhase79FFmpegBootstrap(unittest.TestCase):
    """Bộ kiểm thử tính toàn vẹn và hiệu năng của module FFmpeg Bootstrap."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="ttts_p79_test_"))
        # Đảm bảo khởi tạo trạng thái chuẩn
        initialize_ffmpeg(force_reinit=True)

    @classmethod
    def tearDownClass(cls):
        if cls.temp_dir.exists():
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
        # Khôi phục trạng thái chuẩn sau cùng
        initialize_ffmpeg(force_reinit=True)

    def test_01_ffmpeg_path_valid(self):
        """1. Kiểm tra file binary FFmpeg tồn tại và có khả năng thực thi (-version)."""
        self.assertTrue(is_ffmpeg_ready(), "FFmpeg phải ở trạng thái sẵn sàng (ready)")
        exe_path = get_ffmpeg_path()
        self.assertIsNotNone(exe_path, "Đường dẫn FFmpeg không được None")
        p = Path(exe_path)
        self.assertTrue(p.is_file(), f"Binary FFmpeg không tồn tại trên đĩa: {p}")

        # Thực thi kiểm tra trực tiếp
        res = subprocess.run(
            [str(p), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        self.assertEqual(res.returncode, 0, f"FFmpeg trả về mã lỗi: {res.returncode}")
        self.assertIn("ffmpeg version", res.stdout.lower(), "Output không chứa thông tin version FFmpeg")

        status = get_ffmpeg_status()
        self.assertTrue(status.get("available"))
        self.assertIsNotNone(status.get("version_info"))
        self.assertIsNone(status.get("error"))

    def test_02_initialization_idempotent(self):
        """2. Kiểm tra tính lũy đọng: gọi nhiều lần không làm nhân bản PATH hay đổi status."""
        initial_path = os.environ.get("PATH", "")
        initial_status = get_ffmpeg_status()

        # Gọi liên tục 5 lần
        for _ in range(5):
            st = initialize_ffmpeg()
            self.assertEqual(st.get("available"), initial_status.get("available"))
            self.assertEqual(st.get("executable_path"), initial_status.get("executable_path"))

        current_path = os.environ.get("PATH", "")
        # Kiểm tra thư mục chứa FFmpeg không xuất hiện lặp lại nhiều hơn 1 lần
        ffmpeg_dir = Path(initial_status["executable_path"]).parent
        norm_dir = os.path.normcase(os.path.normpath(str(ffmpeg_dir)))
        entries = [os.path.normcase(os.path.normpath(p)) for p in current_path.split(os.pathsep) if p]
        count = entries.count(norm_dir)
        self.assertEqual(count, 1, f"Thư mục FFmpeg bị lặp lại trong PATH ({count} lần)")

    def test_03_pydub_converter_assigned(self):
        """3. Kiểm tra AudioSegment.converter và AudioSegment.ffmpeg đã được gán chính xác."""
        from pydub import AudioSegment

        converter = getattr(AudioSegment, "converter", None)
        self.assertIsNotNone(converter, "AudioSegment.converter không được để trống")
        self.assertTrue(Path(converter).is_file(), f"Converter path không tồn tại: {converter}")

        if hasattr(AudioSegment, "ffmpeg"):
            self.assertIsNotNone(AudioSegment.ffmpeg)
            self.assertTrue(Path(AudioSegment.ffmpeg).is_file())

    def test_04_startup_zero_runtime_warning(self):
        """4. Khởi chạy tiến trình Python con độc lập: đảm bảo 0 RuntimeWarning khi import pydub."""
        python_exe = sys.executable
        code = (
            "import sys\n"
            f"sys.path.insert(0, r'{ROOT_DIR}')\n"
            "import warnings\n"
            "warnings.simplefilter('always')\n"
            "import backend\n"
            "from pydub import AudioSegment\n"
            "print('T_TTS_BOOTSTRAP_OK')\n"
        )
        res = subprocess.run(
            [python_exe, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        self.assertEqual(res.returncode, 0, f"Tiến trình con thất bại: {res.stderr}")
        self.assertIn("T_TTS_BOOTSTRAP_OK", res.stdout)

        # Cảnh báo RuntimeWarning từ pydub không được xuất hiện
        self.assertNotIn("RuntimeWarning", res.stderr, f"Phát hiện RuntimeWarning trong stderr: {res.stderr}")
        self.assertNotIn("Couldn't find ffmpeg", res.stderr, f"Phát hiện cảnh báo thiếu ffmpeg: {res.stderr}")

    def test_05_wav_to_mp3_conversion(self):
        """5. Kiểm tra chuyển đổi từ WAV sang MP3 bằng FFmpeg."""
        wav_path = self.temp_dir / "test_sine.wav"
        mp3_path = self.temp_dir / "test_sine.mp3"

        # Sinh âm thanh mẫu 1 giây 440Hz 24000Hz
        sample_rate = 24000
        t = np.linspace(0, 1.0, sample_rate, endpoint=False, dtype=np.float32)
        sine = 0.5 * np.sin(2 * np.pi * 440.0 * t)
        save_wav(wav_path, sine, sr=sample_rate)
        self.assertTrue(wav_path.is_file())

        # Chuyển đổi sang MP3
        ok = wav_to_mp3(wav_path, mp3_path)
        self.assertTrue(ok, "wav_to_mp3 phải trả về True")
        self.assertTrue(mp3_path.is_file(), "File MP3 đầu ra phải tồn tại")
        self.assertGreater(mp3_path.stat().st_size, 1024, "File MP3 phải có dung lượng hợp lệ (>1KB)")

    def test_06_mp3_to_audiosegment_loading(self):
        """6. Kiểm tra nạp MP3 thành AudioSegment an toàn thông qua load_audio_segment_safe."""
        wav_path = self.temp_dir / "test_sine.wav"
        mp3_path = self.temp_dir / "test_sine.mp3"
        if not mp3_path.is_file():
            sample_rate = 24000
            t = np.linspace(0, 1.0, sample_rate, endpoint=False, dtype=np.float32)
            sine = 0.5 * np.sin(2 * np.pi * 440.0 * t)
            save_wav(wav_path, sine, sr=sample_rate)
            wav_to_mp3(wav_path, mp3_path)

        self.assertTrue(mp3_path.is_file(), "Tệp MP3 mẫu chưa sẵn sàng")

        # Nạp tệp an toàn
        seg = load_audio_segment_safe(mp3_path)
        self.assertIsNotNone(seg)
        # Độ dài xấp xỉ 1000ms (+- 100ms do MP3 padding)
        duration_ms = len(seg)
        self.assertGreater(duration_ms, 800)
        self.assertLess(duration_ms, 1200)

        # Kiểm tra đo thời lượng safe
        dur_sec = get_audio_duration_safe(mp3_path)
        self.assertGreater(dur_sec, 0.8)
        self.assertLess(dur_sec, 1.2)

    def test_07_audio_concatenation_and_ducking(self):
        """7. Kiểm tra ghép nối âm thanh đa luồng và ducking qua pydub."""
        from pydub import AudioSegment

        # Tạo 2 phân đoạn âm thanh
        tone1 = AudioSegment.silent(duration=500, frame_rate=24000)
        tone2 = AudioSegment.silent(duration=500, frame_rate=24000)

        # Ghép nối tuần tự
        stitched = tone1 + tone2
        self.assertEqual(len(stitched), 1000)

        # Trộn đè (overlay) và hạ âm lượng (ducking)
        bg_music = AudioSegment.silent(duration=1500, frame_rate=24000)
        bg_ducked = bg_music - 12  # Giảm 12 dB
        mixed = bg_ducked.overlay(stitched, position=200)
        self.assertEqual(len(mixed), 1500)

    def test_08_missing_ffmpeg_graceful_handling(self):
        """8. Kiểm tra ứng xử an toàn, không crash khi không tìm thấy binary FFmpeg."""
        # Giả lập lỗi không tìm thấy binary
        with patch("imageio_ffmpeg.get_ffmpeg_exe", return_value=None):
            st = initialize_ffmpeg(force_reinit=True)
            self.assertFalse(st["available"])
            self.assertIsNotNone(st["error"])
            self.assertFalse(is_ffmpeg_ready())
            self.assertIsNone(get_ffmpeg_path())

        # Khôi phục trạng thái chuẩn
        restore_st = initialize_ffmpeg(force_reinit=True)
        self.assertTrue(restore_st["available"])
        self.assertTrue(is_ffmpeg_ready())


if __name__ == "__main__":
    unittest.main(verbosity=2)
