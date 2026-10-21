"""backend/service.py — LỚP DỊCH VỤ NGHIỆP VỤ PYTHON CHO T-TTS v1.0.1 DESKTOP
=============================================================================
Đóng gói toàn bộ logic TTS, nhân bản giọng, xử lý âm thanh, lịch sử và bản quyền.
Cho phép giao diện Desktop (PySide6) gọi trực tiếp qua hàm nội bộ, hoàn toàn
không cần Flask, không cần localhost, không cần cổng HTTP loopback.
"""

from __future__ import annotations

import io
import math
import os
import re
import sys
import time
import shutil
import threading
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

# Đảm bảo mã hóa UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .storage import init_storage, get_app_dir
from .tts_engine import TTSEngine, DEFAULT_VOICE, ALLOWLIST_25_VOICES, PRESET_CATALOG
from .pron_dict import PronDict
from .history import History
from .license import license_manager, get_machine_id, STATUS_ACTIVE, STATUS_EXPIRED
from .audio_utils import (
    save_wav,
    wav_to_mp3,
    SAMPLE_RATE,
    clean_text,
    validate_and_convert_reference_audio,
)

_STORAGE_INFO = init_storage()
APP_DIR = _STORAGE_INFO["app_dir"]
DATA_DIR = _STORAGE_INFO["data_dir"]
OUT_DIR = _STORAGE_INFO["out_dir"]
UPLOAD_DIR = _STORAGE_INFO["upload_dir"]


def safe_filename(s: str, default: str = "audio") -> str:
    """Tạo tên tệp an toàn từ tiêu đề hoặc văn bản."""
    s = re.sub(r"[^\w\- ]+", "", s or "", flags=re.UNICODE).strip().replace(" ", "_")
    return s[:40] or default


class TTSService:
    """Lớp điều phối nghiệp vụ TTS tập trung cho T-TTS Desktop Native."""

    def __init__(self):
        self.storage = _STORAGE_INFO
        self.app_dir: Path = APP_DIR
        self.data_dir: Path = DATA_DIR
        self.default_out_dir: Path = OUT_DIR
        self.upload_dir: Path = UPLOAD_DIR

        self.engine = TTSEngine(mode="v3turbo", precision="int8", device="cpu")
        self.pron = PronDict()
        self.history = History(out_dir=self.default_out_dir)

        self._model_state = "unloaded"  # 'unloaded' | 'loading' | 'ready' | 'error'
        self._model_error = ""
        self._infer_lock = threading.Lock()
        self._init_lock = threading.Lock()

    # =========================================================================
    # 1. KHỞI TẠO VÀ TRẠNG THÁI MÔ HÌNH (MODEL LIFECYCLE)
    # =========================================================================
    def initialize_model(self, on_progress: Optional[Callable[[str], None]] = None) -> bool:
        """Khởi tạo mô hình VieNeu-TTS v3 Turbo ONNX CPU trong tiến trình hiện tại.

        Hàm này an toàn để chạy trong QThread / background worker.
        """
        with self._init_lock:
            if self.engine.ready:
                self._model_state = "ready"
                return True

            self._model_state = "loading"
            self._model_error = ""
            if on_progress:
                on_progress("Đang nạp tài nguyên mô hình VieNeu-TTS...")

            try:
                self.engine.load()
                self._model_state = "ready"
                if on_progress:
                    on_progress("Mô hình đã sẵn sàng")
                return True
            except Exception as e:
                self._model_state = "error"
                self._model_error = str(e)
                traceback.print_exc()
                if on_progress:
                    on_progress(f"Khởi tạo mô hình thất bại: {e}")
                return False

    def get_model_status(self) -> Dict[str, Any]:
        """Trả về trạng thái thực tế của mô hình âm thanh."""
        is_ready = self.engine.ready
        state = "ready" if is_ready else self._model_state
        return {
            "ready": is_ready,
            "state": state,
            "error": self._model_error,
            "device": getattr(self.engine, "effective_device", "cpu"),
            "mode": self.engine.mode,
            "precision": self.engine.precision,
            "backend": getattr(self.engine, "backend", "onnx"),
        }

    # =========================================================================
    # 2. DANH SÁCH GIỌNG ĐỌC & TÙY CHỈNH
    # =========================================================================
    def list_voices(self) -> List[Dict[str, Any]]:
        """Trả về danh sách 25 giọng preset allowlist + các giọng custom nhân bản."""
        return self.engine.list_voices()

    def is_valid_voice(self, voice_id: str) -> bool:
        return self.engine.is_valid_voice(voice_id)

    def resolve_voice(self, voice_id: Optional[str]) -> str:
        return self.engine.resolve_voice(voice_id)

    # =========================================================================
    # 3. TỔNG HỢP GIỌNG NÓI (TEXT-TO-SPEECH)
    # =========================================================================
    def synthesize_text(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        out_format: str = "wav",
        filename_prefix: Optional[str] = None,
        custom_out_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Tổng hợp văn bản tiếng Việt thành file âm thanh (WAV / MP3).

        Bảo vệ bản quyền: Nếu bản quyền hết hạn hoặc không hợp lệ,
        từ chối xử lý ở tầng nghiệp vụ và trả về thông báo lỗi rõ ràng.
        """
        # Kiểm tra bản quyền offline
        if not license_manager.is_active():
            info = license_manager.get_status_info()
            return {
                "success": False,
                "error": f"Chức năng bị khóa: {info['status_message']}",
                "license_locked": True,
                "status_code": info["status"],
            }

        clean = (text or "").strip()
        if not clean:
            return {"success": False, "error": "Văn bản nhập vào đang để trống."}

        # Xác thực tốc độ đọc (0.75x - 1.50x)
        try:
            speed = float(speed)
            if math.isnan(speed) or math.isinf(speed) or not (0.75 <= speed <= 1.50):
                speed = 1.0
        except Exception:
            speed = 1.0

        # Xác định giọng đọc
        resolved_voice = self.resolve_voice(voice_id)

        # Thư mục xuất file
        out_folder = Path(custom_out_dir) if custom_out_dir else self.default_out_dir
        out_folder.mkdir(parents=True, exist_ok=True)

        # Đặt tên tệp xuất
        tag = safe_filename(filename_prefix or clean[:30])
        time_stamp = int(time.time() * 1000)
        base_name = f"{time_stamp}_{tag}"

        wav_path = out_folder / f"{base_name}.wav"
        mp3_path = out_folder / f"{base_name}.mp3"

        with self._infer_lock:
            # Gọi trực tiếp mô hình VieNeu-TTS v3 Turbo ONNX CPU
            audio, sr = self.engine.synthesize(
                clean,
                voice=resolved_voice,
                speed=speed,
                pron_dict=self.pron.all(),
            )

        # Lưu file WAV chuẩn PCM 16-bit
        save_wav(wav_path, audio, sr)

        # Tính thời lượng thực tế
        duration_sec = round(len(audio) / float(sr), 2) if sr > 0 else 0.0

        # Nếu người dùng yêu cầu xuất định dạng MP3
        saved_mp3_path = None
        main_path = wav_path
        if out_format.lower() == "mp3":
            ok_mp3 = wav_to_mp3(wav_path, mp3_path)
            if ok_mp3 and mp3_path.exists():
                saved_mp3_path = str(mp3_path)
                main_path = mp3_path

        size_bytes = main_path.stat().st_size if main_path.exists() else 0

        # Lưu vào lịch sử sử dụng
        hist_item = self.history.add(
            text=clean,
            voice=resolved_voice,
            speed=speed,
            wav_path=str(wav_path),
            mp3_path=saved_mp3_path,
            kind="tts",
        )

        return {
            "success": True,
            "main_file": str(main_path),
            "wav_path": str(wav_path),
            "mp3_path": saved_mp3_path,
            "duration": duration_sec,
            "size_bytes": size_bytes,
            "voice": resolved_voice,
            "speed": speed,
            "text": clean,
            "history_id": hist_item.get("id"),
        }

    # =========================================================================
    # 4. NHÂN BẢN GIỌNG NÓI (VOICE CLONING)
    # =========================================================================
    def clone_voice(
        self,
        voice_name: str,
        ref_audio_path: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """Tạo giọng nhân bản mới từ file âm thanh mẫu (WAV/MP3)."""
        if not license_manager.is_active():
            info = license_manager.get_status_info()
            return {
                "success": False,
                "error": f"Chức năng nhân bản giọng bị khóa: {info['status_message']}",
                "license_locked": True,
            }

        name_clean = (voice_name or "").strip()
        if not name_clean:
            return {"success": False, "error": "Vui lòng nhập tên cho giọng nhân bản."}

        src_path = Path(ref_audio_path)
        if not src_path.is_file():
            return {"success": False, "error": f"Không tìm thấy file âm thanh mẫu: {ref_audio_path}"}

        # Chuẩn hóa âm thanh mẫu sang 16-bit Mono 44.1kHz lưu vào uploads
        safe_name = safe_filename(name_clean)
        clean_ref_wav = self.upload_dir / f"ref_clone_{int(time.time())}_{safe_name}.wav"

        try:
            validate_and_convert_reference_audio(src_path, clean_ref_wav, min_duration=2.5)
        except Exception as e:
            return {"success": False, "error": f"File âm thanh mẫu không hợp lệ: {e}"}

        try:
            with self._infer_lock:
                self.engine.add_custom_voice(name_clean, str(clean_ref_wav), save=True)
            return {
                "success": True,
                "voice_name": name_clean,
                "ref_file": str(clean_ref_wav),
                "message": f"Nhân bản thành công giọng: '{name_clean}'!",
            }
        except Exception as e:
            traceback.print_exc()
            return {"success": False, "error": f"Lỗi tạo giọng nhân bản: {e}"}

    def delete_custom_voice(self, voice_name: str) -> Dict[str, Any]:
        """Xóa một giọng nhân bản của người dùng."""
        try:
            self.engine.remove_custom_voice(voice_name)
            return {"success": True, "message": f"Đã xóa giọng nhân bản '{voice_name}'."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # 5. XỬ LÝ HÀNG LOẠT (BATCH PROCESSING)
    # =========================================================================
    def process_batch(
        self,
        items: List[Dict[str, Any]],
        common_voice: Optional[str] = None,
        common_speed: float = 1.0,
        out_format: str = "wav",
        custom_out_dir: Optional[Path] = None,
        on_progress: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Xử lý danh sách các đoạn văn bản hàng loạt với cơ chế cách ly lỗi."""
        if not license_manager.is_active():
            info = license_manager.get_status_info()
            return {
                "success": False,
                "error": f"Chức năng xử lý hàng loạt bị khóa: {info['status_message']}",
                "license_locked": True,
            }

        total = len(items)
        if total == 0:
            return {"success": True, "total": 0, "completed": 0, "results": []}

        results = []
        completed_count = 0
        failed_count = 0

        for idx, it in enumerate(items):
            if should_cancel and should_cancel():
                break

            text = it.get("text", "")
            voice = it.get("voice") or common_voice
            speed = it.get("speed", common_speed)
            tag = it.get("tag") or f"batch_{idx+1:03d}"

            try:
                res = self.synthesize_text(
                    text=text,
                    voice_id=voice,
                    speed=speed,
                    out_format=out_format,
                    filename_prefix=tag,
                    custom_out_dir=custom_out_dir,
                )
                res["index"] = idx
                res["original_item"] = it
                if res.get("success"):
                    completed_count += 1
                else:
                    failed_count += 1
                results.append(res)
            except Exception as e:
                failed_count += 1
                res = {
                    "index": idx,
                    "success": False,
                    "error": str(e),
                    "original_item": it,
                }
                results.append(res)

            if on_progress:
                on_progress(idx + 1, total, res)

        return {
            "success": True,
            "total": total,
            "completed": completed_count,
            "failed": failed_count,
            "results": results,
        }

    # =========================================================================
    # 6. QUẢN LÝ LỊCH SỬ & DỮ LIỆU
    # =========================================================================
    def get_history(self) -> List[Dict[str, Any]]:
        return self.history.all()

    def get_history_stats(self) -> Dict[str, Any]:
        return self.history.get_stats()

    def delete_history_item(self, item_id: str) -> bool:
        return self.history.delete(item_id)

    def clear_history(self) -> bool:
        return self.history.clear()

    # =========================================================================
    # 7. QUẢN LÝ BẢN QUYỀN OFFLINE
    # =========================================================================
    def get_license_info(self) -> Dict[str, Any]:
        return license_manager.get_status_info()

    def get_machine_id(self) -> str:
        return get_machine_id()

    def activate_license(self, raw_key: str) -> Tuple[bool, str, Dict[str, Any]]:
        return license_manager.activate(raw_key)


# Khởi tạo singleton dùng xuyên suốt toàn ứng dụng Desktop
tts_service = TTSService()
