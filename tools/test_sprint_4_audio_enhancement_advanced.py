"""tools/test_sprint_4_audio_enhancement_advanced.py
=================================================
Automated test suite for Sprint 4 (Phase 8.4 - 8.8 DSP Advanced & Studio Integration):
1. 8.4 De-Esser filter execution on sibilant audio.
2. 8.5 Dynamic Compressor filter execution on dynamic audio.
3. 8.6 Four Professional Military & Media Presets verification.
4. 8.7 Complete sequential DSP Pipeline execution.
5. 8.8 A/B Comparison Preview Dialog & Audio Studio / Broadcast Studio UI integration.
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
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    # Tần số nền 200Hz xen kẽ xung tần số cao 6kHz mô phỏng âm xuýt /s/, /x/
    signal = 0.4 * np.sin(2 * np.pi * 200 * t) + 0.3 * np.sin(2 * np.pi * 6000 * t)
    audio = np.clip(signal, -0.95, 0.95)

    pcm = (audio * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return path


class TestSprint4AudioEnhancementAdvanced(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_ffmpeg()
        cls.ffmpeg_ok = is_ffmpeg_ready()
        cls.test_dir = PROJECT_ROOT / "temp" / "test_sprint_4"
        cls.test_dir.mkdir(parents=True, exist_ok=True)

        cls.sample_wav = cls.test_dir / "sample_sibilant.wav"
        _generate_test_wav(cls.sample_wav, duration_sec=2.5)

    def test_01_deesser_execution(self):
        """Kiểm tra 8.4 Bộ lọc De-Esser triệt tiêu âm xuýt rít."""
        if not self.ffmpeg_ok:
            self.skipTest("FFmpeg chưa sẵn sàng.")

        out_wav = self.test_dir / "out_deesser.wav"
        cfg = AudioEnhancementConfig(
            enable_deesser=True,
            deesser_intensity=0.7,
            enable_noise_reduction=False,
            enable_eq=False,
            enable_loudnorm=False,
            enable_compressor=False,
        )

        res = audio_enhancement_engine.enhance_audio(self.sample_wav, out_wav, config=cfg)
        self.assertTrue(res["success"], f"De-Esser error: {res.get('error')}")
        self.assertTrue(out_wav.is_file())
        self.assertGreater(out_wav.stat().st_size, 10000)

    def test_02_compressor_execution(self):
        """Kiểm tra 8.5 Bộ nén động lực học giọng nói (Dynamic Compressor)."""
        if not self.ffmpeg_ok:
            self.skipTest("FFmpeg chưa sẵn sàng.")

        out_wav = self.test_dir / "out_compressor.wav"
        cfg = AudioEnhancementConfig(
            enable_compressor=True,
            compressor_threshold=-18.0,
            compressor_ratio=3.5,
            compressor_attack=15.0,
            compressor_release=200.0,
            enable_noise_reduction=False,
            enable_eq=False,
            enable_loudnorm=False,
            enable_deesser=False,
        )

        res = audio_enhancement_engine.enhance_audio(self.sample_wav, out_wav, config=cfg)
        self.assertTrue(res["success"], f"Compressor error: {res.get('error')}")
        self.assertTrue(out_wav.is_file())
        self.assertGreater(out_wav.stat().st_size, 10000)

    def test_03_all_presets_execution(self):
        """Kiểm tra 8.6 Thực thi toàn bộ 4 cấu hình Presets chuyên nghiệp."""
        if not self.ffmpeg_ok:
            self.skipTest("FFmpeg chưa sẵn sàng.")

        presets_to_test = [
            ("broadcast_military", "out_preset_military.wav"),
            ("warm_narrative", "out_preset_warm.wav"),
            ("outdoor_loudspeaker", "out_preset_outdoor.wav"),
            ("podcast_studio", "out_preset_podcast.wav"),
        ]

        for p_key, out_name in presets_to_test:
            out_file = self.test_dir / out_name
            cfg = PRESETS[p_key]
            res = audio_enhancement_engine.enhance_audio(self.sample_wav, out_file, config=cfg)
            self.assertTrue(res["success"], f"Preset {p_key} lỗi: {res.get('error')}")
            self.assertTrue(out_file.is_file())
            self.assertGreater(out_file.stat().st_size, 10000)

    def test_04_full_dsp_pipeline_chain(self):
        """Kiểm tra 8.7 Chuỗi xử lý DSP liên hoàn đầy đủ."""
        if not self.ffmpeg_ok:
            self.skipTest("FFmpeg chưa sẵn sàng.")

        out_wav = self.test_dir / "out_full_pipeline.wav"
        cfg = AudioEnhancementConfig(
            enable_noise_reduction=True,
            noise_reduction_db=12.0,
            highpass_freq=80.0,
            lowpass_freq=12000.0,
            enable_deesser=True,
            deesser_intensity=0.5,
            enable_eq=True,
            eq_warmth_gain=2.0,
            eq_boxiness_gain=-1.5,
            eq_presence_gain=3.0,
            eq_air_gain=1.5,
            enable_compressor=True,
            compressor_threshold=-18.0,
            compressor_ratio=3.0,
            enable_loudnorm=True,
            target_lufs=-16.0,
            loudness_range=7.0,
            true_peak=-1.5,
        )

        res = audio_enhancement_engine.enhance_audio(self.sample_wav, out_wav, config=cfg)
        self.assertTrue(res["success"])
        self.assertTrue(out_wav.is_file())
        # Verify 5 stages applied
        self.assertGreaterEqual(len(res["applied_filters"]), 5)

    def test_05_gui_ab_dialog_and_studio_integration(self):
        """Kiểm tra 8.8 Giao diện Dialog so sánh A/B và nút tích hợp trên Studio."""
        from PySide6.QtWidgets import QApplication, QPushButton
        app = QApplication.instance()
        if not app:
            app = QApplication([])

        from gui.dialog_audio_enhancement import AudioEnhancementDialog
        from gui.pages.page_audio_studio import PageAudioStudio
        from gui.pages.page_broadcast import PageBroadcast

        dlg = AudioEnhancementDialog(input_wav_path=self.sample_wav)
        self.assertIsNotNone(dlg.rb_original)
        self.assertIsNotNone(dlg.rb_enhanced)
        self.assertIsNotNone(dlg.btn_preview_play)
        self.assertIsNotNone(dlg.btn_apply)
        self.assertIsNotNone(dlg.btn_cancel)
        dlg.close()

        # Check Audio Studio has btn_dsp
        studio = PageAudioStudio()
        buttons = studio.findChildren(QPushButton)
        btn_texts = [b.text() for b in buttons]
        self.assertIn("✨ Nâng Cấp DSP", btn_texts)

        # Check Broadcast Studio has chk_dsp_mastering
        broadcast = PageBroadcast()
        self.assertTrue(hasattr(broadcast, "chk_dsp_mastering"))
        self.assertTrue(broadcast.chk_dsp_mastering.isChecked())


if __name__ == "__main__":
    unittest.main()
