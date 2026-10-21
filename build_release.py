"""Kịch bản build tự động T-TTS v1.0.1:
1. PyInstaller: đóng gói ra dist/T-TTS_v1.0.1_Exe_Portable
2. Sao chép tài nguyên: models, data, output, README_WINDOWS.txt, portable.txt
3. Kiểm tra toàn bộ đường dẫn Source trong setup_installer.iss
4. Inno Setup: biên dịch dist/T-TTS_v1.0.1_Setup_Installer.exe
5. Ghi nhật ký đầy đủ ra build-log.txt
"""
import os
import sys
import shutil
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD_LOG = ROOT / "build-log.txt"
PORTABLE_DIR = DIST / "T-TTS_v1.0.1_Exe_Portable"
PYTHON_EXE = ROOT / "python312" / "python" / "python.exe"
ISCC_EXE = Path(r"C:\Users\Minh Dang\AppData\Local\Programs\Antigravity IDE\resources\app\node_modules\innosetup\bin\ISCC.exe")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

log_entries = []

def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    log_entries.append(line)

def run_cmd(cmd, cwd=ROOT):
    log(f"CHẠY LỆNH: {' '.join(str(c) for c in cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.stdout:
        for l in res.stdout.strip().splitlines()[-25:]: # ghi 25 dòng cuối
            log(f"  [STDOUT] {l}")
    if res.stderr:
        for l in res.stderr.strip().splitlines()[-25:]:
            log(f"  [STDERR] {l}")
    if res.returncode != 0:
        log(f"LỖI (Return code {res.returncode})")
        raise RuntimeError(f"Lệnh thất bại với mã lỗi {res.returncode}")
    log(f"[OK] Lệnh hoàn thành thành công (code 0)")
    return res

def main():
    start_time = time.time()
    log("================================================================================")
    log("BẮT ĐẦU QUY TRÌNH BUILD T-TTS v1.0.1 (PORTABLE & INNO SETUP INSTALLER)")
    log("================================================================================")

    # 1. Chạy PyInstaller
    if "--skip-pyi" in sys.argv and (PORTABLE_DIR / "T-TTS.exe").exists():
        log("\n--- BƯỚC 1: BỎ QUA PYINSTALLER (--skip-pyi) VÌ BINARY ĐÃ TỒN TẠI ---")
    else:
        log("\n--- BƯỚC 1: BUILD PYINSTALLER THỐNG NHẤT RA T-TTS_v1.0.1_Exe_Portable ---")
        spec_path = ROOT / "t_tts.spec"
        if not spec_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file spec: {spec_path}")
        
        pyi_cmd = [str(PYTHON_EXE), "-m", "PyInstaller", "--clean", "-y", str(spec_path)]
        run_cmd(pyi_cmd)

    # 2. Bổ sung các thư mục tài nguyên và file hướng dẫn vào thư mục portable
    log("\n--- BƯỚC 2: SAO CHÉP MODELS, DATA, OUTPUT, README_WINDOWS.txt VÀO PORTABLE ---")
    if not PORTABLE_DIR.exists():
        raise FileNotFoundError(f"Thư mục portable {PORTABLE_DIR} không tồn tại sau khi PyInstaller chạy!")

    # Đồng bộ Visual C++ Runtime DLLs tương thích ONNX Runtime (tránh crash 0xc0000005)
    sys32 = Path(r"C:\Windows\System32")
    internal_dir = PORTABLE_DIR / "_internal"
    for dll_name in ["msvcp140.dll", "msvcp140_1.dll", "vcruntime140.dll", "vcruntime140_1.dll"]:
        sys_dll = sys32 / dll_name
        if sys_dll.exists():
            shutil.copy2(sys_dll, internal_dir / dll_name)
    log("[OK] Đã cập nhật VC Runtime DLLs từ System32 vào _internal để tương thích ONNX Runtime")

    # Đảm bảo tài nguyên vieneu/assets (giọng preset mẫu) và sea_g2p (từ điển phát âm Rust)
    sp_dir = ROOT / "python312" / "python" / "Lib" / "site-packages"
    dst_vieneu_assets = internal_dir / "vieneu" / "assets"
    if not dst_vieneu_assets.exists():
        src_vieneu_assets = sp_dir / "vieneu" / "assets"
        if src_vieneu_assets.exists():
            shutil.copytree(src_vieneu_assets, dst_vieneu_assets)
            log("[OK] Đã bổ sung vieneu/assets vào _internal")

    dst_seag2p_bin = internal_dir / "sea_g2p" / "sea_g2p.bin"
    if not dst_seag2p_bin.exists():
        src_seag2p_bin = sp_dir / "sea_g2p" / "sea_g2p.bin"
        if src_seag2p_bin.exists():
            dst_seag2p_bin.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_seag2p_bin, dst_seag2p_bin)
            log("[OK] Đã bổ sung sea_g2p/sea_g2p.bin vào _internal")

    # Models
    src_models = ROOT / "models"
    dst_models = PORTABLE_DIR / "models"
    log(f"Sao chép models từ {src_models} -> {dst_models}...")
    if dst_models.exists():
        shutil.rmtree(dst_models)
    shutil.copytree(src_models, dst_models)
    log(f"[OK] Đã sao chép models ({len(list(dst_models.rglob('*')))} files)")

    # Data
    src_data = ROOT / "data"
    dst_data = PORTABLE_DIR / "data"
    log(f"Sao chép data từ {src_data} -> {dst_data}...")
    if dst_data.exists():
        shutil.rmtree(dst_data)
    shutil.copytree(src_data, dst_data)
    log(f"[OK] Đã sao chép data ({len(list(dst_data.rglob('*')))} files)")

    # Output (đảm bảo tồn tại và có file giữ chỗ để Inno Setup không báo lỗi rỗng)
    dst_output = PORTABLE_DIR / "output"
    dst_output.mkdir(parents=True, exist_ok=True)
    gitkeep = dst_output / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("T-TTS output placeholder\n", encoding="utf-8")
    log(f"[OK] Đã khởi tạo thư mục output tại {dst_output}")

    # Sao chép app_icon.ico vào portable dir
    src_icon = ROOT / "app_icon.ico"
    if src_icon.exists():
        shutil.copy2(src_icon, PORTABLE_DIR / "app_icon.ico")
        log(f"[OK] Đã sao chép app_icon.ico vào {PORTABLE_DIR}")

    # README_WINDOWS.txt
    readme_text = """========================================================================
T-TTS v1.0.1 — PHẦN MỀM CHUYỂN VĂN BẢN THÀNH GIỌNG NÓI TIẾNG VIỆT
========================================================================

T-TTS do Tiệp Nguyễn phát triển.
Sử dụng mô hình giọng nói VieNeu-TTS của tác giả Phạm Nguyễn Ngọc Bảo.

HƯỚNG DẪN SỬ DỤNG CHẠY OFFLINE TRÊN WINDOWS 10/11:

1. KHỞI ĐỘNG ỨNG DỤNG:
   - Nhấp đôi biểu tượng `T-TTS` trên Desktop, Start Menu hoặc file `T-TTS.exe`.
   - Giao diện mở trực tiếp trong cửa sổ ứng dụng Windows (Microsoft Edge WebView2).
   - Không yêu cầu mở trình duyệt bên ngoài (Chrome/Edge), không mở cửa sổ console đen.

2. TÍNH NĂNG NỔI BẬT:
   - Đủ 25 giọng đọc preset truyền cảm chuẩn tiếng Việt (Hải Đăng, Mai Anh, Trúc Ly...)
   - Chỉnh tốc độ đọc chuẩn WSOLA từ 0.75x đến 1.50x (giữ nguyên cao độ giọng).
   - Thẻ cảm xúc [cười], [hắng giọng], [thở dài] và thẻ nghỉ [nghỉ 500ms], [nghỉ 2s].
   - Tạo giọng nói hàng loạt theo mốc [P1], [P2]... và tải bộ file .ZIP.
   - Trích xuất văn bản từ file PDF, DOCX, TXT kèm tính năng làm sạch văn bản.
   - Tạo file âm thanh WAV/MP3 kèm file phụ đề .SRT mốc thời gian từng câu.
   - Lồng tiếng tự động theo file phụ đề .SRT/.VTT (tự cân chỉnh tốc độ không cắt chữ).
   - Kịch bản hội thoại nhiều nhân vật / Podcast.
   - Thu âm trực tiếp từ Micro để tạo giọng đọc nhân bản AI cá nhân.
   - Từ điển phát âm lưu persistent (VD: KTX -> ký túc xá).
   - Tự động quản lý lịch sử tạo audio và theo dõi dung lượng ổ đĩa.
   - Quản lý mô hình và chạy hoàn toàn offline trên CPU.

3. ĐÓNG ỨNG DỤNG:
   - Nhấn nút Đóng (X) trên góc phải cửa sổ ứng dụng để thoát hoàn toàn.
   - Tiến trình backend tự động đóng sạch sẽ.

========================================================================
"""
    readme_path = PORTABLE_DIR / "README_WINDOWS.txt"
    readme_path.write_text(readme_text, encoding="utf-8")
    log(f"[OK] Đã tạo file {readme_path}")

    # portable.txt (cờ đánh dấu chế độ portable độc lập ngoài Program Files)
    portable_flag = PORTABLE_DIR / "portable.txt"
    portable_flag.write_text("T-TTS v1.0.1 Portable Mode\n", encoding="utf-8")
    log(f"[OK] Đã tạo cờ {portable_flag}")

    # 3. Kiểm tra toàn bộ đường dẫn Source trong setup_installer.iss
    log("\n--- BƯỚC 3: KIỂM TRA TOÀN BỘ SOURCE TRONG SETUP_INSTALLER.ISS ---")
    iss_sources = [
        PORTABLE_DIR / "T-TTS.exe",
        PORTABLE_DIR / "_internal",
        PORTABLE_DIR / "models",
        PORTABLE_DIR / "README_WINDOWS.txt",
        PORTABLE_DIR / "data",
        PORTABLE_DIR / "output",
        ROOT / "app_icon.ico",
    ]
    for s in iss_sources:
        if not s.exists():
            raise FileNotFoundError(f"[LỖI CRITICAL] Source không tồn tại cho Inno Setup: {s}")
        log(f"  [VERIFIED] Source tồn tại: {s.name} ({'Thư mục' if s.is_dir() else f'File {s.stat().st_size} bytes'})")

    # 4. Biên dịch Inno Setup
    log("\n--- BƯỚC 4: BIÊN DỊCH BỘ CÀI ĐẶT INNO SETUP (ISCC) ---")
    if not ISCC_EXE.exists():
        raise FileNotFoundError(f"Không tìm thấy ISCC.exe tại {ISCC_EXE}")

    iss_file = ROOT / "setup_installer.iss"
    iscc_cmd = [str(ISCC_EXE), str(iss_file)]
    run_cmd(iscc_cmd)

    installer_exe = DIST / "T-TTS_Setup_v1.0.1_Offline.exe"
    if not installer_exe.exists():
        raise FileNotFoundError(f"Không tìm thấy file installer sau khi ISCC chạy: {installer_exe}")
    installer_mb = round(installer_exe.stat().st_size / (1024 * 1024), 2)
    log(f"[THÀNH CÔNG] Đã tạo file Inno Setup Installer: {installer_exe.name} ({installer_mb} MB)")

    # 5. Tạo file ZIP bản Portable dự phòng
    log("\n--- BƯỚC 5: TẠO FILE ZIP BẢN PORTABLE DỰ PHÒNG ---")
    zip_dest = DIST / "T-TTS_v1.0.1_Exe_Portable"
    log(f"Đang nén zip {PORTABLE_DIR} -> {zip_dest}.zip...")
    shutil.make_archive(str(zip_dest), "zip", root_dir=DIST, base_dir="T-TTS_v1.0.1_Exe_Portable")
    zip_file = DIST / "T-TTS_v1.0.1_Exe_Portable.zip"
    zip_mb = round(zip_file.stat().st_size / (1024 * 1024), 2)
    log(f"[THÀNH CÔNG] Đã tạo file Zip Portable: {zip_file.name} ({zip_mb} MB)")

    elapsed = round(time.time() - start_time, 2)
    log(f"\n================================================================================")
    log(f"HOÀN TẤT BUILD T-TTS v1.0.1 TRONG {elapsed} GIÂY")
    log(f"  - Bản Portable Exe:    {PORTABLE_DIR}")
    log(f"  - File Zip Portable:   {zip_file} ({zip_mb} MB)")
    log(f"  - File Setup Installer: {installer_exe} ({installer_mb} MB)")
    log(f"================================================================================")

    BUILD_LOG.write_text("\n".join(log_entries) + "\n", encoding="utf-8")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"[FATAL ERROR] {e}")
        BUILD_LOG.write_text("\n".join(log_entries) + f"\n[FATAL ERROR] {e}\n", encoding="utf-8")
        sys.exit(1)
