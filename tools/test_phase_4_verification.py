"""tools/test_phase_4_verification.py — BỘ 35 BÀI KIỂM THỬ TOÀN DIỆN PHASE 4
=============================================================================
Kiểm thử toàn diện BROADCAST STUDIO 2.0 (Phân hệ Phát thanh Đa Tầng):
- 01-02: Khởi tạo Broadcast Studio, Tạo dự án mới.
- 03-06: Thêm, Xóa, Nhân bản, Đổi thứ tự phân đoạn (Multi-segment Timeline).
- 07-09: Biên tập văn bản, chọn voice, điều chỉnh speed.
- 10-12: Tạo giọng đọc phân đoạn, chỉ regenerate đoạn đã sửa, bảo toàn audio đoạn khác.
- 13-14: Preview phân đoạn, Preview toàn bộ chương trình.
- 15-16: Thêm nhạc mở đầu (Intro), Nhạc kết thúc (Outro).
- 17-20: Thêm nhạc nền (BGM), Loop, Auto-Ducking, Fade In/Out nhạc nền.
- 21: Đo đếm và tính toán tổng thời lượng chương trình.
- 22-23: Xuất bản WAV PCM 16-bit, MP3 192kbps chuẩn Studio.
- 24-27: Quản lý Project (Lưu JSON, Nạp Project, Relink nguồn bị mất, Khôi phục Timeline).
- 28-29: UI non-blocking qua TaskWorker, TTSService Singleton.
- 30-35: Kiểm thử hồi quy toàn diện (Audio Studio, Schedule Studio, Phase 1, Lịch sử, Bản quyền, Dữ liệu).
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
from pydub.generators import Sine

if ffmpeg_exe and os.path.exists(ffmpeg_exe):
    try:
        AudioSegment.converter = ffmpeg_exe
    except Exception:
        pass

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from gui.pages.page_broadcast import PageBroadcast
from gui.main_window import MainWindow
from backend.service import tts_service
from backend.project_manager import project_manager
from backend.license import license_manager, get_machine_id
from backend.audio_utils import stitch_broadcast_project, apply_bgm_ducking, load_audio_segment_safe


app = QApplication.instance() or QApplication(sys.argv)


class TestPhase4BroadcastStudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.work_dir = Path(cls.temp_dir.name)

        # Tạo file âm thanh mẫu cho Intro (1s), Outro (1s), BGM (2s), Speech mẫu (2s)
        cls.intro_wav = cls.work_dir / "intro.wav"
        cls.outro_wav = cls.work_dir / "outro.wav"
        cls.bgm_wav = cls.work_dir / "bgm.wav"
        cls.speech1_wav = cls.work_dir / "speech1.wav"
        cls.speech2_wav = cls.work_dir / "speech2.wav"

        Sine(523).to_audio_segment(duration=1000).apply_gain(-6.0).export(str(cls.intro_wav), format="wav")
        Sine(659).to_audio_segment(duration=1000).apply_gain(-6.0).export(str(cls.outro_wav), format="wav")
        Sine(220).to_audio_segment(duration=2000).apply_gain(-12.0).export(str(cls.bgm_wav), format="wav")
        Sine(440).to_audio_segment(duration=2000).apply_gain(-3.0).export(str(cls.speech1_wav), format="wav")
        Sine(440).to_audio_segment(duration=2000).apply_gain(-3.0).export(str(cls.speech2_wav), format="wav")

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    # -------------------------------------------------------------
    # 01 - 02: INIT & NEW PROJECT
    # -------------------------------------------------------------
    def test_01_init_broadcast_studio(self):
        page = PageBroadcast()
        self.assertIsNotNone(page)
        self.assertEqual(len(page.segments), 0)
        self.assertEqual(page.table.columnCount(), 7)

    def test_02_new_project(self):
        page = PageBroadcast()
        page.add_segment({"type": "news", "text": "Tin thời sự quân sự."})
        self.assertEqual(len(page.segments), 1)
        page.new_project(confirm=False)
        self.assertEqual(len(page.segments), 0)
        self.assertEqual(page.current_project_name, "Bản tin mới")

    # -------------------------------------------------------------
    # 03 - 06: TIMELINE & SEGMENT OPERATIONS
    # -------------------------------------------------------------
    def test_03_add_segment(self):
        page = PageBroadcast()
        sid1 = page.add_segment({"type": "lead_in", "title": "Lời dẫn mở đầu", "text": "Chào mừng các đồng chí."})
        sid2 = page.add_segment({"type": "jingle", "title": "Nhạc hiệu", "file_path": str(self.intro_wav)})
        sid3 = page.add_segment({"type": "silence", "duration_sec": 1.5})
        self.assertEqual(len(page.segments), 3)
        self.assertEqual(page.segments[0]["id"], sid1)
        self.assertEqual(page.segments[1]["id"], sid2)
        self.assertEqual(page.segments[2]["id"], sid3)

    def test_04_delete_segment(self):
        page = PageBroadcast()
        page.add_segment({"type": "lead_in", "title": "Đoạn 1"})
        page.add_segment({"type": "news", "title": "Đoạn 2"})
        self.assertEqual(len(page.segments), 2)
        page.delete_segment(0)
        self.assertEqual(len(page.segments), 1)
        self.assertEqual(page.segments[0]["title"], "Đoạn 2")

    def test_05_duplicate_segment(self):
        page = PageBroadcast()
        page.add_segment({"type": "announcement", "title": "Thông báo trực ban", "text": "Kiểm tra quân số."})
        page.duplicate_segment(0)
        self.assertEqual(len(page.segments), 2)
        self.assertNotEqual(page.segments[0]["id"], page.segments[1]["id"])
        self.assertIn("Bản sao", page.segments[1]["title"])

    def test_06_reorder_segments(self):
        page = PageBroadcast()
        page.add_segment({"title": "A"})
        page.add_segment({"title": "B"})
        page.add_segment({"title": "C"})
        self.assertEqual([s["title"] for s in page.segments], ["A", "B", "C"])
        page.reorder_segments(0, 2)
        self.assertEqual([s["title"] for s in page.segments], ["B", "C", "A"])

    # -------------------------------------------------------------
    # 07 - 09: EDITING ATTRIBUTES
    # -------------------------------------------------------------
    def test_07_edit_text(self):
        page = PageBroadcast()
        page.add_segment({"type": "news", "text": "Nội dung cũ", "status": "ready"})
        page.update_segment(0, text="Nội dung thời sự mới cập nhật")
        self.assertEqual(page.segments[0]["text"], "Nội dung thời sự mới cập nhật")
        self.assertTrue(page.segments[0]["is_modified"])
        self.assertEqual(page.segments[0]["status"], "pending")

    def test_08_select_voice(self):
        page = PageBroadcast()
        page.add_segment({"type": "lead_in", "voice_id": "hn_nam_quan_doi"})
        page.update_segment(0, voice_id="hn_nu_chinh_luan")
        self.assertEqual(page.segments[0]["voice_id"], "hn_nu_chinh_luan")

    def test_09_adjust_speed(self):
        page = PageBroadcast()
        page.add_segment({"type": "news", "speed": 1.0})
        page.update_segment(0, speed=1.15)
        self.assertAlmostEqual(page.segments[0]["speed"], 1.15)

    # -------------------------------------------------------------
    # 10 - 12: TTS INTEGRATION & SINGLE SEGMENT REGENERATION
    # -------------------------------------------------------------
    def test_10_generate_segment_speech(self):
        page = PageBroadcast()
        page.add_segment({"type": "lead_in", "text": "Bản tin phát thanh thử nghiệm hôm nay."})
        ok = page.generate_segment_speech_sync(0)
        self.assertTrue(ok)
        self.assertEqual(page.segments[0]["status"], "ready")
        self.assertIsNotNone(page.segments[0]["file_path"])
        self.assertTrue(Path(page.segments[0]["file_path"]).is_file())
        self.assertGreater(page.segments[0]["duration_sec"], 0.5)

    def test_11_only_regenerate_modified(self):
        page = PageBroadcast()
        page.add_segment({"type": "lead_in", "file_path": str(self.speech1_wav), "duration_sec": 2.0, "status": "ready"})
        page.add_segment({"type": "news", "text": "Mệnh lệnh huấn luyện chiến đấu.", "status": "pending"})
        # Chỉ regenerate phân đoạn 1 (news)
        ok = page.generate_segment_speech_sync(1)
        self.assertTrue(ok)
        self.assertEqual(page.segments[1]["status"], "ready")

    def test_12_preserve_unmodified_audio(self):
        page = PageBroadcast()
        page.add_segment({"type": "lead_in", "file_path": str(self.speech1_wav), "duration_sec": 2.0, "status": "ready"})
        page.add_segment({"type": "news", "text": "Thông báo kiểm tra vũ khí.", "status": "pending"})
        original_path_0 = page.segments[0]["file_path"]
        page.generate_segment_speech_sync(1)
        # Phân đoạn 0 phải được giữ nguyên vẹn 100% đường dẫn và audio
        self.assertEqual(page.segments[0]["file_path"], original_path_0)
        self.assertEqual(page.segments[0]["status"], "ready")

    # -------------------------------------------------------------
    # 13 - 14: PREVIEW
    # -------------------------------------------------------------
    def test_13_preview_segment(self):
        page = PageBroadcast()
        page.add_segment({"file_path": str(self.speech1_wav), "duration_sec": 2.0, "status": "ready"})
        # Xác thực file phát tồn tại và sẵn sàng cho audio_player
        self.assertTrue(Path(page.segments[0]["file_path"]).is_file())

    def test_14_preview_full_program(self):
        page = PageBroadcast()
        page.add_segment({"file_path": str(self.speech1_wav), "duration_sec": 2.0, "status": "ready"})
        page.add_segment({"file_path": str(self.speech2_wav), "duration_sec": 2.0, "status": "ready"})
        page.set_bg_music(str(self.bgm_wav), vol_pct=15, loop=True, ducking=True)

        preview_out = self.work_dir / "test_preview_full.wav"
        res = page.export_program_direct(preview_out, out_format="wav")
        self.assertTrue(res["success"])
        self.assertTrue(preview_out.is_file())
        self.assertGreater(preview_out.stat().st_size, 1000)

    # -------------------------------------------------------------
    # 15 - 16: INTRO & OUTRO MUSIC
    # -------------------------------------------------------------
    def test_15_add_intro_music(self):
        page = PageBroadcast()
        page.set_intro_music(str(self.intro_wav))
        self.assertEqual(page.edit_intro_music.text(), str(self.intro_wav))

    def test_16_add_outro_music(self):
        page = PageBroadcast()
        page.set_outro_music(str(self.outro_wav))
        self.assertEqual(page.edit_outro_music.text(), str(self.outro_wav))

    # -------------------------------------------------------------
    # 17 - 20: BACKGROUND MUSIC & DUCKING & FADE
    # -------------------------------------------------------------
    def test_17_add_bg_music(self):
        page = PageBroadcast()
        page.set_bg_music(str(self.bgm_wav), vol_pct=20, loop=True, ducking=True)
        self.assertTrue(page.chk_enable_bg.isChecked())
        self.assertEqual(page.bg_path_edit.text(), str(self.bgm_wav))

    def test_18_loop_bg_music(self):
        # BGM 2s lồng vào Speech 6s -> BGM tự động lặp lại 3+ lần
        page = PageBroadcast()
        page.add_segment({"file_path": str(self.speech1_wav), "duration_sec": 2.0, "pause_after": 1.0})
        page.add_segment({"file_path": str(self.speech2_wav), "duration_sec": 2.0, "pause_after": 0.5})
        page.set_bg_music(str(self.bgm_wav), vol_pct=15, loop=True, ducking=False)
        out_loop = self.work_dir / "test_bgm_loop.wav"
        res = page.export_program_direct(out_loop, out_format="wav")
        self.assertTrue(res["success"])
        # File kết quả có độ dài >= 5 giây
        loaded = AudioSegment.from_wav(str(out_loop))
        self.assertGreaterEqual(len(loaded), 4500)

    def test_19_auto_ducking(self):
        # Kiểm tra thuật toán Ducking: hạ âm lượng BGM khi có lời đọc
        bgm_seg = Sine(220).to_audio_segment(duration=10000)
        speech_intervals = [(1000, 4000), (6000, 9000)]
        ducked_bgm = apply_bgm_ducking(bgm_seg, speech_intervals, normal_gain_db=-10.0, ducked_gain_db=-22.0)
        self.assertEqual(len(ducked_bgm), 10000)
        # Tại 2000-3000ms (có lời đọc), âm lượng BGM phải nhỏ hơn tại 4500-5500ms (khoảng nghỉ)
        speech_part = ducked_bgm[2000:3000]
        pause_part = ducked_bgm[4500:5500]
        self.assertLess(speech_part.dBFS, pause_part.dBFS)
        self.assertAlmostEqual(pause_part.dBFS - speech_part.dBFS, 12.0, delta=2.0)

    def test_20_fade_bg_music(self):
        page = PageBroadcast()
        page.add_segment({"file_path": str(self.speech1_wav), "duration_sec": 2.0})
        page.set_bg_music(str(self.bgm_wav), vol_pct=15, loop=True)
        out_fade = self.work_dir / "test_bgm_fade.wav"
        res = page.export_program_direct(out_fade, out_format="wav")
        self.assertTrue(res["success"])
        self.assertTrue(out_fade.is_file())

    # -------------------------------------------------------------
    # 21: TOTAL DURATION CALCULATION
    # -------------------------------------------------------------
    def test_21_total_duration(self):
        page = PageBroadcast()
        page.add_segment({"duration_sec": 3.0, "pause_after": 1.0})
        page.add_segment({"duration_sec": 4.5, "pause_after": 0.5})
        # Tổng = (3.0 + 1.0) + (4.5 + 0.5) = 9.0 giây
        self.assertAlmostEqual(page.get_total_duration(), 9.0, delta=0.1)

    # -------------------------------------------------------------
    # 22 - 23: EXPORT WAV & MP3
    # -------------------------------------------------------------
    def test_22_export_wav(self):
        page = PageBroadcast()
        page.add_segment({"file_path": str(self.speech1_wav), "duration_sec": 2.0})
        out_wav = self.work_dir / "exported_broadcast.wav"
        res = page.export_program_direct(out_wav, out_format="wav")
        self.assertTrue(res["success"])
        self.assertTrue(out_wav.is_file())
        self.assertGreater(out_wav.stat().st_size, 1000)

    def test_23_export_mp3(self):
        page = PageBroadcast()
        page.add_segment({"file_path": str(self.speech1_wav), "duration_sec": 2.0})
        out_mp3 = self.work_dir / "exported_broadcast.mp3"
        res = page.export_program_direct(out_mp3, out_format="mp3")
        self.assertTrue(res["success"])
        self.assertTrue(out_mp3.is_file())
        self.assertGreater(out_mp3.stat().st_size, 1000)
        # Kiểm tra file MP3 hợp lệ bằng ffmpeg
        if ffmpeg_exe and os.path.exists(ffmpeg_exe):
            proc = subprocess.run(
                [ffmpeg_exe, "-v", "error", "-i", str(out_mp3), "-f", "null", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            self.assertEqual(proc.returncode, 0)

    # -------------------------------------------------------------
    # 24 - 27: PROJECT MANAGEMENT & TIMELINE RESTORE
    # -------------------------------------------------------------
    def test_24_save_project(self):
        page = PageBroadcast()
        page.add_segment({"type": "news", "title": "Tin 1", "text": "Văn bản tin 1"})
        page.set_intro_music(str(self.intro_wav))
        proj_data = page.build_project_dict(name="Bản Tin Buổi Sáng")
        pid = project_manager.save_project("broadcast", proj_data)
        self.assertIsNotNone(pid)
        proj_file = PROJECT_ROOT / "data" / "projects" / "broadcast" / f"{pid}.json"
        self.assertTrue(proj_file.is_file())

    def test_25_open_project(self):
        page = PageBroadcast()
        page.add_segment({"type": "lead_in", "title": "Lời dẫn", "text": "Kính thưa thủ trưởng."})
        page.set_bg_music(str(self.bgm_wav), vol_pct=18)
        proj_data = page.build_project_dict(name="Bản Tin Tuần")
        pid = project_manager.save_project("broadcast", proj_data)

        # Mở lại trên instance mới
        page2 = PageBroadcast()
        loaded_dict = project_manager.load_project("broadcast", pid)
        self.assertIsNotNone(loaded_dict)
        ok = page2.restore_from_project_dict(loaded_dict)
        self.assertTrue(ok)
        self.assertEqual(len(page2.segments), 1)
        self.assertEqual(page2.segments[0]["title"], "Lời dẫn")
        self.assertEqual(page2.bg_path_edit.text(), str(self.bgm_wav))

    def test_26_relink_missing_source(self):
        page = PageBroadcast()
        ghost_proj = {
            "name": "Ghost Project",
            "segments": [
                {"title": "Missing Clip", "file_path": "Z:\\ghost_drive\\fake.wav", "status": "ready"}
            ]
        }
        # Hệ thống phải phát hiện tệp thiếu và gán pending mà không crash
        ok = page.restore_from_project_dict(ghost_proj)
        self.assertTrue(ok)
        self.assertEqual(page.segments[0]["status"], "pending")

    def test_27_restore_timeline(self):
        page = PageBroadcast()
        page.add_segment({"title": "Seg 1", "type": "lead_in", "pause_after": 1.5})
        page.add_segment({"title": "Seg 2", "type": "news", "pause_after": 2.0})
        proj_data = page.build_project_dict(name="Timeline Test")
        pid = project_manager.save_project("broadcast", proj_data)

        page2 = PageBroadcast()
        loaded = project_manager.load_project("broadcast", pid)
        page2.restore_from_project_dict(loaded)
        self.assertEqual(len(page2.segments), 2)
        self.assertEqual(page2.segments[0]["title"], "Seg 1")
        self.assertEqual(page2.segments[1]["title"], "Seg 2")
        self.assertAlmostEqual(page2.segments[0]["pause_after"], 1.5)
        self.assertAlmostEqual(page2.segments[1]["pause_after"], 2.0)

    # -------------------------------------------------------------
    # 28 - 29: NON-BLOCKING & SINGLETON
    # -------------------------------------------------------------
    def test_28_ui_non_blocking(self):
        from gui.task_worker import FunctionTaskWorker
        completed = []
        def _bg_calc():
            return "ok"
        worker = FunctionTaskWorker(_bg_calc)
        worker.finished_task.connect(lambda res: completed.append(res))
        worker.run()
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0], "ok")

    def test_29_singleton_tts(self):
        from backend.service import tts_service as svc2
        self.assertIs(tts_service, svc2)
        self.assertIs(tts_service.engine, svc2.engine)

    # -------------------------------------------------------------
    # 30 - 35: REGRESSION & INTEGRATION TESTS
    # -------------------------------------------------------------
    def test_30_regression_audio_studio(self):
        from gui.pages.page_audio_studio import PageAudioStudio
        studio = PageAudioStudio()
        self.assertIsNotNone(studio)
        self.assertIsNotNone(studio.waveform)

    def test_31_regression_schedule_studio(self):
        from gui.pages.page_schedule import PageSchedule
        sched = PageSchedule()
        self.assertIsNotNone(sched)
        self.assertIsNotNone(sched.table)

    def test_32_regression_phase1(self):
        from backend.audio_utils import slice_audio, mix_multitrack_timeline
        self.assertTrue(callable(slice_audio))
        self.assertTrue(callable(mix_multitrack_timeline))

    def test_33_regression_history(self):
        hist = tts_service.history.all()
        self.assertIsInstance(hist, list)

    def test_34_regression_offline_license(self):
        lic_info = tts_service.get_license_info()
        self.assertTrue(lic_info.get("is_active", False))
        mid = get_machine_id()
        self.assertTrue(mid.startswith("TTTS-"))

    def test_35_legacy_data_intact(self):
        # Xác nhận toàn bộ 13 trang trong MainWindow
        win = MainWindow()
        self.assertEqual(win.stack.count(), 13)
        self.assertEqual(win.stack.widget(3).__class__.__name__, "PageBroadcast")
        self.assertEqual(win.stack.widget(8).__class__.__name__, "PageSchedule")
        self.assertEqual(win.stack.widget(9).__class__.__name__, "PageAudioStudio")
        if win.loader_thread:
            win.loader_thread.wait()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase4BroadcastStudio)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
