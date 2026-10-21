import sys
import json
from pathlib import Path

try:
    from .storage import init_storage
except ImportError:
    from storage import init_storage

_STORAGE_INFO = init_storage()
DEFAULT_PATH = _STORAGE_INFO["dict_path"]

BUILTIN = {
    "KTX": "ký túc xá",
    "SGK": "sách giáo khoa",
    "UBND": "ủy ban nhân dân",
}


class PronDict:
    def __init__(self, path=None):
        self.path = Path(path) if path else DEFAULT_PATH
        self._data = {}
        self.load()

    def load(self):
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._data = dict(BUILTIN)
            self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2),
                             encoding="utf-8")

    def all(self):
        return dict(self._data)

    def set(self, word, reading):
        word = (word or "").strip()
        if not word:
            raise ValueError("Thiếu từ")
        if reading:
            self._data[word] = reading.strip()
        else:
            self._data.pop(word, None)
        self.save()

    def delete(self, word):
        self._data.pop(word, None)
        self.save()
