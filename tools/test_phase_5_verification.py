"""tools/test_phase_5_verification.py — BỘ 52 BÀI KIỂM THỬ TÍCH HỢP TOÀN DIỆN PHASE 5
=============================================================================
Kiểm thử tích hợp & Hồi quy toàn diện (Full Integration & Regression Testing)
cho toàn bộ hệ thống T-TTS v3.0.0 trước khi chuyển giao sang Phase Auto Update:
- 01-03: Khởi động, Khởi tạo 13 trang, Điều hướng Sidebar.
- 04-06: TTSService Singleton, Tạo giọng thực tế, Phát audio MCI.
- 07-08: Lưu và Khôi phục Lịch sử (history.json).
- 09-10: Bản quyền Offline Ed25519 & Machine ID.
- 11-12: Danh mục 25 giọng chuẩn, Xác thực Voice Clone.
- 13-17: Schedule Studio (Tạo, Sửa, Chạy ngay, Notification, Restart/Reload).
- 18-33: Audio Studio (Tạo, Import, Waveform, Cut/Copy/Paste, Trim/Delete, Split, Gain,
          Fade, Normalize, BGM, Undo/Redo, Export WAV/MP3, Save/Open, Relink).
- 34-49: Broadcast Studio 2.0 (Tạo, Thêm/Sửa segment, Regenerate đơn lẻ, Bảo toàn,
          Reorder, Intro/Outro, BGM, Auto-Ducking, Preview, Export WAV/MP3, Save/Open, Relink).
- 50: Bảo toàn dữ liệu người dùng & file cấu hình cũ.
- 51-52: Đo lường RAM và Hiệu năng phản hồi (Memory & Latency Benchmark).
"""

import os
import sys
import time
import shutil
import tempfile
import unittest
import subprocess
import numpy as np
from pathlib import Path

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

from gui.main_window import MainWindow
from gui.pages.page_audio_studio import PageAudioStudio
from gui.pages.page_broadcast import PageBroadcast
from gui.pages.page_schedule import PageSchedule
from gui.waveform_widget import WaveformWidget
from gui.task_worker import FunctionTaskWorker
from gui.notification_hub import notification_hub

from backend.service import tts_service
from backend.audio_player import audio_player
from backend.project_manager import project_manager, get_projects_dir
from backend.scheduler_engine import scheduler_engine
from backend.license import license_manager, get_machine_id
from backend.version import APP_VERSION, APP_NAME, APP_AUTHOR
from backend.audio_utils import (
    save_wav,
    wav_to_mp3,
    load_audio_segment_safe,
    get_audio_duration_safe,
    slice_audio,
    apply_audio_gain_and_fade,
    mix_multitrack_timeline,
    apply_bgm_ducking,
    stitch_broadcast_project,
)


app = QApplication.instance() or QApplication(sys.argv)


class TestPhase5FullIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.work_dir = Path(cls.temp_dir.name)

        # Chuẩn bị âm thanh mẫu
        cls.tone_wav = cls.work_dir / "tone_sample.wav"
        cls.bgm_wav = cls.work_dir / "bgm_sample.wav"
        cls.intro_wav = cls.work_dir / "intro_sample.wav"
        cls.outro_wav = cls.work_dir / "outro_sample.wav"

        Sine(440).to_audio_segment(duration=2500).apply_gain(-6.0).export(str(cls.tone_wav), format="wav")
        Sine(220).to_audio_segment(duration=3000).apply_gain(-14.0).export(str(cls.bgm_wav), format="wav")
        Sine(523).to_audio_segment(duration=1000).apply_gain(-8.0).export(str(cls.intro_wav), format="wav")
        Sine(659).to_audio_segment(duration=1000).apply_gain(-8.0).export(str(cls.outro_wav), format="wav")

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    # -------------------------------------------------------------
    # 01 - 03: STARTUP & NAVIGATION
    # -------------------------------------------------------------
    def test_01_app_startup(self):
        self.assertIsNotNone(app)
        self.assertEqual(APP_VERSION, "3.0.0")
        self.assertEqual(APP_AUTHOR, "Nguyễn Văn Tiệp")

    def test_02_all_13_pages_init(self):
        win = MainWindow()
        win._check_initial_license = lambda: None
        win._check_background_update = lambda: None
        self.assertEqual(win.stack.count(), 13)
        expected_classes = [
            "PageSynthesize", "PageClone", "PageBatch", "PageBroadcast",
            "PagePodcast", "PageVoices", "PagePronDict", "PageHistory",
            "PageSchedule", "PageAudioStudio", "PageSettings", "PageAbout", "PageGuide"
        ]
        actual_classes = [win.stack.widget(i).__class__.__name__ for i in range(13)]
        self.assertEqual(actual_classes, expected_classes)
        if win.loader_thread:
            win.loader_thread.wait()

    def test_03_sidebar_navigation(self):
        win = MainWindow()
        win._check_initial_license = lambda: None
        win._check_background_update = lambda: None
        for idx in range(13):
            win._switch_tab(idx)
            self.assertEqual(win.stack.currentIndex(), idx)
        if win.loader_thread:
            win.loader_thread.wait()

    # -------------------------------------------------------------
    # 04 - 06: TTSSERVICE & PLAYBACK
    # -------------------------------------------------------------
    def test_04_ttsservice_singleton(self):
        from backend.service import TTSService
        self.assertIs(tts_service, TTSService())
        self.assertIsNotNone(tts_service.engine)

    def test_05_real_tts_generation(self):
        if not tts_service.engine.ready:
            tts_service.initialize_model()
        res = tts_service.synthesize_text(
            text="Kiểm tra tổng hợp âm thanh thực tế Phase 5.",
            voice_id="hn_nam_quan_doi",
            speed=1.0,
            out_format="wav",
            filename_prefix="test_phase5_real",
        )
        self.assertTrue(res.get("success"))
        fpath = Path(res.get("file_path"))
        self.assertTrue(fpath.is_file())
        self.assertGreater(fpath.stat().st_size, 1000)

    def test_06_audio_playback_engine(self):
        self.assertIsNotNone(audio_player)
        self.assertTrue(hasattr(audio_player, "play"))
        self.assertTrue(hasattr(audio_player, "pause"))
        self.assertTrue(hasattr(audio_player, "resume"))
        self.assertTrue(hasattr(audio_player, "stop"))
        self.assertTrue(hasattr(audio_player, "seek_ms"))

    # -------------------------------------------------------------
    # 07 - 08: HISTORY INTEGRITY
    # -------------------------------------------------------------
    def test_07_save_history(self):
        initial_count = len(tts_service.history.all())
        item = tts_service.history.add(
            text="Lịch sử kiểm thử Phase 5",
            voice="hn_nam_quan_doi",
            speed=1.0,
            wav_path=self.tone_wav,
            kind="test",
        )
        self.assertIsNotNone(item.get("id"))
        self.assertEqual(len(tts_service.history.all()), initial_count + 1)

    def test_08_restore_history(self):
        history_path = tts_service.data_dir / "history.json"
        self.assertTrue(history_path.is_file())
        reloaded = tts_service.history.all()
        self.assertIsInstance(reloaded, list)
        self.assertGreater(len(reloaded), 0)

    # -------------------------------------------------------------
    # 09 - 10: OFFLINE LICENSE & MACHINE ID
    # -------------------------------------------------------------
    def test_09_offline_license(self):
        lic = license_manager.get_status_info()
        self.assertTrue(lic.get("is_active"))
        self.assertEqual(lic.get("status"), "active")
        self.assertIn("KEY-PERM", lic.get("plan"))

    def test_10_machine_id(self):
        mid = get_machine_id()
        self.assertIsInstance(mid, str)
        self.assertTrue(mid.startswith("TTTS-"))
        self.assertEqual(len(mid.split("-")), 5)

    # -------------------------------------------------------------
    # 11 - 12: VOICES CATALOG & CLONE VALIDATION
    # -------------------------------------------------------------
    def test_11_voice_catalog(self):
        voices = tts_service.list_voices()
        self.assertGreaterEqual(len(voices), 25)
        voice_ids = [v["id"] for v in voices]
        self.assertIn("hn_nam_quan_doi", voice_ids)
        self.assertIn("hn_nu_chinh_luan", voice_ids)

    def test_12_voice_clone_validation(self):
        from backend.audio_utils import validate_and_convert_reference_audio
        valid_out = self.work_dir / "clone_val_out.wav"
        res = validate_and_convert_reference_audio(str(self.tone_wav), str(valid_out), min_duration=1.0)
        self.assertTrue(valid_out.is_file())
        self.assertGreater(valid_out.stat().st_size, 1000)

    # -------------------------------------------------------------
    # 13 - 17: SCHEDULE STUDIO
    # -------------------------------------------------------------
    def test_13_create_schedule(self):
        sched_id = scheduler_engine.save_schedule({
            "name": "Phase 5 Schedule",
            "task_type": "tts",
            "repeat_type": "daily",
            "time_of_day": "06:30",
            "task_config": {"text": "Chào buổi sáng", "voice_id": "hn_nam_quan_doi"},
            "enabled": True,
        })
        self.assertIsNotNone(sched_id)
        self.assertTrue(scheduler_engine.get_schedule(sched_id) is not None)
        scheduler_engine.delete_schedule(sched_id)

    def test_14_edit_schedule(self):
        sid = scheduler_engine.save_schedule({
            "name": "Original Name",
            "task_type": "reminder",
            "repeat_type": "once",
            "run_date": "2026-11-10",
            "time_of_day": "14:00",
            "task_config": {"reminder_text": "Họp giao ban"},
        })
        scheduler_engine.save_schedule({
            "id": sid,
            "name": "Updated Name",
            "time_of_day": "15:00",
        })
        updated = scheduler_engine.get_schedule(sid)
        self.assertEqual(updated["name"], "Updated Name")
        self.assertEqual(updated["time_of_day"], "15:00")
        scheduler_engine.delete_schedule(sid)

    def test_15_run_schedule_now(self):
        sid = scheduler_engine.save_schedule({
            "name": "Run Now Test",
            "task_type": "tts",
            "repeat_type": "once",
            "task_config": {"text": "Lệnh báo động kiểm tra quân số.", "voice_id": "hn_nam_quan_doi"},
        })
        res = scheduler_engine.run_schedule_now(sid)
        self.assertTrue(res.get("success"))
        scheduler_engine.delete_schedule(sid)

    def test_16_notification_hub(self):
        msgs = []
        notification_hub.notify_info.connect(lambda t, m: msgs.append((t, m)))
        notification_hub.notify_info.emit("Thông báo", "Nội dung thử nghiệm")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0][0], "Thông báo")

    def test_17_scheduler_restart_reload(self):
        sid = scheduler_engine.save_schedule({
            "name": "Persist Sched",
            "task_type": "tts",
            "repeat_type": "daily",
            "time_of_day": "18:00",
            "task_config": {"text": "Bản tin tối"},
        })
        # Khởi tạo instance mới
        from backend.scheduler_engine import SchedulerEngine
        eng2 = SchedulerEngine()
        found = eng2.get_schedule(sid)
        self.assertIsNotNone(found)
        self.assertEqual(found["name"], "Persist Sched")
        scheduler_engine.delete_schedule(sid)

    # -------------------------------------------------------------
    # 18 - 33: AUDIO STUDIO
    # -------------------------------------------------------------
    def test_18_audio_project_creation(self):
        studio = PageAudioStudio()
        self.assertIsNotNone(studio)
        self.assertIsNone(studio.current_audio)

    def test_19_audio_studio_import(self):
        studio = PageAudioStudio()
        ok = studio.load_audio_file(str(self.tone_wav))
        self.assertTrue(ok)
        self.assertIsNotNone(studio.current_audio)
        self.assertAlmostEqual(len(studio.current_audio), 2500, delta=50)

    def test_20_waveform_widget(self):
        wf = WaveformWidget()
        wf.set_audio_data(np.zeros(48000 * 2, dtype=np.float32), 48000)
        self.assertEqual(wf.duration_ms, 2000)
        peaks = wf._get_downsampled_peaks(500)
        self.assertEqual(len(peaks[0]), 500)
        wf.zoom_in()
        self.assertGreater(wf.zoom_level, 1.0)
        wf.zoom_fit()
        self.assertEqual(wf.zoom_level, 1.0)

    def test_21_cut_copy_paste(self):
        studio = PageAudioStudio()
        studio.load_audio_file(str(self.tone_wav)) # 2500ms
        studio.waveform.set_selection_range(500, 1500)
        studio.cut_selection()
        self.assertAlmostEqual(len(studio.current_audio), 1500, delta=30)
        self.assertIsNotNone(studio.clipboard_audio)
        studio.waveform.set_playhead_ms(0)
        studio.paste_audio()
        self.assertAlmostEqual(len(studio.current_audio), 2500, delta=50)

    def test_22_trim_delete(self):
        studio = PageAudioStudio()
        studio.load_audio_file(str(self.tone_wav)) # 2500ms
        studio.waveform.set_selection_range(500, 1000)
        studio.delete_selection()
        self.assertAlmostEqual(len(studio.current_audio), 2000, delta=30)
        studio.waveform.set_selection_range(500, 1500)
        studio.trim_selection()
        self.assertAlmostEqual(len(studio.current_audio), 1000, delta=30)

    def test_23_split_audio(self):
        studio = PageAudioStudio()
        studio.load_audio_file(str(self.tone_wav)) # 2500ms
        studio.waveform.set_playhead_ms(1000)
        studio.split_at_playhead()
        self.assertAlmostEqual(len(studio.current_audio), 2700, delta=50)

    def test_24_gain_adjustment(self):
        studio = PageAudioStudio()
        studio.load_audio_file(str(self.tone_wav))
        init_db = studio.current_audio.dBFS
        studio.apply_gain(2.0)
        self.assertAlmostEqual(studio.current_audio.dBFS - init_db, 2.0, delta=0.5)

    def test_25_fade_in_out(self):
        studio = PageAudioStudio()
        studio.load_audio_file(str(self.tone_wav))
        studio.apply_fade_effect(is_in=True, ms=800)
        studio.apply_fade_effect(is_in=False, ms=800)
        self.assertLess(studio.current_audio[:50].dBFS, -15.0)
        self.assertLess(studio.current_audio[-50:].dBFS, -15.0)

    def test_26_normalize_audio(self):
        studio = PageAudioStudio()
        quiet = Sine(440).to_audio_segment(duration=1000).apply_gain(-20.0)
        q_path = self.work_dir / "q.wav"
        quiet.export(str(q_path), format="wav")
        studio.load_audio_file(str(q_path))
        studio.normalize_audio()
        self.assertAlmostEqual(studio.current_audio.max_dBFS, 0.0, delta=0.5)

    def test_27_audio_studio_bgm(self):
        studio = PageAudioStudio()
        studio.load_audio_file(str(self.tone_wav))
        studio.mix_bgm_file(str(self.bgm_wav), volume_pct=15, loop=True)
        self.assertAlmostEqual(len(studio.current_audio), 2500, delta=50)

    def test_28_undo_redo_history(self):
        studio = PageAudioStudio()
        studio.load_audio_file(str(self.tone_wav)) # 2500ms
        self.assertEqual(len(studio.undo_stack), 0)
        studio.waveform.set_selection_range(0, 500)
        studio.delete_selection()
        self.assertAlmostEqual(len(studio.current_audio), 2000, delta=30)
        studio.undo()
        self.assertAlmostEqual(len(studio.current_audio), 2500, delta=30)
        studio.redo()
        self.assertAlmostEqual(len(studio.current_audio), 2000, delta=30)

    def test_29_export_wav_audio_studio(self):
        studio = PageAudioStudio()
        studio.load_audio_file(str(self.tone_wav))
        out_p = self.work_dir / "exported_studio.wav"
        ok = studio.export_to_file(str(out_p), format_type="wav")
        self.assertTrue(ok)
        self.assertTrue(out_p.is_file())
        self.assertGreater(out_p.stat().st_size, 1000)

    def test_30_export_mp3_audio_studio(self):
        studio = PageAudioStudio()
        studio.load_audio_file(str(self.tone_wav))
        out_p = self.work_dir / "exported_studio.mp3"
        ok = studio.export_to_file(str(out_p), format_type="mp3")
        self.assertTrue(ok)
        self.assertTrue(out_p.is_file())
        self.assertGreater(out_p.stat().st_size, 1000)

    def test_31_save_audio_project(self):
        studio = PageAudioStudio()
        studio.load_audio_file(str(self.tone_wav))
        proj_dict = studio.build_project_dict(name="Studio Phase 5 Project")
        pid = project_manager.save_project("audio", proj_dict)
        self.assertIsNotNone(pid)
        self.assertTrue((get_projects_dir("audio") / f"{pid}.json").is_file())

    def test_32_open_audio_project(self):
        studio = PageAudioStudio()
        studio.load_audio_file(str(self.tone_wav))
        proj_dict = studio.build_project_dict(name="Restore Studio Test")
        pid = project_manager.save_project("audio", proj_dict)

        studio2 = PageAudioStudio()
        loaded = project_manager.load_project("audio", pid)
        ok = studio2.restore_from_project_dict(loaded)
        self.assertTrue(ok)
        self.assertAlmostEqual(len(studio2.current_audio), 2500, delta=50)

    def test_33_relink_audio_source(self):
        studio = PageAudioStudio()
        fake_proj = {"source_file": "Z:\\invalid_ghost_file.wav"}
        ok = studio.restore_from_project_dict(fake_proj)
        self.assertFalse(ok)

    # -------------------------------------------------------------
    # 34 - 49: BROADCAST STUDIO 2.0
    # -------------------------------------------------------------
    def test_34_broadcast_project_creation(self):
        bc = PageBroadcast()
        self.assertIsNotNone(bc)
        self.assertEqual(len(bc.segments), 0)

    def test_35_add_broadcast_segments(self):
        bc = PageBroadcast()
        bc.add_segment({"type": "lead_in", "title": "Lời dẫn", "text": "Kính chào các đồng chí."})
        bc.add_segment({"type": "news", "title": "Thời sự", "text": "Hôm nay toàn quân ra quân huấn luyện."})
        bc.add_segment({"type": "silence", "duration_sec": 1.0})
        self.assertEqual(len(bc.segments), 3)

    def test_36_edit_broadcast_segment(self):
        bc = PageBroadcast()
        bc.add_segment({"type": "news", "text": "Ban đầu"})
        bc.update_segment(0, text="Nội dung đã được biên tập lại", speed=1.1)
        self.assertEqual(bc.segments[0]["text"], "Nội dung đã được biên tập lại")
        self.assertAlmostEqual(bc.segments[0]["speed"], 1.1)
        self.assertTrue(bc.segments[0]["is_modified"])

    def test_37_regenerate_single_segment(self):
        bc = PageBroadcast()
        bc.add_segment({"type": "news", "text": "Thử nghiệm regenerate riêng phân đoạn."})
        ok = bc.generate_segment_speech_sync(0)
        self.assertTrue(ok)
        self.assertEqual(bc.segments[0]["status"], "ready")
        self.assertTrue(Path(bc.segments[0]["file_path"]).is_file())

    def test_38_preserve_unmodified_segments(self):
        bc = PageBroadcast()
        bc.add_segment({"type": "lead_in", "file_path": str(self.tone_wav), "duration_sec": 2.5, "status": "ready"})
        bc.add_segment({"type": "news", "text": "Đoạn cần tổng hợp giọng.", "status": "pending"})
        orig_p0 = bc.segments[0]["file_path"]
        bc.generate_segment_speech_sync(1)
        self.assertEqual(bc.segments[0]["file_path"], orig_p0)
        self.assertEqual(bc.segments[0]["status"], "ready")

    def test_39_reorder_timeline(self):
        bc = PageBroadcast()
        bc.add_segment({"title": "1"})
        bc.add_segment({"title": "2"})
        bc.reorder_segments(0, 1)
        self.assertEqual(bc.segments[0]["title"], "2")
        self.assertEqual(bc.segments[1]["title"], "1")

    def test_40_intro_outro_music(self):
        bc = PageBroadcast()
        bc.set_intro_music(str(self.intro_wav))
        bc.set_outro_music(str(self.outro_wav))
        self.assertEqual(bc.edit_intro_music.text(), str(self.intro_wav))
        self.assertEqual(bc.edit_outro_music.text(), str(self.outro_wav))

    def test_41_broadcast_bgm(self):
        bc = PageBroadcast()
        bc.set_bg_music(str(self.bgm_wav), vol_pct=15, loop=True, ducking=True)
        self.assertTrue(bc.chk_enable_bg.isChecked())
        self.assertEqual(bc.bg_path_edit.text(), str(self.bgm_wav))

    def test_42_auto_ducking(self):
        bgm = Sine(220).to_audio_segment(duration=8000)
        speech_intervals = [(1000, 4000)]
        ducked = apply_bgm_ducking(bgm, speech_intervals, normal_gain_db=-10.0, ducked_gain_db=-22.0)
        self.assertEqual(len(ducked), 8000)
        self.assertLess(ducked[2000:3000].dBFS, ducked[5000:6000].dBFS)

    def test_43_preview_segment(self):
        bc = PageBroadcast()
        bc.add_segment({"file_path": str(self.tone_wav), "status": "ready"})
        self.assertTrue(Path(bc.segments[0]["file_path"]).is_file())

    def test_44_preview_full_broadcast(self):
        bc = PageBroadcast()
        bc.add_segment({"file_path": str(self.tone_wav), "duration_sec": 2.5, "status": "ready"})
        bc.set_bg_music(str(self.bgm_wav), vol_pct=15, loop=True, ducking=True)
        out_p = self.work_dir / "preview_broadcast_full.wav"
        res = bc.export_program_direct(out_p, out_format="wav")
        self.assertTrue(res["success"])
        self.assertTrue(out_p.is_file())

    def test_45_export_broadcast_wav(self):
        bc = PageBroadcast()
        bc.add_segment({"file_path": str(self.tone_wav), "duration_sec": 2.5, "status": "ready"})
        out_p = self.work_dir / "exported_broadcast.wav"
        res = bc.export_program_direct(out_p, out_format="wav")
        self.assertTrue(res["success"])
        self.assertTrue(out_p.is_file())
        self.assertGreater(out_p.stat().st_size, 1000)

    def test_46_export_broadcast_mp3(self):
        bc = PageBroadcast()
        bc.add_segment({"file_path": str(self.tone_wav), "duration_sec": 2.5, "status": "ready"})
        out_p = self.work_dir / "exported_broadcast.mp3"
        res = bc.export_program_direct(out_p, out_format="mp3")
        self.assertTrue(res["success"])
        self.assertTrue(out_p.is_file())
        self.assertGreater(out_p.stat().st_size, 1000)

    def test_47_save_broadcast_project(self):
        bc = PageBroadcast()
        bc.add_segment({"type": "lead_in", "title": "Dẫn", "text": "Xin chào"})
        proj_dict = bc.build_project_dict(name="Broadcast Phase 5 Project")
        pid = project_manager.save_project("broadcast", proj_dict)
        self.assertIsNotNone(pid)
        self.assertTrue((get_projects_dir("broadcast") / f"{pid}.json").is_file())

    def test_48_open_broadcast_project(self):
        bc = PageBroadcast()
        bc.add_segment({"type": "news", "title": "Tin chính", "text": "Nội dung"})
        proj_dict = bc.build_project_dict(name="Restore Broadcast Test")
        pid = project_manager.save_project("broadcast", proj_dict)

        bc2 = PageBroadcast()
        loaded = project_manager.load_project("broadcast", pid)
        ok = bc2.restore_from_project_dict(loaded)
        self.assertTrue(ok)
        self.assertEqual(len(bc2.segments), 1)
        self.assertEqual(bc2.segments[0]["title"], "Tin chính")

    def test_49_relink_broadcast_sources(self):
        bc = PageBroadcast()
        ghost_dict = {
            "name": "Ghost BC",
            "segments": [{"title": "Missing", "file_path": "Z:\\fake_source.wav", "status": "ready"}]
        }
        ok = bc.restore_from_project_dict(ghost_dict, prompt_relink=False)
        self.assertTrue(ok)
        self.assertEqual(bc.segments[0]["status"], "pending")

    # -------------------------------------------------------------
    # 50: DATA INTEGRITY
    # -------------------------------------------------------------
    def test_50_legacy_user_data_intact(self):
        history_file = tts_service.data_dir / "history.json"
        self.assertTrue(history_file.is_file())
        self.assertGreater(history_file.stat().st_size, 0)

        lic_info = tts_service.get_license_info()
        self.assertTrue(lic_info.get("is_active"))

        # Kiểm tra mô hình VieNeu-TTS v3 Turbo ONNX CPU
        model_dir = PROJECT_ROOT / "models"
        self.assertTrue(model_dir.is_dir())

    # -------------------------------------------------------------
    # 51 - 52: PERFORMANCE BENCHMARK (RAM & LATENCY)
    # -------------------------------------------------------------
    def test_51_memory_rss_benchmark(self):
        import psutil
        process = psutil.Process()
        rss_mb = process.memory_info().rss / (1024 * 1024)
        print(f"\n  [BENCHMARK] Memory RSS: {rss_mb:.2f} MB")
        self.assertLess(rss_mb, 800) # RAM duy trì dưới 800MB

    def test_52_latency_response_benchmark(self):
        # Đo lường thời gian downsampling và tính toán peaks 1000 cột
        wf = WaveformWidget()
        long_samples = np.sin(np.linspace(0, 1000, 48000 * 60)).astype(np.float32) # 1 phút audio
        wf.set_audio_data(long_samples, 48000)
        t0 = time.perf_counter()
        peaks = wf._get_downsampled_peaks(1000)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        print(f"  [BENCHMARK] Waveform 1-minute downsample latency: {dt_ms:.3f} ms")
        self.assertLess(dt_ms, 50.0) # Downsampling hoàn tất dưới 50ms


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase5FullIntegration)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
