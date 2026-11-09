"""backend/audio_enhancement.py — BỘ XỬ LÝ NÂNG CAO CHẤT LƯỢNG ÂM THANH (PHASE 8 DSP ENGINE)
=======================================================================================
Hệ thống xử lý DSP âm thanh quân sự & phát thanh chuyên nghiệp cho T-TTS v3.1.0:
- 8.1 Giảm nhiễu thích ứng (Adaptive Noise Reduction): afftdn + High-pass + Low-pass
- 8.2 Voice Clarity Equalizer (Equalizer giọng nói tiếng Việt):
      High-pass (80Hz), Bass (100Hz), Warmth (250Hz), Boxiness (600Hz),
      Presence (3.5kHz), Treble (8kHz), Air (10kHz)
- 8.3 Chuẩn hóa âm lượng EBU R128 LUFS: -16 LUFS (Giọng đọc/Podcast), -23 LUFS (Chuẩn truyền thanh),
      LRA 7, True Peak Ceiling -1.0 đến -1.5 dBFS. Đo đạc LUFS thời gian thực.
- 8.4 Bộ giảm âm gió / xuýt (De-Esser): Triệt tiêu tiếng xì rè /s/, /x/, /tr/ (Threshold, Intensity, Frequency)
- 8.5 Bộ nén động lực học giọng nói (Compressor): Cân bằng biên độ, làm dầy giọng đọc (Threshold, Ratio,
      Attack, Release, Makeup Gain, Soft Knee) với 4 preset chuẩn.
- 8.6 Quản lý Cấu hình mẫu (Presets): Clean Voice, Studio Voice, Podcast, Military Narration, Broadcast,
      Voice + Background Music, Custom Presets (CRUD & Import/Export JSON).
- 8.7 Chuỗi xử lý nối tiếp (DSP Pipeline):
      Noise Reduction → EQ → De-Esser → Compressor → LUFS → Limiter
      Bộ xử lý độc lập, bật/tắt từng bộ lọc, thay đổi thứ tự, Reset, Non-destructive.
- 8.8 So sánh A/B và Preview nâng cao: Đồng bộ vị trí phát, Preview theo đoạn chọn (time slice),
      so sánh LUFS và True Peak.
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
from .storage import init_storage

logger = logging.getLogger("T-TTS.AudioEnhancement")

_STORAGE = init_storage()
DATA_DIR: Path = _STORAGE["data_dir"]
PRESETS_DIR: Path = DATA_DIR / "presets"
PRESETS_DIR.mkdir(parents=True, exist_ok=True)
CUSTOM_PRESETS_FILE: Path = PRESETS_DIR / "audio_presets.json"

DEFAULT_PIPELINE_ORDER: List[str] = [
    "noise_reduction",
    "eq",
    "deesser",
    "compressor",
    "loudnorm",
    "limiter",
]


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

    # 2. Equalizer tối ưu giọng nói tiếng Việt 6 dải
    enable_eq: bool = False
    bass_gain: float = 0.0                 # 100 Hz (Âm trầm / Bass: -6 đến +6 dB)
    eq_warmth_gain: float = 1.5            # 250 Hz (Dầy giọng, độ ấm)
    eq_boxiness_gain: float = -1.5         # 600 Hz (Cắt độ nghẹt, tù tiếng)
    eq_presence_gain: float = 3.0          # 3500 Hz (Độ sắc nét phụ âm tiếng Việt)
    treble_gain: float = 0.0               # 8000 Hz (Âm cao / Treble: -6 đến +6 dB)
    eq_air_gain: float = 1.5               # 10000 Hz (Độ thoáng đãng, mở rộng không gian)

    # 3. De-Esser (Giảm âm xuýt rít tiếng Việt)
    enable_deesser: bool = False
    deesser_threshold: float = -20.0       # Ngưỡng kích hoạt (-35 đến -10 dB)
    deesser_intensity: float = 0.45        # Mức độ triệt tiêu âm xuýt (0.1 - 1.0)
    deesser_freq: float = 6000.0           # Tần số trung tâm âm xuýt (4000 - 10000 Hz)

    # 4. Dynamic Speech Compressor (Bộ nén giọng nói)
    enable_compressor: bool = False
    compressor_threshold: float = -18.0    # dB (-30 đến -6 dB)
    compressor_ratio: float = 3.0          # (1.5:1 đến 8:1)
    compressor_attack: float = 20.0        # ms (1 đến 100 ms)
    compressor_release: float = 250.0      # ms (20 đến 1000 ms)
    compressor_makeup_gain: float = 1.5    # dB (0 đến 12 dB bù âm lượng sau nén)
    compressor_knee: float = 2.8           # dB (1.0 đến 8.0 dB độ mềm chuyển tiếp - soft knee)

    # 5. Chuẩn hóa âm lượng EBU R128 LUFS
    enable_loudnorm: bool = True
    target_lufs: float = -16.0             # Mục tiêu âm lượng chuẩn phát thanh (-16.0 LUFS Voice, -23.0 Broadcast)
    loudness_range: float = 7.0            # LRA (3.0 đến 15.0 LU)
    true_peak: float = -1.5                # True Peak trần chống méo loa (-1.0 đến -1.5 dBFS)

    # 6. Final Limiter (Bộ hạn chế biên độ đỉnh chống clipping cuối chuỗi)
    enable_limiter: bool = True
    limiter_ceiling: float = -1.0          # dBFS trần an toàn (-0.5 đến -3.0 dBFS)
    limiter_release: float = 50.0          # ms (10 đến 200 ms)

    # 7. Thứ tự chuỗi xử lý (Pipeline Order)
    pipeline_order: List[str] = field(
        default_factory=lambda: list(DEFAULT_PIPELINE_ORDER)
    )

    # Thông tin preset
    preset_name: Optional[str] = None
    is_custom: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AudioEnhancementConfig:
        clean_data = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "pipeline_order" not in clean_data or not clean_data["pipeline_order"]:
            clean_data["pipeline_order"] = list(DEFAULT_PIPELINE_ORDER)
        return cls(**clean_data)

    def reset_defaults(self):
        """Khôi phục cấu hình về thiết lập mặc định tiêu chuẩn."""
        default_cfg = AudioEnhancementConfig()
        for k in self.__dataclass_fields__:
            setattr(self, k, getattr(default_cfg, k))


# =============================================================================
# CÁC PRESETS HỆ THỐNG CHUẨN (SYSTEM PRESETS)
# =============================================================================
SYSTEM_PRESETS: Dict[str, AudioEnhancementConfig] = {
    "clean_voice": AudioEnhancementConfig(
        preset_name="Giọng đọc sạch (Clean Voice)",
        bypass=False,
        enable_noise_reduction=False,
        enable_highpass=True,
        highpass_freq=80.0,
        enable_eq=True,
        bass_gain=0.5,
        eq_warmth_gain=1.0,
        eq_boxiness_gain=-1.0,
        eq_presence_gain=2.0,
        treble_gain=1.0,
        eq_air_gain=1.0,
        enable_deesser=True,
        deesser_threshold=-22.0,
        deesser_intensity=0.35,
        deesser_freq=6000.0,
        enable_compressor=True,
        compressor_threshold=-20.0,
        compressor_ratio=2.0,
        compressor_attack=25.0,
        compressor_release=200.0,
        compressor_makeup_gain=1.0,
        compressor_knee=3.0,
        enable_loudnorm=True,
        target_lufs=-16.0,
        loudness_range=7.0,
        true_peak=-1.5,
        enable_limiter=True,
        limiter_ceiling=-1.0,
    ),
    "studio_voice": AudioEnhancementConfig(
        preset_name="Phòng thu chuyên nghiệp (Studio Voice)",
        bypass=False,
        enable_noise_reduction=False,
        enable_highpass=True,
        highpass_freq=80.0,
        enable_eq=True,
        bass_gain=1.0,
        eq_warmth_gain=2.0,
        eq_boxiness_gain=-1.5,
        eq_presence_gain=3.0,
        treble_gain=1.5,
        eq_air_gain=2.0,
        enable_deesser=True,
        deesser_threshold=-20.0,
        deesser_intensity=0.45,
        deesser_freq=6200.0,
        enable_compressor=True,
        compressor_threshold=-18.0,
        compressor_ratio=2.8,
        compressor_attack=20.0,
        compressor_release=250.0,
        compressor_makeup_gain=1.5,
        compressor_knee=2.8,
        enable_loudnorm=True,
        target_lufs=-16.0,
        loudness_range=7.0,
        true_peak=-1.5,
        enable_limiter=True,
        limiter_ceiling=-1.0,
    ),
    "podcast": AudioEnhancementConfig(
        preset_name="Phòng thu Podcast (Podcast Voice)",
        bypass=False,
        enable_noise_reduction=True,
        noise_reduction_db=8.0,
        enable_highpass=True,
        highpass_freq=80.0,
        enable_eq=True,
        bass_gain=1.5,
        eq_warmth_gain=2.0,
        eq_boxiness_gain=-2.0,
        eq_presence_gain=3.0,
        treble_gain=1.5,
        eq_air_gain=2.5,
        enable_deesser=True,
        deesser_threshold=-20.0,
        deesser_intensity=0.5,
        deesser_freq=6500.0,
        enable_compressor=True,
        compressor_threshold=-20.0,
        compressor_ratio=3.0,
        compressor_attack=15.0,
        compressor_release=200.0,
        compressor_makeup_gain=2.0,
        compressor_knee=2.5,
        enable_loudnorm=True,
        target_lufs=-16.0,
        loudness_range=7.0,
        true_peak=-1.5,
        enable_limiter=True,
        limiter_ceiling=-1.0,
    ),
    "military_narration": AudioEnhancementConfig(
        preset_name="Thuyết minh Quân đội (Military Narration)",
        bypass=False,
        enable_noise_reduction=True,
        noise_reduction_db=10.0,
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
        enable_deesser=True,
        deesser_threshold=-18.0,
        deesser_intensity=0.4,
        deesser_freq=6000.0,
        enable_compressor=True,
        compressor_threshold=-18.0,
        compressor_ratio=3.2,
        compressor_attack=15.0,
        compressor_release=250.0,
        compressor_makeup_gain=2.0,
        compressor_knee=2.0,
        enable_loudnorm=True,
        target_lufs=-16.0,
        loudness_range=6.5,
        true_peak=-1.0,
        enable_limiter=True,
        limiter_ceiling=-1.0,
    ),
    "broadcast": AudioEnhancementConfig(
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
        enable_deesser=True,
        deesser_threshold=-22.0,
        deesser_intensity=0.4,
        deesser_freq=6000.0,
        enable_compressor=True,
        compressor_threshold=-22.0,
        compressor_ratio=2.5,
        compressor_attack=20.0,
        compressor_release=250.0,
        compressor_makeup_gain=1.0,
        compressor_knee=2.5,
        enable_loudnorm=True,
        target_lufs=-23.0,
        loudness_range=7.0,
        true_peak=-1.0,
        enable_limiter=True,
        limiter_ceiling=-1.0,
    ),
    "voice_bgm": AudioEnhancementConfig(
        preset_name="Giọng đọc kèm Nhạc nền (Voice + BGM)",
        bypass=False,
        enable_noise_reduction=False,
        enable_highpass=True,
        highpass_freq=100.0,     # Cắt trầm tránh xung đột với âm bass bài hát
        enable_eq=True,
        bass_gain=-1.0,
        eq_warmth_gain=0.5,
        eq_boxiness_gain=-2.5,   # Cắt nghẹt để nổi trên nền nhạc
        eq_presence_gain=4.0,    # Rõ chữ tiếng Việt vượt trội
        treble_gain=2.0,
        eq_air_gain=2.0,
        enable_deesser=True,
        deesser_threshold=-20.0,
        deesser_intensity=0.5,
        deesser_freq=6500.0,
        enable_compressor=True,
        compressor_threshold=-16.0,
        compressor_ratio=3.5,
        compressor_attack=10.0,
        compressor_release=150.0,
        compressor_makeup_gain=2.5,
        compressor_knee=2.0,
        enable_loudnorm=True,
        target_lufs=-16.0,
        loudness_range=6.0,
        true_peak=-1.5,
        enable_limiter=True,
        limiter_ceiling=-1.0,
    ),
}

# Ánh xạ tương thích ngược với các tên gọi Sprint 3
SYSTEM_PRESETS["voiceover_narrative"] = SYSTEM_PRESETS["studio_voice"]
SYSTEM_PRESETS["broadcast_military"] = SYSTEM_PRESETS["military_narration"]
SYSTEM_PRESETS["broadcast_standard_ebu"] = SYSTEM_PRESETS["broadcast"]
SYSTEM_PRESETS["podcast_studio"] = SYSTEM_PRESETS["podcast"]
SYSTEM_PRESETS["warm_narrative"] = AudioEnhancementConfig(
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
    enable_deesser=True,
    enable_compressor=True,
    compressor_threshold=-22.0,
    compressor_ratio=2.5,
    enable_loudnorm=True,
    target_lufs=-18.0,
    loudness_range=8.0,
    true_peak=-2.0,
    enable_limiter=True,
    limiter_ceiling=-1.5,
)
SYSTEM_PRESETS["outdoor_loudspeaker"] = AudioEnhancementConfig(
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
    enable_deesser=False,
    enable_compressor=True,
    compressor_threshold=-15.0,
    compressor_ratio=4.5,
    enable_loudnorm=True,
    target_lufs=-14.0,
    loudness_range=4.0,
    true_peak=-1.0,
    enable_limiter=True,
    limiter_ceiling=-0.8,
)

PRESETS: Dict[str, AudioEnhancementConfig] = dict(SYSTEM_PRESETS)


# =============================================================================
# CÁC PRESETS BỘ NÉN GIỌNG NÓI (COMPRESSOR PRESETS)
# =============================================================================
COMPRESSOR_PRESETS: Dict[str, Dict[str, float]] = {
    "gentle_voice": {
        "name": "Nén nhẹ tự nhiên (Gentle Voice)",
        "threshold": -22.0,
        "ratio": 2.0,
        "attack": 25.0,
        "release": 250.0,
        "makeup": 1.0,
        "knee": 3.0,
    },
    "narration": {
        "name": "Thuyết minh truyền cảm (Narration)",
        "threshold": -18.0,
        "ratio": 2.8,
        "attack": 20.0,
        "release": 250.0,
        "makeup": 1.5,
        "knee": 2.8,
    },
    "broadcast": {
        "name": "Phát thanh rõ chữ (Broadcast)",
        "threshold": -16.0,
        "ratio": 3.5,
        "attack": 12.0,
        "release": 200.0,
        "makeup": 2.5,
        "knee": 2.0,
    },
}


# =============================================================================
# BỘ QUẢN LÝ CẤU HÌNH PRESET TÙY CHỈNH (PRESET MANAGER)
# =============================================================================
class PresetManager:
    """Quản lý lưu, tải, chỉnh sửa, nhân bản, xuất nhập JSON các preset cấu hình âm thanh."""

    @classmethod
    def load_custom_presets(cls) -> Dict[str, AudioEnhancementConfig]:
        """Tải danh sách preset người dùng từ file JSON."""
        if not CUSTOM_PRESETS_FILE.is_file():
            return {}
        try:
            with open(CUSTOM_PRESETS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            presets = {}
            for k, v in data.items():
                cfg = AudioEnhancementConfig.from_dict(v)
                cfg.is_custom = True
                presets[k] = cfg
            return presets
        except Exception as e:
            logger.warning(f"Lỗi khi nạp preset người dùng: {e}")
            return {}

    @classmethod
    def save_custom_presets(cls, custom_dict: Dict[str, AudioEnhancementConfig]) -> bool:
        """Ghi danh sách preset tùy chỉnh ra đĩa."""
        try:
            CUSTOM_PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
            export_data = {k: v.to_dict() for k, v in custom_dict.items()}
            with open(CUSTOM_PRESETS_FILE, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Lỗi khi lưu preset tùy chỉnh: {e}")
            return False

    @classmethod
    def list_all_presets(cls) -> Dict[str, AudioEnhancementConfig]:
        """Liệt kê toàn bộ preset gồm cả System và Custom."""
        all_p = dict(SYSTEM_PRESETS)
        custom_p = cls.load_custom_presets()
        all_p.update(custom_p)
        return all_p

    @classmethod
    def save_preset(cls, name: str, config: AudioEnhancementConfig) -> Tuple[bool, str]:
        """Lưu hoặc cập nhật một preset người dùng (Tuyệt đối không ghi đè preset hệ thống)."""
        key = name.strip().lower().replace(" ", "_")
        if key in SYSTEM_PRESETS:
            return False, f"Không thể ghi đè lên cấu hình hệ thống chuẩn: '{name}'"

        customs = cls.load_custom_presets()
        cfg_copy = AudioEnhancementConfig.from_dict(config.to_dict())
        cfg_copy.preset_name = name.strip()
        cfg_copy.is_custom = True
        customs[key] = cfg_copy
        ok = cls.save_custom_presets(customs)
        if ok:
            PRESETS[key] = cfg_copy
            return True, f"Đã lưu cấu hình '{name}' thành công."
        return False, "Không thể lưu cấu hình vào đĩa."

    @classmethod
    def delete_preset(cls, key_or_name: str) -> Tuple[bool, str]:
        """Xóa preset tùy chỉnh (Chỉ cho phép xóa preset người dùng, bảo vệ preset hệ thống)."""
        key = key_or_name.strip().lower().replace(" ", "_")
        if key in SYSTEM_PRESETS:
            return False, f"Bảo vệ hệ thống: Không được phép xóa preset chuẩn '{key_or_name}'."

        customs = cls.load_custom_presets()
        if key not in customs:
            return False, f"Không tìm thấy cấu hình tùy chỉnh '{key_or_name}'."

        del customs[key]
        cls.save_custom_presets(customs)
        PRESETS.pop(key, None)
        return True, f"Đã xóa cấu hình tùy chỉnh '{key_or_name}' thành công."

    @classmethod
    def duplicate_preset(cls, source_key: str, new_name: str) -> Tuple[bool, str]:
        """Nhân bản một cấu hình có sẵn thành cấu hình tùy chỉnh mới."""
        all_p = cls.list_all_presets()
        src_k = source_key.strip().lower().replace(" ", "_")
        if src_k not in all_p:
            return False, f"Không tìm thấy cấu hình nguồn: '{source_key}'"

        src_cfg = all_p[src_k]
        return cls.save_preset(new_name, src_cfg)

    @classmethod
    def export_presets_json(cls, file_path: str | Path) -> Tuple[bool, str]:
        """Xuất toàn bộ preset tùy chỉnh ra tệp JSON dự phòng."""
        out_p = Path(file_path).resolve()
        try:
            customs = cls.load_custom_presets()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            export_data = {k: v.to_dict() for k, v in customs.items()}
            with open(out_p, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            return True, f"Đã xuất {len(customs)} cấu hình ra tệp: {out_p.name}"
        except Exception as e:
            return False, f"Lỗi xuất tệp JSON: {e}"

    @classmethod
    def import_presets_json(cls, file_path: str | Path) -> Tuple[bool, str]:
        """Nhập danh sách preset từ tệp JSON."""
        in_p = Path(file_path).resolve()
        if not in_p.is_file():
            return False, f"Không tìm thấy tệp JSON: {in_p}"
        try:
            with open(in_p, "r", encoding="utf-8") as f:
                data = json.load(f)
            customs = cls.load_custom_presets()
            imported_count = 0
            for k, v in data.items():
                if k not in SYSTEM_PRESETS:
                    cfg = AudioEnhancementConfig.from_dict(v)
                    cfg.is_custom = True
                    customs[k] = cfg
                    PRESETS[k] = cfg
                    imported_count += 1
            cls.save_custom_presets(customs)
            return True, f"Đã nhập thành công {imported_count} cấu hình mới."
        except Exception as e:
            return False, f"Lỗi nhập tệp JSON: {e}"


# Tải các preset tùy chỉnh sẵn có
PRESETS.update(PresetManager.load_custom_presets())


# =============================================================================
# XÂY DỰNG CHUỖI BỘ LỌC FFMPEG THEO PIPELINE THỨ TỰ (PIPELINE BUILDER)
# =============================================================================
def build_ffmpeg_filter_chain(config: AudioEnhancementConfig) -> List[str]:
    """Tạo chuỗi filter audio nối tiếp của FFmpeg theo thứ tự pipeline cấu hình:
    Mặc định: Noise Reduction → EQ → De-Esser → Compressor → LUFS → Limiter
    0. Master Bypass: Nếu bypass=True trả về chuỗi rỗng [].
    1. noise_reduction: High-pass rumble filter + afftdn + lowpass.
    2. eq: 6 dải EQ giọng nói tiếng Việt (100Hz, 250Hz, 600Hz, 3.5kHz, 8kHz, 10kHz).
    3. deesser: Bộ triệt tiêu âm xuýt (Threshold, Intensity, Frequency).
    4. compressor: Bộ nén động lực học (Threshold, Ratio, Attack, Release, Makeup, Knee).
    5. loudnorm: Chuẩn hóa âm lượng EBU R128 LUFS.
    6. limiter: Bộ trần biên độ an toàn alimiter.
    """
    if config.bypass:
        return []

    filters: List[str] = []
    order = config.pipeline_order or DEFAULT_PIPELINE_ORDER

    for proc in order:
        proc_name = proc.strip().lower()

        # 1. NOISE REDUCTION
        if proc_name == "noise_reduction":
            if (config.enable_highpass or config.enable_noise_reduction) and config.highpass_freq > 0:
                filters.append(f"highpass=f={int(config.highpass_freq)}")

            if config.enable_noise_reduction:
                nr = max(1.0, min(30.0, float(config.noise_reduction_db)))
                nf = min(-20.0, max(-80.0, float(config.noise_floor_db)))
                filters.append(f"afftdn=nr={nr:.1f}:nf={nf:.1f}:tn=1")

                if config.lowpass_freq < 20000:
                    filters.append(f"lowpass=f={int(config.lowpass_freq)}")

        # 2. VOICE CLARITY EQUALIZER (6 BANDS)
        elif proc_name == "eq":
            if config.enable_eq:
                # Bass (100 Hz): Trầm ấm
                if abs(config.bass_gain) > 0.05:
                    filters.append(f"equalizer=f=100:t=q:w=0.7:g={config.bass_gain:.1f}")

                # Warmth (250 Hz): Dầy giọng
                if abs(config.eq_warmth_gain) > 0.05:
                    filters.append(f"equalizer=f=250:t=q:w=1.0:g={config.eq_warmth_gain:.1f}")

                # Boxiness (600 Hz): Nghẹt tiếng
                if abs(config.eq_boxiness_gain) > 0.05:
                    filters.append(f"equalizer=f=600:t=q:w=1.2:g={config.eq_boxiness_gain:.1f}")

                # Presence (3500 Hz): Rõ chữ tiếng Việt
                if abs(config.eq_presence_gain) > 0.05:
                    filters.append(f"equalizer=f=3500:t=q:w=1.0:g={config.eq_presence_gain:.1f}")

                # Treble (8000 Hz): Sáng trong
                if abs(config.treble_gain) > 0.05:
                    filters.append(f"equalizer=f=8000:t=q:w=0.8:g={config.treble_gain:.1f}")

                # Air (10000 Hz): Thoáng không gian
                if abs(config.eq_air_gain) > 0.05:
                    filters.append(f"equalizer=f=10000:t=q:w=1.0:g={config.eq_air_gain:.1f}")

        # 3. DE-ESSER
        elif proc_name == "deesser":
            if config.enable_deesser:
                intensity = max(0.1, min(1.0, float(config.deesser_intensity)))
                # Chuẩn hóa tần số trung tâm vào khoảng [0.0, 1.0] cho filter deesser FFmpeg (3000Hz - 12000Hz)
                freq_hz = max(3000.0, min(12000.0, float(config.deesser_freq)))
                f_norm = (freq_hz - 3000.0) / 9000.0
                f_norm = max(0.0, min(1.0, f_norm))
                filters.append(f"deesser=i={intensity:.2f}:m=0.5:f={f_norm:.2f}:s=o")

        # 4. COMPRESSOR
        elif proc_name == "compressor":
            if config.enable_compressor:
                thresh = float(config.compressor_threshold)
                ratio = max(1.1, min(10.0, float(config.compressor_ratio)))
                atk = max(1.0, min(200.0, float(config.compressor_attack)))
                rel = max(10.0, min(1500.0, float(config.compressor_release)))
                makeup = max(0.0, min(12.0, float(config.compressor_makeup_gain)))
                knee = max(1.0, min(8.0, float(config.compressor_knee)))
                filters.append(
                    f"acompressor=threshold={thresh:.1f}dB:ratio={ratio:.1f}:attack={atk:.1f}:release={rel:.1f}:makeup={makeup:.1f}dB:knee={knee:.1f}dB"
                )

        # 5. EBU R128 LUFS LOUDNORM
        elif proc_name == "loudnorm":
            if config.enable_loudnorm:
                target_i = max(-30.0, min(-10.0, float(config.target_lufs)))
                lra = max(3.0, min(20.0, float(config.loudness_range)))
                tp = max(-5.0, min(-0.5, float(config.true_peak)))
                filters.append(f"loudnorm=I={target_i:.1f}:LRA={lra:.1f}:TP={tp:.1f}")

        # 6. FINAL LIMITER
        elif proc_name == "limiter":
            if config.enable_limiter:
                ceil = max(-3.0, min(-0.5, float(config.limiter_ceiling)))
                rel = max(10.0, min(200.0, float(config.limiter_release)))
                filters.append(f"alimiter=limit={ceil:.1f}dB:attack=5:release={rel:.1f}")

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
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Thực thi chuỗi xử lý âm thanh nâng cao (DSP) và xuất ra file mới.
        - Non-destructive: File nguồn không bao giờ bị ghi đè trực tiếp mà chưa kiểm tra.
        - Cancelable: Cho phép dừng tiến trình tức thì qua cancel_check callback.
        - Time Slice Preview: Hỗ trợ chỉ xử lý đoạn được chọn qua start_ms và end_ms.
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

        cfg = config or SYSTEM_PRESETS["clean_voice"]
        filters = build_ffmpeg_filter_chain(cfg)

        out_path.parent.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(10, "Đang cấu hình chuỗi bộ lọc âm thanh DSP...")

        # Xây dựng lệnh gọi FFmpeg
        cmd = [
            ffmpeg_exe,
            "-y",
            "-loglevel", "error",
        ]

        # Hỗ trợ cắt đoạn thời gian (Time Slice Preview)
        if start_ms is not None and start_ms > 0:
            cmd.extend(["-ss", f"{start_ms / 1000.0:.3f}"])
        if end_ms is not None and end_ms > (start_ms or 0):
            cmd.extend(["-to", f"{end_ms / 1000.0:.3f}"])

        cmd.extend(["-i", str(in_path)])

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
