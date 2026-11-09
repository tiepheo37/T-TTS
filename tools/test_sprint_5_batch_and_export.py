"""tools/test_sprint_5_batch_and_export.py
=======================================
Automated test suite for Sprint 5 (Phase 9.4 - 9.6):
1. 9.4 Batch TTS Engine: Queue control (pause, resume, cancel, retry, stitching).
2. 9.5 Unified Export Center: WAV / MP3 export, sample rate conversion, LUFS mastering.
3. 9.6 Auto Update System: Version comparison, pre-update backup, projects preservation.
"""

from __future__ import annotations

import os
import sys
import wave
import json
import unittest
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.ffmpeg_bootstrap import initialize_ffmpeg, is_ffmpeg_ready
from backend.batch_tts import batch_tts_engine
from backend.export_center import export_center
from backend.updater import UpdateManager
from backend.version import is_newer_version


def _create_dummy_wav(path: Path, duration_sec: float = 1.0) -> Path:
    sr = 48000
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    sig = 0.3 * np.sin(2 * np.pi * 440 * t)
    pcm = (sig * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


class TestSprint5BatchAndExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_ffmpeg()
        cls.ffmpeg_ok = is_ffmpeg_ready()
        cls.test_dir = PROJECT_ROOT / "temp" / "test_sprint_5"
        cls.test_dir.mkdir(parents=True, exist_ok=True)

        cls.sample_wav = cls.test_dir / "sample_source.wav"
        _create_dummy_wav(cls.sample_wav, duration_sec=2.0)

    def test_01_batch_tts_queue_controls(self):
        """Kiểm tra điều khiển hàng đợi Batch TTS (pause, resume, cancel)."""
        engine = batch_tts_engine
        self.assertFalse(engine.is_paused())
        self.assertFalse(engine.is_cancelled())

        engine.pause()
        self.assertTrue(engine.is_paused())

        engine.resume()
        self.assertFalse(engine.is_paused())

        engine.cancel()
        self.assertTrue(engine.is_cancelled())

    def test_02_batch_tts_stitching(self):
        """Kiểm tra ghép nối các phân đoạn âm thanh thành bản master hoàn chỉnh."""
        seg1_wav = self.test_dir / "seg_01.wav"
        seg2_wav = self.test_dir / "seg_02.wav"
        _create_dummy_wav(seg1_wav, 1.0)
        _create_dummy_wav(seg2_wav, 1.5)

        proj_mock = {
            "id": "doc_test_stitch",
            "data": {
                "segments": [
                    {"index": 0, "status": "completed", "audio_path": str(seg1_wav)},
                    {"index": 1, "status": "completed", "audio_path": str(seg2_wav)},
                ]
            }
        }

        out_master = self.test_dir / "master_stitched.wav"
        res_file = batch_tts_engine.stitch_project_audio(proj_mock, out_master, pause_ms=400)
        self.assertIsNotNone(res_file)
        self.assertTrue(out_master.is_file())

        with wave.open(str(out_master), "rb") as w:
            n_frames = w.getnframes()
            sr = w.getframerate()
            dur = n_frames / float(sr)
            # 1.0s + 0.4s pause + 1.5s = ~2.9s
            self.assertAlmostEqual(dur, 2.9, delta=0.2)

    def test_03_export_center_wav_with_lufs(self):
        """Kiểm tra trung tâm xuất bản tệp WAV kèm chuẩn hóa LUFS."""
        if not self.ffmpeg_ok:
            self.skipTest("FFmpeg chưa sẵn sàng.")

        out_wav = self.test_dir / "exported_master_48k.wav"
        res = export_center.export_audio(
            input_file=self.sample_wav,
            output_file=out_wav,
            fmt="wav",
            sample_rate=48000,
            apply_lufs_mastering=True,
            target_lufs=-16.0,
        )
        self.assertTrue(res["success"], f"Lỗi export WAV: {res.get('error')}")
        self.assertTrue(out_wav.is_file())
        self.assertGreater(out_wav.stat().st_size, 10000)

        with wave.open(str(out_wav), "rb") as w:
            self.assertEqual(w.getframerate(), 48000)
            self.assertEqual(w.getnchannels(), 1)

    def test_04_export_center_mp3(self):
        """Kiểm tra trung tâm xuất bản tệp MP3 với bitrate 192kbps."""
        if not self.ffmpeg_ok:
            self.skipTest("FFmpeg chưa sẵn sàng.")

        out_mp3 = self.test_dir / "exported_master_192k.mp3"
        res = export_center.export_audio(
            input_file=self.sample_wav,
            output_file=out_mp3,
            fmt="mp3",
            sample_rate=44100,
            bitrate_kbps=192,
            apply_lufs_mastering=False,
        )
        self.assertTrue(res["success"], f"Lỗi export MP3: {res.get('error')}")
        self.assertTrue(out_mp3.is_file())
        self.assertGreater(out_mp3.stat().st_size, 5000)

    def test_05_version_comparator(self):
        """Kiểm tra hàm so sánh phiên bản nhận diện chính xác v3.1.0 > v3.0.1."""
        self.assertTrue(is_newer_version("3.1.0", "3.0.1"))
        self.assertTrue(is_newer_version("v3.1.0", "v3.0.1"))
        self.assertTrue(is_newer_version("3.0.2", "3.0.1"))
        self.assertFalse(is_newer_version("3.0.1", "3.0.1"))
        self.assertFalse(is_newer_version("3.0.0", "3.0.1"))

    def test_06_pre_update_backup_with_projects(self):
        """Kiểm tra sao lưu toàn vẹn dữ liệu người dùng và dự án trước khi update."""
        fake_data_dir = self.test_dir / "mock_app_data"
        fake_data_dir.mkdir(parents=True, exist_ok=True)

        # Tạo file license giả
        (fake_data_dir / "license_state.json").write_text('{"licensed": true, "author": "Nguyễn Văn Tiệp"}', encoding="utf-8")

        # Tạo thư mục dự án
        proj_dir = fake_data_dir / "projects" / "documents"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "doc_sample.json").write_text('{"name": "Dự án phát thanh mẫu"}', encoding="utf-8")

        mgr = UpdateManager(data_dir=fake_data_dir)
        backup_file = mgr.create_pre_update_backup()

        self.assertTrue(backup_file.is_file())
        with open(backup_file, "r", encoding="utf-8") as f:
            b_data = json.load(f)

        self.assertIn("license_state.json", b_data["data_files"])
        self.assertTrue(b_data["data_files"]["license_state.json"]["licensed"])
        self.assertIn("documents\\doc_sample.json", b_data.get("projects_backup", {}) or b_data.get("projects_backup", {}))


if __name__ == "__main__":
    unittest.main()
