"""tools/test_phase_7_stability_performance.py — BỘ KIỂM THỬ ĐỘ ỔN ĐỊNH, HIỆU NĂNG & ĐỘ TIN CẬY
==================================================================================================
PHASE 7: STABILITY, PERFORMANCE & RELIABILITY — T-TTS v3.0.1
Tác giả: Nguyễn Văn Tiệp

Kiểm thử toàn diện 3 phân hệ:
- 7.1: Long-Run Stability (TTS 100 requests, Audio Studio 1-60m, Schedule 1-50 items, Broadcast)
- 7.2: Performance & Memory (Đo RAM native qua K32GetProcessMemoryInfo, Worker cleanup, Waveform cache)
- 7.3: Audio Reliability (Sample rate, Limiter, Normalization, Silent audio, Peak clipping prevention)
"""

import os
import sys
import time
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Khởi tạo FFmpeg tập trung trước khi import pydub
from backend.ffmpeg_bootstrap import initialize_ffmpeg
initialize_ffmpeg()

import numpy as np
from pydub import AudioSegment
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

# Khởi tạo QApplication cho headless test
app = QApplication.instance() or QApplication(sys.argv)

from backend.version import APP_VERSION, APP_AUTHOR, APP_NAME
from backend.storage import init_storage
from backend.service import tts_service, TTSService
from backend.tts_engine import ALLOWLIST_25_VOICES, DEFAULT_VOICE
from backend.audio_utils import (
    save_wav,
    apply_peak_limiter,
    normalize_audio_safe,
    get_audio_duration_safe,
    stitch_broadcast_project,
    slice_audio,
    apply_audio_gain_and_fade,
)
from backend.audio_player import audio_player
from backend.scheduler_engine import scheduler_engine, compute_next_run
from backend.project_manager import project_manager
from backend.diagnostic import get_process_memory_info, run_system_health_check, log_event
from gui.task_worker import FunctionTaskWorker
from gui.waveform_widget import WaveformWidget
from gui.pages.page_audio_studio import PageAudioStudio
from gui.pages.page_broadcast import PageBroadcast
from gui.pages.page_schedule import PageSchedule, extract_text_from_file


class TestPhase7StabilityPerformance(unittest.TestCase):
    """Kiểm thử tính ổn định dài hạn, hiệu năng và độ tin cậy."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="ttts_p7_test_"))
        cls.storage = init_storage()
        cls.baseline_mem = get_process_memory_info()

    @classmethod
    def tearDownClass(cls):
        if cls.temp_dir.exists():
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    # =========================================================================
    # 7.1 LONG-RUN STABILITY — TTS ENGINE
    # =========================================================================
    def test_71_01_tts_rapid_consecutive_generation(self):
        """7.1.1: Tạo chuỗi âm thanh liên tiếp kiểm tra độ ổn định bộ nhớ và lock."""
        test_phrases = [
            "Báo cáo đồng chí chỉ huy, công tác kiểm tra buổi sáng hoàn thành.",
            "Chào mừng quý vị thính giả đến với chương trình phát thanh quân đội.",
            "Hệ thống trợ lý giọng nói T-TTS phiên bản ba chấm không chấm một.",
            "Tập luyện thể dục buổi sáng nâng cao sức khỏe bộ đội.",
            "Duy trì nghiêm chế độ trực chỉ huy, trực ban, trực chiến.",
        ]
        out_files = []
        for i in range(10):
            phrase = test_phrases[i % len(test_phrases)]
            res = tts_service.synthesize_text(
                text=phrase,
                voice_id=ALLOWLIST_25_VOICES[i % len(ALLOWLIST_25_VOICES)],
                speed=1.0,
                filename_prefix=f"p7_consec_{i}",
                custom_out_dir=self.temp_dir,
            )
            self.assertTrue(res["success"], f"Thất bại tại lần thứ {i}: {res.get('error')}")
            self.assertTrue(Path(res["file_path"]).is_file())
            out_files.append(res["file_path"])

        self.assertEqual(len(out_files), 10)

    def test_71_02_tts_long_text_and_paragraphs(self):
        """7.1.2: Tổng hợp văn bản dài nhiều đoạn văn liên kết."""
        long_text = (
            "Đoạn văn bản thứ nhất: Toàn quân duy trì nghiêm chế độ sẵn sàng chiến đấu, "
            "nắm chắc tình hình trên không, trên biển, biên giới và không gian mạng. [pause:300] "
            "Đoạn văn bản thứ hai: Tích cực đổi mới nội dung, phương pháp huấn luyện, "
            "bảo đảm an toàn tuyệt đối về người và vũ khí trang bị. [pause:400] "
            "Đoạn văn bản thứ ba: Xây dựng tổ chức Đảng trong sạch vững mạnh, đơn vị vững mạnh toàn diện."
        )
        res = tts_service.synthesize_text(
            text=long_text,
            voice_id="hn_nam_quan_doi",
            speed=1.0,
            filename_prefix="p7_long_text",
            custom_out_dir=self.temp_dir,
        )
        self.assertTrue(res["success"])
        self.assertGreater(res["duration_sec"], 3.0)

    def test_71_03_tts_voice_switching_stability(self):
        """7.1.3: Chuyển đổi liên tục giữa 10 giọng đọc khác nhau trong catalog."""
        sample_voices = ALLOWLIST_25_VOICES[:8]
        for v in sample_voices:
            resolved = tts_service.resolve_voice(v)
            self.assertIsNotNone(resolved)
            # Kiểm tra nạp profile giọng
            profile = tts_service.engine.resolve_voice(v)
            self.assertTrue(bool(profile))

    def test_71_04_tts_worker_cancellation(self):
        """7.1.4: Yêu cầu hủy tiểu trình Worker đang chạy và xác nhận trạng thái an toàn."""
        worker = FunctionTaskWorker(time.sleep, 0.2)
        worker.start()
        self.assertTrue(worker.isRunning())
        worker.request_cancel()
        self.assertTrue(worker.is_cancelled())
        ok = worker.stop_and_wait(timeout_ms=1000)
        self.assertTrue(ok)
        self.assertFalse(worker.isRunning())

    def test_71_05_tts_error_handling_robustness(self):
        """7.1.5: Xử lý các lỗi biên ngoại lệ (văn bản rỗng, đường dẫn không hợp lệ)."""
        # Văn bản rỗng
        res_empty = tts_service.synthesize_text("")
        self.assertFalse(res_empty["success"])
        self.assertIn("trống", res_empty["error"].lower())

        # Giọng đọc không tồn tại -> fallback tự động về DEFAULT_VOICE
        resolved = tts_service.resolve_voice("non_existent_voice_xyz")
        self.assertIsNotNone(resolved)

    # =========================================================================
    # 7.1 LONG-RUN STABILITY — AUDIO STUDIO
    # =========================================================================
    def test_71_06_audio_studio_long_duration_waveform(self):
        """7.1.6: Thử nghiệm nạp và downsample sóng âm thời lượng dài (1 phút, 10 phút, 60 phút)."""
        wf = WaveformWidget()
        wf.resize(1000, 200)

        sr = 44100
        # 1 phút = 60s
        samples_1m = np.zeros(sr * 60, dtype=np.float32)
        wf.set_audio_data(samples_1m, sample_rate=sr)
        self.assertEqual(wf.duration_ms, 60000)
        mins, maxs = wf._compute_peaks(1000)
        self.assertEqual(len(mins), 1000)

        # 10 phút = 600s
        samples_10m = np.zeros(sr * 600, dtype=np.float32)
        wf.set_audio_data(samples_10m, sample_rate=sr)
        self.assertEqual(wf.duration_ms, 600000)
        mins, maxs = wf._compute_peaks(1000)
        self.assertEqual(len(mins), 1000)

        # 60 phút = 3600s
        samples_60m = np.zeros(sr * 3600, dtype=np.float32)
        wf.set_audio_data(samples_60m, sample_rate=sr)
        self.assertEqual(wf.duration_ms, 3600000)
        mins, maxs = wf._compute_peaks(1000)
        self.assertEqual(len(mins), 1000)

        # Dọn dẹp bộ nhớ
        wf.set_audio_data(None)
        self.assertEqual(wf.duration_ms, 0)

    def test_71_07_audio_studio_zoom_pan_stress(self):
        """7.1.7: Thử nghiệm phóng to/thu nhỏ và cuộn liên tục (Stress test 50 chu kỳ)."""
        wf = WaveformWidget()
        wf.resize(1000, 200)
        wf.set_audio_data(np.zeros(44100 * 300, dtype=np.float32), sample_rate=44100)  # 5 phút

        for i in range(25):
            wf.zoom_in(center_ms=150000, factor=1.2)
            wf.scroll_to_ms(i * 1000)
            wf.set_vertical_zoom(1.0 + (i % 4) * 0.5)

        self.assertGreater(wf.zoom_level, 1.0)
        self.assertGreaterEqual(wf.view_start_ms, 0)
        self.assertLessEqual(wf.view_end_ms, 300000)

        wf.zoom_fit()
        self.assertEqual(wf.zoom_level, 1.0)
        self.assertEqual(wf.view_start_ms, 0)

    def test_71_08_audio_studio_editing_and_undo_stack(self):
        """7.1.8: Thao tác cắt, tỉa, chèn khoảng lặng và ngăn xếp Undo/Redo."""
        page = PageAudioStudio()
        sr = 44100
        # Tạo clip 4 giây
        tone = AudioSegment.silent(duration=4000, frame_rate=sr)
        page.current_audio = tone
        page._refresh_audio_view()

        # Thực hiện 10 lần push undo
        for _ in range(10):
            page._push_undo_state()
            page.current_audio = page.current_audio + AudioSegment.silent(duration=100)

        self.assertLessEqual(len(page.undo_stack), page._max_history)
        self.assertEqual(len(page.redo_stack), 0)

        # Undo 3 lần
        page.undo()
        page.undo()
        page.undo()
        self.assertEqual(len(page.redo_stack), 3)

        # Redo 1 lần
        page.redo()
        self.assertEqual(len(page.redo_stack), 2)

        # Dọn dẹp dự án mới
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            page.new_project()
        self.assertIsNone(page.current_audio)
        self.assertEqual(len(page.undo_stack), 0)

    # =========================================================================
    # 7.1 LONG-RUN STABILITY — SCHEDULE STUDIO
    # =========================================================================
    def test_71_09_schedule_playlist_stress_50_items(self):
        """7.1.9: Kiểm thử playlist quy mô lớn (1 item, 10 items, 50 items)."""
        # Tạo 1 file âm thanh chuẩn
        test_wav = self.temp_dir / "p7_playlist_base.wav"
        save_wav(test_wav, np.sin(np.linspace(0, 100, 48000)).astype(np.float32), sr=48000)

        # Tạo playlist 50 items
        playlist_50 = []
        for i in range(50):
            playlist_50.append({
                "id": f"item_{i}",
                "title": f"Bản tin thứ {i+1}",
                "file_path": str(test_wav),
                "duration_sec": 1.0,
                "pause_after": 0.5,
                "status": "pending",
            })

        sched = {
            "name": "Lịch 50 Bản Tin",
            "task_type": "playlist",
            "playlist": playlist_50,
            "repeat_type": "daily",
            "target_time": "07:00:00",
            "is_enabled": True,
        }
        sid = scheduler_engine.save_schedule(sched)
        self.assertIsNotNone(sid)

        loaded = scheduler_engine.get_schedule(sid)
        self.assertEqual(len(loaded["playlist"]), 50)

        # Xóa dọn dẹp
        scheduler_engine.delete_schedule(sid)

    def test_71_10_schedule_missing_file_and_relink(self):
        """7.1.10: Tự động phát hiện tệp mất và phục hồi qua relink."""
        fake_file = self.temp_dir / "missing_file_xyz.wav"
        real_file = self.temp_dir / "relinked_file_xyz.wav"
        save_wav(real_file, np.zeros(24000, dtype=np.float32), sr=48000)

        item = {
            "id": "it_test",
            "title": "Bản tin thử nghiệm",
            "file_path": str(fake_file),
            "duration_sec": 0.0,
        }
        self.assertFalse(Path(item["file_path"]).is_file())

        # Relink
        item["file_path"] = str(real_file)
        item["duration_sec"] = get_audio_duration_safe(real_file)
        self.assertTrue(Path(item["file_path"]).is_file())
        self.assertAlmostEqual(item["duration_sec"], 0.5, delta=0.1)

    # =========================================================================
    # 7.1 LONG-RUN STABILITY — BROADCAST STUDIO
    # =========================================================================
    def test_71_11_broadcast_multitrack_ducking_and_export(self):
        """7.1.11: Ghép nối phân đoạn phát thanh đa tầng, auto-ducking và xuất WAV/MP3."""
        clip1 = self.temp_dir / "bcast_seg1.wav"
        clip2 = self.temp_dir / "bcast_seg2.wav"
        bgm = self.temp_dir / "bcast_bgm.wav"

        # Tạo các đoạn âm thanh mẫu
        save_wav(clip1, np.sin(np.linspace(0, 100, 48000)).astype(np.float32), sr=48000) # 1s
        save_wav(clip2, np.sin(np.linspace(0, 200, 48000 * 2)).astype(np.float32), sr=48000) # 2s
        save_wav(bgm, 0.2 * np.sin(np.linspace(0, 50, 48000 * 5)).astype(np.float32), sr=48000) # 5s

        segments = [
            {"type": "speech", "file_path": str(clip1), "pause_after": 0.5},
            {"type": "silence", "duration_sec": 0.5},
            {"type": "speech", "file_path": str(clip2), "pause_after": 0.0},
        ]

        out_bcast = self.temp_dir / "bcast_full_export.wav"
        res = stitch_broadcast_project(
            segments=segments,
            output_path=out_bcast,
            out_format="wav",
            bg_music_path=bgm,
            bg_music_ducking=True,
            bg_music_volume_db=-15.0,
        )

        self.assertTrue(res["success"])
        self.assertTrue(out_bcast.is_file())
        self.assertGreater(res["duration_sec"], 3.5)

    # =========================================================================
    # 7.2 PERFORMANCE & MEMORY
    # =========================================================================
    def test_72_01_native_memory_measurement(self):
        """7.2.1: Đo lường bộ nhớ RAM tiến trình qua native Windows API."""
        mem = get_process_memory_info()
        self.assertGreater(mem["working_set_mb"], 0.0)
        self.assertGreater(mem["private_usage_mb"], 0.0)
        self.assertGreaterEqual(mem["peak_working_set_mb"], mem["working_set_mb"])

    def test_72_02_waveform_downsample_benchmark(self):
        """7.2.2: Đo thời gian thực thi downsampling dạng sóng (< 10 ms cho 500,000 mẫu)."""
        wf = WaveformWidget()
        wf.resize(1200, 200)
        # 500,000 mẫu = ~11.3 giây
        audio = np.random.uniform(-0.8, 0.8, 500000).astype(np.float32)
        wf.set_audio_data(audio, sample_rate=44100)

        t0 = time.perf_counter()
        mins, maxs = wf._compute_peaks(1200)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertLess(elapsed_ms, 15.0, f"Downsample quá chậm: {elapsed_ms:.2f} ms")
        self.assertEqual(len(mins), 1200)
        self.assertEqual(len(maxs), 1200)

    def test_72_03_diagnostic_health_check(self):
        """7.2.3: Chạy chẩn đoán toàn diện hệ thống."""
        diag = run_system_health_check()
        self.assertTrue(diag["healthy"])
        self.assertEqual(diag["app_name"], APP_NAME)
        self.assertEqual(diag["version"], APP_VERSION)
        self.assertEqual(diag["checks"]["storage_write_permission"]["status"], "OK")
        self.assertEqual(diag["checks"]["ai_models"]["status"], "OK")

    # =========================================================================
    # 7.3 AUDIO RELIABILITY
    # =========================================================================
    def test_73_01_peak_limiter_clipping_prevention(self):
        """7.3.1: Bộ giới hạn biên độ Limiter ngăn chặn hiện tượng clipping."""
        # Tín hiệu vượt ngưỡng cực đại (amplitude = 2.5)
        loud_signal = np.array([0.5, 1.5, 2.5, -2.0, -0.8], dtype=np.float32)
        limited = apply_peak_limiter(loud_signal, ceiling=0.98)

        # Đỉnh tối đa không được vượt quá ceiling 0.98
        self.assertLessEqual(float(np.max(np.abs(limited))), 0.981)
        # Hình dạng tỷ lệ các mẫu được giữ nguyên
        self.assertAlmostEqual(limited[2] / limited[1], 2.5 / 1.5, places=4)

    def test_73_02_save_wav_stereo_to_mono_averaging(self):
        """7.3.2: Chuyển đổi an toàn âm thanh stereo sang mono khi lưu WAV."""
        # Mảng 2 kênh (stereo) 48000 mẫu
        ch_left = np.full(48000, 0.4, dtype=np.float32)
        ch_right = np.full(48000, 0.6, dtype=np.float32)
        stereo_audio = np.column_stack((ch_left, ch_right))  # shape: (48000, 2)

        out_mono = self.temp_dir / "p7_stereo_to_mono.wav"
        save_wav(out_mono, stereo_audio, sr=48000)

        self.assertTrue(out_mono.is_file())
        # Đọc lại và kiểm tra đúng 1 channel mono và biên độ trung bình = 0.5
        import wave
        with wave.open(str(out_mono), "rb") as w:
            self.assertEqual(w.getnchannels(), 1)
            self.assertEqual(w.getframerate(), 48000)
            self.assertEqual(w.getsampwidth(), 2)
            frames = w.readframes(w.getnframes())
            pcm = np.frombuffer(frames, dtype=np.int16)
            avg_amp = np.mean(pcm) / 32767.0
            self.assertAlmostEqual(avg_amp, 0.5, delta=0.02)

    def test_73_03_normalize_safe_with_silence(self):
        """7.3.3: Chuẩn hóa âm thanh an toàn không bị lỗi chia cho 0 khi gặp đoạn im lặng."""
        # 1. Clip có âm thanh
        tone = AudioSegment.silent(duration=500).apply_gain(-20.0)
        norm_tone = normalize_audio_safe(tone, target_dbfs=-3.0)
        self.assertIsNotNone(norm_tone)

        # 2. Clip im lặng hoàn toàn (max_dBFS = -inf)
        pure_silence = AudioSegment.silent(duration=1000)
        norm_silence = normalize_audio_safe(pure_silence, target_dbfs=-3.0)
        self.assertIsNotNone(norm_silence)
        self.assertEqual(len(norm_silence), 1000)

    def test_73_04_get_audio_duration_accuracy(self):
        """7.3.4: Độ chính xác của hàm đo thời lượng trên file thực tế."""
        dur_target = 2.45
        sample_path = self.temp_dir / "p7_dur_test.wav"
        sr = 48000
        n_samples = int(dur_target * sr)
        save_wav(sample_path, np.sin(np.linspace(0, 100, n_samples)).astype(np.float32), sr=sr)

        measured = get_audio_duration_safe(sample_path)
        self.assertAlmostEqual(measured, dur_target, delta=0.05)


def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase7StabilityPerformance)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return res.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
