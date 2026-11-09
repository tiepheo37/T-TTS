"""backend/intelligent_audio.py — HỆ THỐNG PHÂN TÍCH & TỐI ƯU ÂM THANH THÔNG MINH (PHASE 9)
=======================================================================================
Cung cấp bộ máy phân tích và tối ưu hóa âm thanh thông minh:
- 9.1 Intelligent Voice Enhancement: Đánh giá chất lượng âm thanh, tự động đề xuất preset và thông số EQ/Compressor/LUFS.
- 9.2 Voice Quality Analyzer: Phân tích Integrated LUFS, True Peak, RMS, Dynamic Range, Clipping, Noise Level, Silence Ratio, Duration.
- 9.3 Smart Audio Cleanup: Phát hiện khoảng lặng thừa, clipping, đoạn âm lượng bất thường, đề xuất xử lý non-destructive.
- 9.4 Intelligent Audio Presets: Tự động phân loại và gợi ý preset tối ưu theo đặc tính âm học.
- 9.5 Smart Broadcast Mixing: Phân tích tỷ lệ âm lượng Giọng đọc vs Nhạc nền, đề xuất mức âm lượng cân bằng và Ducking tối ưu.
Hoạt động 100% offline, CPU-first, không làm thay đổi VieNeu-TTS v3 Turbo ONNX.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from pydub import AudioSegment

from .audio_enhancement import (
    AudioEnhancementConfig,
    SYSTEM_PRESETS,
    audio_enhancement_engine,
)
from .audio_utils import load_audio_segment_safe, save_wav, get_audio_duration_safe
from .ffmpeg_bootstrap import get_ffmpeg_path, initialize_ffmpeg, is_ffmpeg_ready

logger = logging.getLogger("T-TTS.IntelligentAudio")


# =============================================================================
# DỮ LIỆU ĐO ĐẠC CHẤT LƯỢNG ÂM THANH (VOICE QUALITY METRICS)
# =============================================================================
@dataclass
class VoiceQualityMetrics:
    file_path: str
    duration_sec: float = 0.0
    sample_rate: int = 48000
    channels: int = 1

    # Dải động & Mức âm lượng
    integrated_lufs: float = -24.0         # Chuẩn EBU R128 (LUFS)
    true_peak_dbfs: float = -3.0           # Biên độ đỉnh thực tế (dBFS)
    rms_dbfs: float = -20.0                # Mức năng lượng hiệu dụng trung bình (dBFS)
    dynamic_range_lu: float = 6.0          # Loudness Range (LU)
    crest_factor_db: float = 12.0          # Peak - RMS (dB)

    # Lỗi âm thanh & Tạp âm
    clipping_detected: bool = False        # Phát hiện vỡ âm / clipping
    clipping_count: int = 0                # Số lượng mẫu đạt ngưỡng xấp xỉ 0 dBFS
    noise_level_dbfs: float = -60.0        # Ngưỡng sàn nhiễu ước lượng (dBFS)

    # Khoảng lặng (Silence)
    silence_duration_sec: float = 0.0      # Tổng thời gian im lặng
    silence_ratio_pct: float = 0.0         # Tỷ lệ % khoảng lặng
    leading_silence_sec: float = 0.0       # Khoảng lặng đầu tệp
    trailing_silence_sec: float = 0.0      # Khoảng lặng cuối tệp

    # Đánh giá tổng thể
    quality_score: int = 80                # Điểm số 0 - 100
    quality_grade: str = "Đạt chuẩn (Broadcast Ready)"
    issues_found: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# BỘ PHÂN TÍCH CHẤT LƯỢNG GIỌNG NÓI (VOICE QUALITY ANALYZER - 9.2)
# =============================================================================
class VoiceQualityAnalyzer:
    """Đo lường các chỉ số âm học chuyên sâu: LUFS, True Peak, RMS, Noise, Silence, Clipping."""

    @classmethod
    def analyze_file(cls, file_path: str | Path) -> VoiceQualityMetrics:
        """Phân tích toàn diện chất lượng tệp âm thanh đầu vào."""
        fpath = Path(file_path).resolve()
        if not fpath.is_file():
            return VoiceQualityMetrics(
                file_path=str(fpath),
                quality_score=0,
                quality_grade="Không khả dụng",
                issues_found=["Không tìm thấy tệp âm thanh nguồn."],
            )

        initialize_ffmpeg()
        seg = load_audio_segment_safe(fpath)
        if seg is None or len(seg) == 0:
            return VoiceQualityMetrics(
                file_path=str(fpath),
                quality_score=0,
                quality_grade="Tệp rỗng",
                issues_found=["Tệp âm thanh rỗng hoặc không thể giải mã."],
            )

        duration_sec = len(seg) / 1000.0
        sr = seg.frame_rate
        channels = seg.channels

        # 1. Đo Integrated LUFS và True Peak qua EBU R128 FFmpeg
        lufs_res = audio_enhancement_engine.measure_loudness(fpath)
        int_lufs = lufs_res.get("integrated_lufs") or -24.0
        true_peak = lufs_res.get("true_peak_dbfs") or -3.0
        lra = lufs_res.get("loudness_range_lu") or 6.0

        # 2. Phân tích dữ liệu sóng âm qua NumPy
        samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
        if channels > 1:
            # Thu về mono trung bình nếu tệp stereo
            samples = samples.reshape((-1, channels)).mean(axis=1)

        # Biên độ đỉnh và RMS
        max_sample = np.max(np.abs(samples)) if len(samples) > 0 else 1.0
        peak_norm = max_sample / 32768.0
        peak_dbfs = 20.0 * math.log10(max(1e-6, peak_norm))

        rms_norm = np.sqrt(np.mean(samples**2)) / 32768.0 if len(samples) > 0 else 1e-4
        rms_dbfs = 20.0 * math.log10(max(1e-6, rms_norm))
        crest_factor = peak_dbfs - rms_dbfs

        # 3. Phát hiện Clipping (Mẫu đạt hoặc vượt 32700 / 32767)
        clip_mask = np.abs(samples) >= 32700
        clipping_count = int(np.sum(clip_mask))
        clipping_detected = clipping_count > 5 or true_peak > -0.3

        # 4. Phân tích khung thời gian (Frame Analysis: 50ms) tính Noise Floor & Silence
        frame_len = max(1, int(0.05 * sr))
        n_frames = len(samples) // frame_len
        frame_energies_db = []

        for i in range(n_frames):
            sub = samples[i * frame_len : (i + 1) * frame_len]
            rms_f = np.sqrt(np.mean(sub**2)) / 32768.0
            frame_energies_db.append(20.0 * math.log10(max(1e-6, rms_f)))

        frame_dbs = np.array(frame_energies_db) if frame_energies_db else np.array([-60.0])

        # Ngưỡng sàn nhiễu: Phân vị thứ 10 của các khung
        noise_floor_db = float(np.percentile(frame_dbs, 10))

        # Phân tích khoảng lặng (Ngưỡng im lặng: -45 dBFS)
        silence_thresh = -45.0
        silence_mask = frame_dbs < silence_thresh
        silence_frames_count = int(np.sum(silence_mask))
        silence_duration = silence_frames_count * 0.05
        silence_ratio = (silence_duration / max(0.01, duration_sec)) * 100.0

        # Khoảng lặng đầu (leading) và cuối (trailing)
        lead_frames = 0
        for val in frame_dbs:
            if val < silence_thresh:
                lead_frames += 1
            else:
                break
        leading_silence = lead_frames * 0.05

        trail_frames = 0
        for val in reversed(frame_dbs):
            if val < silence_thresh:
                trail_frames += 1
            else:
                break
        trailing_silence = trail_frames * 0.05

        # 5. Đánh giá chất lượng và phát hiện vấn đề
        issues = []
        score = 100

        # Trừ điểm clipping
        if clipping_detected:
            score -= 25
            issues.append(f"Phát hiện méo tiếng / clipping ({clipping_count} mẫu vượt trần).")

        # Trừ điểm sàn nhiễu cao
        if noise_floor_db > -42.0:
            score -= 20
            issues.append(f"Sàn nhiễu nền cao ({noise_floor_db:.1f} dBFS), có tạp âm.")
        elif noise_floor_db > -48.0:
            score -= 10
            issues.append(f"Nhiễu nền nhẹ ({noise_floor_db:.1f} dBFS).")

        # Trừ điểm âm lượng không đạt chuẩn
        if int_lufs < -26.0:
            score -= 15
            issues.append(f"Âm lượng quá nhỏ ({int_lufs:.1f} LUFS), cần khuếch đại.")
        elif int_lufs > -12.0:
            score -= 15
            issues.append(f"Âm lượng quá lớn ({int_lufs:.1f} LUFS), có nguy cơ vỡ loa.")

        # Trừ điểm khoảng lặng bất thường
        if leading_silence > 1.2:
            score -= 5
            issues.append(f"Khoảng lặng đầu tệp dài ({leading_silence:.2f}s).")
        if trailing_silence > 1.5:
            score -= 5
            issues.append(f"Khoảng lặng cuối tệp dài ({trailing_silence:.2f}s).")
        if silence_ratio > 35.0:
            score -= 10
            issues.append(f"Tỷ lệ khoảng lặng lớn ({silence_ratio:.1f}% thời lượng).")

        # Trừ điểm dải động quá gắt
        if crest_factor > 18.0:
            score -= 10
            issues.append(f"Dải động gắt, biên độ không đều (Crest Factor: {crest_factor:.1f} dB).")

        score = max(10, min(100, score))

        if score >= 85:
            grade = "Xuất sắc (Studio Grade)"
        elif score >= 70:
            grade = "Đạt chuẩn (Broadcast Ready)"
        elif score >= 50:
            grade = "Cần xử lý (Needs Enhancement)"
        else:
            grade = "Kém (Sub-optimal / Noisy)"

        return VoiceQualityMetrics(
            file_path=str(fpath),
            duration_sec=duration_sec,
            sample_rate=sr,
            channels=channels,
            integrated_lufs=int_lufs,
            true_peak_dbfs=true_peak,
            rms_dbfs=rms_dbfs,
            dynamic_range_lu=lra,
            crest_factor_db=crest_factor,
            clipping_detected=clipping_detected,
            clipping_count=clipping_count,
            noise_level_dbfs=noise_floor_db,
            silence_duration_sec=silence_duration,
            silence_ratio_pct=silence_ratio,
            leading_silence_sec=leading_silence,
            trailing_silence_sec=trailing_silence,
            quality_score=score,
            quality_grade=grade,
            issues_found=issues,
        )


# =============================================================================
# BỘ TỐI ƯU & GỢI Ý THÔNG MINH (INTELLIGENT ENHANCER & PRESETS - 9.1 & 9.4)
# =============================================================================
class IntelligentVoiceEnhancer:
    """Phân tích số đo âm học và đưa ra khuyến nghị cấu hình DSP tối ưu cá nhân hóa."""

    @classmethod
    def evaluate_and_recommend(cls, metrics: VoiceQualityMetrics) -> Dict[str, Any]:
        """Tự động phân tích và tạo cấu hình khuyến nghị dựa trên số đo âm học thực tế."""
        recs: List[str] = []
        cleanup_tips: List[str] = []

        # 1. Lựa chọn preset mẫu phù hợp nhất
        if metrics.noise_level_dbfs > -46.0:
            best_preset = "military_narration"
            explanation = "Âm thanh có sàn nhiễu cao; khuyến nghị áp dụng bộ lọc giảm nhiễu thích ứng afftdn và cắt tần số thấp."
        elif metrics.clipping_detected or metrics.crest_factor_db > 16.0:
            best_preset = "podcast"
            explanation = "Âm thanh có dải động rộng hoặc gần ngưỡng vỡ tiếng; khuyến nghị áp dụng Dynamic Compressor và Limiter bảo vệ."
        elif metrics.integrated_lufs < -22.0:
            best_preset = "studio_voice"
            explanation = "Âm thanh có âm lượng nhỏ; khuyến nghị chuẩn hóa âm lượng EBU R128 về -16 LUFS và làm ấm giọng."
        else:
            best_preset = "clean_voice"
            explanation = "Âm thanh có chất lượng đầu vào sạch; khuyến nghị tinh chỉnh nhẹ EQ và bảo vệ trần True Peak."

        # 2. Xây dựng cấu hình tùy chỉnh chính xác dựa trên từng lỗi phát hiện
        base_cfg = SYSTEM_PRESETS.get(best_preset, SYSTEM_PRESETS["clean_voice"])
        suggested_cfg = AudioEnhancementConfig.from_dict(base_cfg.to_dict())

        # Điều chỉnh giảm nhiễu thông minh
        if metrics.noise_level_dbfs > -45.0:
            suggested_cfg.enable_noise_reduction = True
            # Mức giảm tỷ lệ với độ lớn của nhiễu
            calc_nr = min(22.0, max(8.0, (-40.0 - metrics.noise_level_dbfs) * 1.5 + 8.0))
            suggested_cfg.noise_reduction_db = float(round(calc_nr, 1))
            suggested_cfg.noise_floor_db = float(round(metrics.noise_level_dbfs, 1))
            recs.append(f"Kích hoạt giảm nhiễu thích ứng {suggested_cfg.noise_reduction_db} dB.")
        else:
            suggested_cfg.enable_noise_reduction = False

        # Điều chỉnh Compressor & Limiter nếu dải động rộng hoặc có nguy cơ clipping
        if metrics.clipping_detected:
            suggested_cfg.enable_limiter = True
            suggested_cfg.limiter_ceiling = -1.5
            recs.append("Kích hoạt Limiter với mức trần an toàn -1.5 dBFS để chặn vỡ âm.")

        if metrics.crest_factor_db > 15.0:
            suggested_cfg.enable_compressor = True
            suggested_cfg.compressor_ratio = 3.2
            suggested_cfg.compressor_makeup_gain = 2.0
            recs.append("Kích hoạt Compressor tỷ lệ 3.2:1 để nén cân bằng giọng nói.")

        # Điều chỉnh LUFS
        suggested_cfg.enable_loudnorm = True
        suggested_cfg.target_lufs = -16.0
        recs.append("Chuẩn hóa độ to theo tiêu chuẩn phát thanh -16.0 LUFS.")

        # Gợi ý làm sạch khoảng lặng thừa
        if metrics.leading_silence_sec > 1.0:
            cleanup_tips.append(f"Cắt bớt khoảng lặng đầu thừa ({metrics.leading_silence_sec:.2f}s).")
        if metrics.trailing_silence_sec > 1.2:
            cleanup_tips.append(f"Cắt bớt khoảng lặng cuối thừa ({metrics.trailing_silence_sec:.2f}s).")

        return {
            "recommended_preset_key": best_preset,
            "recommended_preset_name": base_cfg.preset_name,
            "explanation": explanation,
            "suggested_config": suggested_cfg,
            "tuning_recommendations": recs,
            "cleanup_suggestions": cleanup_tips,
        }


# =============================================================================
# BỘ LÀM SẠCH ÂM THANH THÔNG MINH (SMART AUDIO CLEANUP - 9.3)
# =============================================================================
class SmartAudioCleanup:
    """Phát hiện và loại bỏ các lỗi cơ học: khoảng lặng thừa, cắt gọt an toàn non-destructive."""

    @classmethod
    def detect_cleanup_actions(cls, file_path: str | Path) -> Dict[str, Any]:
        """Phát hiện các điểm cần làm sạch mà không làm thay đổi nội dung âm thanh gốc."""
        metrics = VoiceQualityAnalyzer.analyze_file(file_path)
        actions = []

        should_trim_lead = metrics.leading_silence_sec > 0.6
        should_trim_trail = metrics.trailing_silence_sec > 0.8
        should_repair_clip = metrics.clipping_detected

        if should_trim_lead:
            actions.append({
                "type": "trim_leading",
                "label": f"Cắt bớt khoảng lặng đầu: {metrics.leading_silence_sec:.2f}s",
                "start_trim_ms": int(max(0.0, metrics.leading_silence_sec - 0.2) * 1000),
            })

        if should_trim_trail:
            actions.append({
                "type": "trim_trailing",
                "label": f"Cắt bớt khoảng lặng cuối: {metrics.trailing_silence_sec:.2f}s",
                "end_trim_ms": int(max(0.0, metrics.duration_sec - metrics.trailing_silence_sec + 0.3) * 1000),
            })

        if should_repair_clip:
            actions.append({
                "type": "declip_limiter",
                "label": "Áp dụng Limiter trần -1.5 dBFS để kiểm soát méo tiếng",
            })

        return {
            "file_path": str(file_path),
            "duration_sec": metrics.duration_sec,
            "actions_suggested": actions,
            "has_suggestions": len(actions) > 0,
        }

    @classmethod
    def apply_cleanup(
        cls,
        input_file: str | Path,
        output_file: str | Path,
        trim_leading: bool = True,
        trim_trailing: bool = True,
        keep_margin_ms: int = 200,
    ) -> Dict[str, Any]:
        """Thực hiện làm sạch âm thanh xuất ra file mới (Non-destructive)."""
        in_p = Path(input_file).resolve()
        out_p = Path(output_file).resolve()
        if not in_p.is_file():
            return {"success": False, "error": f"Không tìm thấy tệp: {in_p}"}

        seg = load_audio_segment_safe(in_p)
        if seg is None or len(seg) == 0:
            return {"success": False, "error": "Không thể nạp tệp âm thanh."}

        metrics = VoiceQualityAnalyzer.analyze_file(in_p)
        start_ms = 0
        end_ms = len(seg)

        if trim_leading and metrics.leading_silence_sec > 0.5:
            cut_sec = max(0.0, metrics.leading_silence_sec - (keep_margin_ms / 1000.0))
            start_ms = int(cut_sec * 1000)

        if trim_trailing and metrics.trailing_silence_sec > 0.6:
            cut_sec = max(0.0, metrics.trailing_silence_sec - (keep_margin_ms / 1000.0))
            end_ms = len(seg) - int(cut_sec * 1000)

        if start_ms >= end_ms:
            # An toàn: Tránh cắt nhầm toàn bộ file
            start_ms = 0
            end_ms = len(seg)

        cleaned_seg = seg[start_ms:end_ms]

        # Fade in/out siêu êm 10ms để tránh click/pop
        cleaned_seg = cleaned_seg.fade_in(15).fade_out(25)

        out_p.parent.mkdir(parents=True, exist_ok=True)
        fmt = "mp3" if out_p.suffix.lower() == ".mp3" else "wav"
        cleaned_seg.export(str(out_p), format=fmt)

        return {
            "success": True,
            "input_file": str(in_p),
            "output_file": str(out_p),
            "original_duration_ms": len(seg),
            "cleaned_duration_ms": len(cleaned_seg),
            "trimmed_leading_ms": start_ms,
            "trimmed_trailing_ms": len(seg) - end_ms,
        }


# =============================================================================
# TRỘN PHÁT THANH THÔNG MINH (SMART BROADCAST MIXING - 9.5)
# =============================================================================
class SmartBroadcastMixer:
    """Phân tích cân bằng giọng đọc và nhạc nền, tối ưu hóa Auto-Ducking và âm lượng."""

    @classmethod
    def analyze_mix_balance(
        cls,
        voice_file: str | Path,
        bgm_file: str | Path,
    ) -> Dict[str, Any]:
        """Phân tích mức âm lượng giữa lời đọc và bài hát nền, tính toán độ lệch dB hoàn hảo."""
        v_path = Path(voice_file).resolve()
        b_path = Path(bgm_file).resolve()

        if not v_path.is_file():
            return {"success": False, "error": f"Không tìm thấy tệp giọng đọc: {v_path}"}
        if not b_path.is_file():
            return {"success": False, "error": f"Không tìm thấy tệp nhạc nền: {b_path}"}

        v_metrics = VoiceQualityAnalyzer.analyze_file(v_path)
        b_metrics = VoiceQualityAnalyzer.analyze_file(b_path)

        # Mức năng lượng RMS
        v_rms = v_metrics.rms_dbfs
        b_rms = b_metrics.rms_dbfs

        # Khoảng cách lý tưởng: Nhạc nền khi phát cùng giọng đọc nên nhỏ hơn giọng đọc từ -18 đến -22 dB
        target_diff = -20.0
        # Mức tăng giảm dB cần áp dụng cho BGM
        desired_bgm_rms = v_rms + target_diff
        suggested_volume_db = round(desired_bgm_rms - b_rms, 1)

        # Giới hạn trong khoảng an toàn [-32 dB, -10 dB]
        suggested_volume_db = max(-32.0, min(-10.0, suggested_volume_db))

        # Đề xuất thông số Ducking
        ducking_attenuation_db = -14.0       # Giảm thêm 14 dB khi có lời đọc
        ducking_attack_ms = 150             # Thời gian hạ nhạc mượt mà
        ducking_release_ms = 500            # Thời gian nhả nhạc tự nhiên

        return {
            "success": True,
            "voice_file": str(v_path),
            "bgm_file": str(b_path),
            "voice_rms_dbfs": round(v_rms, 1),
            "bgm_rms_dbfs": round(b_rms, 1),
            "voice_lufs": round(v_metrics.integrated_lufs, 1),
            "suggested_bgm_volume_db": suggested_volume_db,
            "ducking_attenuation_db": ducking_attenuation_db,
            "ducking_attack_ms": ducking_attack_ms,
            "ducking_release_ms": ducking_release_ms,
            "recommended_target_lufs": -16.0,
            "recommended_limiter_ceiling": -1.0,
            "explanation": f"Giọng đọc ở mức {v_rms:.1f} dBFS, nhạc nền ở mức {b_rms:.1f} dBFS. Đề xuất cân chỉnh nhạc nền ở mức {suggested_volume_db:+.1f} dB và tự động hạ thêm {ducking_attenuation_db:.0f} dB khi đọc.",
        }


# Khởi tạo singleton dùng chung
voice_quality_analyzer = VoiceQualityAnalyzer()
intelligent_voice_enhancer = IntelligentVoiceEnhancer()
smart_audio_cleanup = SmartAudioCleanup()
smart_broadcast_mixer = SmartBroadcastMixer()
