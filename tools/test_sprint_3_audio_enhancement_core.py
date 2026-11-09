"""tools/test_sprint_3_audio_enhancement_core.py
==============================================
Automated test suite for Sprint 3 (Phase 8.1 - 8.3 DSP Core):
1. AudioEnhancementConfig & Presets.
2. Filter chain generation (afftdn, highpass, lowpass, equalizer, loudnorm).
3. Real WAV DSP processing:
   - 8.1 Adaptive Noise Reduction.
   - 8.2 Voice Clarity 5-Band EQ.
   - 8.3 EBU R128 LUFS Loudness Normalization.
4. Output audio integrity verification (48kHz, valid PCM).
"""

from __future__ import annotations

import os
import sys
import wave
import unittest
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.ffmpeg_bootstrap import initialize_ffmpeg, is_ffmpeg_ready
from backend.audio_enhancement import (
    AudioEnhancementConfig,
    PRESETS,
    build_ffmpeg_filter_chain,
    audio_enhancement_engine,
)


def _generate_test_wav(path: Path, duration_sec: float = 3.0, sample_rate: int = 48000) -> Path:
    """Tạo tệp WAV thử nghiệm gồm âm thanh tần số cơ bản trộn với nhiễu nhẹ."""
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    # Tần số giọng nói ~220Hz (A3) và họa âm 880Hz, cộng nhiễu ngẫu nhiên
    signal = 0.5 * np.sin(2 * np.pi * 220 * t) + 0.2 * np.sin(2 * np.pi * 880 * t)
    noise = 0.05 * np.random.normal(0, 1, len(t))
    audio = np.clip(signal + noise, -0.95, 0.95)

    pcm = (audio * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return path


class TestSprint3AudioEnhancementCore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_res = initialize_ffmpeg()
        cls.ffmpeg_ok = is_ffmpeg_ready()
        cls.test_dir = PROJECT_ROOT / "temp" / "test_sprint_3"
        cls.test_dir.mkdir(parents=True, exist_ok=True)

        cls.sample_wav = cls.test_dir / "sample_voice.wav"
        _generate_test_wav(cls.sample_wav, duration_sec=2.5)

    def test_01_config_and_presets(self):
        """Kiểm tra cấu hình AudioEnhancementConfig và các bộ presets chuyên nghiệp."""
        cfg = AudioEnhancementConfig(
            enable_noise_reduction=True,
            noise_reduction_db=15.0,
            enable_loudnorm=True,
            target_lufs=-16.0,
        )
        d = cfg.to_dict()
        self.assertTrue(d["enable_noise_reduction"])
        self.assertEqual(d["noise_reduction_db"], 15.0)
        self.assertEqual(d["target_lufs"], -16.0)

        # Kiểm tra các presets
        self.assertIn("broadcast_military", PRESETS)
        self.assertIn("warm_narrative", PRESETS)
        self.assertIn("outdoor_loudspeaker", PRESETS)
        self.assertIn("podcast_studio", PRESETS)

    def test_02_filter_chain_generation(self):
        """Kiểm tra sinh chuỗi lệnh filter FFmpeg chính xác."""
        cfg = AudioEnhancementConfig(
            enable_noise_reduction=True,
            noise_reduction_db=14.0,
            highpass_freq=85.0,
            lowpass_freq=11000.0,
            enable_eq=True,
            eq_warmth_gain=2.0,
            eq_presence_gain=3.5,
            enable_loudnorm=True,
            target_lufs=-16.0,
            loudness_range=7.0,
            true_peak=-1.5,
        )

        filters = build_ffmpeg_filter_chain(cfg)
        filter_str = ",".join(filters)

        # 8.1 Noise Reduction
        self.assertIn("highpass=f=85", filter_str)
        self.assertIn("afftdn=nr=14.0", filter_str)
        self.assertIn("lowpass=f=11000", filter_str)

        # 8.2 Voice Clarity EQ
        self.assertIn("equalizer=f=250:t=q:w=1.0:g=2.0", filter_str)
        self.assertIn("equalizer=f=3500:t=q:w=1.0:g=3.5", filter_str)

        # 8.3 EBU R128 LUFS Loudnorm
        self.assertIn("loudnorm=I=-16.0:LRA=7.0:TP=-1.5", filter_str)

    def test_03_dsp_noise_reduction(self):
        """Kiểm tra thực thi Giảm nhiễu thích ứng 8.1 trên tệp WAV thực tế."""
        if not self.ffmpeg_ok:
            self.skipTest("FFmpeg chưa sẵn sàng trên hệ thống.")

        out_wav = self.test_dir / "out_noise_reduction.wav"
        cfg = AudioEnhancementConfig(
            enable_noise_reduction=True,
            noise_reduction_db=12.0,
            highpass_freq=80.0,
            lowpass_freq=12000.0,
            enable_eq=False,
            enable_loudnorm=False,
        )

        res = audio_enhancement_engine.enhance_audio(self.sample_wav, out_wav, config=cfg)
        self.assertTrue(res["success"], f"Lỗi lọc nhiễu: {res.get('error')}")
        self.assertTrue(out_wav.is_file())
        self.assertGreater(out_wav.stat().st_size, 10000)

        # Verify WAV header
        with wave.open(str(out_wav), "rb") as w:
            self.assertEqual(w.getnchannels(), 1)
            self.assertEqual(w.getframerate(), 48000)

    def test_04_dsp_voice_clarity_eq(self):
        """Kiểm tra thực thi Voice Clarity Equalizer 8.2 trên tệp WAV thực tế."""
        if not self.ffmpeg_ok:
            self.skipTest("FFmpeg chưa sẵn sàng trên hệ thống.")

        out_wav = self.test_dir / "out_eq.wav"
        cfg = AudioEnhancementConfig(
            enable_noise_reduction=False,
            enable_eq=True,
            eq_warmth_gain=2.0,
            eq_boxiness_gain=-1.5,
            eq_presence_gain=3.0,
            eq_air_gain=1.5,
            enable_loudnorm=False,
        )

        res = audio_enhancement_engine.enhance_audio(self.sample_wav, out_wav, config=cfg)
        self.assertTrue(res["success"], f"Lỗi cân bằng EQ: {res.get('error')}")
        self.assertTrue(out_wav.is_file())
        self.assertGreater(out_wav.stat().st_size, 10000)

    def test_05_dsp_ebu_r128_loudnorm(self):
        """Kiểm tra chuẩn hóa âm lượng EBU R128 LUFS 8.3 trên tệp WAV thực tế."""
        if not self.ffmpeg_ok:
            self.skipTest("FFmpeg chưa sẵn sàng trên hệ thống.")

        out_wav = self.test_dir / "out_loudnorm.wav"
        cfg = AudioEnhancementConfig(
            enable_noise_reduction=False,
            enable_eq=False,
            enable_loudnorm=True,
            target_lufs=-16.0,
            loudness_range=7.0,
            true_peak=-1.5,
        )

        res = audio_enhancement_engine.enhance_audio(self.sample_wav, out_wav, config=cfg)
        self.assertTrue(res["success"], f"Lỗi chuẩn hóa Loudnorm: {res.get('error')}")
        self.assertTrue(out_wav.is_file())
        self.assertGreater(out_wav.stat().st_size, 10000)

    def test_06_error_handling(self):
        """Kiểm tra xử lý lỗi an toàn khi tệp không tồn tại."""
        missing_wav = self.test_dir / "not_found.wav"
        out_wav = self.test_dir / "out_dummy.wav"

        res = audio_enhancement_engine.enhance_audio(missing_wav, out_wav)
        self.assertFalse(res["success"])
        self.assertIn("Không tìm thấy tệp", res["error"])


if __name__ == "__main__":
    unittest.main()
