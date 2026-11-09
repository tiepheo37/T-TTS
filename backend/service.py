"""backend/service.py — LỚP DỊCH VỤ NGHIỆP VỤ PYTHON CHO T-TTS v2.0 DESKTOP
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

        self._settings_path = self.data_dir / "settings.json"
        self._load_persistent_settings()

        self._model_state = "unloaded"  # 'unloaded' | 'loading' | 'ready' | 'error'
        self._model_error = ""
        self._infer_lock = threading.Lock()
        self._init_lock = threading.Lock()

    @property
    def output_dir(self) -> Path:
        """Thư mục xuất file âm thanh đang hoạt động (bí danh đồng bộ cho default_out_dir)."""
        return self.default_out_dir

    @output_dir.setter
    def output_dir(self, val: Union[str, Path]):
        self.set_default_out_dir(val)

    def _load_persistent_settings(self):
        try:
            if self._settings_path.exists():
                import json
                data = json.loads(self._settings_path.read_text(encoding="utf-8"))
                custom_out = data.get("default_out_dir")
                if custom_out:
                    p = Path(custom_out)
                    if p.exists() or p.parent.exists():
                        p.mkdir(parents=True, exist_ok=True)
                        self.default_out_dir = p
                        self.history.out_dir = p
        except Exception:
            pass

    def set_default_out_dir(self, new_dir: Union[str, Path]) -> bool:
        """Thiết lập và lưu vĩnh viễn thư mục lưu âm thanh mặc định."""
        p = Path(new_dir).resolve()
        try:
            p.mkdir(parents=True, exist_ok=True)
            self.default_out_dir = p
            self.history.out_dir = p
            cfg = {}
            if self._settings_path.exists():
                try:
                    import json
                    cfg = json.loads(self._settings_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            cfg["default_out_dir"] = str(p)
            import json
            self._settings_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception:
            return False

    def open_output_folder(self, folder: Optional[Union[str, Path]] = None) -> bool:
        """Mở thư mục chứa file âm thanh trong Windows Explorer an toàn."""
        target = Path(folder or self.default_out_dir).resolve()
        target.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(target))
                return True
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(target)])
                return True
        except Exception:
            return False

    def open_file_in_explorer(self, file_path: Union[str, Path]) -> bool:
        """Mở Windows Explorer và highlight chính xác tệp âm thanh vừa tạo."""
        fp = Path(file_path).resolve()
        if not fp.exists():
            return False
        try:
            if sys.platform == "win32":
                import subprocess
                subprocess.run(f'explorer /select,"{str(fp)}"', shell=True)
                return True
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(fp.parent)])
                return True
        except Exception:
            try:
                os.startfile(str(fp.parent))
                return True
            except Exception:
                return False

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

    # Bí danh tương thích ngược
    initialize_models = initialize_model


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
            "file_path": str(main_path),
            "wav_path": str(wav_path),
            "mp3_path": saved_mp3_path,
            "duration": duration_sec,
            "duration_sec": duration_sec,
            "size_bytes": size_bytes,
            "file_size_bytes": size_bytes,
            "format": out_format.lower(),
            "voice": resolved_voice,
            "speed": speed,
            "text": clean,
            "history_id": hist_item.get("id"),
        }

    # Bí danh tương thích ngược
    synthesize = synthesize_text

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
    # 5B. TẠO BẢN TIN PHÁT THANH (BROADCAST STUDIO)
    # =========================================================================
    def stitch_broadcast(
        self,
        segments: List[Dict[str, Any]],
        title: str = "Ban_tin_phat_thanh",
        out_format: str = "wav",
        default_pause_sec: float = 1.0,
        bg_music_path: Optional[str | Path] = None,
        bg_music_volume_db: float = -18.0,
        bg_music_loop: bool = True,
        bg_music_ducking: bool = True,
        bg_music_fade_in_ms: int = 1500,
        bg_music_fade_out_ms: int = 2000,
        intro_music_path: Optional[str | Path] = None,
        intro_music_vol_db: float = 0.0,
        outro_music_path: Optional[str | Path] = None,
        outro_music_vol_db: float = 0.0,
        custom_out_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Ghép nhiều đoạn đọc và nhạc thành bản tin phát thanh hoàn chỉnh."""
        if not license_manager.is_active():
            info = license_manager.get_status_info()
            return {
                "success": False,
                "error": f"Chức năng tạo bản tin bị khóa: {info['status_message']}",
                "license_locked": True,
            }

        from .audio_utils import stitch_broadcast_project
        out_dir = custom_out_dir or self.default_out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        clean_title = safe_filename(title, "Ban_tin_phat_thanh")
        out_file = out_dir / f"{clean_title}_{stamp}.{out_format.lower()}"

        res = stitch_broadcast_project(
            segments=segments,
            output_path=out_file,
            out_format=out_format,
            default_pause_sec=default_pause_sec,
            bg_music_path=bg_music_path,
            bg_music_volume_db=bg_music_volume_db,
            bg_music_loop=bg_music_loop,
            bg_music_ducking=bg_music_ducking,
            bg_music_fade_in_ms=bg_music_fade_in_ms,
            bg_music_fade_out_ms=bg_music_fade_out_ms,
            intro_music_path=intro_music_path,
            intro_music_vol_db=intro_music_vol_db,
            outro_music_path=outro_music_path,
            outro_music_vol_db=outro_music_vol_db,
        )

        # Log vào lịch sử
        summary = f"Bản tin phát thanh: {title} ({len(segments)} đoạn)"
        wav_p = out_file if out_format.lower() == "wav" else None
        mp3_p = out_file if out_format.lower() == "mp3" else None
        hist_item = self.history.add(
            text=summary,
            voice="Bản tin tổng hợp",
            speed=1.0,
            wav_path=wav_p,
            mp3_path=mp3_p,
            kind="broadcast",
        )
        res["history_id"] = hist_item.get("id")
        res["title"] = title
        return res

    # =========================================================================
    # 5C. TỔNG HỢP KỊCH BẢN PODCAST / HỘI THOẠI ĐA NHÂN VẬT
    # =========================================================================
    def synthesize_podcast(
        self,
        lines: List[Dict[str, Any]],
        title: str = "Kich_ban_podcast",
        out_format: str = "wav",
        custom_out_dir: Optional[Path] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Tổng hợp kịch bản nhiều nhân vật thành một tệp podcast duy nhất."""
        if not license_manager.is_active():
            info = license_manager.get_status_info()
            return {
                "success": False,
                "error": f"Chức năng tạo podcast bị khóa: {info['status_message']}",
                "license_locked": True,
            }

        if not lines:
            return {"success": False, "error": "Kịch bản rỗng, chưa có câu thoại nào."}

        out_dir = custom_out_dir or self.default_out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        temp_segments = []
        summary_lines = []

        total = len(lines)
        for idx, line in enumerate(lines):
            if should_cancel and should_cancel():
                return {"success": False, "error": "Người dùng đã hủy tiến trình podcast."}

            spk = line.get("speaker", f"Nhân vật {idx+1}")
            txt = (line.get("text") or "").strip()
            v_id = line.get("voice_id") or "Hải Đăng"
            spd = float(line.get("speed", 1.0))
            pause_after = float(line.get("pause_after", 0.5))

            if not txt:
                continue

            summary_lines.append(f"{spk}: {txt}")
            if on_progress:
                on_progress(idx + 1, total, f"Đang đọc: {spk}...")

            # Synthesize line to temp wav
            line_res = self.synthesize_text(
                text=txt,
                voice_id=v_id,
                speed=spd,
                out_format="wav",
                filename_prefix=f"_temp_pc_{idx}",
                custom_out_dir=self.upload_dir,
            )
            if line_res.get("success"):
                temp_segments.append({
                    "file_path": line_res["main_file"],
                    "pause_after": pause_after,
                    "title": f"{spk}: {txt[:30]}",
                })

        if not temp_segments:
            return {"success": False, "error": "Không thể tổng hợp bất kỳ câu thoại nào trong kịch bản."}

        from .audio_utils import stitch_broadcast_project
        clean_title = safe_filename(title, "Kich_ban_podcast")
        out_file = out_dir / f"{clean_title}_{stamp}.{out_format.lower()}"

        res = stitch_broadcast_project(
            segments=temp_segments,
            output_path=out_file,
            out_format=out_format,
            default_pause_sec=0.5,
        )

        # Dọn dẹp tệp tạm
        for ts in temp_segments:
            try:
                Path(ts["file_path"]).unlink(missing_ok=True)
            except Exception:
                pass

        # Log vào lịch sử
        summary = "\n".join(summary_lines[:5])
        wav_p = out_file if out_format.lower() == "wav" else None
        mp3_p = out_file if out_format.lower() == "mp3" else None
        hist_item = self.history.add(
            text=summary,
            voice="Nhiều giọng đọc (Podcast)",
            speed=1.0,
            wav_path=wav_p,
            mp3_path=mp3_p,
            kind="podcast",
        )
        res["history_id"] = hist_item.get("id")
        res["title"] = title
        return res

    # =========================================================================
    # 5D. THIẾT BỊ MICROPHONE & THU ÂM TRỰC TIẾP
    # =========================================================================
    def get_microphone_devices(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các thiết bị thu âm Micro có sẵn trên máy tính."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            mic_list = []
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    mic_list.append({
                        "index": idx,
                        "name": dev.get("name", f"Microphone {idx}"),
                        "channels": dev.get("max_input_channels", 1),
                        "default_sr": dev.get("default_samplerate", 44100),
                    })
            return mic_list
        except Exception:
            return []

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

    # =========================================================================
    # 8. QUẢN LÝ TỪ ĐIỂN PHÁT ÂM (PRONUNCIATION DICTIONARY)
    # =========================================================================
    def get_pron_dict(self) -> Dict[str, str]:
        return self.pron.all()

    def set_pron_dict_entry(self, word: str, reading: str) -> Dict[str, str]:
        self.pron.set(word, reading)
        return self.pron.all()

    def delete_pron_dict_entry(self, word: str) -> Dict[str, str]:
        self.pron.delete(word)
        return self.pron.all()

    def clear_pron_dict(self) -> Dict[str, str]:
        for k in list(self.pron.all().keys()):
            self.pron.delete(k)
        return self.pron.all()

    def preview_pron_text(self, text: str) -> str:
        from .audio_utils import apply_pron_dict
        return apply_pron_dict(text, self.pron.all())


# Khởi tạo singleton dùng xuyên suốt toàn ứng dụng Desktop
tts_service = TTSService()
