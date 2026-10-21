"""Lớp bọc SDK chính thức `vieneu` (VieNeu-TTS v3 Turbo & Nano).

TUYỆT ĐỐI KHÔNG tự viết lại pipeline inference — mọi tổng hợp giọng đều đi qua
`Vieneu(mode="v3turbo")` của tác giả model (pip install vieneu).
"""
import os
import sys
import threading
import numpy as np

try:
    from .audio_utils import (
        SAMPLE_RATE, apply_pron_dict, split_pause_tags, silence, time_stretch,
    )
except ImportError:
    from audio_utils import (
        SAMPLE_RATE, apply_pron_dict, split_pause_tags, silence, time_stretch,
    )

DEFAULT_VOICE = "Hải Đăng"

# Allowlist chính thức 25 giọng đọc được phép của T-TTS v1.0.1
ALLOWLIST_25_VOICES = [
    "Adam bựa",
    "Trúc Ly",
    "Thiện Minh",
    "Mai Anh",
    "Hải Đăng",
    "Thùy Dung",
    "Thiền Tâm Đức",
    "Ngọc Huyền",
    "Quang Sơn",
    "Ngọc Trân",
    "Minh Đức",
    "Phạm Tuyên",
    "Thái Sơn",
    "Xuân Vĩnh",
    "Thanh Bình",
    "Ngọc Linh",
    "Đoan Trang",
    "Thục Đoan",
    "Minh Triết",
    "Mỹ Duyên",
    "Quỳnh Anh",
    "Đức Trí",
    "Kim Thanh",
    "Adam",
    "Quốc Tuấn",
]
ALLOWLIST_SET = set(ALLOWLIST_25_VOICES)

# Danh mục 25 giọng preset VieNeu v3 Turbo chính thức kèm Giới tính / Vùng miền / Phong cách
PRESET_CATALOG = {
    "Hải Đăng": {"gender": "Nam", "region": "Miền Bắc", "style": "Truyền cảm (Mặc định)", "desc": "Giọng nam Bắc chuẩn, truyền cảm, hào sảng"},
    "Mai Anh": {"gender": "Nữ", "region": "Miền Bắc", "style": "Truyền cảm", "desc": "Giọng nữ Bắc mượt mà, truyền cảm"},
    "Trúc Ly": {"gender": "Nữ", "region": "Miền Nam", "style": "Dịu dàng", "desc": "Giọng nữ Nam Bộ dịu dàng, tự nhiên"},
    "Thiện Minh": {"gender": "Nam", "region": "Miền Bắc", "style": "Trang trọng", "desc": "Giọng nam Bắc trang trọng, phát thanh chính luận"},
    "Thùy Dung": {"gender": "Nữ", "region": "Miền Bắc", "style": "Nhẹ nhàng", "desc": "Giọng nữ Bắc nhẹ nhàng, thanh thoát"},
    "Thiền Tâm Đức": {"gender": "Nam", "region": "Miền Bắc", "style": "Sâu lắng", "desc": "Giọng nam trầm ấm, sâu lắng"},
    "Ngọc Huyền": {"gender": "Nữ", "region": "Miền Bắc", "style": "Trong trẻo", "desc": "Giọng nữ Hà Nội trong trẻo"},
    "Quang Sơn": {"gender": "Nam", "region": "Miền Bắc", "style": "Ấm áp", "desc": "Giọng nam Bắc ấm áp, dễ nghe"},
    "Ngọc Trân": {"gender": "Nữ", "region": "Miền Nam", "style": "Tự nhiên", "desc": "Giọng nữ Nam Bộ phát thanh viên"},
    "Minh Đức": {"gender": "Nam", "region": "Miền Bắc", "style": "Phát thanh", "desc": "Giọng nam phát thanh viên chính luận"},
    "Phạm Tuyên": {"gender": "Nam", "region": "Miền Bắc", "style": "Diễn cảm", "desc": "Giọng nam diễn cảm, kể chuyện"},
    "Thái Sơn": {"gender": "Nam", "region": "Miền Nam", "style": "Hiện đại", "desc": "Giọng nam Sài Gòn hiện đại"},
    "Xuân Vĩnh": {"gender": "Nam", "region": "Miền Bắc", "style": "Chính luận", "desc": "Giọng nam đọc văn bản chính luận"},
    "Thanh Bình": {"gender": "Nam", "region": "Miền Bắc", "style": "Thời sự", "desc": "Giọng nam tin tức thời sự"},
    "Ngọc Linh": {"gender": "Nữ", "region": "Miền Nam", "style": "Quảng cáo", "desc": "Giọng nữ vui tươi, năng động"},
    "Đoan Trang": {"gender": "Nữ", "region": "Miền Bắc", "style": "Sách nói", "desc": "Giọng nữ đọc truyện, tài liệu"},
    "Thục Đoan": {"gender": "Nữ", "region": "Miền Nam", "style": "Ngọt ngào", "desc": "Giọng nữ Tây Nam Bộ ngọt ngào"},
    "Minh Triết": {"gender": "Nam", "region": "Miền Bắc", "style": "Kể chuyện", "desc": "Giọng nam kể chuyện, thuyết minh"},
    "Mỹ Duyên": {"gender": "Nữ", "region": "Miền Bắc", "style": "Dịu dàng", "desc": "Giọng nữ Bắc dịu dàng"},
    "Quỳnh Anh": {"gender": "Nữ", "region": "Miền Bắc", "style": "Đọc truyện", "desc": "Giọng nữ chuyên đọc văn học"},
    "Đức Trí": {"gender": "Nam", "region": "Miền Nam", "style": "Trẻ trung", "desc": "Giọng nam trẻ trung"},
    "Kim Thanh": {"gender": "Nữ", "region": "Miền Bắc", "style": "Tin tức", "desc": "Giọng nữ thời sự quốc gia"},
    "Adam": {"gender": "Nam", "region": "Song ngữ", "style": "Quốc tế", "desc": "Giọng nam phát âm tiếng Anh/Song ngữ"},
    "Quốc Tuấn": {"gender": "Nam", "region": "Miền Bắc", "style": "Hào sảng", "desc": "Giọng nam hào sảng dứt khoát"},
    "Adam bựa": {"gender": "Nam", "region": "Vui nhộn", "style": "Giải trí", "desc": "Giọng nam phong cách vui nhộn"}
}


class TTSEngine:
    def __init__(self, mode="v3turbo", precision="int8", device="cpu"):
        self.mode = mode
        self.precision = precision
        self.device = device
        self._tts = None
        self._lock = threading.Lock()
        self.backend = None

    def load(self, mode=None, precision=None, device=None):
        """Tải mô hình VieNeu-TTS với cấu hình CPU/GPU phù hợp."""
        with self._lock:
            if mode:
                self.mode = mode
            if precision:
                self.precision = precision
            if device:
                self.device = device

            try:
                from .hardware import resolve_device_policy, get_hardware_status_report
            except ImportError:
                from hardware import resolve_device_policy, get_hardware_status_report

            # Kiểm tra chính sách thiết bị (CPU / GPU / AUTO)
            policy = resolve_device_policy(self.device)
            if self.device in ("cuda", "gpu") and not policy["allowed"]:
                raise ValueError(policy["reason"])

            self.effective_device = policy["effective_device"]

            try:
                from .models_bootstrap import ensure_local_models, patch_sdk_fetch
            except ImportError:
                from models_bootstrap import ensure_local_models, patch_sdk_fetch
            onnx_dir, codec_dir = ensure_local_models(precision=self.precision)
            patch_sdk_fetch(onnx_dir, codec_dir)

            from vieneu import Vieneu
            # Khởi tạo VieNeu SDK (mặc định v3turbo dùng ONNX Runtime Lite)
            self._tts = Vieneu(mode=self.mode, precision=self.precision, onnx_dir=onnx_dir)
            self.backend = getattr(self._tts, "backend", "onnx")
            self._load_persisted_custom_voices()

    @property
    def ready(self):
        return self._tts is not None

    def ensure(self):
        if self._tts is None:
            self.load()

    def get_hardware_status(self):
        """Lấy thông tin chi tiết phần cứng thực tế (CPU/GPU, VRAM, Driver, ONNX Provider)."""
        try:
            from .hardware import get_hardware_status_report
        except ImportError:
            from hardware import get_hardware_status_report
        return get_hardware_status_report(self)

    def list_voices(self):
        """Danh sách giọng đọc CHỈ gồm 25 giọng thuộc ALLOWLIST + Giọng custom."""
        out = []
        seen_ids = set()

        presets = []
        if self._tts is not None:
            try:
                presets = self._tts.list_preset_voices() or []
            except Exception:
                presets = []

        for item in presets:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                label, vid = item[0], item[1]
            else:
                label = vid = str(item)
            vid = str(vid)
            if not vid or vid in seen_ids:
                continue

            # BẮT BUỘC CHỈ GIỮ CÁC GIỌNG THUỘC ALLOWLIST 25 GIỌNG
            if vid not in ALLOWLIST_SET and str(label) not in ALLOWLIST_SET:
                continue

            seen_ids.add(vid)
            try:
                meta = self._tts.get_preset_voice(vid) or {}
            except Exception:
                meta = {}
            if not isinstance(meta, dict):
                meta = {}

            # Ưu tiên dữ liệu từ PRESET_CATALOG nếu SDK không có
            cat_info = PRESET_CATALOG.get(vid, {})
            gender = str(meta.get("gender") or cat_info.get("gender") or "")
            region = str(meta.get("region") or cat_info.get("region") or "")
            style = str(meta.get("style") or cat_info.get("style") or "")
            desc = str(meta.get("description") or cat_info.get("desc") or label or vid)

            label_txt = f"{vid} ({gender} - {region} - {style})" if gender else str(label or vid)
            out.append({
                "id": vid,
                "name": vid,
                "label": label_txt,
                "gender": gender or "Khác",
                "region": region or "Toàn quốc",
                "style": style or "Tự nhiên",
                "description": desc,
                "is_custom": False,
            })

        # Fallback từ Catalog nếu SDK chưa nạp hoặc trả về rỗng trong test
        if not out:
            for vid in ALLOWLIST_25_VOICES:
                meta = PRESET_CATALOG.get(vid, {"gender": "Nam", "region": "Miền Bắc", "style": "Tự nhiên", "desc": vid})
                out.append({
                    "id": vid,
                    "name": vid,
                    "label": f"{vid} ({meta['gender']} - {meta['region']} - {meta['style']})",
                    "gender": meta["gender"],
                    "region": meta["region"],
                    "style": meta["style"],
                    "description": meta["desc"],
                    "is_custom": False,
                })
                seen_ids.add(vid)

        # Thêm giọng custom đã nhân bản của người dùng
        for name in self._custom_voices():
            if name not in seen_ids:
                out.append({
                    "id": name,
                    "name": name,
                    "label": f"🎤 {name} (Giọng nhân bản)",
                    "gender": "Cá nhân",
                    "region": "Tự chọn",
                    "style": "Giọng của bạn",
                    "description": "Giọng nói được nhân bản qua thu âm micro",
                    "is_custom": True,
                })
                seen_ids.add(name)

        return out

    def is_valid_voice(self, voice_id):
        """Kiểm tra xem voice_id có thực sự tồn tại trong SDK presets hoặc custom voices không."""
        if not voice_id:
            return False
        vid = str(voice_id).strip()
        voices = self.list_voices()
        return any(v["id"] == vid or v["id"].lower() == vid.lower() for v in voices)

    def resolve_voice(self, voice_id):
        """Đảm bảo luôn trả về voice_id hợp lệ cho VieNeu SDK."""
        self.ensure()
        if not voice_id:
            return DEFAULT_VOICE
        vid = str(voice_id).strip()
        for v in self.list_voices():
            if v["id"] == vid or v["id"].lower() == vid.lower():
                return v["id"]
        for v in self.list_voices():
            if vid.lower() in v["id"].lower():
                return v["id"]
        return DEFAULT_VOICE

    def synthesize(self, text, voice=None, speed=1.0, pron_dict=None):
        """Tổng hợp giọng nói -> (audio float32, sample_rate 48000)."""
        self.ensure()
        text = apply_pron_dict(text or "", pron_dict)
        voice_name = self.resolve_voice(voice)
        chunks = []

        for seg, pause in split_pause_tags(text):
            if seg:
                wav = self._tts.infer(seg, voice=voice_name)
                wav = np.asarray(wav, dtype=np.float32)
                chunks.append(wav)
            if pause > 0:
                chunks.append(silence(pause))

        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        if abs(speed - 1.0) > 1e-5 and audio.size > 0:
            audio = time_stretch(audio, speed)

        return audio, SAMPLE_RATE

    def _load_persisted_custom_voices(self):
        """Tải các giọng nhân bản đã lưu từ data/custom_voices.json vào VieNeu SDK."""
        if self._tts is None:
            return
        import json
        from pathlib import Path
        try:
            from .storage import init_storage
        except ImportError:
            from storage import init_storage

        store = init_storage()
        custom_file = store["data_dir"] / "custom_voices.json"
        if not custom_file.exists():
            return

        try:
            data = json.loads(custom_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            for name, item in data.items():
                if not name or not isinstance(item, dict):
                    continue
                # Nếu đã có speaker_emb trong file JSON, nạp trực tiếp vào preset_voices
                emb = item.get("speaker_emb")
                codes = item.get("codes")
                ref_path = item.get("ref_audio_path")
                if emb is not None:
                    preset_dict = getattr(self._tts, "_preset_voices", None)
                    if isinstance(preset_dict, dict):
                        preset_dict[name] = {
                            "description": item.get("description", "Giọng nhân bản micro"),
                            "gender": item.get("gender", "Cá nhân"),
                            "style": item.get("style", "natural"),
                            "speaker_emb": np.asarray(emb, dtype=np.float32),
                            "codes": np.asarray(codes, dtype=np.int64) if codes is not None else None,
                        }
                elif ref_path and Path(ref_path).is_file():
                    try:
                        self._tts.add_voice(name, ref_path, denoise=True)
                    except Exception:
                        pass
        except Exception:
            pass

    def add_custom_voice(self, name, ref_audio_path, save=True):
        self.ensure()
        clean = (name or "").strip()
        if not clean:
            raise ValueError("Thiếu tên giọng nhân bản.")
        
        # Đăng ký với VieNeu SDK (denoise=True để lọc ồn micro)
        self._tts.add_voice(clean, str(ref_audio_path), denoise=True)

        if save:
            try:
                import json
                from pathlib import Path
                try:
                    from .storage import init_storage
                except ImportError:
                    from storage import init_storage

                store = init_storage()
                custom_file = store["data_dir"] / "custom_voices.json"
                records = {}
                if custom_file.exists():
                    try:
                        records = json.loads(custom_file.read_text(encoding="utf-8")) or {}
                    except Exception:
                        records = {}

                v_info = getattr(self._tts, "_preset_voices", {}).get(clean, {})
                emb = v_info.get("speaker_emb")
                codes = v_info.get("codes")

                records[clean] = {
                    "name": clean,
                    "ref_audio_path": str(ref_audio_path),
                    "description": "Giọng nói được nhân bản từ micro",
                    "gender": "Cá nhân",
                    "style": "Giọng của bạn",
                    "speaker_emb": [round(float(x), 6) for x in np.asarray(emb).reshape(-1)] if emb is not None else None,
                    "codes": np.asarray(codes, dtype=int).tolist() if codes is not None else None,
                }
                custom_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as save_err:
                print(f"[CẢNH BÁO] Không thể lưu custom_voices.json: {save_err}", flush=True)

        return clean

    def remove_custom_voice(self, name):
        self.ensure()
        clean = (name or "").strip()
        try:
            if hasattr(self._tts, "remove_voice"):
                self._tts.remove_voice(clean)
            elif hasattr(self._tts, "_preset_voices") and isinstance(self._tts._preset_voices, dict):
                self._tts._preset_voices.pop(clean, None)
        except Exception as e:
            raise ValueError(f"Không xóa được giọng: {e}")

        try:
            import json
            try:
                from .storage import init_storage
            except ImportError:
                from storage import init_storage

            store = init_storage()
            custom_file = store["data_dir"] / "custom_voices.json"
            if custom_file.exists():
                records = json.loads(custom_file.read_text(encoding="utf-8")) or {}
                if clean in records:
                    del records[clean]
                    custom_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _custom_voices(self):
        """Lấy danh sách các giọng custom đã nhân bản."""
        custom_names = set()
        # Đọc từ file custom_voices.json
        try:
            import json
            try:
                from .storage import init_storage
            except ImportError:
                from storage import init_storage

            store = init_storage()
            custom_file = store["data_dir"] / "custom_voices.json"
            if custom_file.exists():
                records = json.loads(custom_file.read_text(encoding="utf-8")) or {}
                custom_names.update(records.keys())
        except Exception:
            pass

        # Bổ sung các giọng hiện có trong _preset_voices nhưng không nằm trong allowlist 25 giọng
        try:
            presets = getattr(self._tts, "_preset_voices", None)
            if isinstance(presets, dict):
                for k in presets.keys():
                    if k not in ALLOWLIST_SET:
                        custom_names.add(k)
        except Exception:
            pass

        return sorted(list(custom_names))
