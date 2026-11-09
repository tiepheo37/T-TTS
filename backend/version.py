"""backend/version.py — THÔNG TIN PHIÊN BẢN VÀ CẤU HÌNH AUTO UPDATE CHO T-TTS
=============================================================================
Tác giả: Nguyễn Văn Tiệp
Hệ thống: T-TTS Windows Native Desktop (VieNeu-TTS v3 Turbo ONNX CPU)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Tuple

APP_VERSION = "3.0.1"
APP_NAME = "T-TTS"
APP_DISPLAY_NAME = "T-TTS v3.0.1 — Hệ Thống Trợ Lý Giọng Nói Quân Đội"
APP_AUTHOR = "Nguyễn Văn Tiệp"
APP_ID = "com.nguyenvantiep.ttts"

DEFAULT_GITHUB_REPO = "tiepheo37/T-TTS"
DEFAULT_CHANNEL = "stable"


def parse_version(ver_str: str) -> Tuple[int, ...]:
    """Phân tích chuỗi phiên bản thành tuple số nguyên để so sánh chuẩn xác.
    Ví dụ: 'v3.0.1' -> (3, 0, 1), '3.0' -> (3, 0, 0), 'v3.0.10' -> (3, 0, 10), '3.0.1_Offline' -> (3, 0, 1)
    """
    import re
    cleaned = str(ver_str).strip().lstrip("vV").split("-")[0].split("+")[0].split("_")[0]
    parts = []
    for part in cleaned.split("."):
        # Lấy các chữ số đầu tiên trong phân đoạn nếu có ký tự lạ
        m = re.match(r"^(\d+)", part)
        if m:
            parts.append(int(m.group(1)))
        else:
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer_version(remote_version: str, current_version: str = APP_VERSION) -> bool:
    """Trả về True nếu remote_version lớn hơn current_version theo thứ tự số học (tuple số nguyên)."""
    r_parts = list(parse_version(remote_version))
    c_parts = list(parse_version(current_version))
    max_len = max(len(r_parts), len(c_parts), 3)
    while len(r_parts) < max_len:
        r_parts.append(0)
    while len(c_parts) < max_len:
        c_parts.append(0)
    return tuple(r_parts) > tuple(c_parts)


def get_update_config_file(data_dir: Path) -> Path:
    return data_dir / "update_config.json"


def load_update_config(data_dir: Path) -> Dict[str, Any]:
    cfg_file = get_update_config_file(data_dir)
    default_cfg = {
        "auto_check_on_startup": True,
        "github_repo": DEFAULT_GITHUB_REPO,
        "channel": DEFAULT_CHANNEL,
        "last_checked_time": None,
        "last_version_checked": None,
    }
    if cfg_file.is_file():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                default_cfg.update(loaded)
        except Exception:
            pass
    return default_cfg


def save_update_config(data_dir: Path, cfg: Dict[str, Any]) -> bool:
    cfg_file = get_update_config_file(data_dir)
    try:
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
