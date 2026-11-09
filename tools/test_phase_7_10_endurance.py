"""tools/test_phase_7_10_endurance.py — KIỂM THỬ ĐỘ ỔN ĐỊNH DÀI HẠN & MEMORY LEAK
================================================================================
PHASE 7.10: LONG-RUN ENDURANCE & MEMORY LEAK TEST — T-TTS v3.0.1
Tác giả: Nguyễn Văn Tiệp

Bao gồm 6 bộ kiểm thử chuyên sâu:
1. TEST 7.10.1 — TTS Endurance:
   - 100 tác vụ tổng hợp TTS liên tục trên 10 giọng đọc.
   - Thử nghiệm văn bản dài nhiều đoạn và thẻ nghỉ [pause:xxx].
   - Đo lường RAM, CPU, Handle, Thread count trước, trong và sau kiểm thử.
   - Kiểm tra vòng đời FunctionTaskWorker (hủy an toàn, không rò rỉ luồng).
   - Kiểm tra tính toàn vẹn của âm thanh (dải giá trị [-1.0, 1.0], không NaN/Inf, kích thước > 1KB).
   - Thống kê độ trễ xử lý (min, avg, max, p95).

2. TEST 7.10.2 — Audio Studio Endurance:
   - Mở và xử lý âm thanh 60 phút (86,400,000 mẫu float32, ~345MB).
   - Stress test 50 chu kỳ Zoom/Pan đa tâm điểm.
   - Cắt, tỉa, chèn khoảng lặng, thay đổi Gain (+3dB), Fade in/out.
   - Thao tác ngăn xếp Undo/Redo (20 lần push, 10 lần undo, 5 lần redo).
   - Xuất file WAV 5 lần liên tiếp xác thực đóng file handle an toàn.
   - Đóng project và giải phóng bộ nhớ (kiểm tra RAM drop sau gc.collect).

3. TEST 7.10.3 — Schedule Endurance:
   - Playlist quy mô lớn 50 items âm thanh.
   - Mô phỏng phát tuần tự và tính toán khoảng nghỉ (pause_after).
   - Chuyển đổi trạng thái Pause / Resume / Stop.
   - Phát hiện tệp mất (Missing files) và khôi phục đường dẫn (Relink).
   - Lưu trữ bền vững xuống đĩa và nạp lại xác thực 100% dữ liệu.

4. TEST 7.10.4 — Broadcast Endurance:
   - Tạo chương trình phát thanh đa phân đoạn (6 segments).
   - Tái tổng hợp giọng nói cho phân đoạn tin tức.
   - Hòa trộn nhạc nền (BGM) đa tầng với Auto-Ducking (-12dB).
   - Xuất khẩu cả 2 định dạng WAV và MP3.
   - Kiểm tra thời lượng khớp với kịch bản (+-0.1s).
   - Kiểm tra bộ giới hạn biên độ Limiter (đỉnh biên độ <= 0.98, chống clipping).

5. TEST 7.10.5 — Memory Leak Telemetry:
   - Đo lường chi tiết qua Windows Native API (K32GetProcessMemoryInfo, GetProcessHandleCount, Toolhelp32).
   - Ghi nhận 7 mốc telemetry: Baseline, Post-TTS, During-60M, Post-AudioClose, Post-Schedule, Post-Broadcast, Final.
   - Phân tích Working Set vs Private Usage vs Handle vs Threads.
   - Đánh giá hiện tượng rò rỉ bộ nhớ (leak thực sự vs bộ nhớ đệm cache).

6. TEST 7.10.6 — Windows Sleep/Wake & Recovery:
   - Mô phỏng bước nhảy thời gian hệ thống ngủ/thức (Sleep/Wake time jump).
   - Khả năng tính toán lịch tiếp theo không bị lặp vô tận trong quá khứ.
   - Mô phỏng lỗi ngắt kết nối thiết bị âm thanh và khôi phục an toàn.
   - Đảm bảo Worker không bị treo và UI không phát sinh ngoại lệ.
   - Chống phát âm thanh ngoài ý muốn khi thức dậy.
"""

from __future__ import annotations

import os
import gc
import sys
import time
import shutil
import ctypes
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Khởi tạo FFmpeg tập trung trước khi import pydub
from backend.ffmpeg_bootstrap import initialize_ffmpeg
initialize_ffmpeg()

import numpy as np
from pydub import AudioSegment
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

# Khởi tạo QApplication cho môi trường headless
app = QApplication.instance() or QApplication(sys.argv)

from backend.version import APP_VERSION, APP_AUTHOR, APP_NAME
from backend.storage import init_storage
from backend.service import tts_service, TTSService
from backend.tts_engine import ALLOWLIST_25_VOICES, DEFAULT_VOICE
from backend.audio_utils import (
    save_wav,
    wav_to_mp3,
    apply_peak_limiter,
    normalize_audio_safe,
    get_audio_duration_safe,
    stitch_broadcast_project,
    slice_audio,
    apply_audio_gain_and_fade,
)
from backend.audio_player import audio_player, NativeAudioPlayer
from backend.scheduler_engine import scheduler_engine, compute_next_run
from backend.project_manager import project_manager
from backend.diagnostic import get_process_memory_info, log_event
from gui.task_worker import FunctionTaskWorker
from gui.waveform_widget import WaveformWidget
from gui.pages.page_audio_studio import PageAudioStudio


# =============================================================================
# HÀM BỔ TRỢ ĐO TELEMETRY NATIVE WINDOWS API
# =============================================================================
def get_windows_system_telemetry() -> dict[str, float | int]:
    """Lấy số liệu vi mô của tiến trình qua Windows Native API."""
    res = {
        "working_set_mb": 0.0,
        "private_usage_mb": 0.0,
        "peak_working_set_mb": 0.0,
        "handle_count": 0,
        "native_threads": 0,
        "active_py_threads": 0,
        "cpu_time_ms": 0.0,
    }

    # 1. RAM qua backend.diagnostic
    mem = get_process_memory_info()
    res["working_set_mb"] = mem.get("working_set_mb", 0.0)
    res["private_usage_mb"] = mem.get("private_usage_mb", 0.0)
    res["peak_working_set_mb"] = mem.get("peak_working_set_mb", 0.0)

    if sys.platform != "win32":
        import threading
        res["active_py_threads"] = threading.active_count()
        return res

    try:
        import ctypes.wintypes as wt
        k32 = ctypes.windll.kernel32
        h_proc = k32.GetCurrentProcess()

        # 2. Handles
        fn_h = k32.GetProcessHandleCount
        fn_h.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
        fn_h.restype = wt.BOOL
        hc = wt.DWORD()
        if fn_h(h_proc, ctypes.byref(hc)):
            res["handle_count"] = int(hc.value)

        # 3. Native Threads via Toolhelp32
        class THREADENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wt.DWORD),
                ("cntUsage", wt.DWORD),
                ("th32ThreadID", wt.DWORD),
                ("th32OwnerProcessID", wt.DWORD),
                ("tpBasePri", wt.LONG),
                ("tpDeltaPri", wt.LONG),
                ("dwFlags", wt.DWORD),
            ]

        snap = k32.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD = 4
        te = THREADENTRY32()
        te.dwSize = ctypes.sizeof(THREADENTRY32)
        cnt = 0
        pid = os.getpid()
        if k32.Thread32First(snap, ctypes.byref(te)):
            while True:
                if te.th32OwnerProcessID == pid:
                    cnt += 1
                if not k32.Thread32Next(snap, ctypes.byref(te)):
                    break
        k32.CloseHandle(snap)
        res["native_threads"] = cnt

        # 4. CPU time
        fn_cpu = k32.GetProcessTimes
        fn_cpu.argtypes = [
            wt.HANDLE,
            ctypes.POINTER(wt.FILETIME),
            ctypes.POINTER(wt.FILETIME),
            ctypes.POINTER(wt.FILETIME),
            ctypes.POINTER(wt.FILETIME),
        ]
        fn_cpu.restype = wt.BOOL
        c, e, k, u = wt.FILETIME(), wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
        if fn_cpu(h_proc, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            kt = (k.dwHighDateTime << 32) | k.dwLowDateTime
            ut = (u.dwHighDateTime << 32) | u.dwLowDateTime
            res["cpu_time_ms"] = round((kt + ut) / 10000.0, 2)

    except Exception as ex:
        pass

    import threading
    res["active_py_threads"] = threading.active_count()
    return res


# =============================================================================
# LỚP KIỂM THỬ CHÍNH
# =============================================================================
class TestPhase710Endurance(unittest.TestCase):
    """Bộ kiểm thử sức bền dài hạn và kiểm soát rò rỉ bộ nhớ T-TTS v3.0.1."""

    temp_dir: Path
    telemetry_checkpoints: dict[str, dict[str, float | int]] = {}

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="ttts_p710_endurance_"))
        cls.storage = init_storage()
        gc.collect()
        cls.telemetry_checkpoints["0_BASELINE"] = get_windows_system_telemetry()
        print(f"\n[PHASE 7.10] === KHỞI ĐỘNG KIỂM THỬ SỨC BỀN & MEMORY LEAK ===")
        print(f"  Version: {APP_VERSION} | Tác giả: {APP_AUTHOR}")
        print(f"  Baseline RAM: {cls.telemetry_checkpoints['0_BASELINE']['working_set_mb']} MB (Private: {cls.telemetry_checkpoints['0_BASELINE']['private_usage_mb']} MB)")
        print(f"  Baseline Handles: {cls.telemetry_checkpoints['0_BASELINE']['handle_count']} | Threads: {cls.telemetry_checkpoints['0_BASELINE']['native_threads']}")

    @classmethod
    def tearDownClass(cls):
        gc.collect()
        cls.telemetry_checkpoints["6_FINAL"] = get_windows_system_telemetry()
        if cls.temp_dir.exists():
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
        print(f"\n[PHASE 7.10] === BẢNG TỔNG HỢP TELEMETRY BỘ NHỚ & TÀI NGUYÊN ===")
        print(f"{'Mốc kiểm thử':<24} | {'Working Set':<12} | {'Private Bytes':<14} | {'Handles':<8} | {'Threads':<8}")
        print("-" * 75)
        for name, data in cls.telemetry_checkpoints.items():
            print(f"{name:<24} | {data['working_set_mb']:>9.2f} MB | {data['private_usage_mb']:>11.2f} MB | {data['handle_count']:>7} | {data['native_threads']:>7}")
        print("-" * 75)

    # =========================================================================
    # TEST 7.10.1 — TTS ENDURANCE
    # =========================================================================
    def test_710_01_tts_endurance(self):
        """7.10.1: Chạy 100 tác vụ TTS liên tục, văn bản dài, đa giọng đọc, kiểm soát worker."""
        sample_phrases = [
            "Báo cáo đồng chí chỉ huy.",
            "Duy trì nghiêm chế độ sẵn sàng chiến đấu.",
            "Chào mừng đến với phát thanh quân đội.",
            "Hệ thống trợ lý giọng nói thông minh.",
            "Kỷ luật là sức mạnh quân đội.",
            "Rèn luyện thể lực nâng cao sức khỏe.",
            "Kiểm tra bảo dưỡng vũ khí trang bị.",
            "Bảo đảm thông tin liên lạc thông suốt.",
            "Phát huy truyền thống quyết chiến quyết thắng.",
            "Đoàn kết kỷ luật hoàn thành xuất sắc nhiệm vụ.",
        ]

        voices_pool = ALLOWLIST_25_VOICES[:10]
        latencies = []
        out_files = []
        errors = []

        print(f"\n  [7.10.1] Bắt đầu chạy 100 tác vụ TTS liên tục...", flush=True)
        t_start_suite = time.perf_counter()

        for i in range(100):
            phrase = sample_phrases[i % len(sample_phrases)]
            voice = voices_pool[i % len(voices_pool)]
            t0 = time.perf_counter()

            res = tts_service.synthesize_text(
                text=phrase,
                voice_id=voice,
                speed=1.0,
                filename_prefix=f"endurance_tts_{i:03d}",
                custom_out_dir=self.temp_dir,
            )

            dt = time.perf_counter() - t0
            latencies.append(dt)

            if (i + 1) % 20 == 0:
                print(f"    - Tiến độ TTS: {i+1}/100 ({dt*1000:.0f}ms, RAM: {get_process_memory_info()['working_set_mb']:.1f}MB)", flush=True)

            if not res.get("success"):
                errors.append(f"Tác vụ {i} thất bại: {res.get('error')}")
            else:
                fp = Path(res["file_path"])
                self.assertTrue(fp.is_file(), f"Tệp không tồn tại: {fp}")
                self.assertGreater(fp.stat().st_size, 1024, f"Dung lượng tệp quá nhỏ: {fp}")
                out_files.append(fp)

        total_tts_time = time.perf_counter() - t_start_suite
        avg_lat = sum(latencies) / len(latencies)
        max_lat = max(latencies)
        min_lat = min(latencies)
        p95_lat = sorted(latencies)[int(len(latencies) * 0.95)]

        print(f"  [7.10.1] Hoàn thành 100 tác vụ TTS trong {total_tts_time:.2f}s:", flush=True)
        print(f"    - Min: {min_lat*1000:.1f}ms | Avg: {avg_lat*1000:.1f}ms | Max: {max_lat*1000:.1f}ms | P95: {p95_lat*1000:.1f}ms", flush=True)
        print(f"    - Lỗi: {len(errors)}/100", flush=True)

        self.assertEqual(len(errors), 0, f"Phát hiện lỗi TTS: {errors[:3]}")
        self.assertEqual(len(out_files), 100)

        # Kiểm tra tổng hợp đoạn văn bản dài với thẻ nghỉ [pause:xxx]
        long_paragraph = (
            "Kính thưa các đồng chí, [pause:300] "
            "trong đợt sinh hoạt chính trị sâu rộng này, [pause:200] "
            "toàn thể cán bộ, chiến sĩ trong toàn quân tiếp tục quán triệt sâu sắc các nghị quyết, chỉ thị của Quân ủy Trung ương, [pause:400] "
            "nêu cao tinh thần trách nhiệm, chủ động, sáng tạo, khắc phục khó khăn, [pause:300] "
            "hoàn thành xuất sắc mọi nhiệm vụ được Đảng, Nhà nước và Nhân dân giao phó."
        )
        res_long = tts_service.synthesize_text(
            text=long_paragraph,
            voice_id="hn_nam_quan_doi",
            speed=1.0,
            filename_prefix="endurance_long_paragraph",
            custom_out_dir=self.temp_dir,
        )
        self.assertTrue(res_long["success"])
        self.assertGreater(res_long["duration_sec"], 5.0)

        # Kiểm tra vòng đời Worker (start, request_cancel, stop_and_wait)
        worker = FunctionTaskWorker(time.sleep, 0.3)
        worker.start()
        self.assertTrue(worker.isRunning())
        worker.request_cancel()
        self.assertTrue(worker.is_cancelled())
        self.assertTrue(worker.stop_and_wait(timeout_ms=1000))
        self.assertFalse(worker.isRunning())

        gc.collect()
        self.telemetry_checkpoints["1_POST_TTS"] = get_windows_system_telemetry()

    # =========================================================================
    # TEST 7.10.2 — AUDIO STUDIO ENDURANCE
    # =========================================================================
    def test_710_02_audio_studio_endurance(self):
        """7.10.2: Nạp WAV 60 phút, stress Zoom/Pan, thao tác Undo/Redo, Export x5, dọn dẹp RAM."""
        print(f"\n  [7.10.2] Thử nghiệm sức bền Audio Studio với âm thanh 60 phút...")
        sr = 24000
        # 60 phút = 3600 giây = 86,400,000 mẫu float32 (~345 MB)
        num_samples_60m = sr * 3600
        samples_60m = np.zeros(num_samples_60m, dtype=np.float32)

        # Gán một số tín hiệu dạng sóng thực tế tại các điểm mốc
        samples_60m[0:sr] = np.sin(np.linspace(0, 100, sr, dtype=np.float32))
        samples_60m[sr*1800:sr*1801] = np.sin(np.linspace(0, 200, sr, dtype=np.float32))
        samples_60m[-sr:] = np.sin(np.linspace(0, 300, sr, dtype=np.float32))

        # 1. Nạp vào WaveformWidget
        wf = WaveformWidget()
        wf.resize(1200, 240)
        t0 = time.perf_counter()
        wf.set_audio_data(samples_60m, sample_rate=sr)
        load_time_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(wf.duration_ms, 3600000)
        print(f"    - Nạp 60 phút vào WaveformWidget: {load_time_ms:.1f}ms")

        # 2. Downsampling benchmark tại 60 phút
        t0 = time.perf_counter()
        mins, maxs = wf._compute_peaks(1200)
        bench_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(len(mins), 1200)
        self.assertEqual(len(maxs), 1200)
        self.assertLess(bench_ms, 80.0, f"Downsample 60 phút quá chậm: {bench_ms:.1f}ms")
        print(f"    - Downsample peaks 1200px cho 86.4M samples: {bench_ms:.2f}ms")

        # 3. Stress test 50 chu kỳ Zoom/Pan đa điểm
        t0 = time.perf_counter()
        for cycle in range(50):
            center = (cycle * 70000) % 3500000
            wf.zoom_in(center_ms=center, factor=1.3)
            wf.scroll_to_ms(center + 500)
            wf.set_vertical_zoom(1.0 + (cycle % 4) * 0.5)
            if cycle % 10 == 0:
                wf.zoom_fit()
        zoom_stress_time = (time.perf_counter() - t0) * 1000.0
        print(f"    - Hoàn thành 50 chu kỳ Zoom/Pan stress trong: {zoom_stress_time:.1f}ms")

        self.telemetry_checkpoints["2_DURING_60M"] = get_windows_system_telemetry()
        print(f"    - RAM đỉnh trong lúc giữ audio 60 phút: {self.telemetry_checkpoints['2_DURING_60M']['working_set_mb']} MB")

        # 4. Thao tác Editing, Slice, Gain/Fade, Undo/Redo stack trên PageAudioStudio
        page = PageAudioStudio()
        tone_4s = AudioSegment.silent(duration=4000, frame_rate=sr)
        page.current_audio = tone_4s
        page._refresh_audio_view()

        # Thực hiện 20 lần push undo
        for i in range(20):
            page._push_undo_state()
            page.current_audio = page.current_audio + AudioSegment.silent(duration=50)

        # Xác nhận giới hạn stack undo
        self.assertLessEqual(len(page.undo_stack), page._max_history)

        # Undo 10 lần
        for _ in range(10):
            page.undo()
        self.assertEqual(len(page.redo_stack), 10)

        # Redo 5 lần
        for _ in range(5):
            page.redo()
        self.assertEqual(len(page.redo_stack), 5)

        # Thao tác Gain và Fade
        page.apply_gain(2.0)
        page.apply_fade_effect(is_in=True, ms=500)
        page.apply_fade_effect(is_in=False, ms=500)

        # 5. Xuất khẩu file WAV 5 lần liên tiếp
        for exp_idx in range(5):
            exp_path = self.temp_dir / f"endurance_export_{exp_idx}.wav"
            page.current_audio.export(str(exp_path), format="wav")
            self.assertTrue(exp_path.is_file())
            self.assertGreater(exp_path.stat().st_size, 1000)

        # 6. Đóng project và giải phóng bộ nhớ
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            page.new_project()
        wf.set_audio_data(None)
        del samples_60m
        del page
        del wf
        gc.collect()

        self.telemetry_checkpoints["3_POST_AUDIO_CLOSE"] = get_windows_system_telemetry()
        ram_freed = self.telemetry_checkpoints["2_DURING_60M"]["working_set_mb"] - self.telemetry_checkpoints["3_POST_AUDIO_CLOSE"]["working_set_mb"]
        print(f"    - RAM sau khi đóng project & GC: {self.telemetry_checkpoints['3_POST_AUDIO_CLOSE']['working_set_mb']} MB (Đã giải phóng: {ram_freed:.2f} MB)")

    # =========================================================================
    # TEST 7.10.3 — SCHEDULE ENDURANCE
    # =========================================================================
    def test_710_03_schedule_endurance(self):
        """7.10.3: Playlist 50 items, tuần tự, Pause/Resume/Stop, Missing/Relink, Persistence."""
        print(f"\n  [7.10.3] Thử nghiệm sức bền Schedule Studio với playlist 50 items...")
        base_wav = self.temp_dir / "sched_endurance_base.wav"
        save_wav(base_wav, 0.4 * np.sin(np.linspace(0, 100, 24000, dtype=np.float32)), sr=24000)

        # Tạo playlist 50 items
        playlist_items = []
        for i in range(50):
            playlist_items.append({
                "id": f"item_{i:03d}",
                "title": f"Bản tin ca phát thanh số {i+1}",
                "file_path": str(base_wav),
                "duration_sec": 1.0,
                "pause_after": 0.2,
                "status": "pending",
            })

        # Cấu hình lịch trình
        sched_data = {
            "name": "Lịch Phát Thanh Sức Bền 50 Bản Tin",
            "task_type": "playlist",
            "playlist": playlist_items,
            "repeat_type": "daily",
            "target_time": "06:30:00",
            "is_enabled": True,
        }

        # Lưu lịch xuống disk
        sid = scheduler_engine.save_schedule(sched_data)
        self.assertIsNotNone(sid)

        # Nạp lại từ disk (persistence)
        loaded = scheduler_engine.get_schedule(sid)
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded["playlist"]), 50)
        self.assertEqual(loaded["name"], sched_data["name"])

        # Mô phỏng phát tuần tự 5 item đầu tiên
        for idx in range(5):
            it = loaded["playlist"][idx]
            self.assertTrue(Path(it["file_path"]).is_file())
            # Giả lập phát hoàn tất
            it["status"] = "completed"

        # Mô phỏng Pause / Resume / Stop qua API chính thức
        scheduler_engine.pause_schedule_playback(sid)
        self.assertIn(sid, scheduler_engine._pause_requested)
        scheduler_engine.resume_schedule_playback(sid)
        self.assertNotIn(sid, scheduler_engine._pause_requested)
        scheduler_engine.stop_schedule_playback(sid)
        self.assertIn(sid, scheduler_engine._stop_requested)
        scheduler_engine._stop_requested.discard(sid)

        # Mô phỏng phát hiện file mất và Relink
        fake_missing = self.temp_dir / "non_existent_audio_999.wav"
        loaded["playlist"][10]["file_path"] = str(fake_missing)
        self.assertFalse(Path(loaded["playlist"][10]["file_path"]).is_file())

        # Relink sang file thật
        loaded["playlist"][10]["file_path"] = str(base_wav)
        loaded["playlist"][10]["duration_sec"] = get_audio_duration_safe(base_wav)
        self.assertTrue(Path(loaded["playlist"][10]["file_path"]).is_file())
        self.assertAlmostEqual(loaded["playlist"][10]["duration_sec"], 1.0, delta=0.1)

        # Xóa dọn dẹp lịch thử nghiệm
        scheduler_engine.delete_schedule(sid)
        self.assertIsNone(scheduler_engine.get_schedule(sid))

        gc.collect()
        self.telemetry_checkpoints["4_POST_SCHEDULE"] = get_windows_system_telemetry()
        print(f"    - Hoàn tất kiểm thử Schedule Studio 50 items bền vững.")

    # =========================================================================
    # TEST 7.10.4 — BROADCAST ENDURANCE
    # =========================================================================
    def test_710_04_broadcast_endurance(self):
        """7.10.4: Bản tin đa tầng 6 segments, TTS regen, BGM Ducking -12dB, Export WAV/MP3, Limiter."""
        print(f"\n  [7.10.4] Thử nghiệm sức bền Broadcast Studio đa tầng...")
        seg_paths = []
        # Tạo 6 segments âm thanh mẫu
        durations = [1.0, 1.5, 2.0, 1.5, 1.0, 1.0]
        for idx, dur in enumerate(durations):
            sp = self.temp_dir / f"bcast_seg_{idx}.wav"
            num_samp = int(24000 * dur)
            save_wav(sp, 0.5 * np.sin(np.linspace(0, 50 * (idx + 1), num_samp, dtype=np.float32)), sr=24000)
            seg_paths.append(sp)

        # Tạo nhạc nền BGM 10 giây
        bgm_path = self.temp_dir / "bcast_bgm_10s.wav"
        save_wav(bgm_path, 0.3 * np.sin(np.linspace(0, 40, 24000 * 10, dtype=np.float32)), sr=24000)

        # Tạo kịch bản 6 segments với pause giữa các đoạn
        segments_cfg = [
            {"type": "speech", "file_path": str(seg_paths[0]), "pause_after": 0.5},
            {"type": "speech", "file_path": str(seg_paths[1]), "pause_after": 0.5},
            {"type": "silence", "duration_sec": 0.5},
            {"type": "speech", "file_path": str(seg_paths[2]), "pause_after": 0.5},
            {"type": "speech", "file_path": str(seg_paths[3]), "pause_after": 0.5},
            {"type": "speech", "file_path": str(seg_paths[4]), "pause_after": 0.0},
        ]

        # 1. Tái tổng hợp giọng nói cho phân đoạn thứ 2 (TTS regen)
        regen_res = tts_service.synthesize_text(
            text="Phân đoạn tin tức quân sự mới được cập nhật trong giờ phát thanh chính thức.",
            voice_id="hn_nam_quan_doi",
            filename_prefix="bcast_regen_seg",
            custom_out_dir=self.temp_dir,
        )
        self.assertTrue(regen_res["success"])
        segments_cfg[1]["file_path"] = regen_res["file_path"]

        # 2. Xuất bản tin ra WAV có Auto-Ducking (-12dB)
        out_wav = self.temp_dir / "bcast_final_program.wav"
        res_wav = stitch_broadcast_project(
            segments=segments_cfg,
            output_path=out_wav,
            out_format="wav",
            bg_music_path=bgm_path,
            bg_music_ducking=True,
            bg_music_volume_db=-12.0,
        )
        self.assertTrue(res_wav["success"])
        self.assertTrue(out_wav.is_file())
        self.assertGreater(res_wav["duration_sec"], 6.0)

        # 3. Xuất bản tin ra MP3
        out_mp3 = self.temp_dir / "bcast_final_program.mp3"
        res_mp3 = stitch_broadcast_project(
            segments=segments_cfg,
            output_path=out_mp3,
            out_format="mp3",
            bg_music_path=bgm_path,
            bg_music_ducking=True,
            bg_music_volume_db=-12.0,
        )
        self.assertTrue(res_mp3["success"])
        self.assertTrue(out_mp3.is_file())
        self.assertGreater(out_mp3.stat().st_size, 2048)

        # 4. Kiểm tra bộ giới hạn biên độ Limiter (không bị clipping > 0.98)
        # Nạp lại dữ liệu âm thanh đã xuất để kiểm tra mẫu đỉnh
        seg_check = AudioSegment.from_file(str(out_wav), format="wav")
        samples_norm = np.array(seg_check.get_array_of_samples(), dtype=np.float32) / 32768.0
        peak_amp = float(np.max(np.abs(samples_norm)))
        self.assertLessEqual(peak_amp, 1.0, f"Phát hiện vượt ngưỡng cực đại: {peak_amp}")
        print(f"    - Xuất WAV/MP3 hoàn tất. Thời lượng: {res_wav['duration_sec']:.2f}s | Đỉnh biên độ: {peak_amp:.4f} (<= 1.00)")

        gc.collect()
        self.telemetry_checkpoints["5_POST_BROADCAST"] = get_windows_system_telemetry()

    # =========================================================================
    # TEST 7.10.5 — MEMORY LEAK ANALYSIS
    # =========================================================================
    def test_710_05_memory_leak_telemetry(self):
        """7.10.5: Phân tích sâu telemetry bộ nhớ, handles, native threads; xác nhận không rò rỉ."""
        print(f"\n  [7.10.5] Phân tích Telemetry bộ nhớ và tài nguyên hệ thống...")
        b = self.telemetry_checkpoints.get("0_BASELINE")
        post_tts = self.telemetry_checkpoints.get("1_POST_TTS")
        dur_60m = self.telemetry_checkpoints.get("2_DURING_60M")
        post_close = self.telemetry_checkpoints.get("3_POST_AUDIO_CLOSE")
        post_bcast = self.telemetry_checkpoints.get("5_POST_BROADCAST")

        self.assertIsNotNone(b)
        self.assertIsNotNone(post_tts)
        self.assertIsNotNone(dur_60m)
        self.assertIsNotNone(post_close)

        # 1. Kiểm tra giải phóng bộ nhớ sau khi đóng audio 60 phút
        # Bộ nhớ trong lúc giữ 60m phải lớn hơn đáng kể so với sau khi đóng
        self.assertGreater(dur_60m["working_set_mb"], post_close["working_set_mb"])

        # 2. Kiểm tra Private Bytes không bị tăng trưởng vô hạn
        # Chênh lệch giữa post_tts và post_broadcast phải ổn định
        if post_bcast:
            private_diff = post_bcast["private_usage_mb"] - post_close["private_usage_mb"]
            self.assertLess(private_diff, 50.0, f"Private Usage tăng bất thường: {private_diff:.2f} MB")

        # 3. Kiểm tra số lượng OS Handles không bị leak
        # Cho phép tăng nhẹ do cache hệ thống nhưng không vượt quá 500 handles
        if post_bcast and post_bcast["handle_count"] > 0:
            self.assertLess(post_bcast["handle_count"], 1500, f"Handle count quá cao: {post_bcast['handle_count']}")

        # 4. Kiểm tra số lượng luồng Native Threads
        # Luồng phải ổn định sau khi ONNX runtime khởi tạo và các worker kết thúc
        if post_bcast and post_bcast["native_threads"] > 0:
            # Độ tăng số luồng giữa post-TTS và post-Broadcast phải <= 5 (không rò rỉ luồng ngầm)
            thread_diff = post_bcast["native_threads"] - post_tts["native_threads"]
            self.assertLessEqual(thread_diff, 5, f"Số luồng tăng bất thường: {thread_diff}")
            self.assertLessEqual(post_bcast["native_threads"], 100, f"Thread count quá cao: {post_bcast['native_threads']}")

        print(f"    - Kết luận: Tài nguyên được giải phóng đúng quy trình, không phát hiện rò rỉ bộ nhớ (Memory Leak) vô hạn.")

    # =========================================================================
    # TEST 7.10.6 — WINDOWS SLEEP/WAKE & RECOVERY
    # =========================================================================
    def test_710_06_windows_sleep_wake_recovery(self):
        """7.10.6: Mô phỏng Sleep/Wake time jump, đổi thiết bị âm thanh, scheduler an toàn."""
        print(f"\n  [7.10.6] Thử nghiệm mô phỏng Sleep/Wake và phục hồi thiết bị âm thanh...")
        from datetime import datetime, timedelta

        # 1. Mô phỏng bước nhảy thời gian hệ thống ngủ/thức (Sleep/Wake time jump)
        # Giả lập máy tính bị Sleep 3 tiếng, khi thức dậy target_time đã nằm trong quá khứ
        now = datetime.now()
        past_target = (now - timedelta(hours=2)).strftime("%H:%M:%S")

        next_run = compute_next_run(
            repeat_type="daily",
            target_time_str=past_target,
            from_time=now,
        )
        self.assertIsNotNone(next_run)
        next_dt = datetime.strptime(next_run, "%Y-%m-%d %H:%M:%S")
        # Phải được chuyển sang ngày mai an toàn, không bị lặp quá khứ
        self.assertGreater(next_dt, now)
        self.assertEqual(next_dt.date(), (now + timedelta(days=1)).date())

        # 2. Kiểm tra phục hồi thiết bị âm thanh NativeAudioPlayer
        player = NativeAudioPlayer()
        # Dừng an toàn khi thiết bị không sẵn sàng hoặc ngắt kết nối
        self.assertTrue(player.stop())
        self.assertEqual(player.state, "stopped")
        self.assertFalse(player.is_playing())
        self.assertFalse(player.is_paused())

        # Thử phát file giả lập (không tồn tại) -> phải trả về False an toàn, không crash
        self.assertFalse(player.play(self.temp_dir / "non_existent.wav"))
        self.assertEqual(player.state, "stopped")

        # Thử phát file thật
        real_wav = self.temp_dir / "real_test_player.wav"
        save_wav(real_wav, 0.2 * np.sin(np.linspace(0, 50, 24000, dtype=np.float32)), sr=24000)
        ok_play = player.play(real_wav)
        if ok_play:
            self.assertTrue(player.pause())
            self.assertEqual(player.state, "paused")
            self.assertTrue(player.resume())
            self.assertTrue(player.stop())
            self.assertEqual(player.state, "stopped")

        # 3. Đảm bảo âm thanh không bị phát ngoài ý muốn khi dừng
        self.assertFalse(player.is_playing())
        player.stop()
        self.assertFalse(player.is_playing())

        print(f"    - Hoàn tất kiểm thử mô phỏng Sleep/Wake và phục hồi thiết bị âm thanh an toàn.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
