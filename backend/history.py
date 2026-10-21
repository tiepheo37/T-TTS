import sys
import json
import time
import shutil
from pathlib import Path

try:
    from .storage import init_storage
except ImportError:
    from storage import init_storage

_STORAGE_INFO = init_storage()
DEFAULT_DIR = _STORAGE_INFO["out_dir"]
DEFAULT_INDEX = _STORAGE_INFO["history_index"]
STORAGE_WARN_THRESHOLD_BYTES = 1024 * 1024 * 1024  # 1 GB


class History:
    def __init__(self, out_dir=None, index_path=None):
        self.out_dir = Path(out_dir) if out_dir else DEFAULT_DIR
        self.index_path = Path(index_path) if index_path else DEFAULT_INDEX
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._items = []
        self.load()

    def load(self):
        try:
            if self.index_path.exists():
                self._items = json.loads(self.index_path.read_text(encoding="utf-8"))
            else:
                self._items = []
        except Exception:
            self._items = []

    def _save_index(self):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(self._items, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, text, voice, speed, wav_path, mp3_path=None, srt_path=None, kind="tts"):
        size = 0
        for p_val in (wav_path, mp3_path, srt_path):
            if p_val and Path(p_val).exists():
                try:
                    size += Path(p_val).stat().st_size
                except Exception:
                    pass

        item = {
            "id": f"{int(time.time()*1000)}",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": kind,
            "text": (text or "")[:400],
            "voice": voice,
            "speed": speed,
            "wav": Path(wav_path).name if wav_path else None,
            "mp3": Path(mp3_path).name if mp3_path else None,
            "srt": Path(srt_path).name if srt_path else None,
            "size": size,
        }
        self._items.insert(0, item)
        self._items = self._items[:500]
        self._save_index()
        return item

    def all(self):
        return list(self._items)

    def get_stats(self):
        """Tính tổng số bản ghi và tổng dung lượng sử dụng thực tế trên ổ đĩa."""
        total_size = 0
        for it in self._items:
            for key in ("wav", "mp3", "srt"):
                fn = it.get(key)
                if fn:
                    p = self.out_dir / fn
                    if p.exists():
                        try:
                            total_size += p.stat().st_size
                        except Exception:
                            pass
        count = len(self._items)
        warn_cleanup = total_size >= STORAGE_WARN_THRESHOLD_BYTES
        size_mb = round(total_size / (1024 * 1024), 2)
        return {
            "count": count,
            "size_bytes": total_size,
            "size_mb": size_mb,
            "warn_cleanup": warn_cleanup,
        }

    def get(self, item_id):
        for it in self._items:
            if it["id"] == item_id:
                return it
        return None

    def delete(self, item_id):
        item = self.get(item_id)
        if not item:
            return False
        # Xóa các file vật lý
        for key in ("wav", "mp3", "srt"):
            fn = item.get(key)
            if fn:
                p = self.out_dir / fn
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
        self._items = [it for it in self._items if it["id"] != item_id]
        self._save_index()
        return True

    def clear(self):
        """Xóa toàn bộ lịch sử và dọn dẹp các file trong folder output."""
        for it in self._items:
            for key in ("wav", "mp3", "srt"):
                fn = it.get(key)
                if fn:
                    p = self.out_dir / fn
                    if p.exists():
                        try:
                            p.unlink()
                        except Exception:
                            pass
        self._items = []
        self._save_index()

    def resolve(self, item, fmt="wav"):
        name = item.get(fmt) or item.get("wav")
        if not name:
            return None
        p = self.out_dir / name
        if p.exists():
            return p
        # Fallback kiểm tra file trong app_dir nếu đang dùng user data dir
        app_out = _STORAGE_INFO["app_dir"] / "output" / name
        if app_out.exists():
            try:
                self.out_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(app_out, p)
                return p
            except Exception:
                return app_out
        return None
