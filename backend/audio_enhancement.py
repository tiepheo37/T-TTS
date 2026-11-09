"""backend/audio_enhancement.py — BỘ XỬ LÝ NÂNG CAO CHẤT LƯỢNG ÂM THANH (PHASE 8 DSP ENGINE)
=======================================================================================
Hệ thống xử lý DSP âm thanh quân sự & phát thanh chuyên nghiệp cho T-TTS v3.1.0:
- 8.1 Giảm nhiễu thích ứng (Adaptive Noise Reduction): afftdn + High-pass + Low-pass
- 8.2 Voice Clarity Equalizer (5-Band EQ giọng nói rõ âm tiếng Việt): 80Hz, 250Hz, 600Hz, 3.5kHz, 10kHz
- 8.3 Chuẩn hóa âm lượng EBU R128 LUFS: -16 LUFS (Phát thanh/Podcast), LRA 7, True Peak -1.5 dBFS
- 8.4 Bộ giảm âm gió / xuýt (De-Esser): Triệt tiêu tiếng xì rè /s/, /x/, /tr/
- 8.5 Bộ nén động lực học giọng nói (Compressor): Cân bằng biên độ, làm dầy giọng đọc
- 8.6 Cấu hình mẫu (Presets): Phát thanh quân sự, Giọng ấm truyền cảm, Ngoài trời / Loa phóng thanh, Podcast
- 8.7 Chuỗi xử lý nối tiếp (DSP Pipeline) chạy trên FFmpeg 7.1 offline nguyên bản.
"""

from __future__ import annotations

import os
import shutil
import logging
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .ffmpeg_bootstrap import get_ffmpeg_path, is_ffmpeg_ready

logger = logging.getLogger("T-TTS.AudioEnhancement")


# =============================================================================
# CẤU HÌNH XỬ LÝ ÂM THANH (DSP CONFIG)
# =============================================================================
@dataclass
class AudioEnhancementConfig:
    # 1. Giảm nhiễu (Noise Reduction)
    enable_noise_reduction: bool = False
    noise_reduction_db: float = 12.0       # Mức giảm nhiễu (6 - 24 dB)
    noise_floor_db: float = -50.0          # Ngưỡng sàn nhiễu
    highpass_freq: float = 80.0            # Cắt tần số thấp (rumble / rung mic)
    lowpass_freq: float = 12000.0          # Cắt tần số quá cao (rít / hiss)

    # 2. Equalizer tối ưu giọng nói tiếng Việt
    enable_eq: bool = False
    eq_warmth_gain: float = 1.5            # 250 Hz (Dầy giọng, độ ấm)
    eq_boxiness_gain: float = -1.5         # 600 Hz (Cắt độ nghẹt, tù tiếng)
    eq_presence_gain: float = 3.0          # 3500 Hz (Độ sắc nét phụ âm tiếng Việt)
    eq_air_gain: float = 1.5               # 10000 Hz (Độ thoáng đãng, mở rộng không gian)

    # 3. Chuẩn hóa âm lượng EBU R128 LUFS
    enable_loudnorm: bool = True
    target_lufs: float = -16.0             # Mục tiêu âm lượng chuẩn phát thanh (-16.0 LUFS)
    loudness_range: float = 7.0            # LRA
    true_peak: float = -1.5                # True Peak trần chống méo loa (-1.5 dBFS)

    # 4. De-Esser (Giảm âm xuýt rít tiếng Việt)
    enable_deesser: bool = False
    deesser_intensity: float = 0.5         # Mức độ triệt tiêu âm xuýt (0.1 - 1.0)

    # 5. Dynamic Compressor (Bộ nén giọng)
    enable_compressor: bool = False
    compressor_threshold: float = -18.0    # dB
    compressor_ratio: float = 3.0          # 3:1
    compressor_attack: float = 20.0        # ms
    compressor_release: float = 250.0      # ms

    # Tên preset hiện tại (nếu có)
    preset_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AudioEnhancementConfig:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# =============================================================================
# CÁC PRESETS CHUYÊN NGHIỆP PHỤC VỤ QUÂN ĐỘI & TRUYỀN THÔNG
# =============================================================================
PRESETS: Dict[str, AudioEnhancementConfig] = {
    "broadcast_military": AudioEnhancementConfig(
        preset_name="Phát thanh Quân đội tiêu chuẩn",
        enable_noise_reduction=True,
        noise_reduction_db=12.0,
        highpass_freq=85.0,
        lowpass_freq=11000.0,
        enable_eq=True,
        eq_warmth_gain=1.5,
        eq_boxiness_gain=-1.5,
        eq_presence_gain=3.5,
        eq_air_gain=1.0,
        enable_loudnorm=True,
        target_lufs=-16.0,
        loudness_range=6.5,
        true_peak=-1.5,
        enable_deesser=True,
        deesser_intensity=0.4,
        enable_compressor=True,
        compressor_threshold=-18.0,
        compressor_ratio=3.5,
    ),
    "warm_narrative": AudioEnhancementConfig(
        preset_name="Giọng ấm truyền cảm (Kể chuyện / Văn nghệ)",
        enable_noise_reduction=True,
        noise_reduction_db=8.0,
        highpass_freq=70.0,
        lowpass_freq=12500.0,
        enable_eq=True,
        eq_warmth_gain=3.0,
        eq_boxiness_gain=-1.0,
        eq_presence_gain=2.0,
        eq_air_gain=2.0,
        enable_loudnorm=True,
        target_lufs=-18.0,
        loudness_range=8.0,
        true_peak=-2.0,
        enable_deesser=True,
        deesser_intensity=0.5,
        enable_compressor=True,
        compressor_threshold=-22.0,
        compressor_ratio=2.5,
    ),
    "outdoor_loudspeaker": AudioEnhancementConfig(
        preset_name="Rõ tiếng ngoài trời / Loa phóng thanh truyền thanh",
        enable_noise_reduction=True,
        noise_reduction_db=16.0,
        highpass_freq=120.0,
        lowpass_freq=8500.0,
        enable_eq=True,
        eq_warmth_gain=0.0,
        eq_boxiness_gain=-3.0,
        eq_presence_gain=5.0,
        eq_air_gain=0.0,
        enable_loudnorm=True,
        target_lufs=-14.0,
        loudness_range=4.0,
        true_peak=-1.0,
        enable_deesser=False,
        enable_compressor=True,
        compressor_threshold=-15.0,
        compressor_ratio=4.5,
    ),
    "podcast_studio": AudioEnhancementConfig(
        preset_name="Phòng thu Podcast hiện đại",
        enable_noise_reduction=True,
        noise_reduction_db=10.0,
        highpass_freq=80.0,
        lowpass_freq=13000.0,
        enable_eq=True,
        eq_warmth_gain=2.0,
        eq_boxiness_gain=-2.0,
        eq_presence_gain=3.0,
        eq_air_gain=2.5,
        enable_loudnorm=True,
        target_lufs=-16.0,
        loudness_range=7.0,
        true_peak=-1.5,
        enable_deesser=True,
        deesser_intensity=0.6,
        enable_compressor=True,
        compressor_threshold=-20.0,
        compressor_ratio=3.0,
    ),
}


# =============================================================================
# XÂY DỰNG CHUỖI BỘ LỌC FFMPEG (FILTER CHAIN BUILDER)
# =============================================================================
def build_ffmpeg_filter_chain(config: AudioEnhancementConfig) -> List[str]:
    """Tạo chuỗi filter audio nối tiếp của FFmpeg theo thứ tự chuẩn:
    1. Giảm nhiễu thích ứng + Lọc cao tần / thấp tần
    2. De-Esser (Giảm âm xuýt trước khi qua EQ/Compressor)
    3. Equalizer giọng nói tiếng Việt 5 dải
    4. Compressor động lực học
    5. Chuẩn hóa độ to theo chuẩn EBU R128 LUFS
    """
    filters: List[str] = []

    # 1. Giảm nhiễu
    if config.enable_noise_reduction:
        # Cắt ù nền dưới highpass_freq
        if config.highpass_freq > 0:
            filters.append(f"highpass=f={int(config.highpass_freq)}")

        # Bộ giảm nhiễu thích ứng FFT chuyên dụng của FFmpeg
        nr = max(1.0, min(30.0, float(config.noise_reduction_db)))
        nf = min(-20.0, float(config.noise_floor_db))
        filters.append(f"afftdn=nr={nr:.1f}:nf={nf:.1f}:tn=1")

        # Cắt rít tần số cao
        if config.lowpass_freq < 20000:
            filters.append(f"lowpass=f={int(config.lowpass_freq)}")

    # 2. De-Esser
    if config.enable_deesser:
        intensity = max(0.1, min(1.0, float(config.deesser_intensity)))
        filters.append(f"deesser=i={intensity:.2f}:m=0.5:f=0.5:s=o")

    # 3. Equalizer 5 dải
    if config.enable_eq:
        # Dải ấm / Body giọng: 250 Hz
        if abs(config.eq_warmth_gain) > 0.05:
            filters.append(f"equalizer=f=250:t=q:w=1.0:g={config.eq_warmth_gain:.1f}")

        # Dải nghẹt / Boxiness: 600 Hz
        if abs(config.eq_boxiness_gain) > 0.05:
            filters.append(f"equalizer=f=600:t=q:w=1.2:g={config.eq_boxiness_gain:.1f}")

        # Dải rõ chữ / Presence tiếng Việt: 3500 Hz
        if abs(config.eq_presence_gain) > 0.05:
            filters.append(f"equalizer=f=3500:t=q:w=1.0:g={config.eq_presence_gain:.1f}")

        # Dải thoáng / Air: 10000 Hz
        if abs(config.eq_air_gain) > 0.05:
            filters.append(f"equalizer=f=10000:t=q:w=1.0:g={config.eq_air_gain:.1f}")

    # 4. Compressor
    if config.enable_compressor:
        thresh = float(config.compressor_threshold)
        ratio = max(1.1, float(config.compressor_ratio))
        atk = max(1.0, float(config.compressor_attack))
        rel = max(10.0, float(config.compressor_release))
        filters.append(f"acompressor=threshold={thresh:.1f}dB:ratio={ratio:.1f}:attack={atk:.1f}:release={rel:.1f}")

    # 5. EBU R128 LUFS Loudness Normalization (Bộ lọc cuối cùng trong chuỗi)
    if config.enable_loudnorm:
        target_i = max(-30.0, min(-10.0, float(config.target_lufs)))
        lra = max(3.0, min(20.0, float(config.loudness_range)))
        tp = max(-5.0, min(-0.5, float(config.true_peak)))
        filters.append(f"loudnorm=I={target_i:.1f}:LRA={lra:.1f}:TP={tp:.1f}")

    return filters


# =============================================================================
# ĐIỀU PHỐI XỬ LÝ ÂM THANH (AUDIO ENHANCEMENT ENGINE)
# =============================================================================
class AudioEnhancementEngine:
    """Động cơ xử lý nâng cao âm thanh DSP offline dựa trên FFmpeg 7.1."""

    @classmethod
    def enhance_audio(
        cls,
        input_file: str | Path,
        output_file: str | Path,
        config: Optional[AudioEnhancementConfig] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Any]:
        """Thực thi chuỗi xử lý âm thanh nâng cao (DSP) và xuất ra file mới."""
        in_path = Path(input_file).resolve()
        out_path = Path(output_file).resolve()

        if not in_path.is_file():
            return {
                "success": False,
                "input_file": str(in_path),
                "output_file": str(out_path),
                "applied_filters": [],
                "error": f"Không tìm thấy tệp âm thanh đầu vào: {in_path}",
            }

        ffmpeg_exe = get_ffmpeg_path()
        if not ffmpeg_exe or not Path(ffmpeg_exe).is_file():
            return {
                "success": False,
                "input_file": str(in_path),
                "output_file": str(out_path),
                "applied_filters": [],
                "error": "Không tìm thấy chương trình xử lý FFmpeg trong hệ thống.",
            }

        cfg = config or PRESETS["broadcast_military"]
        filters = build_ffmpeg_filter_chain(cfg)

        out_path.parent.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(10, "Đang cấu hình chuỗi bộ lọc âm thanh DSP...")

        # Xây dựng lệnh gọi FFmpeg
        cmd = [
            ffmpeg_exe,
            "-y",
            "-loglevel", "error",
            "-i", str(in_path),
        ]

        if filters:
            filter_str = ",".join(filters)
            cmd.extend(["-af", filter_str])

        # Định dạng xuất dựa trên đuôi file
        out_ext = out_path.suffix.lower()
        if out_ext == ".mp3":
            cmd.extend(["-codec:a", "libmp3lame", "-b:a", "192k"])
        else:
            cmd.extend(["-codec:a", "pcm_s16le", "-ar", "48000"])

        cmd.append(str(out_path))

        if progress_callback:
            progress_callback(30, "Đang thực thi xử lý âm thanh lọc nhiễu và cân bằng EQ...")

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            if res.returncode != 0:
                logger.error(f"FFmpeg DSP error: {res.stderr}")
                return {
                    "success": False,
                    "input_file": str(in_path),
                    "output_file": str(out_path),
                    "applied_filters": filters,
                    "error": f"Lỗi FFmpeg: {res.stderr.strip()}",
                }

            if not out_path.is_file() or out_path.stat().st_size == 0:
                return {
                    "success": False,
                    "input_file": str(in_path),
                    "output_file": str(out_path),
                    "applied_filters": filters,
                    "error": "Tệp đầu ra rỗng hoặc không được tạo thành công.",
                }

            if progress_callback:
                progress_callback(100, "Xử lý nâng cao chất lượng âm thanh hoàn tất!")

            return {
                "success": True,
                "input_file": str(in_path),
                "output_file": str(out_path),
                "applied_filters": filters,
                "file_size": out_path.stat().st_size,
                "preset_name": cfg.preset_name,
                "error": None,
            }

        except Exception as e:
            logger.exception("Ngoại lệ khi thực thi DSP Audio Enhancement:")
            return {
                "success": False,
                "input_file": str(in_path),
                "output_file": str(out_path),
                "applied_filters": filters,
                "error": str(e),
            }


audio_enhancement_engine = AudioEnhancementEngine()
