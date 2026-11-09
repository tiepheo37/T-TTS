"""backend/audio_enhancement.py — BỘ XỬ LÝ NÂNG CAO CHẤT LƯỢNG ÂM THANH (PHASE 8 DSP ENGINE)
=======================================================================================
Hệ thống xử lý DSP âm thanh quân sự & phát thanh chuyên nghiệp cho T-TTS v3.1.0:
- 8.1 Giảm nhiễu thích ứng (Adaptive Noise Reduction): afftdn + High-pass + Low-pass
- 8.2 Voice Clarity Equalizer (Equalizer giọng nói tiếng Việt):
      High-pass (80Hz), Bass (100Hz), Warmth (250Hz), Boxiness (600Hz),
      Presence (3.5kHz), Treble (8kHz), Air (10kHz)
- 8.3 Chuẩn hóa âm lượng EBU R128 LUFS: -16 LUFS (Giọng đọc/Podcast), -23 LUFS (Chuẩn truyền thanh),
      LRA 7, True Peak Ceiling -1.0 đến -1.5 dBFS. Đo đạc LUFS thời gian thực.
- 8.4 Bộ giảm âm gió / xuýt (De-Esser): Triệt tiêu tiếng xì rè /s/, /x/, /tr/
- 8.5 Bộ nén động lực học giọng nói (Compressor): Cân bằng biên độ, làm dầy giọng đọc
- 8.6 Cấu hình mẫu (Presets): Thuyết minh chuyên nghiệp, Phát thanh Quân đội, Giọng ấm, Ngoài trời, Podcast, Chuẩn EBU
- 8.7 Chuỗi xử lý nối tiếp (DSP Pipeline) chạy trên FFmpeg 7.1 offline nguyên bản, hỗ trợ Preview, Bypass, Non-destructive.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .ffmpeg_bootstrap import get_ffmpeg_path, is_ffmpeg_ready

logger = logging.getLogger("T-TTS.AudioEnhancement")


# =============================================================================
# CẤU HÌNH XỬ LÝ ÂM THANH (DSP CONFIG)
# =============================================================================
@dataclass
class AudioEnhancementConfig:
    # 0. Master Bypass (Tắt toàn bộ hiệu ứng, truyền thẳng audio gốc)
    bypass: bool = False

    # 1. Giảm nhiễu (Noise Reduction) - Mặc định TẮT cho TTS sạch
    enable_noise_reduction: bool = False
    noise_reduction_db: float = 12.0       # Mức giảm nhiễu (6 - 24 dB)
    noise_floor_db: float = -50.0          # Ngưỡng sàn nhiễu (-80 đến -20 dB)
    enable_highpass: bool = True           # Bật bộ lọc cắt tần số thấp (rumble filter)
    highpass_freq: float = 80.0            # Cắt tần số thấp (rumble / rung mic 50 - 150 Hz)
    lowpass_freq: float = 12000.0          # Cắt tần số quá cao (rít / hiss)

    # 2. Equalizer tối ưu giọng nói tiếng Việt
    enable_eq: bool = False
    bass_gain: float = 0.0                 # 100 Hz (Âm trầm / Bass: -6 đến +6 dB)
    eq_warmth_gain: float = 1.5            # 250 Hz (Dầy giọng, độ ấm)
    eq_boxiness_gain: float = -1.5         # 600 Hz (Cắt độ nghẹt, tù tiếng)
    eq_presence_gain: float = 3.0          # 3500 Hz (Độ sắc nét phụ âm tiếng Việt)
    treble_gain: float = 0.0               # 8000 Hz (Âm cao / Treble: -6 đến +6 dB)
    eq_air_gain: float = 1.5               # 10000 Hz (Độ thoáng đãng, mở rộng không gian)

    # 3. Chuẩn hóa âm lượng EBU R128 LUFS
    enable_loudnorm: bool = True
    target_lufs: float = -16.0             # Mục tiêu âm lượng chuẩn phát thanh (-16.0 LUFS Voice, -23.0 Broadcast)
    loudness_range: float = 7.0            # LRA
    true_peak: float = -1.5                # True Peak trần chống méo loa (-1.0 đến -1.5 dBFS)

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
    "voiceover_narrative": AudioEnhancementConfig(
        preset_name="Thuyết minh chuyên nghiệp (Voiceover / Giảng bài)",
        bypass=False,
        enable_noise_reduction=False,      # TTS sạch không cần afftdn
        enable_highpass=True,
        highpass_freq=80.0,
        enable_eq=True,
        bass_gain=1.0,
        eq_warmth_gain=1.5,
        eq_boxiness_gain=-1.0,
        eq_presence_gain=2.5,
        treble_gain=1.5,
        eq_air_gain=1.5,
        enable_loudnorm=True,
        target_lufs=-16.0,
        loudness_range=7.0,
        true_peak=-1.5,
        enable_deesser=True,
        deesser_intensity=0.4,
        enable_compressor=True,
        compressor_threshold=-20.0,
        compressor_ratio=2.5,
    ),
    "broadcast_military": AudioEnhancementConfig(
        preset_name="Phát thanh Quân đội tiêu chuẩn",
        bypass=False,
        enable_noise_reduction=True,
        noise_reduction_db=12.0,
        enable_highpass=True,
        highpass_freq=85.0,
        lowpass_freq=11000.0,
        enable_eq=True,
        bass_gain=1.0,
        eq_warmth_gain=1.5,
        eq_boxiness_gain=-1.5,
        eq_presence_gain=3.5,
        treble_gain=1.0,
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
    "broadcast_standard_ebu": AudioEnhancementConfig(
        preset_name="Chuẩn truyền thanh EBU R128 (-23 LUFS)",
        bypass=False,
        enable_noise_reduction=False,
        enable_highpass=True,
        highpass_freq=80.0,
        lowpass_freq=15000.0,
        enable_eq=True,
        bass_gain=0.0,
        eq_warmth_gain=1.0,
        eq_boxiness_gain=-1.0,
        eq_presence_gain=2.0,
        treble_gain=1.0,
        eq_air_gain=1.0,
        enable_loudnorm=True,
        target_lufs=-23.0,
        loudness_range=7.0,
        true_peak=-1.0,
        enable_deesser=True,
        deesser_intensity=0.4,
        enable_compressor=True,
        compressor_threshold=-22.0,
        compressor_ratio=2.5,
    ),
    "warm_narrative": AudioEnhancementConfig(
        preset_name="Giọng ấm truyền cảm (Kể chuyện / Văn nghệ)",
        bypass=False,
        enable_noise_reduction=True,
        noise_reduction_db=8.0,
        enable_highpass=True,
        highpass_freq=70.0,
        lowpass_freq=12500.0,
        enable_eq=True,
        bass_gain=2.0,
        eq_warmth_gain=3.0,
        eq_boxiness_gain=-1.0,
        eq_presence_gain=2.0,
        treble_gain=0.5,
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
        bypass=False,
        enable_noise_reduction=True,
        noise_reduction_db=16.0,
        enable_highpass=True,
        highpass_freq=120.0,
        lowpass_freq=8500.0,
        enable_eq=True,
        bass_gain=-2.0,
        eq_warmth_gain=0.0,
        eq_boxiness_gain=-3.0,
        eq_presence_gain=5.0,
        treble_gain=2.0,
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
        bypass=False,
        enable_noise_reduction=True,
        noise_reduction_db=10.0,
        enable_highpass=True,
        highpass_freq=80.0,
        lowpass_freq=13000.0,
        enable_eq=True,
        bass_gain=1.5,
        eq_warmth_gain=2.0,
        eq_boxiness_gain=-2.0,
        eq_presence_gain=3.0,
        treble_gain=1.5,
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
    0. Bypass check: Nếu bypass=True trả về chuỗi rỗng
    1. Lọc cắt tần số thấp (High-pass filter rumble ~80Hz)
    2. Giảm nhiễu thích ứng FFT (afftdn) + Low-pass
    3. De-Esser (Giảm âm xuýt trước khi qua EQ/Compressor)
    4. Equalizer giọng nói tiếng Việt đa dải: Bass (100Hz), Warmth (250Hz),
       Boxiness (600Hz), Presence (3.5kHz), Treble (8kHz), Air (10kHz)
    5. Compressor động lực học
    6. Chuẩn hóa độ to theo chuẩn EBU R128 LUFS (bộ lọc kiểm soát True Peak cuối cùng)
    """
    if config.bypass:
        return []

    filters: List[str] = []
    applied_highpass = False

    # 1. High-pass filter (Lọc tiếng ù nền / rung chấn)
    if (config.enable_highpass or config.enable_noise_reduction) and config.highpass_freq > 0:
        filters.append(f"highpass=f={int(config.highpass_freq)}")
        applied_highpass = True

    # 2. Giảm nhiễu thích ứng FFT
    if config.enable_noise_reduction:
        nr = max(1.0, min(30.0, float(config.noise_reduction_db)))
        nf = min(-20.0, max(-80.0, float(config.noise_floor_db)))
        filters.append(f"afftdn=nr={nr:.1f}:nf={nf:.1f}:tn=1")

        if config.lowpass_freq < 20000:
            filters.append(f"lowpass=f={int(config.lowpass_freq)}")

    # 3. De-Esser
    if config.enable_deesser:
        intensity = max(0.1, min(1.0, float(config.deesser_intensity)))
        filters.append(f"deesser=i={intensity:.2f}:m=0.5:f=0.5:s=o")

    # 4. Equalizer tối ưu giọng nói
    if config.enable_eq:
        # Bass (100 Hz): Trầm ấm
        if abs(config.bass_gain) > 0.05:
            filters.append(f"equalizer=f=100:t=q:w=0.7:g={config.bass_gain:.1f}")

        # Dải ấm / Body giọng: 250 Hz
        if abs(config.eq_warmth_gain) > 0.05:
            filters.append(f"equalizer=f=250:t=q:w=1.0:g={config.eq_warmth_gain:.1f}")

        # Dải nghẹt / Boxiness: 600 Hz
        if abs(config.eq_boxiness_gain) > 0.05:
            filters.append(f"equalizer=f=600:t=q:w=1.2:g={config.eq_boxiness_gain:.1f}")

        # Dải rõ chữ / Presence tiếng Việt: 3500 Hz
        if abs(config.eq_presence_gain) > 0.05:
            filters.append(f"equalizer=f=3500:t=q:w=1.0:g={config.eq_presence_gain:.1f}")

        # Treble (8000 Hz): Sáng trong
        if abs(config.treble_gain) > 0.05:
            filters.append(f"equalizer=f=8000:t=q:w=0.8:g={config.treble_gain:.1f}")

        # Dải thoáng / Air: 10000 Hz
        if abs(config.eq_air_gain) > 0.05:
            filters.append(f"equalizer=f=10000:t=q:w=1.0:g={config.eq_air_gain:.1f}")

    # 5. Compressor động lực học
    if config.enable_compressor:
        thresh = float(config.compressor_threshold)
        ratio = max(1.1, float(config.compressor_ratio))
        atk = max(1.0, float(config.compressor_attack))
        rel = max(10.0, float(config.compressor_release))
        filters.append(f"acompressor=threshold={thresh:.1f}dB:ratio={ratio:.1f}:attack={atk:.1f}:release={rel:.1f}")

    # 6. EBU R128 LUFS Loudness Normalization
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
    def measure_loudness(cls, audio_file: str | Path) -> Dict[str, Any]:
        """Đo lường độ to tích hợp LUFS (Integrated Loudness), True Peak và Loudness Range (LRA)
        chuẩn EBU R128 thời gian thực.
        """
        in_path = Path(audio_file).resolve()
        if not in_path.is_file():
            return {
                "success": False,
                "error": f"Không tìm thấy tệp âm thanh: {in_path}",
                "integrated_lufs": None,
                "true_peak_dbfs": None,
                "loudness_range_lu": None,
            }

        ffmpeg_exe = get_ffmpeg_path()
        if not ffmpeg_exe or not Path(ffmpeg_exe).is_file():
            return {
                "success": False,
                "error": "Không tìm thấy chương trình FFmpeg.",
                "integrated_lufs": None,
                "true_peak_dbfs": None,
                "loudness_range_lu": None,
            }

        cmd = [
            ffmpeg_exe,
            "-hide_banner",
            "-nostats",
            "-i", str(in_path),
            "-af", "loudnorm=I=-16:TP=-1.5:print_format=json",
            "-f", "null",
            "-",
        ]

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            # Phân tích khối JSON trả về từ FFmpeg stderr
            lines = res.stderr.splitlines()
            json_lines = []
            in_json = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("{"):
                    in_json = True
                if in_json:
                    json_lines.append(stripped)
                if stripped.endswith("}"):
                    in_json = False

            if json_lines:
                json_str = "\n".join(json_lines)
                data = json.loads(json_str)
                return {
                    "success": True,
                    "input_file": str(in_path),
                    "integrated_lufs": float(data.get("input_i", -99.0)),
                    "true_peak_dbfs": float(data.get("input_tp", -99.0)),
                    "loudness_range_lu": float(data.get("input_lra", 0.0)),
                    "threshold_dbfs": float(data.get("input_thresh", -99.0)),
                    "target_offset": float(data.get("target_offset", 0.0)),
                    "raw_data": data,
                    "error": None,
                }
            else:
                return {
                    "success": False,
                    "error": "Không thể phân tích dữ liệu EBU R128 từ FFmpeg.",
                    "integrated_lufs": None,
                    "true_peak_dbfs": None,
                    "loudness_range_lu": None,
                }

        except Exception as e:
            logger.exception("Lỗi khi đo lường độ to âm thanh LUFS:")
            return {
                "success": False,
                "error": str(e),
                "integrated_lufs": None,
                "true_peak_dbfs": None,
                "loudness_range_lu": None,
            }

    @classmethod
    def enhance_audio(
        cls,
        input_file: str | Path,
        output_file: str | Path,
        config: Optional[AudioEnhancementConfig] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Thực thi chuỗi xử lý âm thanh nâng cao (DSP) và xuất ra file mới.
        - Non-destructive: File nguồn không bao giờ bị ghi đè trực tiếp mà chưa kiểm tra.
        - Cancelable: Cho phép dừng tiến trình tức thì qua cancel_check callback.
        """
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

        cfg = config or PRESETS["voiceover_narrative"]
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
            progress_callback(30, "Đang thực thi xử lý âm thanh DSP...")

        try:
            # Khởi tạo subprocess hỗ trợ kiểm tra hủy ngang (Cancellation)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Giám sát tiến trình với cơ chế kiểm tra hủy
            while proc.poll() is None:
                if cancel_check and cancel_check():
                    proc.kill()
                    try:
                        proc.communicate(timeout=2.0)
                    except Exception:
                        pass
                    if out_path.is_file():
                        try:
                            out_path.unlink()
                        except Exception:
                            pass
                    return {
                        "success": False,
                        "cancelled": True,
                        "input_file": str(in_path),
                        "output_file": str(out_path),
                        "applied_filters": filters,
                        "error": "Tiến trình xử lý DSP đã bị hủy bởi người dùng.",
                    }
                time.sleep(0.05)

            stdout, stderr = proc.communicate()

            if proc.returncode != 0:
                logger.error(f"FFmpeg DSP error: {stderr}")
                return {
                    "success": False,
                    "input_file": str(in_path),
                    "output_file": str(out_path),
                    "applied_filters": filters,
                    "error": f"Lỗi FFmpeg: {stderr.strip()}",
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
