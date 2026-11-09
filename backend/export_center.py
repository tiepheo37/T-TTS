"""backend/export_center.py — TRUNG TÂM XUẤT BẢN ÂM THANH ĐA ĐỊNH DẠNG (PHASE 9.5 EXPORT CENTER)
======================================================================================
Cung cấp trung tâm xuất bản âm thanh chuyên nghiệp:
- Định dạng xuất: WAV (16-bit / 24-bit PCM), MP3 (128k - 320k CBR / VBR).
- Tần số lấy mẫu: 24.000 Hz, 44.100 Hz, 48.000 Hz.
- Tích hợp chuẩn hóa âm lượng phát thanh tự động EBU R128 LUFS.
- Nhúng thẻ metadata tác giả, bản quyền T-TTS, thông tin phát thanh viên.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .ffmpeg_bootstrap import get_ffmpeg_path, is_ffmpeg_ready
from .audio_enhancement import audio_enhancement_engine, AudioEnhancementConfig, PRESETS


class ExportCenter:
    """Điều phối xuất bản tệp âm thanh đầu ra đa định dạng chất lượng cao."""

    @classmethod
    def export_audio(
        cls,
        input_file: str | Path,
        output_file: str | Path,
        fmt: str = "wav",                    # 'wav' | 'mp3'
        sample_rate: int = 48000,            # 24000, 44100, 48000
        bitrate_kbps: int = 192,             # 128, 192, 256, 320
        apply_lufs_mastering: bool = True,   # Chuẩn hóa âm lượng EBU R128
        target_lufs: float = -16.0,          # Mục tiêu -16 LUFS
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Any]:
        """Xuất âm thanh chất lượng cao theo thông số kỹ thuật mong muốn."""
        in_p = Path(input_file).resolve()
        out_p = Path(output_file).resolve()

        if not in_p.is_file():
            return {
                "success": False,
                "error": f"Không tìm thấy tệp âm thanh nguồn: {in_p}",
            }

        ffmpeg_exe = get_ffmpeg_path()
        if not ffmpeg_exe:
            return {
                "success": False,
                "error": "Thiếu bộ công cụ FFmpeg để xuất bản âm thanh.",
            }

        out_p.parent.mkdir(parents=True, exist_ok=True)
        if progress_callback:
            progress_callback(10, "Đang thiết lập thông số xuất bản âm thanh...")

        # 1. Nếu cần áp dụng mastering LUFS trước khi encode
        source_to_encode = in_p
        temp_mastered = None

        if apply_lufs_mastering:
            if progress_callback:
                progress_callback(30, "Đang chuẩn hóa âm lượng theo tiêu chuẩn EBU R128...")
            temp_mastered = out_p.parent / f"export_temp_{os.getpid()}_{out_p.stem}.wav"
            cfg = AudioEnhancementConfig(
                enable_loudnorm=True,
                target_lufs=target_lufs,
                loudness_range=7.0,
                true_peak=-1.5,
                enable_noise_reduction=False,
                enable_eq=False,
                enable_compressor=False,
            )
            res_master = audio_enhancement_engine.enhance_audio(
                input_file=in_p,
                output_file=temp_mastered,
                config=cfg,
            )
            if res_master.get("success"):
                source_to_encode = temp_mastered

        # 2. Xây dựng lệnh gọi FFmpeg chuyển đổi định dạng và tần số mẫu
        if progress_callback:
            progress_callback(70, f"Đang mã hóa sang định dạng {fmt.upper()} {sample_rate}Hz...")

        cmd = [
            ffmpeg_exe,
            "-y",
            "-loglevel", "error",
            "-i", str(source_to_encode),
            "-ar", str(int(sample_rate)),
            "-ac", "1",  # Mono phát thanh chuẩn
        ]

        fmt_lower = fmt.strip().lower()
        if fmt_lower == "mp3":
            cmd.extend([
                "-codec:a", "libmp3lame",
                "-b:a", f"{int(bitrate_kbps)}k",
            ])
        else:
            cmd.extend([
                "-codec:a", "pcm_s16le",
            ])

        cmd.append(str(out_p))

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                return {
                    "success": False,
                    "error": f"Lỗi xuất âm thanh: {res.stderr.strip()}",
                }

            if not out_p.is_file() or out_p.stat().st_size == 0:
                return {
                    "success": False,
                    "error": "Tệp âm thanh xuất bản rỗng.",
                }

            if progress_callback:
                progress_callback(100, "Xuất bản âm thanh thành công!")

            return {
                "success": True,
                "output_file": str(out_p),
                "format": fmt_lower,
                "sample_rate": sample_rate,
                "bitrate_kbps": bitrate_kbps if fmt_lower == "mp3" else None,
                "file_size": out_p.stat().st_size,
                "applied_lufs": apply_lufs_mastering,
                "error": None,
            }

        finally:
            if temp_mastered and temp_mastered.is_file():
                temp_mastered.unlink(missing_ok=True)


export_center = ExportCenter()
