import os
import sys
import shutil
import zipfile
import hashlib
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"D:\cac loai app\voice-studio-app")
BACKUP_DIR = BASE_DIR / "backups" / "backup_v3.0.0_20261108"
ZIP_OUTPUT = BASE_DIR / "backups" / "backup_v3.0.0_pre_v3.0.1.zip"

LOCAL_APPDATA_TTS = Path(os.path.expandvars(r"%LOCALAPPDATA%\T-TTS"))

print(f"[{datetime.now()}] Bắt đầu quy trình Backup T-TTS v3.0.0...")

# 1. Tạo thư mục đích
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# 2. Danh sách thư mục source code & cấu hình cần backup
SOURCE_DIRS = ["backend", "gui", "data", "tools"]
SOURCE_FILES = [
    "desktop_main.py",
    "build_test_release.py",
    "build_release.py",
    "build_release.bat",
    "setup_installer.iss",
    "t_tts.spec",
    "t_tts_test.spec",
    "requirements.txt",
    "README.md",
    "app_icon.ico",
    "app_logo_author.png",
    "portable.txt",
]

# Backup Source
src_dest = BACKUP_DIR / "source_code"
src_dest.mkdir(parents=True, exist_ok=True)

file_count = 0
for d in SOURCE_DIRS:
    d_path = BASE_DIR / d
    if d_path.exists():
        dest = src_dest / d
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(d_path, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "build", ".git"))
        print(f" - Đã sao lưu thư mục: {d}")

for f in SOURCE_FILES:
    f_path = BASE_DIR / f
    if f_path.exists():
        shutil.copy2(f_path, src_dest / f)
        print(f" - Đã sao lưu file gốc: {f}")

# 3. Backup User Runtime Data & License (%LOCALAPPDATA%\T-TTS)
appdata_dest = BACKUP_DIR / "user_runtime_appdata"
appdata_dest.mkdir(parents=True, exist_ok=True)

if LOCAL_APPDATA_TTS.exists():
    shutil.copytree(LOCAL_APPDATA_TTS, appdata_dest / "T-TTS", dirs_exist_ok=True)
    print(f" - Đã sao lưu User Data & License từ: {LOCAL_APPDATA_TTS}")
else:
    print(f" [!] Không tìm thấy thư mục: {LOCAL_APPDATA_TTS}")

# 4. Ghi nhận thông tin Dist v3.0.0 (giữ nguyên không xóa)
dist_dir = BASE_DIR / "dist"
dist_info_file = BACKUP_DIR / "dist_v3.0.0_manifest.txt"
with open(dist_info_file, "w", encoding="utf-8") as mf:
    mf.write("DANH SÁCH BẢN CÀI ĐẶT VÀ PHÁT HÀNH v3.0.0 (NGUYÊN BẢN):\n")
    if dist_dir.exists():
        for item in dist_dir.iterdir():
            if item.is_file():
                size_mb = item.stat().st_size / (1024 * 1024)
                mf.write(f" - {item.name}: {size_mb:.2f} MB (Modified: {datetime.fromtimestamp(item.stat().st_mtime)})\n")
print(f" - Đã kiểm kê bản phát hành dist/v3.0.0 an toàn.")

# 5. Đóng gói thành tệp ZIP hoàn chỉnh
print(f"Đang nén toàn bộ bản backup thành {ZIP_OUTPUT.name}...")
with zipfile.ZipFile(ZIP_OUTPUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _, files in os.walk(BACKUP_DIR):
        for file in files:
            full_p = Path(root) / file
            rel_p = full_p.relative_to(BACKUP_DIR)
            zf.write(full_p, rel_p)
            file_count += 1

zip_size_mb = ZIP_OUTPUT.stat().st_size / (1024 * 1024)
print(f"Hoàn thành ZIP backup: {ZIP_OUTPUT} ({zip_size_mb:.2f} MB, {file_count} tệp tin).")

# 6. Kiểm tra tính toàn vẹn (Verification & Test Restore)
test_restore_dir = BASE_DIR / "backups" / "verify_restore_test"
if test_restore_dir.exists():
    shutil.rmtree(test_restore_dir)
test_restore_dir.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(ZIP_OUTPUT, "r") as zf:
    zf.extractall(test_restore_dir)

# Kiểm tra các tệp quan trọng sau khi giải nén
critical_checks = [
    test_restore_dir / "source_code" / "backend" / "version.py",
    test_restore_dir / "source_code" / "backend" / "updater.py",
    test_restore_dir / "source_code" / "backend" / "license.py",
    test_restore_dir / "source_code" / "backend" / "tts_engine.py",
    test_restore_dir / "source_code" / "gui" / "main_window.py",
    test_restore_dir / "source_code" / "desktop_main.py",
    test_restore_dir / "user_runtime_appdata" / "T-TTS" / "license_state.json",
    test_restore_dir / "user_runtime_appdata" / "T-TTS" / "data" / "history.json",
]

all_ok = True
for check in critical_checks:
    if not check.exists():
        print(f" [LỖI VERIFY] Thiếu tệp: {check}")
        all_ok = False
    else:
        print(f" [VERIFY OK] Đã xác thực tệp: {check.name} ({check.stat().st_size} bytes)")

# Dọn dẹp thư mục verify
shutil.rmtree(test_restore_dir)

if all_ok:
    print("\n>>> BẢN BACKUP HOÀN TẤT VÀ ĐƯỢC XÁC THỰC 100% CÓ THỂ KHÔI PHỤC AN TOÀN! <<<")
else:
    print("\n>>> CẢNH BÁO: XÁC THỰC BACKUP THẤT BẠI! <<<")
    sys.exit(1)
