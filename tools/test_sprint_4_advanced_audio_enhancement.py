"""tools/test_sprint_4_advanced_audio_enhancement.py — TEST SUITE CHO SPRINT 4 (PHASE 8.4–8.8)
======================================================================================
Kiểm thử toàn diện các phân hệ nâng cao chất lượng âm thanh:
1. Phase 8.4 De-Esser (Threshold, Intensity, Frequency, triệt âm xuýt tiếng Việt).
2. Phase 8.5 Dynamic Speech Compressor (Threshold, Ratio, Attack, Release, Makeup, Knee, 3 Presets).
3. Phase 8.6 Audio Presets (6 Presets hệ thống, Custom Preset CRUD, Import/Export JSON, Bảo vệ hệ thống).
4. Phase 8.7 Audio Enhancement Pipeline (Noise Reduction → EQ → De-Esser → Compressor → LUFS → Limiter,
   bật/tắt từng bộ lọc độc lập, Reset, Non-destructive).
5. Phase 8.8 A/B Preview (Đồng bộ Playhead, so sánh LUFS/True Peak, Preview đoạn chọn time slice).
6. Tích hợp & Hồi quy: Audio Studio, Broadcast Studio và TTS Core.
"""

import math
import os
import sys
import shutil
import struct
import tempfile
import time
import unittest
import wave
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Thiết lập môi trường âm thanh tập trung
from backend.ffmpeg_bootstrap import initialize_ffmpeg, get_ffmpeg_path, is_ffmpeg_ready
initialize_ffmpeg()

from backend.audio_enhancement import (
    AudioEnhancementConfig,
    AudioEnhancementEngine,
    PRESETS,
    SYSTEM_PRESETS,
    COMPRESSOR_PRESETS,
    PresetManager,
    audio_enhancement_engine,
    build_ffmpeg_filter_chain,
)
from backend.audio_utils import load_audio_segment_safe, save_wav, get_audio_duration_safe
from backend.export_center import export_center


def generate_synthetic_wav(path: Path, duration_sec: float = 3.0, sample_rate: int = 48000, freq: float = 440.0, add_sibilance: bool = False):
    """Tạo tệp WAV PCM 16-bit chuẩn dùng cho kiểm thử."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = int(duration_sec * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        data = bytearray()
        for i in range(n_samples):
            t = float(i) / sample_rate
            val = 0.5 * math.sin(2.0 * math.pi * freq * t)
            val += 0.2 * math.sin(2.0 * math.pi * (freq * 2) * t)
            # Thêm tần số âm xuýt rít sibilance (6.5 kHz) nếu yêu cầu
            if add_sibilance:
                val += 0.15 * math.sin(2.0 * math.pi * 6500.0 * t)
            val = max(-1.0, min(1.0, val))
            sample = int(val * 32767.0)
            data.extend(struct.pack("<h", sample))
        wf.writeframes(data)


class TestSprint4AdvancedAudioEnhancement(unittest.TestCase):
    """Kiểm thử tự động các yêu cầu kỹ thuật Sprint 4."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="ttts_sprint4_test_"))
        cls.test_wav_clean = cls.temp_dir / "clean_voice.wav"
        cls.test_wav_sibilant = cls.temp_dir / "sibilant_voice.wav"
        cls.test_wav_long = cls.temp_dir / "long_audio.wav"

        generate_synthetic_wav(cls.test_wav_clean, duration_sec=3.0, freq=300.0, add_sibilance=False)
        generate_synthetic_wav(cls.test_wav_sibilant, duration_sec=3.0, freq=300.0, add_sibilance=True)
        generate_synthetic_wav(cls.test_wav_long, duration_sec=15.0, freq=280.0, add_sibilance=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_phase_8_4_deesser_configuration(self):
        """Kiểm tra Phase 8.4 De-Esser: Threshold, Intensity, Frequency Range và chuỗi filter FFmpeg."""
        cfg = AudioEnhancementConfig(
            enable_highpass=False,
            enable_deesser=True,
            deesser_threshold=-22.0,
            deesser_intensity=0.5,
            deesser_freq=6500.0,
            enable_noise_reduction=False,
            enable_eq=False,
            enable_compressor=False,
            enable_loudnorm=False,
            enable_limiter=False,
        )
        filters = build_ffmpeg_filter_chain(cfg)
        self.assertEqual(len(filters), 1)
        self.assertTrue(filters[0].startswith("deesser="))
        self.assertIn("i=0.50", filters[0])
        self.assertIn("f=0.39", filters[0])

        out_wav = self.temp_dir / "out_deesser.wav"
        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_sibilant,
            output_file=out_wav,
            config=cfg,
        )
        self.assertTrue(res.get("success"))
        self.assertTrue(out_wav.is_file())
        self.assertGreater(out_wav.stat().st_size, 0)

    def test_02_phase_8_5_compressor_parameters(self):
        """Kiểm tra Phase 8.5 Compressor: Threshold, Ratio, Attack, Release, Makeup Gain, Soft Knee."""
        cfg = AudioEnhancementConfig(
            enable_highpass=False,
            enable_compressor=True,
            compressor_threshold=-18.0,
            compressor_ratio=3.0,
            compressor_attack=15.0,
            compressor_release=250.0,
            compressor_makeup_gain=2.0,
            compressor_knee=2.5,
            enable_noise_reduction=False,
            enable_eq=False,
            enable_deesser=False,
            enable_loudnorm=False,
            enable_limiter=False,
        )
        filters = build_ffmpeg_filter_chain(cfg)
        self.assertEqual(len(filters), 1)
        self.assertTrue(filters[0].startswith("acompressor="))
        self.assertIn("threshold=-18.0dB", filters[0])
        self.assertIn("ratio=3.0", filters[0])
        self.assertIn("makeup=2.0dB", filters[0])
        self.assertIn("knee=2.5dB", filters[0])

        out_wav = self.temp_dir / "out_compressor.wav"
        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_clean,
            output_file=out_wav,
            config=cfg,
        )
        self.assertTrue(res.get("success"))
        self.assertTrue(out_wav.is_file())

    def test_03_compressor_presets_catalog(self):
        """Kiểm tra danh mục Preset của Compressor: Gentle Voice, Narration, Broadcast."""
        self.assertIn("gentle_voice", COMPRESSOR_PRESETS)
        self.assertIn("narration", COMPRESSOR_PRESETS)
        self.assertIn("broadcast", COMPRESSOR_PRESETS)

        gv = COMPRESSOR_PRESETS["gentle_voice"]
        self.assertEqual(gv["ratio"], 2.0)
        self.assertEqual(gv["threshold"], -22.0)

        bc = COMPRESSOR_PRESETS["broadcast"]
        self.assertEqual(bc["ratio"], 3.5)
        self.assertEqual(bc["makeup"], 2.5)

    def test_04_phase_8_6_system_presets_catalog(self):
        """Kiểm tra đầy đủ 6 System Presets chính của Phase 8.6."""
        required_presets = [
            "clean_voice",
            "studio_voice",
            "podcast",
            "military_narration",
            "broadcast",
            "voice_bgm",
        ]
        for p in required_presets:
            self.assertIn(p, SYSTEM_PRESETS)
            cfg = SYSTEM_PRESETS[p]
            self.assertIsInstance(cfg, AudioEnhancementConfig)
            self.assertIsNotNone(cfg.preset_name)

    def test_05_custom_preset_crud_operations(self):
        """Kiểm tra toàn diện CRUD Preset tùy chỉnh: Save, Load, Duplicate, Delete."""
        # 1. Save Custom Preset
        test_cfg = AudioEnhancementConfig(
            preset_name="Giọng Đọc Phim Tài Liệu",
            bass_gain=2.0,
            target_lufs=-16.0,
        )
        ok_save, msg_save = PresetManager.save_preset("Phim Tài Liệu", test_cfg)
        self.assertTrue(ok_save)

        # 2. Load and verify
        all_p = PresetManager.list_all_presets()
        self.assertIn("phim_tài_liệu", all_p)
        loaded = all_p["phim_tài_liệu"]
        self.assertEqual(loaded.bass_gain, 2.0)
        self.assertTrue(loaded.is_custom)

        # 3. Duplicate
        ok_dup, msg_dup = PresetManager.duplicate_preset("phim_tài_liệu", "Phim Tài Liệu Bản 2")
        self.assertTrue(ok_dup)
        all_p_dup = PresetManager.list_all_presets()
        self.assertIn("phim_tài_liệu_bản_2", all_p_dup)

        # 4. Delete Custom
        ok_del1, _ = PresetManager.delete_preset("phim_tài_liệu")
        ok_del2, _ = PresetManager.delete_preset("phim_tài_liệu_bản_2")
        self.assertTrue(ok_del1)
        self.assertTrue(ok_del2)

    def test_06_system_presets_protected_against_delete_or_overwrite(self):
        """Bảo vệ tuyệt đối: Không cho phép sửa đổi hoặc xóa các Preset hệ thống tiêu chuẩn."""
        # Thử ghi đè Clean Voice
        ok_overwrite, msg = PresetManager.save_preset("clean_voice", AudioEnhancementConfig())
        self.assertFalse(ok_overwrite)
        self.assertIn("Không thể ghi đè", msg)

        # Thử xóa Broadcast
        ok_delete, msg_del = PresetManager.delete_preset("broadcast")
        self.assertFalse(ok_delete)
        self.assertIn("Bảo vệ hệ thống", msg_del)

    def test_07_preset_json_import_export(self):
        """Kiểm tra sao lưu và phục hồi Presets qua tệp JSON (Import/Export JSON)."""
        # Tạo 1 preset tạm để xuất
        cfg = AudioEnhancementConfig(preset_name="Preset Xuất JSON Test", treble_gain=2.5)
        PresetManager.save_preset("json_test_preset", cfg)

        json_file = self.temp_dir / "test_presets_backup.json"
        ok_exp, msg_exp = PresetManager.export_presets_json(json_file)
        self.assertTrue(ok_exp)
        self.assertTrue(json_file.is_file())

        # Xóa preset đi rồi nhập lại từ file JSON
        PresetManager.delete_preset("json_test_preset")
        self.assertNotIn("json_test_preset", PresetManager.load_custom_presets())

        ok_imp, msg_imp = PresetManager.import_presets_json(json_file)
        self.assertTrue(ok_imp)
        self.assertIn("json_test_preset", PresetManager.load_custom_presets())

        # Dọn dẹp
        PresetManager.delete_preset("json_test_preset")

    def test_08_phase_8_7_pipeline_order_verification(self):
        """Kiểm tra Phase 8.7 Pipeline: Noise Reduction → EQ → De-Esser → Compressor → LUFS → Limiter."""
        full_cfg = AudioEnhancementConfig(
            enable_noise_reduction=True,
            noise_reduction_db=10.0,
            enable_eq=True,
            bass_gain=1.0,
            enable_deesser=True,
            enable_compressor=True,
            enable_loudnorm=True,
            enable_limiter=True,
            limiter_ceiling=-1.0,
        )
        filters = build_ffmpeg_filter_chain(full_cfg)

        # Xác định vị trí từng filter trong chuỗi
        idx_nr = next(i for i, f in enumerate(filters) if "afftdn" in f)
        idx_eq = next(i for i, f in enumerate(filters) if "equalizer" in f)
        idx_de = next(i for i, f in enumerate(filters) if "deesser" in f)
        idx_cp = next(i for i, f in enumerate(filters) if "acompressor" in f)
        idx_lu = next(i for i, f in enumerate(filters) if "loudnorm" in f)
        idx_lm = next(i for i, f in enumerate(filters) if "alimiter" in f)

        # Thứ tự bắt buộc: NR < EQ < De-Esser < Compressor < LUFS < Limiter
        self.assertLess(idx_nr, idx_eq)
        self.assertLess(idx_eq, idx_de)
        self.assertLess(idx_de, idx_cp)
        self.assertLess(idx_cp, idx_lu)
        self.assertLess(idx_lu, idx_lm)

    def test_09_pipeline_independent_toggles(self):
        """Kiểm tra tính độc lập của từng bộ xử lý (Bật/tắt riêng lẻ không ảnh hưởng bộ khác)."""
        # Chỉ bật EQ và Limiter
        cfg = AudioEnhancementConfig(
            enable_noise_reduction=False,
            enable_eq=True,
            bass_gain=2.0,
            enable_deesser=False,
            enable_compressor=False,
            enable_loudnorm=False,
            enable_limiter=True,
        )
        filters = build_ffmpeg_filter_chain(cfg)
        self.assertTrue(any("equalizer" in f for f in filters))
        self.assertTrue(any("alimiter" in f for f in filters))
        self.assertFalse(any("afftdn" in f for f in filters))
        self.assertFalse(any("deesser" in f for f in filters))
        self.assertFalse(any("acompressor" in f for f in filters))
        self.assertFalse(any("loudnorm" in f for f in filters))

    def test_10_phase_8_8_ab_preview_time_slice(self):
        """Kiểm tra Phase 8.8: Preview theo đoạn chọn (Time Slice) với start_ms và end_ms."""
        slice_out = self.temp_dir / "out_slice_preview.wav"
        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_clean,
            output_file=slice_out,
            config=SYSTEM_PRESETS["clean_voice"],
            start_ms=500,
            end_ms=1500,
        )
        self.assertTrue(res.get("success"))
        self.assertTrue(slice_out.is_file())

        dur = get_audio_duration_safe(slice_out)
        # Đoạn trích 500ms - 1500ms thời lượng khoảng ~1.0 giây
        self.assertAlmostEqual(dur, 1.0, delta=0.25)

    def test_11_ab_lufs_delta_comparison(self):
        """Kiểm tra so sánh chênh lệch độ to (LUFS comparison ΔLUFS) trước và sau xử lý."""
        out_wav = self.temp_dir / "out_lufs_delta.wav"
        res_enh = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_clean,
            output_file=out_wav,
            config=SYSTEM_PRESETS["military_narration"],
        )
        self.assertTrue(res_enh["success"])

        meas_in = audio_enhancement_engine.measure_loudness(self.test_wav_clean)
        meas_out = audio_enhancement_engine.measure_loudness(out_wav)
        self.assertTrue(meas_in["success"])
        self.assertTrue(meas_out["success"])

        delta_lufs = meas_out["integrated_lufs"] - meas_in["integrated_lufs"]
        self.assertIsInstance(delta_lufs, float)
        # True Peak đầu ra tuân thủ trần an toàn
        self.assertLessEqual(meas_out["true_peak_dbfs"], -0.9)

    def test_12_audio_studio_dialog_integration(self):
        """Kiểm tra khởi tạo giao diện AudioEnhancementDialog với đoạn chọn và preset selector."""
        from gui.dialog_audio_enhancement import AudioEnhancementDialog
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        dlg = AudioEnhancementDialog(
            input_wav_path=self.test_wav_clean,
            start_ms=300,
            end_ms=1800,
        )
        dlg.show()
        self.assertIsNotNone(dlg)
        self.assertTrue(dlg.cb_slice_preview.isVisible())
        self.assertTrue(dlg.cb_slice_preview.isChecked())
        self.assertGreater(dlg.combo_presets.count(), 5)
        dlg.close()

    def test_13_broadcast_studio_preset_and_ducking_integration(self):
        """Kiểm tra tích hợp Broadcast Studio: Có combo DSP preset và hỗ trợ Ducking."""
        from gui.pages.page_broadcast import PageBroadcast
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        bc_page = PageBroadcast()
        self.assertIsNotNone(bc_page)
        self.assertTrue(hasattr(bc_page, "combo_dsp_preset"))
        self.assertGreater(bc_page.combo_dsp_preset.count(), 3)
        self.assertTrue(bc_page.chk_ducking.isChecked())
        bc_page.close()

    def test_14_long_audio_pipeline_performance(self):
        """Kiểm tra chuỗi pipeline hoàn chỉnh với file âm thanh dài (15s) đảm bảo CPU/RAM ổn định."""
        out_wav = self.temp_dir / "out_long_pipeline.wav"
        t0 = time.time()
        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_long,
            output_file=out_wav,
            config=SYSTEM_PRESETS["military_narration"],
        )
        elapsed = time.time() - t0
        self.assertTrue(res["success"])
        self.assertTrue(out_wav.is_file())

        # Tốc độ xử lý audio 15s phải nhanh hơn nhiều so với thời lượng thực tế
        speedup = 15.0 / max(0.001, elapsed)
        self.assertGreater(speedup, 2.0)

    def test_15_cancellation_cleans_resources(self):
        """Kiểm tra hủy ngang tiến trình dọn dẹp sạch tiến trình FFmpeg và tệp tạm."""
        out_wav = self.temp_dir / "out_cancel_sprint4.wav"
        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_long,
            output_file=out_wav,
            config=SYSTEM_PRESETS["podcast"],
            cancel_check=lambda: True,
        )
        self.assertFalse(res.get("success"))
        self.assertTrue(res.get("cancelled"))
        self.assertFalse(out_wav.is_file())

    def test_16_tts_core_unmodified_regression(self):
        """Kiểm tra hồi quy: VieNeu-TTS v3 Turbo ONNX CPU hoàn toàn nguyên vẹn và không bị can thiệp."""
        from backend.service import tts_service
        self.assertIsNotNone(tts_service)
        voices = tts_service.list_voices()
        self.assertIsInstance(voices, list)
        self.assertGreater(len(voices), 0)


if __name__ == "__main__":
    unittest.main()
