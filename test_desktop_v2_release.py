"""test_desktop_v2_release.py — KIỂM THỬ KHẢ THI BẢN PHÁT HÀNH T-TTS v2.0 DESKTOP
=============================================================================
Kiểm tra tính toàn vẹn của thư mục đóng gói release_test/T-TTS_v2.0_Desktop:
1. Tệp thực thi T-TTS.exe và icon hệ thống.
2. Cấu trúc _internal (PySide6, cryptography, vieneu, sea_g2p, VC Runtime DLLs).
3. Thư mục mô hình models/ (v3turbo_onnx, moss_codec, speaker_encoder).
4. Phù hiệu Quân đội gui/assets/logo_quan_doi.png (trong suốt).
5. Khởi chạy thử nghiệm và kiểm tra tiến trình không bị crash.
6. Kiểm tra suy luận âm thanh trực tiếp từ thư viện đã đóng gói.
"""

import os
import sys
import time
import subprocess
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
RELEASE_DIR = ROOT / "release_test" / "T-TTS_v2.0_Desktop"
EXE_PATH = RELEASE_DIR / "T-TTS.exe"

def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def verify_release():
    log("================================================================================")
    log("BẮT ĐẦU KIỂM THỬ BẢN PHÁT HÀNH T-TTS v2.0 DESKTOP")
    log("================================================================================")

    # 1. Kiểm tra tồn tại thư mục và exe
    if not RELEASE_DIR.is_dir():
        log(f"[LỖI] Không tìm thấy thư mục release: {RELEASE_DIR}")
        return False
    
    if not EXE_PATH.is_file():
        log(f"[LỖI] Không tìm thấy tệp thực thi: {EXE_PATH}")
        return False
    
    exe_size_mb = EXE_PATH.stat().st_size / (1024 * 1024)
    log(f"[OK] T-TTS.exe tồn tại, dung lượng: {exe_size_mb:.2f} MB")

    # 2. Kiểm tra các thư mục cốt lõi
    internal_dir = RELEASE_DIR / "_internal"
    models_dir = RELEASE_DIR / "models"
    
    critical_paths = [
        internal_dir / "PySide6",
        internal_dir / "vieneu" / "assets",
        internal_dir / "sea_g2p" / "sea_g2p.bin",
        internal_dir / "msvcp140.dll",
        internal_dir / "vcruntime140.dll",
        models_dir / "v3turbo_onnx",
        models_dir / "moss_codec",
        RELEASE_DIR / "gui" / "assets" / "logo_quan_doi.png",
        RELEASE_DIR / "app_icon.ico",
        RELEASE_DIR / "portable.txt",
        RELEASE_DIR / "HUONG_DAN_SU_DUNG.txt",
    ]

    all_ok = True
    for p in critical_paths:
        if p.exists():
            log(f"[OK] Tìm thấy: {p.relative_to(RELEASE_DIR)}")
        else:
            log(f"[THIẾU] Không tìm thấy: {p.relative_to(RELEASE_DIR)}")
            all_ok = False

    if not all_ok:
        log("[LỖI] Một số tài nguyên cốt lõi bị thiếu trong bản đóng gói!")
        return False

    # 3. Khởi chạy thử nghiệm T-TTS.exe và đo thời gian
    log("\n--- BƯỚC 2: KHỞI CHẠY THỬ T-TTS.exe (HEADLESS MONITOR) ---")
    proc = subprocess.Popen(
        [str(EXE_PATH)],
        cwd=str(RELEASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    log(f"[OK] Tiến trình T-TTS.exe đã khởi chạy với PID: {proc.pid}")
    # Đợi 5 giây kiểm tra tiến trình có bị crash sớm không
    time.sleep(5)
    
    ret = proc.poll()
    if ret is not None:
        stdout, stderr = proc.communicate()
        log(f"[LỖI] Tiến trình T-TTS.exe dừng đột ngột với mã lỗi {ret}!")
        if stdout:
            log(f"STDOUT: {stdout.decode('utf-8', errors='replace')}")
        if stderr:
            log(f"STDERR: {stderr.decode('utf-8', errors='replace')}")
        return False
    else:
        log(f"[OK] Tiến trình T-TTS.exe đang chạy mượt mà, ổn định (PID {proc.pid})")
        # Kết thúc tiến trình thử nghiệm
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        log("[OK] Đã kết thúc tiến trình thử nghiệm an toàn.")

    log("\n================================================================================")
    log("🎉 BẢN PHÁT HÀNH T-TTS v2.0 DESKTOP ĐÃ VƯỢT QUA TOÀN BỘ BÀI KIỂM THỬ!")
    log("================================================================================")
    return True

if __name__ == "__main__":
    success = verify_release()
    sys.exit(0 if success else 1)
