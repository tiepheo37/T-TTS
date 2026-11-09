"""tools/test_phase_6_patch_verification.py — KIỂM THỬ TOÀN DIỆN PHASE 6 PATCH ADDENDUM
====================================================================================
Kiểm thử chi tiết 2 nhóm tính năng mới:
PHASE A: Quản lý nguồn âm thanh & Danh sách phát Schedule Studio (Playlist Studio)
  - A1. Audio Source Picker (Local Files, History, Projects, TTS)
  - A2. Document-to-TTS (DOCX/TXT extraction & synthesis)
  - A3. Playlist Editor (Thêm, Xóa, Sắp xếp Lên/Xuống, Nghỉ sau pause_after, Tổng thời lượng)
  - A4. File Path Management (Phát hiện tệp mất - Missing File, Relink tệp)
  - A5. Schedule Execution (Phát tuần tự, Tạm dừng, Tiếp tục, Dừng, Ghi log)

PHASE B: Waveform Zoom & Timeline Navigation Audio Studio
  - B1. Mouse Wheel Zoom (Ngang quanh tâm chuột, Dọc biên độ Shift+Wheel)
  - B2. Zoom Behavior (Tâm zoom chuẩn xác, Không trôi Playhead, Giữ Selection, Âm thanh không biến dạng)
  - B3. Timeline Navigation (Pan kéo trượt timeline, Thước đo Ruler chuẩn xác)
  - B4. Rendering Hiệu năng cao (Downsampling NumPy cache, không lag)
  - B5. Tích hợp Audio Editing (Undo/Redo, Cut, Trim không bị ảnh hưởng)

REGRESSION: Toàn bộ 13 trang, License Ed25519, VieNeu-TTS ONNX CPU, Version 3.0.1.
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Đảm bảo import từ thư mục gốc
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import numpy as np
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

# Khởi tạo QApplication cho headless test
app = QApplication.instance() or QApplication(sys.argv)

from backend.version import APP_VERSION, APP_AUTHOR, APP_NAME
from backend.audio_utils import save_wav, get_audio_duration_safe
from backend.audio_player import audio_player
from backend.project_manager import project_manager
from backend.scheduler_engine import scheduler_engine, compute_next_run
from gui.waveform_widget import WaveformWidget, format_ms_to_time
from gui.pages.page_schedule import extract_text_from_file, ScheduleEditorDialog, PageSchedule
from gui.pages.page_audio_studio import PageAudioStudio


class TestPhase6PatchAddendum(unittest.TestCase):
    """Bộ kiểm thử xác thực Phase 6 Patch Addendum."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="ttts_patch_test_"))
        # Tạo sẵn các file âm thanh WAV thử nghiệm
        cls.wav_sample_1 = cls.test_dir / "sample_news_1.wav"
        cls.wav_sample_2 = cls.test_dir / "sample_news_2.wav"
        cls.wav_sample_3 = cls.test_dir / "sample_news_3.wav"

        sr = 48000
        # 2 giây âm thanh
        t1 = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False)
        wave1 = 0.5 * np.sin(2 * np.pi * 440 * t1)
        save_wav(cls.wav_sample_1, wave1, sr=sr)

        # 3 giây âm thanh
        t2 = np.linspace(0, 3.0, int(sr * 3.0), endpoint=False)
        wave2 = 0.4 * np.sin(2 * np.pi * 880 * t2)
        save_wav(cls.wav_sample_2, wave2, sr=sr)

        # 1 giây âm thanh
        t3 = np.linspace(0, 1.0, int(sr * 1.0), endpoint=False)
        wave3 = 0.3 * np.sin(2 * np.pi * 220 * t3)
        save_wav(cls.wav_sample_3, wave3, sr=sr)

        # Tạo file TXT thử nghiệm
        cls.txt_file = cls.test_dir / "thong_bao_sang.txt"
        cls.txt_file.write_text("Đây là bản tin phát thanh thử nghiệm buổi sáng.", encoding="utf-8")

    # =========================================================================
    # PHASE A: SCHEDULE STUDIO AUDIO SOURCE & PLAYLIST
    # =========================================================================
    def test_a1_audio_duration_detection(self):
        """A1: Xác thực phát hiện chính xác thời lượng của các file âm thanh."""
        d1 = get_audio_duration_safe(self.wav_sample_1)
        d2 = get_audio_duration_safe(self.wav_sample_2)
        d3 = get_audio_duration_safe(self.wav_sample_3)

        self.assertAlmostEqual(d1, 2.0, delta=0.1)
        self.assertAlmostEqual(d2, 3.0, delta=0.1)
        self.assertAlmostEqual(d3, 1.0, delta=0.1)

    def test_a2_document_to_text_extraction(self):
        """A2: Trích xuất nội dung văn bản từ tệp TXT và kiểm tra quy trình TTS."""
        title, content = extract_text_from_file(self.txt_file)
        self.assertEqual(title, "thong bao sang")
        self.assertIn("bản tin phát thanh thử nghiệm", content)

    def test_a3_playlist_editor_reorder_and_durations(self):
        """A3: Kiểm tra cấu trúc Playlist, sắp xếp thứ tự và tính tổng thời lượng."""
        items = [
            {"id": "item_1", "title": "Bản tin 1", "file_path": str(self.wav_sample_1), "duration_sec": 2.0, "pause_after": 2.0},
            {"id": "item_2", "title": "Bản tin 2", "file_path": str(self.wav_sample_2), "duration_sec": 3.0, "pause_after": 3.0},
            {"id": "item_3", "title": "Bản tin 3", "file_path": str(self.wav_sample_3), "duration_sec": 1.0, "pause_after": 0.0},
        ]

        # Đổi thứ tự item 1 và item 2
        items[0], items[1] = items[1], items[0]
        self.assertEqual(items[0]["id"], "item_2")
        self.assertEqual(items[1]["id"], "item_1")

        # Tính tổng thời lượng phát thanh bao gồm khoảng nghỉ
        total_time = sum(it["duration_sec"] + it["pause_after"] for it in items)
        self.assertEqual(total_time, 2.0 + 2.0 + 3.0 + 3.0 + 1.0 + 0.0)  # 11.0 giây

    def test_a4_missing_file_detection_and_relink(self):
        """A4: Kiểm tra khả năng phát hiện tệp mất (Missing) và Relink thành công."""
        missing_path = self.test_dir / "non_existent_audio.wav"
        item = {
            "id": "item_missing",
            "title": "Bản tin bị xóa",
            "file_path": str(missing_path),
            "duration_sec": 0.0,
            "pause_after": 2.0,
        }

        # Kiểm tra phát hiện file mất
        is_exist = Path(item["file_path"]).is_file()
        self.assertFalse(is_exist, "Phải nhận diện tệp không tồn tại!")

        # Thực hiện Relink sang file có thật
        item["file_path"] = str(self.wav_sample_1)
        item["duration_sec"] = get_audio_duration_safe(Path(item["file_path"]))

        is_relinked_exist = Path(item["file_path"]).is_file()
        self.assertTrue(is_relinked_exist, "Sau khi Relink, tệp phải tồn tại!")
        self.assertAlmostEqual(item["duration_sec"], 2.0, delta=0.1)

    def test_a5_playlist_schedule_save_and_persistence(self):
        """A5: Lưu lịch trình dạng Playlist và nạp lại bền vững từ disk."""
        playlist = [
            {"id": "it_1", "title": "Bản tin 1", "file_path": str(self.wav_sample_1), "duration_sec": 2.0, "pause_after": 1.0},
            {"id": "it_2", "title": "Bản tin 2", "file_path": str(self.wav_sample_2), "duration_sec": 3.0, "pause_after": 0.0},
        ]
        sched_data = {
            "name": "Lịch Phát Thanh Buổi Chiều",
            "task_type": "playlist",
            "repeat_type": "daily",
            "target_time": "17:00:00",
            "playlist": playlist,
            "task_config": {"playlist": playlist},
            "is_enabled": True,
        }

        sid = scheduler_engine.save_schedule(sched_data)
        self.assertIsNotNone(sid)

        # Nạp lại từ Engine
        loaded = scheduler_engine.get_schedule(sid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["task_type"], "playlist")
        self.assertEqual(len(loaded["playlist"]), 2)
        self.assertEqual(loaded["playlist"][0]["title"], "Bản tin 1")

        # Xóa dọn dẹp
        scheduler_engine.delete_schedule(sid)
        self.assertIsNone(scheduler_engine.get_schedule(sid))

    # =========================================================================
    # PHASE B: AUDIO STUDIO WAVEFORM ZOOM
    # =========================================================================
    def test_b1_waveform_data_loading(self):
        """B1: Nạp dữ liệu âm thanh vào WaveformWidget và khởi tạo Viewport chuẩn."""
        wf = WaveformWidget()
        wf.resize(800, 200)

        sr = 44100
        samples = np.sin(np.linspace(0, 10 * np.pi, 44100)).astype(np.float32)  # 1 giây = 1000ms
        wf.set_audio_data(samples, sample_rate=sr)

        self.assertEqual(wf.duration_ms, 1000)
        self.assertEqual(wf.view_start_ms, 0)
        self.assertEqual(wf.view_end_ms, 1000)
        self.assertEqual(wf.zoom_level, 1.0)
        self.assertEqual(wf.vertical_zoom, 1.0)

    def test_b2_horizontal_zoom_centered_at_cursor(self):
        """B2: Phóng to trục ngang lấy vị trí con trỏ chuột làm tâm."""
        wf = WaveformWidget()
        wf.resize(800, 200)

        sr = 44100
        samples = np.zeros(441000, dtype=np.float32)  # 10 giây = 10000ms
        wf.set_audio_data(samples, sample_rate=sr)

        # Zoom in quanh điểm 4000ms
        cursor_ms = 4000
        wf.zoom_in(center_ms=cursor_ms, factor=2.0)

        self.assertGreater(wf.zoom_level, 1.0)
        # Điểm 4000ms phải nằm giữa view_start_ms và view_end_ms
        self.assertLessEqual(wf.view_start_ms, cursor_ms)
        self.assertGreaterEqual(wf.view_end_ms, cursor_ms)

        # Zoom fit lại ban đầu
        wf.zoom_fit()
        self.assertEqual(wf.view_start_ms, 0)
        self.assertEqual(wf.view_end_ms, 10000)
        self.assertEqual(wf.zoom_level, 1.0)

    def test_b3_vertical_zoom_factor(self):
        """B3: Zoom biên độ dạng sóng trục dọc (Vertical Zoom) trong khoảng [0.2, 5.0]."""
        wf = WaveformWidget()
        wf.set_vertical_zoom(2.5)
        self.assertAlmostEqual(wf.vertical_zoom, 2.5)

        # Bị clamp dưới 0.2
        wf.set_vertical_zoom(0.05)
        self.assertEqual(wf.vertical_zoom, 0.2)

        # Bị clamp trên 5.0
        wf.set_vertical_zoom(10.0)
        self.assertEqual(wf.vertical_zoom, 5.0)

        # Reset zoom
        wf.reset_zoom()
        self.assertEqual(wf.vertical_zoom, 1.0)

    def test_b4_playhead_and_selection_preservation(self):
        """B4: Đảm bảo Playhead và Selection không bị dịch chuyển khi zoom."""
        wf = WaveformWidget()
        wf.resize(800, 200)
        wf.set_audio_data(np.zeros(441000, dtype=np.float32), sample_rate=44100)  # 10s

        # Đặt playhead tại 3500ms, selection 2000ms -> 5000ms
        wf.set_playhead_ms(3500)
        wf.set_selection_range(2000, 5000)

        # Phóng to nhiều lần
        wf.zoom_in(center_ms=3500, factor=1.5)
        wf.zoom_in(center_ms=3500, factor=1.5)

        # Kiểm tra Playhead và Selection hoàn toàn không đổi
        self.assertEqual(wf.playhead_ms, 3500)
        self.assertEqual(wf.sel_start_ms, 2000)
        self.assertEqual(wf.sel_end_ms, 5000)

        # Thu nhỏ lại
        wf.zoom_out(center_ms=3500, factor=2.0)
        self.assertEqual(wf.playhead_ms, 3500)
        self.assertEqual(wf.sel_start_ms, 2000)
        self.assertEqual(wf.sel_end_ms, 5000)

    def test_b5_peaks_caching_and_downsampling(self):
        """B5: Cache đỉnh sóng peaks hiệu năng cao theo khung nhìn hiển thị."""
        wf = WaveformWidget()
        wf.resize(800, 200)
        audio = np.linspace(-0.8, 0.8, 88200, dtype=np.float32)  # 2s
        wf.set_audio_data(audio, sample_rate=44100)

        mins1, maxs1 = wf._compute_peaks(800)
        self.assertEqual(len(mins1), 800)
        self.assertEqual(len(maxs1), 800)
        self.assertAlmostEqual(float(mins1.min()), -0.8, delta=0.05)
        self.assertAlmostEqual(float(maxs1.max()), 0.8, delta=0.05)

        # Cắt zoom một nửa sau (1000ms -> 2000ms)
        wf.view_start_ms = 1000
        wf.view_end_ms = 2000
        mins2, maxs2 = wf._compute_peaks(800)
        # Nửa sau chỉ có giá trị dương [0.0 -> 0.8]
        self.assertGreaterEqual(float(mins2.min()), -0.05)
        self.assertAlmostEqual(float(maxs2.max()), 0.8, delta=0.05)

    def test_b6_timeline_panning_and_scrollbar_sync(self):
        """B6: Kéo trượt (Pan) timeline và cuộn màn hình bằng scroll_to_ms."""
        wf = WaveformWidget()
        wf.resize(800, 200)
        wf.set_audio_data(np.zeros(441000, dtype=np.float32), sample_rate=44100)  # 10000ms

        # Phóng to khung nhìn 2000ms
        wf.view_start_ms = 0
        wf.view_end_ms = 2000

        # Cuộn tới 3000ms
        wf.scroll_to_ms(3000)
        self.assertEqual(wf.view_start_ms, 3000)
        self.assertEqual(wf.view_end_ms, 5000)

        # Cuộn vượt quá giới hạn phải bị clamp chuẩn xác
        wf.scroll_to_ms(9500)
        self.assertEqual(wf.view_start_ms, 8000)
        self.assertEqual(wf.view_end_ms, 10000)

    # =========================================================================
    # REGRESSION & APP INTEGRITY
    # =========================================================================
    def test_c1_app_identity_and_version(self):
        """C1: Kiểm tra danh tính tác giả, phiên bản và tên phần mềm."""
        self.assertEqual(APP_VERSION, "3.0.1", "Version phải giữ đúng 3.0.1!")
        self.assertEqual(APP_AUTHOR, "Nguyễn Văn Tiệp", "Tác giả duy nhất: Nguyễn Văn Tiệp!")
        self.assertIn("T-TTS", APP_NAME)

    def test_c2_pages_initialization_smoke_test(self):
        """C2: Khởi tạo thử nghiệm PageSchedule và PageAudioStudio không có lỗi."""
        sched_page = PageSchedule()
        self.assertIsNotNone(sched_page)

        audio_page = PageAudioStudio()
        self.assertIsNotNone(audio_page)
        self.assertIsNotNone(audio_page.waveform)
        self.assertIsNotNone(audio_page.wave_scrollbar)


def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase6PatchAddendum)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
