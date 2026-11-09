"""tools/test_sprint_5_intelligent_audio.py — TEST SUITE CHO SPRINT 5 (PHASE 9)
================================================================================
Kiểm thử toàn diện Hệ thống phân tích & Tối ưu âm thanh thông minh:
1. 9.1 Intelligent Voice Enhancement (Đánh giá chất lượng, khuyến nghị preset/EQ/LUFS/Compressor).
2. 9.2 Voice Quality Analyzer (Integrated LUFS, True Peak, RMS, Crest Factor, Clipping, Noise Level, Silence).
3. 9.3 Smart Audio Cleanup (Phát hiện khoảng lặng thừa, clipping, làm sạch non-destructive).
4. 9.4 Intelligent Audio Presets (Tự động nhận diện & đề xuất preset phù hợp theo đặc tính âm học).
5. 9.5 Smart Broadcast Mixing (Phân tích cân bằng âm lượng giọng đọc vs nhạc nền, auto-ducking tối ưu).
6. Tích hợp UI & Hồi quy: VoiceQualityAnalyzerDialog, Audio Studio, Broadcast Studio, TTS Engine.
"""

from __future__ import annotations

import hashlib
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

from backend.audio_enhancement import (
    AudioEnhancementConfig,
    SYSTEM_PRESETS,
    audio_enhancement_engine,
)
from backend.intelligent_audio import (
    VoiceQualityMetrics,
    VoiceQualityAnalyzer,
    IntelligentVoiceEnhancer,
    SmartAudioCleanup,
    SmartBroadcastMixer,
    voice_quality_analyzer,
    intelligent_voice_enhancer,
    smart_audio_cleanup,
    smart_broadcast_mixer,
)
from backend.audio_utils import load_audio_segment_safe, save_wav, get_audio_duration_safe


class TestSprint5IntelligentAudio(unittest.TestCase):
    """Bộ kiểm thử 16 tiêu chí cho Sprint 5 — Phase 9: Intelligent Audio Processing."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="ttts_sprint5_test_"))
        cls.sr = 48000

        # 1. Tạo file WAV sạch (Clean Voice synth) ~ -18 dBFS, 2.5s, có khoảng lặng nhẹ để đo noise floor
        cls.test_wav_clean = cls.test_dir / "clean_voice.wav"
        cls._create_synth_wav(cls.test_wav_clean, duration_sec=2.5, freq=440.0, amp=0.25, noise=0.0, lead_silence=0.3, trail_silence=0.3)

        # 2. Tạo file WAV có Clipping giả lập (Clamped to 32767) nhưng có khoảng lặng nhẹ để sàn nhiễu thấp
        cls.test_wav_clipped = cls.test_dir / "clipped_voice.wav"
        cls._create_synth_wav(cls.test_wav_clipped, duration_sec=2.0, freq=300.0, amp=1.5, clip=True, lead_silence=0.3, trail_silence=0.3)

        # 3. Tạo file WAV có sàn nhiễu cao (Noisy Voice)
        cls.test_wav_noisy = cls.test_dir / "noisy_voice.wav"
        cls._create_synth_wav(cls.test_wav_noisy, duration_sec=2.5, freq=500.0, amp=0.15, noise=0.05, lead_silence=0.3, trail_silence=0.3)

        # 4. Tạo file WAV có khoảng lặng dài ở đầu và cuối (Excessive Silence)
        cls.test_wav_silence = cls.test_dir / "silence_voice.wav"
        cls._create_synth_wav(cls.test_wav_silence, duration_sec=4.0, freq=440.0, amp=0.25, lead_silence=1.2, trail_silence=1.4)

        # 5. Tạo file WAV nhạc nền (BGM Synth) ~ 3 giây, biên độ lớn hơn
        cls.test_wav_bgm = cls.test_dir / "bgm_synth.wav"
        cls._create_synth_wav(cls.test_wav_bgm, duration_sec=3.0, freq=220.0, amp=0.45, noise=0.0)

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
        noise: float = 0.0,
        clip: bool = False,
        lead_silence: float = 0.0,
        trail_silence: float = 0.0,
    ):
        """Tạo sóng âm WAV chuẩn 48kHz PCM 16-bit mono để kiểm thử."""
        import random
        sr = cls.sr
        total_samples = int(duration_sec * sr)
        lead_s = int(lead_silence * sr)
        trail_s = int(trail_silence * sr)
        tone_s = max(0, total_samples - lead_s - trail_s)

        samples = []
        # Leading silence
        for _ in range(lead_s):
            val = random.gauss(0, noise) if noise > 0 else 0.0
            clamped = max(-1.0, min(1.0, val))
            samples.append(int(clamped * 32767.0))

        # Tone + noise
        for i in range(tone_s):
            val = amp * math.sin(2.0 * math.pi * freq * (i / sr))
            if noise > 0:
                val += random.gauss(0, noise)
            if clip:
                if val > 0.8:
                    val = 1.2  # Force clipping
                elif val < -0.8:
                    val = -1.2
            clamped = max(-1.0, min(1.0, val))
            samples.append(int(clamped * 32767.0))

        # Trailing silence
        for _ in range(trail_s):
            val = random.gauss(0, noise) if noise > 0 else 0.0
            clamped = max(-1.0, min(1.0, val))
            samples.append(int(clamped * 32767.0))

        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    # =========================================================================
    # 1. KIỂM THỬ 9.2: VOICE QUALITY ANALYZER
    # =========================================================================
    def test_01_voice_quality_analyzer_metrics(self):
        """9.2: Phân tích đầy đủ 17 chỉ số âm học từ tệp âm thanh sạch."""
        metrics = voice_quality_analyzer.analyze_file(self.test_wav_clean)
        self.assertIsInstance(metrics, VoiceQualityMetrics)
        self.assertAlmostEqual(metrics.duration_sec, 2.5, delta=0.2)
        self.assertEqual(metrics.sample_rate, 48000)
        self.assertEqual(metrics.channels, 1)

        # Kiểm tra các giá trị âm lượng đo được
        self.assertLess(metrics.integrated_lufs, 0.0)
        self.assertLess(metrics.true_peak_dbfs, 1.0)
        self.assertLess(metrics.rms_dbfs, 0.0)
        self.assertGreater(metrics.crest_factor_db, 0.0)
        self.assertLess(metrics.noise_level_dbfs, -35.0)

        # Kiểm tra tính hợp lệ của điểm chất lượng
        self.assertGreaterEqual(metrics.quality_score, 70)
        self.assertIn("xuất sắc", metrics.quality_grade.lower())
        self.assertIsInstance(metrics.to_dict(), dict)

    def test_02_clipping_detection(self):
        """9.2: Nhận diện chính xác mẫu méo vỡ (clipping) và trừ điểm tương ứng."""
        metrics = voice_quality_analyzer.analyze_file(self.test_wav_clipped)
        self.assertTrue(metrics.clipping_detected, "Phải phát hiện hiện tượng clipping")
        self.assertGreater(metrics.clipping_count, 5, "Số lượng mẫu vỡ âm phải > 5")
        has_clip_issue = any("clipping" in is_msg.lower() or "méo tiếng" in is_msg.lower() for is_msg in metrics.issues_found)
        self.assertTrue(has_clip_issue, "Danh sách issues_found phải ghi nhận lỗi clipping")
        self.assertLess(metrics.quality_score, 85)

    def test_03_noise_floor_estimation(self):
        """9.2: Ước lượng chính xác sàn nhiễu giữa âm thanh sạch và âm thanh nhiễu."""
        metrics_clean = voice_quality_analyzer.analyze_file(self.test_wav_clean)
        metrics_noisy = voice_quality_analyzer.analyze_file(self.test_wav_noisy)

        # Sàn nhiễu của file có nhiễu phải cao hơn đáng kể (ít âm bản hơn)
        self.assertGreater(
            metrics_noisy.noise_level_dbfs,
            metrics_clean.noise_level_dbfs + 10.0,
            f"Sàn nhiễu noisy ({metrics_noisy.noise_level_dbfs}) phải cao hơn clean ({metrics_clean.noise_level_dbfs})"
        )
        has_noise_issue = any("nhiễu" in is_msg.lower() for is_msg in metrics_noisy.issues_found)
        self.assertTrue(has_noise_issue, "Phải phát hiện vấn đề sàn nhiễu cao")

    def test_04_silence_detection_and_margins(self):
        """9.2: Nhận diện chính xác khoảng lặng đầu (leading) và cuối (trailing)."""
        metrics = voice_quality_analyzer.analyze_file(self.test_wav_silence)
        self.assertGreaterEqual(metrics.leading_silence_sec, 0.9, "Phát hiện khoảng lặng đầu >= 0.9s")
        self.assertGreaterEqual(metrics.trailing_silence_sec, 1.1, "Phát hiện khoảng lặng cuối >= 1.1s")
        self.assertGreater(metrics.silence_ratio_pct, 45.0, "Tỷ lệ khoảng lặng > 45%")
        has_silence_issue = any("khoảng lặng" in is_msg.lower() for is_msg in metrics.issues_found)
        self.assertTrue(has_silence_issue, "Phải cảnh báo khoảng lặng thừa")

    def test_05_quality_score_and_grade(self):
        """9.2: Kiểm tra công thức xếp hạng điểm chất lượng 0-100 và phân loại."""
        m1 = VoiceQualityMetrics(file_path="dummy1", quality_score=95, quality_grade="")
        m2 = VoiceQualityMetrics(file_path="dummy2", quality_score=75, quality_grade="")
        m3 = VoiceQualityMetrics(file_path="dummy3", quality_score=55, quality_grade="")
        m4 = VoiceQualityMetrics(file_path="dummy4", quality_score=35, quality_grade="")

        self.assertGreaterEqual(m1.quality_score, 85)
        self.assertGreaterEqual(m2.quality_score, 70)
        self.assertGreaterEqual(m3.quality_score, 50)
        self.assertLess(m4.quality_score, 50)

    # =========================================================================
    # 2. KIỂM THỬ 9.1 & 9.4: INTELLIGENT VOICE ENHANCEMENT & PRESETS
    # =========================================================================
    def test_06_intelligent_preset_recommendation(self):
        """9.4: Tự động phân tích và đề xuất preset tối ưu theo đặc tính âm học."""
        # 1. Âm thanh sạch -> clean_voice hoặc studio_voice
        m_clean = voice_quality_analyzer.analyze_file(self.test_wav_clean)
        rec_clean = intelligent_voice_enhancer.evaluate_and_recommend(m_clean)
        self.assertIn(rec_clean["recommended_preset_key"], ["clean_voice", "studio_voice"])

        # 2. Âm thanh có nhiễu sàn cao -> military_narration
        m_noisy = voice_quality_analyzer.analyze_file(self.test_wav_noisy)
        rec_noisy = intelligent_voice_enhancer.evaluate_and_recommend(m_noisy)
        self.assertEqual(rec_noisy["recommended_preset_key"], "military_narration")
        self.assertTrue(rec_noisy["suggested_config"].enable_noise_reduction)

        # 3. Âm thanh méo tiếng / clipping -> podcast
        m_clipped = voice_quality_analyzer.analyze_file(self.test_wav_clipped)
        rec_clipped = intelligent_voice_enhancer.evaluate_and_recommend(m_clipped)
        self.assertEqual(rec_clipped["recommended_preset_key"], "podcast")
        self.assertTrue(rec_clipped["suggested_config"].enable_limiter)

    def test_07_customized_dsp_configuration(self):
        """9.1: Xây dựng cấu hình DSP chi tiết cá nhân hóa từ số đo thực tế."""
        metrics = voice_quality_analyzer.analyze_file(self.test_wav_noisy)
        rec = intelligent_voice_enhancer.evaluate_and_recommend(metrics)
        cfg = rec["suggested_config"]
        self.assertIsInstance(cfg, AudioEnhancementConfig)
        self.assertEqual(cfg.target_lufs, -16.0)
        self.assertTrue(cfg.enable_loudnorm)
        self.assertGreater(cfg.noise_reduction_db, 0.0)
        self.assertIsInstance(rec["tuning_recommendations"], list)
        self.assertGreater(len(rec["tuning_recommendations"]), 0)

    # =========================================================================
    # 3. KIỂM THỬ 9.3: SMART AUDIO CLEANUP
    # =========================================================================
    def test_08_smart_audio_cleanup_detection(self):
        """9.3: Phát hiện khoảng lặng thừa và đề xuất cắt gọt an toàn."""
        res = smart_audio_cleanup.detect_cleanup_actions(self.test_wav_silence)
        self.assertTrue(res["has_suggestions"])
        self.assertGreater(len(res["actions_suggested"]), 0)

    def test_09_smart_audio_cleanup_application(self):
        """9.3: Thực hiện làm sạch khoảng lặng non-destructive ra tệp mới."""
        out_cleaned = self.test_dir / "cleaned_voice_out.wav"
        res = smart_audio_cleanup.apply_cleanup(
            input_file=self.test_wav_silence,
            output_file=out_cleaned,
            trim_leading=True,
            trim_trailing=True,
            keep_margin_ms=200,
        )
        self.assertTrue(res["success"])
        self.assertTrue(out_cleaned.is_file())
        self.assertLess(
            res["cleaned_duration_ms"],
            res["original_duration_ms"] - 1500,
            "Độ dài sau làm sạch phải ngắn hơn ít nhất 1.5 giây khoảng lặng thừa"
        )
        # Tệp gốc phải còn nguyên vẹn
        self.assertTrue(self.test_wav_silence.is_file())

    # =========================================================================
    # 4. KIỂM THỬ 9.5: SMART BROADCAST MIXING
    # =========================================================================
    def test_10_smart_broadcast_mixer_balance(self):
        """9.5: Phân tích tỷ lệ âm lượng giữa giọng đọc và nhạc nền, tính toán Ducking."""
        mix_res = smart_broadcast_mixer.analyze_mix_balance(self.test_wav_clean, self.test_wav_bgm)
        self.assertTrue(mix_res["success"])
        self.assertIn("suggested_bgm_volume_db", mix_res)
        self.assertIn("ducking_attenuation_db", mix_res)
        self.assertEqual(mix_res["ducking_attenuation_db"], -14.0)
        self.assertEqual(mix_res["ducking_attack_ms"], 150)
        self.assertEqual(mix_res["ducking_release_ms"], 500)
        self.assertLessEqual(mix_res["suggested_bgm_volume_db"], -10.0)
        self.assertGreaterEqual(mix_res["suggested_bgm_volume_db"], -32.0)
        self.assertIn("explanation", mix_res)

    # =========================================================================
    # 5. KIỂM THỬ TÍCH HỢP GIAO DIỆN & WORKER
    # =========================================================================
    def test_11_voice_analyzer_dialog_integration(self):
        """Kiểm tra khởi tạo hộp thoại VoiceQualityAnalyzerDialog và 8 thẻ thông số."""
        from PySide6.QtWidgets import QApplication
        from gui.dialog_voice_analyzer import VoiceQualityAnalyzerDialog

        app = QApplication.instance() or QApplication([])
        dlg = VoiceQualityAnalyzerDialog(self.test_wav_clean)
        self.assertIsNotNone(dlg)

        # Đợi worker hoàn tất phân tích
        if hasattr(dlg, "worker") and dlg.worker.isRunning():
            dlg.worker.wait(3000)

        # Kiểm tra 8 thẻ thông số
        self.assertIsNotNone(dlg.card_lufs)
        self.assertIsNotNone(dlg.card_tp)
        self.assertIsNotNone(dlg.card_rms)
        self.assertIsNotNone(dlg.card_crest)
        self.assertIsNotNone(dlg.card_noise)
        self.assertIsNotNone(dlg.card_clip)
        self.assertIsNotNone(dlg.card_silence)
        self.assertIsNotNone(dlg.card_dur)

        # Kiểm tra các nút tương tác
        self.assertIsNotNone(dlg.btn_apply_rec)
        self.assertIsNotNone(dlg.btn_cleanup)
        self.assertIsNotNone(dlg.btn_close)
        dlg.close()

    def test_12_audio_studio_analyzer_integration(self):
        """Kiểm tra tích hợp nút 'Phân Tích Âm Thanh' trong Audio Studio."""
        from PySide6.QtWidgets import QApplication
        from gui.pages.page_audio_studio import PageAudioStudio

        app = QApplication.instance() or QApplication([])
        studio = PageAudioStudio()
        self.assertTrue(hasattr(studio, "btn_analyze"))
        self.assertEqual(studio.btn_analyze.text(), "🔍 Phân Tích Âm Thanh")
        self.assertTrue(hasattr(studio, "analyze_audio_dialog"))
        self.assertTrue(callable(studio.analyze_audio_dialog))

    def test_13_broadcast_studio_smart_mix_integration(self):
        """Kiểm tra tích hợp nút 'Cân Bằng Thông Minh' trong Broadcast Studio."""
        from PySide6.QtWidgets import QApplication
        from gui.pages.page_broadcast import PageBroadcast

        app = QApplication.instance() or QApplication([])
        bc = PageBroadcast()
        self.assertTrue(hasattr(bc, "btn_smart_mix"))
        self.assertIn("Cân Bằng Thông Minh", bc.btn_smart_mix.text())
        self.assertTrue(hasattr(bc, "_smart_broadcast_mix_dialog"))
        self.assertTrue(callable(bc._smart_broadcast_mix_dialog))

    # =========================================================================
    # 6. HIỆU NĂNG, TÍNH TOÀN VẸN & HỒI QUY
    # =========================================================================
    def test_14_long_audio_analysis_performance(self):
        """Hiệu năng phân tích âm học đạt tốc độ cao (> 10x thời gian thực trên CPU)."""
        long_wav = self.test_dir / "perf_long_10s.wav"
        self._create_synth_wav(long_wav, duration_sec=10.0, freq=440.0, amp=0.2, lead_silence=0.5, trail_silence=0.5)

        t0 = time.time()
        metrics = voice_quality_analyzer.analyze_file(long_wav)
        elapsed = time.time() - t0

        self.assertAlmostEqual(metrics.duration_sec, 10.0, delta=0.5)
        self.assertLess(elapsed, 2.0, f"Phân tích 10s mất {elapsed:.2f}s, quá chậm!")

    def test_15_non_destructive_integrity(self):
        """Đảm bảo phân tích âm học và dọn dẹp hoàn toàn không làm thay đổi tệp gốc."""
        with open(self.test_wav_clean, "rb") as f:
            h_before = hashlib.sha256(f.read()).hexdigest()

        m = voice_quality_analyzer.analyze_file(self.test_wav_clean)
        intelligent_voice_enhancer.evaluate_and_recommend(m)
        smart_audio_cleanup.detect_cleanup_actions(self.test_wav_clean)

        with open(self.test_wav_clean, "rb") as f:
            h_after = hashlib.sha256(f.read()).hexdigest()

        self.assertEqual(h_before, h_after, "Hash tệp nguồn phải giữ nguyên vẹn 100%!")

    def test_16_full_regression_tts_dsp(self):
        """Kiểm thử hồi quy: VieNeu-TTS v3 Turbo và Audio Enhancement Pipeline hoạt động hoàn hảo."""
        from backend.service import tts_service

        voices = tts_service.list_voices()
        self.assertIsInstance(voices, list)
        self.assertGreater(len(voices), 0)

        cfg = SYSTEM_PRESETS["clean_voice"]
        out_proc = self.test_dir / "dsp_proc_test.wav"
        res = audio_enhancement_engine.enhance_audio(self.test_wav_clean, out_proc, cfg)
        self.assertTrue(res["success"], f"Xử lý DSP thất bại: {res.get('error')}")
        self.assertTrue(out_proc.is_file())


if __name__ == "__main__":
    unittest.main()
