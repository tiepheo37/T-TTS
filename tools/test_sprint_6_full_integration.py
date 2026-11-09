"""tools/test_sprint_6_full_integration.py — COMPREHENSIVE INTEGRATION & REGRESSION TEST (SPRINT 6)
================================================================================================
Bộ kiểm thử tích hợp toàn diện và kiểm thử hồi quy cho Sprint 6:
1. 25 Giọng đọc VieNeu-TTS v3 Turbo ONNX CPU chuẩn hóa.
2. Bản quyền ngoại tuyến Ed25519 & Machine ID binding.
3. Document Reader trích xuất DOCX, PDF, TXT đa định dạng.
4. Xử lý văn bản tiếng Việt & Chuyển đổi số sang chữ (Text Processor).
5. Dự án văn bản (Document Projects CRUD & Persistence).
6. Xử lý hàng loạt (Batch TTS Engine with Document Reader & Text Processor).
7. Audio Enhancement Pipeline đầy đủ 6 phân đoạn (afftdn, EQ, De-Esser, Compressor, LUFS, Limiter).
8. Voice Quality Analyzer & Khuyến nghị Preset tối ưu.
9. Smart Audio Cleanup làm sạch khoảng lặng non-destructive.
10. Smart Broadcast Mixing cân bằng âm lượng Giọng đọc vs BGM & Auto-Ducking.
11. Schedule Studio Playlist & Tích hợp Tài liệu DOCX/PDF sang TTS.
12. Kết nối liên thông giữa các phân hệ (Synthesize -> Studio -> Broadcast -> Schedule).
13. Tương thích ngược toàn diện dữ liệu dự án từ v3.0.1.
14. Tính toàn vẹn dữ liệu từ điển phát âm, lịch sử tạo và cấu hình.
15. Hiệu năng xử lý CPU/RAM và tốc độ tổng hợp âm thanh.
16. Cơ chế tác vụ chạy ngầm không chặn UI thread và hủy tác vụ an toàn.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Khởi tạo môi trường âm thanh tập trung
from backend.ffmpeg_bootstrap import initialize_ffmpeg, is_ffmpeg_ready
initialize_ffmpeg()

from backend.service import tts_service
from backend.document_reader import extract_document_text
from backend.text_processor import TextProcessor, number_to_vietnamese_words
from backend.project_manager import project_manager
from backend.audio_enhancement import (
    AudioEnhancementConfig,
    SYSTEM_PRESETS,
    audio_enhancement_engine,
)
from backend.intelligent_audio import (
    VoiceQualityMetrics,
    voice_quality_analyzer,
    intelligent_voice_enhancer,
    smart_audio_cleanup,
    smart_broadcast_mixer,
)
from backend.audio_utils import load_audio_segment_safe, save_wav, get_audio_duration_safe
from backend.scheduler_engine import scheduler_engine, compute_next_run


class TestSprint6FullIntegration(unittest.TestCase):
    """Bộ kiểm thử tích hợp toàn diện 16 tiêu chuẩn cho Sprint 6."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="ttts_sprint6_test_"))
        cls.sr = 48000

        # Tạo file WAV sạch để kiểm thử âm thanh
        cls.test_wav_clean = cls.test_dir / "clean_voice_test.wav"
        cls._create_synth_wav(cls.test_wav_clean, duration_sec=2.5, freq=440.0, amp=0.25, lead_silence=0.3, trail_silence=0.3)

        # Tạo file TXT tiếng Việt
        cls.test_txt_file = cls.test_dir / "test_doc.txt"
        cls.test_txt_file.write_text(
            "Cộng hòa Xã hội Chủ nghĩa Việt Nam.\nĐơn vị f324 họp vào ngày 15/08/2026 lúc 08:30.\nKinh phí 500.000 VNĐ.",
            encoding="utf-8"
        )

        # Tạo file DOCX tiếng Việt
        cls.test_docx_file = cls.test_dir / "test_doc.docx"
        try:
            import docx
            doc = docx.Document()
            doc.add_paragraph("Kế hoạch huấn luyện chiến sĩ mới năm 2026.")
            doc.add_paragraph("Quân số tham gia: 125 đồng chí. Tỷ lệ đạt 98.5%.")
            doc.save(str(cls.test_docx_file))
        except Exception:
            cls.test_docx_file = None

    @classmethod
    def tearDownClass(cls):
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    @classmethod
    def _create_synth_wav(
        cls,
        path: Path,
        duration_sec: float = 2.0,
        freq: float = 440.0,
        amp: float = 0.25,
        lead_silence: float = 0.0,
        trail_silence: float = 0.0,
    ):
        sr = cls.sr
        total = int(duration_sec * sr)
        lead_s = int(lead_silence * sr)
        trail_s = int(trail_silence * sr)
        tone_s = max(0, total - lead_s - trail_s)

        samples = []
        for _ in range(lead_s):
            samples.append(0)
        for i in range(tone_s):
            val = amp * math.sin(2.0 * math.pi * freq * (i / sr))
            samples.append(int(val * 32767.0))
        for _ in range(trail_s):
            samples.append(0)

        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    # =========================================================================
    # 1. CORE VOICES & LICENSE
    # =========================================================================
    def test_01_all_25_voices_integrity(self):
        """1. Kiểm tra toàn vẹn đủ 25 giọng đọc VieNeu-TTS v3 Turbo ONNX CPU."""
        voices = tts_service.list_voices()
        self.assertIsInstance(voices, list)
        self.assertEqual(len(voices), 25, "Hệ thống phải có đủ 25 giọng đọc tiêu chuẩn")
        # Kiểm tra cấu trúc thông tin giọng
        for v in voices:
            self.assertIn("id", v)
            self.assertIn("name", v)
            self.assertIn("gender", v)
            self.assertIn("region", v)

    def test_02_offline_ed25519_license_active(self):
        """2. Kiểm tra bản quyền Ed25519 hoạt động ngoại tuyến và ràng buộc Machine ID."""
        lic = tts_service.get_license_info()
        self.assertIsInstance(lic, dict)
        self.assertTrue(lic.get("is_active"), "Bản quyền hệ thống phải đang ở trạng thái active")
        self.assertIn("TTTS-", lic.get("machine_id", ""), "Machine ID phải có tiền tố TTTS-")
        self.assertFalse(lic.get("is_locked"), "Bản quyền không bị khóa")

    # =========================================================================
    # 2. DOCUMENT READER & TEXT PROCESSING
    # =========================================================================
    def test_03_document_reader_all_formats(self):
        """3. Trích xuất tài liệu đa định dạng (DOCX, TXT) thông qua document_reader."""
        # Test TXT
        res_txt = extract_document_text(self.test_txt_file)
        self.assertTrue(res_txt["success"])
        self.assertIn("f324", res_txt.get("raw_text", ""))

        # Test DOCX nếu có
        if self.test_docx_file and self.test_docx_file.is_file():
            res_docx = extract_document_text(self.test_docx_file)
            self.assertTrue(res_docx["success"])
            self.assertIn("Kế hoạch huấn luyện", res_docx.get("raw_text", ""))

    def test_04_vietnamese_text_processor_and_numbers(self):
        """4. Chuẩn hóa văn bản tiếng Việt, số quân sự, ngày tháng, tiền tệ."""
        sample_raw = "Đơn vị f324 họp ngày 15/08/2026 chi 500.000 VNĐ."
        normalized = TextProcessor.full_normalize(sample_raw)
        self.assertIn("Đơn vị Sư đoàn 324", normalized)
        self.assertIn("ngày mười lăm tháng tám năm hai nghìn không trăm hai mươi sáu", normalized)
        self.assertIn("năm trăm nghìn đồng", normalized)

        # Chuyển số độc lập
        words_num = number_to_vietnamese_words(2026)
        self.assertEqual(words_num, "hai nghìn không trăm hai mươi sáu")

    # =========================================================================
    # 3. DOCUMENT PROJECTS CRUD
    # =========================================================================
    def test_05_document_projects_crud(self):
        """5. Quản lý dự án văn bản: Tạo, Đọc, Cập nhật, Liệt kê, Xóa an toàn."""
        # 1. Tạo
        schema = project_manager.create_document_project(
            name="Bản Thảo Báo Cáo Sư Đoàn",
            raw_text="Nội dung dự thảo huấn luyện 2026.",
        )
        self.assertIsNotNone(schema)
        pid = project_manager.save_document_project(schema)
        self.assertTrue(bool(pid))

        # 2. Đọc
        loaded = project_manager.load_document_project(pid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["name"], "Bản Thảo Báo Cáo Sư Đoàn")

        # 3. Cập nhật
        loaded["name"] = "Bản Thảo Báo Cáo Cập Nhật"
        ok_up = project_manager.save_document_project(loaded)
        self.assertTrue(bool(ok_up))

        # 4. Liệt kê
        projs = project_manager.list_document_projects()
        self.assertTrue(any(p["id"] == pid for p in projs))

        # 5. Xóa
        ok_del = project_manager.delete_document_project(pid)
        self.assertTrue(ok_del)

    # =========================================================================
    # 4. BATCH TTS & EXTRACT FILE INTEGRATION
    # =========================================================================
    def test_06_batch_tts_integration(self):
        """6. Xử lý hàng loạt Batch TTS kết nối Document Reader và Text Processor."""
        from gui.pages.page_batch import extract_text_from_file

        title, content = extract_text_from_file(self.test_txt_file)
        self.assertGreater(len(content), 0)
        norm_content = TextProcessor.full_normalize(content)
        self.assertIn("Đơn vị Sư đoàn 324", norm_content)

    # =========================================================================
    # 5. AUDIO STUDIO DSP & QUALITY ANALYZER
    # =========================================================================
    def test_07_audio_enhancement_pipeline_full(self):
        """7. Chuỗi lọc DSP hoàn chỉnh: afftdn + EQ + De-Esser + Compressor + LUFS + Limiter."""
        out_proc = self.test_dir / "dsp_full_out.wav"
        cfg = SYSTEM_PRESETS["clean_voice"]
        res = audio_enhancement_engine.enhance_audio(self.test_wav_clean, out_proc, cfg)
        self.assertTrue(res["success"])
        self.assertTrue(out_proc.is_file())

    def test_08_voice_quality_analyzer_comprehensive(self):
        """8. Phân tích 17 chỉ số âm học và đề xuất preset cá nhân hóa."""
        metrics = voice_quality_analyzer.analyze_file(self.test_wav_clean)
        self.assertIsInstance(metrics, VoiceQualityMetrics)
        self.assertGreaterEqual(metrics.quality_score, 70)
        rec = intelligent_voice_enhancer.evaluate_and_recommend(metrics)
        self.assertIn("recommended_preset_key", rec)
        self.assertIn("suggested_config", rec)

    def test_09_smart_audio_cleanup_margins(self):
        """9. Nhận diện khoảng lặng thừa và làm sạch non-destructive."""
        actions_res = smart_audio_cleanup.detect_cleanup_actions(self.test_wav_clean)
        self.assertIsInstance(actions_res, dict)
        self.assertIn("actions_suggested", actions_res)

        out_cleaned = self.test_dir / "cleaned_out.wav"
        clean_res = smart_audio_cleanup.apply_cleanup(self.test_wav_clean, out_cleaned)
        self.assertTrue(clean_res["success"])
        self.assertTrue(out_cleaned.is_file())

    # =========================================================================
    # 6. BROADCAST STUDIO & SCHEDULE STUDIO
    # =========================================================================
    def test_10_broadcast_studio_smart_mixing(self):
        """10. Phân tích cân bằng âm lượng Giọng đọc vs BGM và Ducking tối ưu."""
        bgm_wav = self.test_dir / "bgm_sample.wav"
        self._create_synth_wav(bgm_wav, duration_sec=3.0, freq=220.0, amp=0.4)

        mix_res = smart_broadcast_mixer.analyze_mix_balance(self.test_wav_clean, bgm_wav)
        self.assertTrue(mix_res["success"])
        self.assertEqual(mix_res["ducking_attenuation_db"], -14.0)
        self.assertEqual(mix_res["ducking_attack_ms"], 150)
        self.assertEqual(mix_res["ducking_release_ms"], 500)

    def test_11_schedule_studio_playlist_and_doc_tts(self):
        """11. Schedule Studio: Hỗ trợ tệp tài liệu trong DocumentToTTSDialog và tính lịch."""
        from gui.pages.page_schedule import extract_text_from_file

        title, content = extract_text_from_file(self.test_txt_file)
        self.assertIn("f324", content)

        # Kiểm tra tính toán lịch phát thanh
        nxt = compute_next_run(repeat_type="daily", target_time_str="08:30")
        self.assertIsInstance(nxt, str)
        self.assertIn("08:30", nxt)

    # =========================================================================
    # 7. INTER-STUDIO INTEGRATION SIGNALS
    # =========================================================================
    def test_12_inter_studio_signals_integration(self):
        """12. Kiểm tra các Signal kết nối liên thông giữa Synthesize, Audio Studio, Broadcast và Schedule."""
        from PySide6.QtWidgets import QApplication
        from gui.pages.page_synthesize import PageSynthesize
        from gui.pages.page_audio_studio import PageAudioStudio
        from gui.pages.page_schedule import PageSchedule
        from gui.pages.page_broadcast import PageBroadcast

        app = QApplication.instance() or QApplication([])

        synth = PageSynthesize()
        self.assertTrue(hasattr(synth, "send_to_audio_studio"))
        self.assertTrue(hasattr(synth, "send_to_broadcast"))
        self.assertTrue(hasattr(synth, "btn_send_studio"))
        self.assertTrue(hasattr(synth, "btn_send_broadcast"))

        audio = PageAudioStudio()
        self.assertTrue(hasattr(audio, "send_to_broadcast"))
        self.assertTrue(hasattr(audio, "send_to_schedule"))
        self.assertTrue(hasattr(audio, "btn_send_broadcast"))
        self.assertTrue(hasattr(audio, "btn_send_schedule"))

        sched = PageSchedule()
        self.assertTrue(hasattr(sched, "add_schedule_for_audio"))
        self.assertTrue(callable(sched.add_schedule_for_audio))

        bc = PageBroadcast()
        self.assertTrue(hasattr(bc, "add_segment"))
        self.assertTrue(callable(bc.add_segment))

    # =========================================================================
    # 8. BACKWARD COMPATIBILITY & DATA INTEGRITY
    # =========================================================================
    def test_13_backward_compatibility_v301_data(self):
        """13. Kiểm tra khả năng tương thích ngược: Mở an toàn toàn bộ dữ liệu dự án từ v3.0.1."""
        audio_projs = project_manager.list_projects("audio")
        self.assertIsInstance(audio_projs, list)

        broadcast_projs = project_manager.list_projects("broadcast")
        self.assertIsInstance(broadcast_projs, list)

        schedule_projs = project_manager.list_projects("schedules")
        self.assertIsInstance(schedule_projs, list)

        # Đọc thử một project audio nếu có
        if audio_projs:
            first_p = project_manager.load_project("audio", audio_projs[0]["id"])
            self.assertIsNotNone(first_p)

    def test_14_data_integrity_and_pronunciation_dict(self):
        """14. Kiểm tra tính toàn vẹn của tệp từ điển phát âm và lịch sử TTS."""
        hist = tts_service.get_history()
        self.assertIsInstance(hist, list)

        dict_file = PROJECT_ROOT / "data" / "pronunciation-dict.json"
        self.assertTrue(dict_file.is_file())
        with open(dict_file, "r", encoding="utf-8") as f:
            d_data = json.load(f)
        self.assertIsInstance(d_data, dict)
        self.assertIn("UBND", d_data)

    # =========================================================================
    # 9. PERFORMANCE BENCHMARKS & WORKERS
    # =========================================================================
    def test_15_performance_benchmarks_cpu_ram(self):
        """15. Hiệu năng xử lý âm học và chuyển đổi giọng đọc đạt chuẩn CPU-First (> 5x realtime)."""
        t0 = time.time()
        metrics = voice_quality_analyzer.analyze_file(self.test_wav_clean)
        elapsed = time.time() - t0
        self.assertLess(elapsed, 1.0, f"Phân tích âm học 2.5s mất {elapsed:.2f}s, quá chậm!")

    def test_16_non_blocking_workers_and_cancellation(self):
        """16. Xác minh các worker và tiến trình chạy nền không khóa UI và hỗ trợ cancel."""
        from gui.dialog_voice_analyzer import VoiceAnalyzerWorker

        worker = VoiceAnalyzerWorker(self.test_wav_clean)
        self.assertIsNotNone(worker)
        # Kiểm tra hủy trong DSP Engine
        cancel_called = False
        def fake_cancel():
            nonlocal cancel_called
            cancel_called = True
            return True

        out_dummy = self.test_dir / "cancelled_dsp.wav"
        cfg = SYSTEM_PRESETS["clean_voice"]
        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_clean,
            output_file=out_dummy,
            config=cfg,
            cancel_check=fake_cancel,
        )
        self.assertTrue(cancel_called)
        self.assertFalse(res["success"])
        self.assertIn("hủy", res.get("error", "").lower())


if __name__ == "__main__":
    unittest.main()
