"""tools/test_sprint_3_audio_enhancement.py — TEST SUITE CHO SPRINT 3 (PHASE 8.1–8.3)
======================================================================================
Kiểm thử toàn diện 3 module cốt lõi nâng cao chất lượng âm thanh:
1. Giảm nhiễu thích ứng (Noise Reduction afftdn).
2. Voice Enhancement EQ (High-pass, Bass, Warmth, Boxiness, Presence, Treble, Air).
3. Chuẩn hóa âm lượng EBU R128 LUFS (-16 LUFS Voice, -23 LUFS Broadcast, True Peak).
4. Bypass, Đo đạc LUFS thời gian thực, Hủy bỏ (Cancellation) an toàn.
5. Non-destructive audio & Export normalization trong Audio Studio.
6. Hồi quy Audio Studio, Broadcast Studio và TTS Core.
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
    audio_enhancement_engine,
    build_ffmpeg_filter_chain,
)
from backend.audio_utils import load_audio_segment_safe, save_wav, get_audio_duration_safe
from backend.export_center import export_center
from gui.pages.page_audio_studio import PageAudioStudio, AudioStudioExportDialog
from pydub import AudioSegment


def generate_synthetic_wav(path: Path, duration_sec: float = 3.0, sample_rate: int = 48000, freq: float = 440.0, add_noise: bool = False):
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
            # Sóng âm cơ bản
            val = 0.5 * math.sin(2.0 * math.pi * freq * t)
            # Thêm hài âm giọng nói
            val += 0.2 * math.sin(2.0 * math.pi * (freq * 2) * t)
            # Thêm nhiễu nền nếu yêu cầu
            if add_noise:
                val += 0.05 * math.sin(2.0 * math.pi * 3141.59 * t)
            # Giới hạn biên độ
            val = max(-1.0, min(1.0, val))
            sample = int(val * 32767.0)
            data.extend(struct.pack("<h", sample))
        wf.writeframes(data)


class TestSprint3AudioEnhancement(unittest.TestCase):
    """Kiểm thử tự động các yêu cầu kỹ thuật Sprint 3."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="ttts_sprint3_test_"))
        cls.test_wav_clean = cls.temp_dir / "clean_voice.wav"
        cls.test_wav_noisy = cls.temp_dir / "noisy_voice.wav"
        cls.test_wav_long = cls.temp_dir / "long_audio.wav"

        # Tạo các tệp âm thanh giả lập
        generate_synthetic_wav(cls.test_wav_clean, duration_sec=3.0, freq=300.0, add_noise=False)
        generate_synthetic_wav(cls.test_wav_noisy, duration_sec=3.0, freq=300.0, add_noise=True)
        generate_synthetic_wav(cls.test_wav_long, duration_sec=15.0, freq=250.0, add_noise=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_ffmpeg_bootstrap_readiness(self):
        """Kiểm tra FFmpeg 7.1 đã được nạp sẵn sàng từ ffmpeg_bootstrap."""
        self.assertTrue(is_ffmpeg_ready())
        ffmpeg_path = get_ffmpeg_path()
        self.assertIsNotNone(ffmpeg_path)
        self.assertTrue(Path(ffmpeg_path).is_file())

    def test_02_lufs_loudness_measurement(self):
        """Kiểm tra đo lường độ to LUFS, True Peak và LRA chuẩn EBU R128 thời gian thực."""
        res = audio_enhancement_engine.measure_loudness(self.test_wav_clean)
        self.assertTrue(res.get("success"))
        self.assertIsNotNone(res.get("integrated_lufs"))
        self.assertIsNotNone(res.get("true_peak_dbfs"))
        self.assertIsNotNone(res.get("loudness_range_lu"))

        # Độ to âm thanh nhân tạo phải nằm trong ngưỡng vật lý bình thường (-50 đến 0 LUFS)
        self.assertGreater(res["integrated_lufs"], -50.0)
        self.assertLess(res["integrated_lufs"], 0.0)
        self.assertLessEqual(res["true_peak_dbfs"], 0.0)

    def test_03_noise_reduction_dsp(self):
        """Kiểm tra module Giảm nhiễu thích ứng FFmpeg afftdn và lọc tần số thấp/cao."""
        out_wav = self.temp_dir / "out_noise_reduction.wav"
        cfg = AudioEnhancementConfig(
            enable_noise_reduction=True,
            noise_reduction_db=15.0,
            noise_floor_db=-45.0,
            highpass_freq=85.0,
            lowpass_freq=11000.0,
            enable_eq=False,
            enable_loudnorm=False,
            enable_compressor=False,
            enable_deesser=False,
        )

        filters = build_ffmpeg_filter_chain(cfg)
        self.assertTrue(any("afftdn" in f for f in filters))
        self.assertTrue(any("highpass=f=85" in f for f in filters))
        self.assertTrue(any("lowpass=f=11000" in f for f in filters))

        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_noisy,
            output_file=out_wav,
            config=cfg,
        )
        self.assertTrue(res.get("success"))
        self.assertTrue(out_wav.is_file())
        self.assertGreater(out_wav.stat().st_size, 0)

    def test_04_noise_reduction_clean_tts_default_disabled(self):
        """Kiểm tra nguyên tắc an toàn: Không bật giảm nhiễu mặc định cho giọng TTS sạch."""
        cfg_default = AudioEnhancementConfig()
        self.assertFalse(cfg_default.enable_noise_reduction)

        # Preset thuyết minh cho TTS sạch cũng không bật afftdn
        cfg_voiceover = PRESETS["voiceover_narrative"]
        self.assertFalse(cfg_voiceover.enable_noise_reduction)

    def test_05_voice_enhancement_eq(self):
        """Kiểm tra Voice Clarity EQ 6 dải: Bass, Warmth, Boxiness, Presence, Treble, Air."""
        out_wav = self.temp_dir / "out_voice_eq.wav"
        cfg = AudioEnhancementConfig(
            enable_noise_reduction=False,
            enable_highpass=True,
            highpass_freq=80.0,
            enable_eq=True,
            bass_gain=2.0,
            eq_warmth_gain=1.5,
            eq_boxiness_gain=-2.0,
            eq_presence_gain=3.0,
            treble_gain=1.5,
            eq_air_gain=1.0,
            enable_loudnorm=False,
        )

        filters = build_ffmpeg_filter_chain(cfg)
        self.assertTrue(any("equalizer=f=100" in f for f in filters))   # Bass
        self.assertTrue(any("equalizer=f=250" in f for f in filters))   # Warmth
        self.assertTrue(any("equalizer=f=600" in f for f in filters))   # Boxiness
        self.assertTrue(any("equalizer=f=3500" in f for f in filters))  # Presence
        self.assertTrue(any("equalizer=f=8000" in f for f in filters))  # Treble
        self.assertTrue(any("equalizer=f=10000" in f for f in filters)) # Air

        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_clean,
            output_file=out_wav,
            config=cfg,
        )
        self.assertTrue(res.get("success"))
        self.assertTrue(out_wav.is_file())

    def test_06_voiceover_narrative_preset(self):
        """Kiểm tra preset Thuyết minh chuyên nghiệp (Voiceover / Giảng bài)."""
        cfg = PRESETS["voiceover_narrative"]
        self.assertEqual(cfg.target_lufs, -16.0)
        self.assertTrue(cfg.enable_eq)
        self.assertFalse(cfg.enable_noise_reduction)

        out_wav = self.temp_dir / "out_preset_narrative.wav"
        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_clean,
            output_file=out_wav,
            config=cfg,
        )
        self.assertTrue(res.get("success"))
        self.assertTrue(out_wav.is_file())

    def test_07_broadcast_standard_ebu_preset(self):
        """Kiểm tra preset Chuẩn truyền thanh EBU R128 (-23 LUFS)."""
        cfg = PRESETS["broadcast_standard_ebu"]
        self.assertEqual(cfg.target_lufs, -23.0)
        self.assertEqual(cfg.true_peak, -1.0)

        out_wav = self.temp_dir / "out_preset_ebu.wav"
        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_clean,
            output_file=out_wav,
            config=cfg,
        )
        self.assertTrue(res.get("success"))
        self.assertTrue(out_wav.is_file())

        # Đo lại đầu ra phải xấp xỉ -23 LUFS
        meas = audio_enhancement_engine.measure_loudness(out_wav)
        self.assertTrue(meas["success"])
        self.assertAlmostEqual(meas["integrated_lufs"], -23.0, delta=2.0)

    def test_08_lufs_normalization_accuracy(self):
        """Kiểm tra độ chính xác của chuẩn hóa EBU R128 (-16 LUFS và -23 LUFS)."""
        out_voice = self.temp_dir / "out_lufs_16.wav"
        cfg_16 = AudioEnhancementConfig(
            enable_loudnorm=True,
            target_lufs=-16.0,
            true_peak=-1.5,
            enable_noise_reduction=False,
            enable_eq=False,
        )
        res_16 = audio_enhancement_engine.enhance_audio(self.test_wav_clean, out_voice, config=cfg_16)
        self.assertTrue(res_16["success"])

        meas_16 = audio_enhancement_engine.measure_loudness(out_voice)
        self.assertAlmostEqual(meas_16["integrated_lufs"], -16.0, delta=1.5)

    def test_09_true_peak_clipping_protection(self):
        """Kiểm tra trần True Peak chống méo loa / clipping (True Peak Ceiling)."""
        out_wav = self.temp_dir / "out_true_peak_ceiling.wav"
        cfg = AudioEnhancementConfig(
            enable_loudnorm=True,
            target_lufs=-14.0,  # Ép âm lượng lớn
            true_peak=-1.5,     # Trần chống méo -1.5 dBFS
            enable_noise_reduction=False,
            enable_eq=False,
        )
        res = audio_enhancement_engine.enhance_audio(self.test_wav_clean, out_wav, config=cfg)
        self.assertTrue(res["success"])

        meas = audio_enhancement_engine.measure_loudness(out_wav)
        # True Peak không được vượt quá trần -1.5 dBFS
        self.assertLessEqual(meas["true_peak_dbfs"], -1.4)

    def test_10_bypass_mode(self):
        """Kiểm tra tính năng Master Bypass (Tắt toàn bộ hiệu ứng, trả về chuỗi rỗng)."""
        cfg = AudioEnhancementConfig(
            bypass=True,
            enable_noise_reduction=True,
            enable_eq=True,
            enable_loudnorm=True,
        )
        filters = build_ffmpeg_filter_chain(cfg)
        self.assertEqual(len(filters), 0)

        out_wav = self.temp_dir / "out_bypass.wav"
        res = audio_enhancement_engine.enhance_audio(self.test_wav_clean, out_wav, config=cfg)
        self.assertTrue(res["success"])
        self.assertEqual(len(res["applied_filters"]), 0)

    def test_11_cancel_processing(self):
        """Kiểm tra dừng / hủy ngang tiến trình xử lý an toàn không để lại file rác hoặc treo tiến trình."""
        out_wav = self.temp_dir / "out_cancelled.wav"

        # Giả lập cancel_check trả về True ngay lập tức
        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_long,
            output_file=out_wav,
            config=PRESETS["broadcast_military"],
            cancel_check=lambda: True,
        )
        self.assertFalse(res.get("success"))
        self.assertTrue(res.get("cancelled"))
        # File dở dang phải được dọn dẹp
        self.assertFalse(out_wav.is_file())

    def test_12_non_destructive_integrity(self):
        """Kiểm tra nguyên tắc Non-destructive: Tệp gốc không bao giờ bị biến đổi hoặc làm mất."""
        orig_size = self.test_wav_clean.stat().st_size
        out_wav = self.temp_dir / "out_non_destructive.wav"

        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_clean,
            output_file=out_wav,
            config=PRESETS["voiceover_narrative"],
        )
        self.assertTrue(res["success"])
        # Kích thước và tính toàn vẹn của file gốc giữ nguyên
        self.assertEqual(self.test_wav_clean.stat().st_size, orig_size)

    def test_13_audio_studio_export_normalization(self):
        """Kiểm tra quy trình xuất file trong Audio Studio: Hỗ trợ cả Peak và LUFS mà không thay thế Peak."""
        from gui.pages.page_audio_studio import AudioStudioExportDialog
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        dlg = AudioStudioExportDialog(default_name="test_export", default_dir=self.temp_dir)
        self.assertIsNotNone(dlg)

        # Kiểm tra danh sách chế độ trong combo box có đủ Peak và LUFS
        modes = [dlg.combo_mode.itemData(i) for i in range(dlg.combo_mode.count())]
        self.assertIn("peak", modes)
        self.assertIn("lufs_voice", modes)
        self.assertIn("lufs_broadcast", modes)
        self.assertIn("none", modes)

        # Thử nghiệm xuất qua ExportCenter với LUFS mastering
        out_mp3 = self.temp_dir / "studio_export_test.mp3"
        exp_res = export_center.export_audio(
            input_file=self.test_wav_clean,
            output_file=out_mp3,
            fmt="mp3",
            apply_lufs_mastering=True,
            target_lufs=-16.0,
        )
        self.assertTrue(exp_res.get("success"))
        self.assertTrue(out_mp3.is_file())

    def test_14_long_audio_stability_and_memory(self):
        """Kiểm tra xử lý âm thanh dài và hiệu năng CPU/RAM."""
        out_wav = self.temp_dir / "out_long_processed.wav"
        t0 = time.time()
        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_long,
            output_file=out_wav,
            config=PRESETS["voiceover_narrative"],
        )
        elapsed = time.time() - t0
        self.assertTrue(res["success"])
        self.assertTrue(out_wav.is_file())

        # Tốc độ xử lý audio 15s phải nhanh hơn nhiều so với thời lượng thực tế (ít nhất 2x realtime)
        duration_audio = get_audio_duration_safe(self.test_wav_long)
        speedup = duration_audio / max(0.001, elapsed)
        self.assertGreater(speedup, 2.0)

    def test_15_regression_broadcast_studio(self):
        """Kiểm tra hồi quy: Broadcast Studio vẫn hoạt động trơn tru với preset broadcast_military."""
        out_wav = self.temp_dir / "out_broadcast_mastered.wav"
        res = audio_enhancement_engine.enhance_audio(
            input_file=self.test_wav_clean,
            output_file=out_wav,
            config=PRESETS["broadcast_military"],
        )
        self.assertTrue(res["success"])
        self.assertTrue(out_wav.is_file())

    def test_16_regression_tts_synthesis(self):
        """Kiểm tra hồi quy: VieNeu-TTS v3 Turbo ONNX CPU vẫn nguyên vẹn và hoạt động tốt."""
        from backend.service import tts_service
        self.assertIsNotNone(tts_service)
        voices = tts_service.list_voices()
        self.assertIsInstance(voices, list)
        self.assertGreater(len(voices), 0)


if __name__ == "__main__":
    unittest.main()
