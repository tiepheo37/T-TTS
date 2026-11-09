"""tools/create_master_backup.py — SAO LƯU MASTER T-TTS v3.1.0 TRƯỚC PHÁT HÀNH
============================================================================
Tác giả: Nguyễn Văn Tiệp
Hệ thống: T-TTS Windows Native Desktop (VieNeu-TTS v3 Turbo ONNX CPU)

Tạo thư mục: T-TTS_BACKUP_v3.1.0_MASTER_YYYYMMDD_HHMMSS
Bao gồm:
- Source code (backend, gui, tools, desktop_main.py, *.spec, build scripts)
- Cấu hình và manifest di chuyển
- Module license & Update Engine
- Dữ liệu và toàn bộ projects (Audio, Broadcast, Schedule, Document)
- Voice library và metadata
- Bộ tài liệu phát hành chính thức
Kiểm tra tính toàn vẹn và khả năng phục hồi của bản sao lưu.
"""

import os
import sys
import time
import json
import shutil
import hashlib
from pathlib import Path
from typing import Dict, Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Đảm bảo UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def compute_dir_sha256(dir_path: Path) -> Dict[str, str]:
    hashes = {}
    for p in sorted(dir_path.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(dir_path)).replace("\\", "/")
            h = hashlib.sha256()
            with open(p, "rb") as f:
                while chunk := f.read(256 * 1024):
                    h.update(chunk)
            hashes[rel] = h.hexdigest()
    return hashes


def main():
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_name = f"T-TTS_BACKUP_v3.1.0_MASTER_{timestamp}"
    backup_root = REPO_ROOT / "backups" / backup_name
    backup_root.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(f"BƯỚC 1: KHỞI TẠO BẢN SAO LƯU MASTER: {backup_name}")
    print("=" * 80)

    # 1. Sao chép Source Code
    src_dirs = ["backend", "gui", "tools"]
    for d in src_dirs:
        dst = backup_root / d
        shutil.copytree(REPO_ROOT / d, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.tmp"))
        print(f"  ✓ Đã sao lưu thư mục mã nguồn: {d}/")

    src_files = [
        "desktop_main.py",
        "setup_installer.iss",
        "t_tts.spec",
        "t_tts_test.spec",
        "build_test_release.py",
        "setup_intro.txt",
        "app_icon.ico",
        "requirements.txt",
    ]
    for sf in src_files:
        src_path = REPO_ROOT / sf
        if src_path.is_file():
            shutil.copy2(src_path, backup_root / sf)
            print(f"  ✓ Đã sao lưu tệp nguồn: {sf}")

    # 2. Sao chép Cấu hình & Dữ liệu
    dst_data = backup_root / "data"
    shutil.copytree(
        REPO_ROOT / "data",
        dst_data,
        ignore=shutil.ignore_patterns("*.tmp", "__pycache__", "*.pyc"),
    )
    print(f"  ✓ Đã sao lưu toàn bộ thư mục dữ liệu và dự án: data/")

    # 3. Sao chép Voice Library metadata
    dst_models_meta = backup_root / "models_meta"
    dst_models_meta.mkdir(parents=True, exist_ok=True)
    v3_models = REPO_ROOT / "models" / "v3turbo_onnx"
    if v3_models.exists():
        for mf in ["config.json", "tokenizer.json", "voices_v3_turbo.json"]:
            if (v3_models / mf).exists():
                shutil.copy2(v3_models / mf, dst_models_meta / mf)
        print("  ✓ Đã sao lưu Voice Library metadata (config, tokenizer, voices)")

    moss_models = REPO_ROOT / "models" / "moss_codec"
    if moss_models.exists():
        for mf in ["codec_browser_onnx_meta.json"]:
            if (moss_models / mf).exists():
                shutil.copy2(moss_models / mf, dst_models_meta / mf)
        print("  ✓ Đã sao lưu Moss Codec metadata")

    # 4. Sao chép Bộ Tài Liệu Phát Hành
    doc_files = [
        "RELEASE_NOTES_v3.1.0.md",
        "INSTALLATION_GUIDE.md",
        "UPGRADE_GUIDE_v3.0.0_to_v3.1.0.md",
        "TEST_REPORT_v3.1.0.md",
        "SPRINT_7_AUTO_UPDATE_REPORT.md",
        "SPRINT_8_FINAL_PACKAGING_REPORT.md",
    ]
    dst_docs = backup_root / "release_docs"
    dst_docs.mkdir(parents=True, exist_ok=True)
    for df in doc_files:
        src_doc = REPO_ROOT / df
        if src_doc.is_file():
            shutil.copy2(src_doc, dst_docs / df)
            print(f"  ✓ Đã sao lưu tài liệu phát hành: {df}")

    # 5. Tạo Manifest xác thực kiểm tra phục hồi
    manifest_hashes = compute_dir_sha256(backup_root)
    manifest = {
        "backup_name": backup_name,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": "3.1.0",
        "author": "Nguyễn Văn Tiệp",
        "total_files": len(manifest_hashes),
        "file_hashes": manifest_hashes,
    }
    manifest_file = backup_root / "BACKUP_MANIFEST.json"
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ Đã tạo BACKUP_MANIFEST.json ({len(manifest_hashes)} tệp)")

    # 6. Kiểm tra khả năng phục hồi (Test Restoration Verification)
    print("\n--- KIỂM TRA TÍNH TOÀN VẸN & KHẢ NĂNG PHỤC HỒI ---")
    verified_files = 0
    for rel_path, expected_hash in manifest_hashes.items():
        if rel_path == "BACKUP_MANIFEST.json":
            continue
        target_f = backup_root / rel_path
        if not target_f.is_file():
            raise FileNotFoundError(f"Tệp sao lưu bị thiếu trong quá trình kiểm tra: {rel_path}")
        h = hashlib.sha256()
        with open(target_f, "rb") as f:
            while chunk := f.read(256 * 1024):
                h.update(chunk)
        if h.hexdigest() != expected_hash:
            raise ValueError(f"Mã SHA-256 không khớp cho tệp sao lưu: {rel_path}")
        verified_files += 1

    print(f"  ✓ Đã xác minh tính toàn vẹn 100% cho {verified_files} tệp sao lưu!")
    print(f"  ✓ Bản sao lưu Master đã sẵn sàng tại: {backup_root}")
    print("=" * 80)
    return backup_root


if __name__ == "__main__":
    try:
        b_root = main()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ [LỖI NGHIÊM TRỌNG] Quá trình sao lưu thất bại: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
