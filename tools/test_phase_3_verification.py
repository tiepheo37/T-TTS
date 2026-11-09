"""tools/test_phase_3_verification.py — BỘ 28 BÀI KIỂM THỬ TOÀN DIỆN PHASE 3
=============================================================================
Kiểm thử toàn diện module AUDIO STUDIO trong T-TTS v3.0.1:
- 01-04: Import các định dạng âm thanh (WAV, MP3, FLAC, OGG).
- 05-07: Waveform rendering, downsampling NumPy, zoom, playhead, selection.
- 08-14: Thao tác biên tập cơ bản (Cut, Copy, Paste, Delete, Trim, Split, Silence, Join).
- 15-19: Xử lý hiệu ứng âm thanh (Gain, Fade In, Fade Out, Normalize, BGM Ducking/Looping).
- 20: Hệ thống Undo / Redo nhiều bước.
- 21-22: Xuất bản âm thanh (WAV PCM 16-bit, MP3).
- 23-25: Quản lý Project (Lưu JSON, Nạp Project, Xử lý file nguồn thất lạc).
- 26: Kiểm thử âm thanh dài (Long Audio 5+ phút) & Giới hạn RAM.
- 27: Luồng xử lý nền không khóa GUI (TaskWorker / Threading).
- 28: Kiểm thử tích hợp MainWindow (13 Tabs, Tab 9 Audio Studio, không hồi quy).
"""

import os
import sys
import tempfile
import unittest
import subprocess
import numpy as np
from pathlib import Path

# Đảm bảo đường dẫn import
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Cấu hình ffmpeg cho pydub
ffmpeg_exe = None
try:
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    if ffmpeg_exe and os.path.exists(ffmpeg_exe):
        ffmpeg_dir = os.path.dirname(ffmpeg_exe)
        if ffmpeg_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

from pydub import AudioSegment
from pydub.effects import normalize as pydub_normalize
from pydub.generators import Sine

if ffmpeg_exe and os.path.exists(ffmpeg_exe):
    try:
        AudioSegment.converter = ffmpeg_exe
    except Exception:
        pass

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from gui.waveform_widget import WaveformWidget, format_ms_to_time
from gui.pages.page_audio_studio import PageAudioStudio
from gui.main_window import MainWindow
from backend.project_manager import project_manager


app = QApplication.instance() or QApplication(sys.argv)


class TestPhase3AudioStudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.work_dir = Path(cls.temp_dir.name)

        # Tạo file âm thanh mẫu chuẩn (Sine 440Hz, 3 giây, -10 dBFS để test gain)
        tone_3s = Sine(440).to_audio_segment(duration=3000).apply_gain(-10.0)
        cls.wav_path = cls.work_dir / "test_3s.wav"
        cls.mp3_path = cls.work_dir / "test_3s.mp3"
        cls.flac_path = cls.work_dir / "test_3s.flac"
        cls.ogg_path = cls.work_dir / "test_3s.ogg"

        tone_3s.export(str(cls.wav_path), format="wav")
        tone_3s.export(str(cls.mp3_path), format="mp3")
        tone_3s.export(str(cls.flac_path), format="flac")
        tone_3s.export(str(cls.ogg_path), format="ogg")

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    # -------------------------------------------------------------
    # 01 - 04: IMPORT TESTS
    # -------------------------------------------------------------
    def test_01_import_wav(self):
        page = PageAudioStudio()
        ok = page.load_audio_file(str(self.wav_path))
        self.assertTrue(ok)
        self.assertIsNotNone(page.current_audio)
        self.assertAlmostEqual(len(page.current_audio), 3000, delta=50)

    def test_02_import_mp3(self):
        page = PageAudioStudio()
        ok = page.load_audio_file(str(self.mp3_path))
        self.assertTrue(ok)
        self.assertIsNotNone(page.current_audio)
        self.assertAlmostEqual(len(page.current_audio), 3000, delta=100)

    def test_03_import_flac(self):
        page = PageAudioStudio()
        ok = page.load_audio_file(str(self.flac_path))
        self.assertTrue(ok)
        self.assertIsNotNone(page.current_audio)
        self.assertAlmostEqual(len(page.current_audio), 3000, delta=50)

    def test_04_import_ogg(self):
        page = PageAudioStudio()
        ok = page.load_audio_file(str(self.ogg_path))
        self.assertTrue(ok)
        self.assertIsNotNone(page.current_audio)
        self.assertAlmostEqual(len(page.current_audio), 3000, delta=100)

    # -------------------------------------------------------------
    # 05 - 07: WAVEFORM & NAVIGATION TESTS
    # -------------------------------------------------------------
    def test_05_waveform_downsampling(self):
        wf = WaveformWidget()
        samples = np.sin(np.linspace(0, 2 * np.pi * 440 * 3, 132300)).astype(np.float32)
        wf.set_audio_data(samples, 44100)
        self.assertEqual(wf.duration_ms, 3000)
        peaks = wf._get_downsampled_peaks(800)
        self.assertEqual(len(peaks[0]), 800)
        self.assertEqual(len(peaks[1]), 800)
        self.assertTrue(np.all(peaks[0] <= 0.05))
        self.assertTrue(np.all(peaks[1] >= -0.05))

    def test_06_waveform_zooming(self):
        wf = WaveformWidget()
        wf.set_audio_data(np.zeros(44100, dtype=np.float32), 44100)
        self.assertEqual(wf.zoom_level, 1.0)
        wf.zoom_in()
        self.assertGreater(wf.zoom_level, 1.0)
        wf.zoom_out()
        self.assertAlmostEqual(wf.zoom_level, 1.0, places=2)
        wf.zoom_fit()
        self.assertEqual(wf.zoom_level, 1.0)

    def test_07_playhead_selection(self):
        wf = WaveformWidget()
        wf.set_audio_data(np.zeros(44100 * 5, dtype=np.float32), 44100)
        wf.set_playhead_ms(1500)
        self.assertEqual(wf.playhead_ms, 1500)
        wf.set_selection_range(500, 2000)
        self.assertEqual(wf.sel_start_ms, 500)
        self.assertEqual(wf.sel_end_ms, 2000)
        wf.clear_selection()
        self.assertEqual(wf.sel_start_ms, 0)
        self.assertEqual(wf.sel_end_ms, 0)

    # -------------------------------------------------------------
    # 08 - 14: EDITING OPERATIONS
    # -------------------------------------------------------------
    def test_08_cut_operation(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path)) # 3000ms
        page.waveform.set_selection_range(1000, 2000)
        page.cut_selection()
        self.assertIsNotNone(page.clipboard_audio)
        self.assertAlmostEqual(len(page.clipboard_audio), 1000, delta=20)
        self.assertAlmostEqual(len(page.current_audio), 2000, delta=20)

    def test_09_copy_paste_operation(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path)) # 3000ms
        page.waveform.set_selection_range(0, 1000)
        page.copy_selection()
        self.assertIsNotNone(page.clipboard_audio)
        self.assertAlmostEqual(len(page.clipboard_audio), 1000, delta=20)
        page.waveform.set_playhead_ms(3000)
        page.paste_audio()
        self.assertAlmostEqual(len(page.current_audio), 4000, delta=40)

    def test_10_delete_operation(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path)) # 3000ms
        page.waveform.set_selection_range(500, 1500)
        page.delete_selection()
        self.assertAlmostEqual(len(page.current_audio), 2000, delta=20)

    def test_11_trim_operation(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path)) # 3000ms
        page.waveform.set_selection_range(1000, 1800)
        page.trim_selection()
        self.assertAlmostEqual(len(page.current_audio), 800, delta=20)

    def test_12_split_operation(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path)) # 3000ms
        page.waveform.set_playhead_ms(1200)
        page.split_at_playhead()
        self.assertAlmostEqual(len(page.current_audio), 3200, delta=50)

    def test_13_insert_silence(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path)) # 3000ms
        page.waveform.set_playhead_ms(1000)
        page.insert_silence(500)
        self.assertAlmostEqual(len(page.current_audio), 3500, delta=20)

    def test_14_join_audio(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path)) # 3000ms
        second_audio = AudioSegment.from_file(str(self.wav_path))
        page.append_audio_segment(second_audio)
        self.assertAlmostEqual(len(page.current_audio), 6000, delta=50)

    # -------------------------------------------------------------
    # 15 - 19: EFFECTS & DSP
    # -------------------------------------------------------------
    def test_15_apply_gain(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path))
        initial_db = page.current_audio.dBFS
        page.apply_gain(3.0)
        new_db = page.current_audio.dBFS
        self.assertAlmostEqual(new_db - initial_db, 3.0, delta=0.5)

    def test_16_fade_in(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path))
        page.waveform.set_selection_range(0, 1000)
        page.apply_fade_effect(is_in=True, ms=1000)
        first_50ms = page.current_audio[:50]
        self.assertLess(first_50ms.dBFS, -20.0)

    def test_17_fade_out(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path))
        page.waveform.set_selection_range(2000, 3000)
        page.apply_fade_effect(is_in=False, ms=1000)
        last_50ms = page.current_audio[-50:]
        self.assertLess(last_50ms.dBFS, -20.0)

    def test_18_normalize_audio(self):
        quiet_seg = Sine(440).to_audio_segment(duration=1000).apply_gain(-20.0)
        temp_quiet = self.work_dir / "quiet.wav"
        quiet_seg.export(str(temp_quiet), format="wav")
        page = PageAudioStudio()
        page.load_audio_file(str(temp_quiet))
        self.assertLess(page.current_audio.max_dBFS, -15.0)
        page.normalize_audio()
        self.assertAlmostEqual(page.current_audio.max_dBFS, 0.0, delta=0.5)

    def test_19_bgm_overlay(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path)) # 3000ms
        bgm_seg = Sine(220).to_audio_segment(duration=2000)
        bgm_file = self.work_dir / "bgm_sample.wav"
        bgm_seg.export(str(bgm_file), format="wav")

        page.mix_bgm_file(str(bgm_file), volume_pct=15, loop=True)
        self.assertAlmostEqual(len(page.current_audio), 3000, delta=50)

    # -------------------------------------------------------------
    # 20: UNDO / REDO
    # -------------------------------------------------------------
    def test_20_undo_redo_stack(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path)) # 3000ms
        self.assertEqual(len(page.undo_stack), 0)

        # Xóa 1000ms
        page.waveform.set_selection_range(0, 1000)
        page.delete_selection()
        self.assertAlmostEqual(len(page.current_audio), 2000, delta=20)
        self.assertEqual(len(page.undo_stack), 1)

        # Undo -> quay lại 3000ms
        page.undo()
        self.assertAlmostEqual(len(page.current_audio), 3000, delta=20)
        self.assertEqual(len(page.redo_stack), 1)

        # Redo -> quay lại 2000ms
        page.redo()
        self.assertAlmostEqual(len(page.current_audio), 2000, delta=20)

    # -------------------------------------------------------------
    # 21 - 22: EXPORT TESTS
    # -------------------------------------------------------------
    def test_21_export_wav(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path))
        out_wav = self.work_dir / "exported.wav"
        ok = page.export_to_file(str(out_wav), format_type="wav")
        self.assertTrue(ok)
        self.assertTrue(out_wav.is_file())
        self.assertGreater(out_wav.stat().st_size, 1000)
        loaded = AudioSegment.from_wav(str(out_wav))
        self.assertAlmostEqual(len(loaded), 3000, delta=50)

    def test_22_export_mp3(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path))
        out_mp3 = self.work_dir / "exported.mp3"
        ok = page.export_to_file(str(out_mp3), format_type="mp3")
        self.assertTrue(ok)
        self.assertTrue(out_mp3.is_file())
        self.assertGreater(out_mp3.stat().st_size, 1000)
        
        # Xác minh MP3 hợp lệ bằng ffmpeg binary nếu có
        if ffmpeg_exe and os.path.exists(ffmpeg_exe):
            res = subprocess.run(
                [ffmpeg_exe, "-v", "error", "-i", str(out_mp3), "-f", "null", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            self.assertEqual(res.returncode, 0)

    # -------------------------------------------------------------
    # 23 - 25: PROJECT MANAGEMENT TESTS
    # -------------------------------------------------------------
    def test_23_save_project(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path))
        proj_data = page.build_project_dict(name="Test Audio Project")
        proj_id = project_manager.save_project("audio", proj_data)
        self.assertIsNotNone(proj_id)
        proj_file = PROJECT_ROOT / "data" / "projects" / "audio" / f"{proj_id}.json"
        self.assertTrue(proj_file.is_file())

    def test_24_open_project(self):
        page = PageAudioStudio()
        page.load_audio_file(str(self.wav_path))
        proj_data = page.build_project_dict(name="Test Open Project")
        proj_id = project_manager.save_project("audio", proj_data)

        page2 = PageAudioStudio()
        loaded_dict = project_manager.load_project("audio", proj_id)
        self.assertIsNotNone(loaded_dict)
        ok = page2.restore_from_project_dict(loaded_dict)
        self.assertTrue(ok)
        self.assertIsNotNone(page2.current_audio)
        self.assertAlmostEqual(len(page2.current_audio), 3000, delta=50)

    def test_25_missing_source_handling(self):
        page = PageAudioStudio()
        fake_dict = {
            "name": "Ghost Project",
            "source_path": "Z:\\non_existent_drive\\fake_sound.wav",
            "edits": []
        }
        ok = page.restore_from_project_dict(fake_dict)
        self.assertFalse(ok)

    # -------------------------------------------------------------
    # 26: LONG AUDIO MEMORY TEST
    # -------------------------------------------------------------
    def test_26_long_audio_performance(self):
        long_seg = AudioSegment.silent(duration=300000, frame_rate=44100)
        self.assertEqual(len(long_seg), 300000)
        samples = np.array(long_seg.get_array_of_samples(), dtype=np.float32)
        wf = WaveformWidget()
        wf.set_audio_data(samples, 44100)
        self.assertEqual(wf.duration_ms, 300000)
        peaks = wf._get_downsampled_peaks(1000)
        self.assertEqual(len(peaks[0]), 1000)
        self.assertLess(sys.getsizeof(peaks[0]) + sys.getsizeof(peaks[1]), 50 * 1024 * 1024)

    # -------------------------------------------------------------
    # 27: UI THREADING TEST
    # -------------------------------------------------------------
    def test_27_ui_worker_threading(self):
        from gui.task_worker import FunctionTaskWorker
        results = []
        def heavy_calc():
            return sum(i * i for i in range(100000))
        worker = FunctionTaskWorker(heavy_calc)
        worker.result_ready.connect(lambda res: results.append(res))
        worker.run()
        self.assertEqual(len(results), 1)
        self.assertGreater(results[0], 0)

    # -------------------------------------------------------------
    # 28: MAINWINDOW INTEGRATION & REGRESSION TEST
    # -------------------------------------------------------------
    def test_28_regression_and_sidebar(self):
        win = MainWindow()
        self.assertEqual(win.stack.count(), 13)
        self.assertEqual(win.stack.widget(0).__class__.__name__, "PageSynthesize")
        self.assertEqual(win.stack.widget(1).__class__.__name__, "PageClone")
        self.assertEqual(win.stack.widget(2).__class__.__name__, "PageBatch")
        self.assertEqual(win.stack.widget(3).__class__.__name__, "PageBroadcast")
        self.assertEqual(win.stack.widget(4).__class__.__name__, "PagePodcast")
        self.assertEqual(win.stack.widget(5).__class__.__name__, "PageVoices")
        self.assertEqual(win.stack.widget(6).__class__.__name__, "PagePronDict")
        self.assertEqual(win.stack.widget(7).__class__.__name__, "PageHistory")
        self.assertEqual(win.stack.widget(8).__class__.__name__, "PageSchedule")
        self.assertEqual(win.stack.widget(9).__class__.__name__, "PageAudioStudio")
        self.assertEqual(win.stack.widget(10).__class__.__name__, "PageSettings")
        self.assertEqual(win.stack.widget(11).__class__.__name__, "PageAbout")
        self.assertEqual(win.stack.widget(12).__class__.__name__, "PageGuide")

        win._switch_tab(9)
        self.assertEqual(win.stack.currentIndex(), 9)

        if win.loader_thread:
            win.loader_thread.wait()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase3AudioStudio)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
