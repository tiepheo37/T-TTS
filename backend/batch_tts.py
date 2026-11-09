"""backend/batch_tts.py — ĐỘNG CƠ TỔNG HỢP GIỌNG NÓI HÀNG LOẠT (PHASE 9.4 BATCH TTS)
=============================================================================
Động cơ tổng hợp giọng nói đa phân đoạn chuyên nghiệp cho T-TTS v3.1.0:
- Xử lý hàng loạt theo từng khối (Chunk / Segment) của tài liệu văn bản.
- Theo dõi tiến trình thực tế, ước tính thời gian hoàn thành (ETA).
- Hỗ trợ Tạm dừng (Pause), Tiếp tục (Resume), Hủy ngang (Cancel) và Thử lại (Retry) phân đoạn lỗi.
- Tự động ghép nối các phân đoạn thành tệp âm thanh hoàn chỉnh với khoảng lặng tùy chỉnh.
"""

from __future__ import annotations

import os
import time
import uuid
import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydub import AudioSegment

from .service import tts_service
from .audio_utils import load_audio_segment_safe, save_wav, wav_to_mp3
from .project_manager import project_manager

logger = logging.getLogger("T-TTS.BatchTTS")


class BatchTTSEngine:
    """Động cơ điều phối tổng hợp giọng nói hàng loạt cho các dự án tài liệu."""

    def __init__(self):
        self._is_paused = False
        self._is_cancelled = False
        self._lock = threading.Lock()

    def pause(self):
        with self._lock:
            self._is_paused = True

    def resume(self):
        with self._lock:
            self._is_paused = False

    def cancel(self):
        with self._lock:
            self._is_cancelled = True

    def is_paused(self) -> bool:
        with self._lock:
            return self._is_paused

    def is_cancelled(self) -> bool:
        with self._lock:
            return self._is_cancelled

    def process_project_segments(
        self,
        project_dict: Dict[str, Any],
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int, str, float], None]] = None,
        segment_callback: Optional[Callable[[int, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Tổng hợp toàn bộ các phân đoạn trong dự án tài liệu."""
        self._is_paused = False
        self._is_cancelled = False

        data = project_dict.get("data", {})
        segments = data.get("segments", [])
        total = len(segments)
        if total == 0:
            return {"success": False, "error": "Dự án không có phân đoạn văn bản nào để xử lý."}

        target_dir = Path(output_dir or tts_service.default_out_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        voice_id = data.get("voice_id", "v-nam-1")
        speed = float(data.get("speed", 1.0))
        fmt = data.get("format", "wav").lower()

        start_time = time.time()
        completed = 0

        for idx, seg in enumerate(segments):
            # Kiểm tra cờ hủy
            if self.is_cancelled():
                return {
                    "success": False,
                    "cancelled": True,
                    "completed_segments": completed,
                    "total_segments": total,
                    "error": "Người dùng đã hủy tiến trình tổng hợp hàng loạt.",
                }

            # Kiểm tra trạng thái tạm dừng
            while self.is_paused() and not self.is_cancelled():
                time.sleep(0.3)

            if self.is_cancelled():
                return {
                    "success": False,
                    "cancelled": True,
                    "completed_segments": completed,
                    "total_segments": total,
                    "error": "Người dùng đã hủy tiến trình tổng hợp hàng loạt.",
                }

            text = seg.get("text", "").strip()
            if not text:
                seg["status"] = "completed"
                continue

            # Nếu phân đoạn đã hoàn thành trước đó (ví dụ sau resume), bỏ qua
            if seg.get("status") == "completed" and seg.get("audio_path") and Path(seg["audio_path"]).is_file():
                completed += 1
                continue

            seg["status"] = "synthesizing"
            if progress_callback:
                elapsed = time.time() - start_time
                avg_time = elapsed / max(1, completed)
                eta = (total - completed) * avg_time
                progress_callback(completed, total, f"Đang đọc đoạn {idx+1}/{total}...", eta)

            try:
                # Gọi tổng hợp âm thanh bằng VieNeu-TTS
                res = tts_service.synthesize(
                    text=text,
                    voice_id=seg.get("voice_id") or voice_id,
                    speed=float(seg.get("speed") or speed),
                    out_format="wav",
                )

                if res.get("success"):
                    src_file = res.get("file_path") or res.get("main_file")
                    dur = float(res.get("duration", 0.0))

                    # Lưu ra vị trí quản lý của project
                    dest_file = target_dir / f"{project_dict.get('id', 'doc')}_seg_{idx+1:03d}.wav"
                    if src_file and Path(src_file).is_file():
                        import shutil
                        shutil.copy2(src_file, dest_file)
                        seg["audio_path"] = str(dest_file)
                    else:
                        seg["audio_path"] = src_file

                    seg["duration"] = dur
                    seg["status"] = "completed"
                    seg["error"] = None
                    completed += 1
                else:
                    seg["status"] = "error"
                    seg["error"] = res.get("error", "Lỗi tạo giọng VieNeu-TTS.")

            except Exception as e:
                seg["status"] = "error"
                seg["error"] = str(e)

            if segment_callback:
                segment_callback(idx, seg)

        # Cập nhật số lượng hoàn thành vào project
        data["completed_segments"] = completed

        # Tự động ghép nối các phân đoạn thành tệp âm thanh hoàn chỉnh
        merged_path = self.stitch_project_audio(project_dict, target_dir / f"{project_dict.get('id', 'doc')}_full.{fmt}")
        data["merged_audio_path"] = str(merged_path) if merged_path else None

        # Lưu lại project
        project_manager.save_document_project(project_dict)

        return {
            "success": (completed == total),
            "completed_segments": completed,
            "total_segments": total,
            "merged_audio_path": str(merged_path) if merged_path else None,
            "error": None if completed == total else f"Có {total - completed} phân đoạn bị lỗi.",
        }

    def retry_segment(self, project_dict: Dict[str, Any], seg_index: int) -> bool:
        """Thử lại một phân đoạn cụ thể bị lỗi."""
        data = project_dict.get("data", {})
        segments = data.get("segments", [])
        if not (0 <= seg_index < len(segments)):
            return False

        seg = segments[seg_index]
        text = seg.get("text", "").strip()
        voice_id = seg.get("voice_id") or data.get("voice_id", "v-nam-1")
        speed = float(seg.get("speed") or data.get("speed", 1.0))

        try:
            res = tts_service.synthesize(text=text, voice_id=voice_id, speed=speed, out_format="wav")
            if res.get("success"):
                seg["audio_path"] = res.get("file_path") or res.get("main_file")
                seg["duration"] = float(res.get("duration", 0.0))
                seg["status"] = "completed"
                seg["error"] = None
                project_manager.save_document_project(project_dict)
                return True
            else:
                seg["status"] = "error"
                seg["error"] = res.get("error")
                return False
        except Exception as e:
            seg["status"] = "error"
            seg["error"] = str(e)
            return False

    def stitch_project_audio(
        self,
        project_dict: Dict[str, Any],
        output_file: Path,
        pause_ms: int = 500,
    ) -> Optional[Path]:
        """Ghép nối tất cả các phân đoạn đã hoàn thành thành 1 file âm thanh tổng thể."""
        data = project_dict.get("data", {})
        segments = data.get("segments", [])

        silence = AudioSegment.silent(duration=pause_ms, frame_rate=48000)
        master: Optional[AudioSegment] = None

        for seg in segments:
            if seg.get("status") == "completed" and seg.get("audio_path"):
                p = Path(seg["audio_path"])
                if p.is_file():
                    clip = load_audio_segment_safe(p)
                    if clip.frame_rate != 48000:
                        clip = clip.set_frame_rate(48000)
                    if clip.channels != 1:
                        clip = clip.set_channels(1)

                    if master is None:
                        master = clip
                    else:
                        master = master + silence + clip

        if master is not None and len(master) > 0:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            fmt = output_file.suffix.lstrip(".").lower()
            if fmt == "mp3":
                temp_wav = output_file.with_suffix(".wav")
                master.export(str(temp_wav), format="wav")
                wav_to_mp3(temp_wav, output_file)
                temp_wav.unlink(missing_ok=True)
            else:
                master.export(str(output_file), format="wav")
            return output_file

        return None


batch_tts_engine = BatchTTSEngine()
