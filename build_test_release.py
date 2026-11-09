"""build_test_release.py — BUILD BẢN THỬ NGHIỆM ĐỘC LẬP T-TTS v3.0 DESKTOP
=============================================================================
Đóng gói ra thư mục riêng biệt: `release_test/T-TTS_v3.0_Desktop/`
Không ghi đè hoặc ảnh hưởng đến bản ổn định trước đó.
"""

import os
import sys
import json
import shutil
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from backend.version import APP_VERSION

DIST = ROOT / "dist"
RELEASE_TEST_DIR = ROOT / "release_test" / f"T-TTS_v{APP_VERSION}_Desktop"
PYTHON_EXE = ROOT / "python312" / "python" / "python.exe"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


def run_cmd(cmd, cwd=ROOT):
    log(f"CHẠY LỆNH: {' '.join(str(c) for c in cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(
        cmd,
        cwd=cwd,
        shell=isinstance(cmd, str),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if res.stdout:
        for l in res.stdout.strip().splitlines()[-15:]:
            log(f"  [STDOUT] {l}")
    if res.stderr:
        for l in res.stderr.strip().splitlines()[-15:]:
            log(f"  [STDERR] {l}")
    if res.returncode != 0:
        log(f"LỖI (Return code {res.returncode})")
        raise RuntimeError(f"Lệnh thất bại với mã lỗi {res.returncode}")
    log(f"[OK] Hoàn thành lệnh thành công (code 0)")
    return res


def main():
    start_time = time.time()
    log("================================================================================")
    log("BẮT ĐẦU BUILD BẢN NATIVE DESKTOP: release_test/T-TTS_v2.0_Desktop")
    log("================================================================================")

    # 1. Chạy PyInstaller với t_tts_test.spec (bỏ qua nếu có cờ --skip-pyi)
    built_dir = DIST / f"T-TTS_v{APP_VERSION}_Desktop"
    if "--skip-pyi" in sys.argv and built_dir.exists():
        log(f"⚡ [SKIP-PYI] Đã có thư mục build sẵn tại {built_dir}, bỏ qua biên dịch lại.")
    else:
        spec_path = ROOT / "t_tts_test.spec"
        if not spec_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file spec: {spec_path}")

        pyi_cmd = [str(PYTHON_EXE), "-m", "PyInstaller", "--clean", "-y", str(spec_path)]
        run_cmd(pyi_cmd)

    if not built_dir.exists():
        raise FileNotFoundError(f"Thư mục build {built_dir} không tồn tại sau khi PyInstaller chạy!")

    # 2. Chuyển/Sao chép sang release_test/T-TTS_v2.0_Desktop
    log(f"\n--- BƯỚC 2: SAO CHÉP BUILD SANG {RELEASE_TEST_DIR} ---")
    if RELEASE_TEST_DIR.exists():
        shutil.rmtree(RELEASE_TEST_DIR)
    RELEASE_TEST_DIR.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(built_dir, RELEASE_TEST_DIR)

    internal_dir = RELEASE_TEST_DIR / "_internal"

    # 3. Đồng bộ Visual C++ Runtime DLLs
    log("\n--- BƯỚC 3: ĐỒNG BỘ VC RUNTIME DLLS VÀO _INTERNAL ---")
    sys32 = Path(r"C:\Windows\System32")
    for dll_name in ["msvcp140.dll", "msvcp140_1.dll", "vcruntime140.dll", "vcruntime140_1.dll"]:
        sys_dll = sys32 / dll_name
        if sys_dll.exists():
            shutil.copy2(sys_dll, internal_dir / dll_name)
    log("[OK] Đã cập nhật VC Runtime DLLs từ System32")

    # 4. Sao chép tài nguyên vieneu/assets và sea_g2p nếu thiếu
    sp_dir = ROOT / "python312" / "python" / "Lib" / "site-packages"
    dst_vieneu_assets = internal_dir / "vieneu" / "assets"
    if not dst_vieneu_assets.exists():
        src_vieneu_assets = sp_dir / "vieneu" / "assets"
        if src_vieneu_assets.exists():
            shutil.copytree(src_vieneu_assets, dst_vieneu_assets)
            log("[OK] Đã sao chép vieneu/assets vào _internal")

    dst_seag2p_bin = internal_dir / "sea_g2p" / "sea_g2p.bin"
    if not dst_seag2p_bin.exists():
        src_seag2p_bin = sp_dir / "sea_g2p" / "sea_g2p.bin"
        if src_seag2p_bin.exists():
            dst_seag2p_bin.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_seag2p_bin, dst_seag2p_bin)
            log("[OK] Đã sao chép sea_g2p.bin vào _internal")

    dst_sd = internal_dir / "_sounddevice_data"
    if not dst_sd.exists():
        src_sd = sp_dir / "_sounddevice_data"
        if src_sd.exists():
            shutil.copytree(src_sd, dst_sd)
            log("[OK] Đã sao chép _sounddevice_data vào _internal")

    # 5. Sao chép models, data, output
    log("\n--- BƯỚC 4: SAO CHÉP MODELS, DATA, OUTPUT VÀO THƯ MỤC THỬ NGHIỆM ---")
    src_models = ROOT / "models"
    dst_models = RELEASE_TEST_DIR / "models"
    if src_models.exists():
        if dst_models.exists():
            shutil.rmtree(dst_models)
        shutil.copytree(src_models, dst_models)
        log("[OK] Đã sao chép thư mục models/ đầy đủ vào release_test")

    # Đồng bộ cả sang built_dir trong dist nếu người dùng mở từ dist
    dst_models_dist = built_dir / "models"
    if src_models.exists():
        if dst_models_dist.exists():
            shutil.rmtree(dst_models_dist)
        shutil.copytree(src_models, dst_models_dist)
        log("[OK] Đã sao chép thư mục models/ đầy đủ vào dist")

    # Chuẩn bị thư mục data/ sạch cho bản phát hành (Không chứa license cá nhân hoặc dự án thử nghiệm)
    dst_data = RELEASE_TEST_DIR / "data"
    dst_data.mkdir(parents=True, exist_ok=True)
    (dst_data / "logs").mkdir(parents=True, exist_ok=True)
    (dst_data / "presets").mkdir(parents=True, exist_ok=True)
    for p_sub in ["audio", "broadcast", "documents", "schedules"]:
        (dst_data / "projects" / p_sub).mkdir(parents=True, exist_ok=True)

    # Cấu hình mặc định sạch
    default_cfg = {
        "channel": "stable",
        "github_repo": "tiepheo37/T-TTS",
        "auto_check_on_startup": True,
        "last_checked_time": "",
        "last_version_checked": APP_VERSION,
    }
    (dst_data / "update_config.json").write_text(json.dumps(default_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    (dst_data / "custom_voices.json").write_text("{}", encoding="utf-8")
    (dst_data / "history.json").write_text("[]", encoding="utf-8")

    src_dict = ROOT / "data" / "pronunciation-dict.json"
    if src_dict.exists():
        shutil.copy2(src_dict, dst_data / "pronunciation-dict.json")
    else:
        (dst_data / "pronunciation-dict.json").write_text(json.dumps({"UBND": "ủy ban nhân dân", "QĐND": "quân đội nhân dân"}, ensure_ascii=False, indent=2), encoding="utf-8")

    src_presets = ROOT / "data" / "presets" / "audio_presets.json"
    if src_presets.exists():
        shutil.copy2(src_presets, dst_data / "presets" / "audio_presets.json")
    else:
        default_presets = {
            "version": APP_VERSION,
            "presets": {
                "military_comm": {"name": "Truyền thanh Doanh trại", "eq_low": -2.0, "eq_mid": 2.5, "eq_high": 1.0, "lufs": -16.0},
                "studio_narrator": {"name": "Thuyết minh Tài liệu Quân sự", "eq_low": 0.5, "eq_mid": 1.0, "eq_high": 2.0, "lufs": -18.0},
                "field_radio": {"name": "Bộ đàm Dã chiến", "eq_low": -6.0, "eq_mid": 4.0, "eq_high": -3.0, "lufs": -14.0},
            }
        }
        (dst_data / "presets" / "audio_presets.json").write_text(json.dumps(default_presets, ensure_ascii=False, indent=2), encoding="utf-8")

    # Loại bỏ tuyệt đối license cá nhân nếu còn sót lại trong release_test
    (dst_data / "license_state.json").unlink(missing_ok=True)
    (dst_data / ".sys_lic_vault.dat").unlink(missing_ok=True)
    log("[OK] Đã chuẩn bị cấu trúc data/ sạch (100% không chứa license cá nhân hay dự án thừa)")

    dst_output = RELEASE_TEST_DIR / "output"
    dst_output.mkdir(parents=True, exist_ok=True)
    (dst_output / "uploads").mkdir(parents=True, exist_ok=True)

    # Cờ portable.txt
    (RELEASE_TEST_DIR / "portable.txt").write_text(f"T-TTS v{APP_VERSION} Desktop Portable Flag", encoding="utf-8")
    if built_dir.exists():
        (built_dir / "portable.txt").write_text(f"T-TTS v{APP_VERSION} Desktop Portable Flag", encoding="utf-8")

    # Icon & Phù hiệu Quân đội
    if (ROOT / "app_icon.ico").exists():
        shutil.copy2(ROOT / "app_icon.ico", RELEASE_TEST_DIR / "app_icon.ico")
    
    src_assets = ROOT / "gui" / "assets"
    if src_assets.exists():
        dst_assets1 = internal_dir / "gui" / "assets"
        dst_assets1.mkdir(parents=True, exist_ok=True)
        for f in src_assets.glob("*"):
            shutil.copy2(f, dst_assets1 / f.name)

        dst_assets2 = RELEASE_TEST_DIR / "gui" / "assets"
        dst_assets2.mkdir(parents=True, exist_ok=True)
        for f in src_assets.glob("*"):
            shutil.copy2(f, dst_assets2 / f.name)
        log("[OK] Đã sao chép phù hiệu Quân đội nhân dân Việt Nam vào assets")

    # 6. Tạo file Hướng dẫn sử dụng & Chẩn đoán lỗi cơ bản
    guide_txt = f"""================================================================================
T-TTS v{APP_VERSION} — PHẦN MỀM CHUYỂN VĂN BẢN THÀNH GIỌNG NÓI TIẾNG VIỆT
BẢN NATIVE DESKTOP WINDOWS (PORTABLE)
================================================================================
Tác giả: Nguyễn Văn Tiệp
Mô hình giọng nói: VieNeu-TTS v3 Turbo do Phạm Nguyễn Ngọc Bảo phát triển.
Công nghệ suy luận: ONNX Runtime Lite CPU (100% Offline, không phụ thuộc GPU).

1. CÁCH KHỞI CHẠY:
   - Nhấp đúp vào file "T-TTS.exe" trong thư mục này để mở phần mềm.
   - Không cần cài đặt, không cần kết nối Internet, không mở trình duyệt.

2. CÁC TÍNH NĂNG CHÍNH:
   - Tạo giọng nói: Nhập văn bản tiếng Việt, chọn trong 25 giọng đọc chuẩn allowlist.
   - Nhân bản giọng: Tải file âm thanh mẫu (WAV/MP3 5-15s) để tạo giọng riêng.
   - Xử lý hàng loạt: Đọc danh sách nhiều câu hoặc nhiều file văn bản cùng lúc.
   - Quản lý giọng: Nghe thử và quản lý 25 giọng preset cùng các giọng nhân bản.
   - Từ điển phát âm: Thêm quy tắc thay thế từ viết tắt, thuật ngữ nước ngoài.
   - Lịch sử: Tra cứu và nghe lại các tệp âm thanh đã tạo trước đó.
   - Bản quyền & Giấy phép: Xem mã máy, hạn sử dụng và kích hoạt key.

3. HỖ TRỢ 6 GÓI BẢN QUYỀN OFFLINE:
   - 1 Ngày: Dùng thử 24 giờ.
   - 7 Ngày: Trải nghiệm 168 giờ.
   - 30 Ngày: Dùng thử 1 tháng (720 giờ).
   - 6 Tháng: Cấp phép nửa năm theo ngày lịch.
   - 1 Năm: Cấp phép 1 năm theo ngày lịch.
   - Vĩnh Viễn: Sử dụng trọn đời không giới hạn thời gian.
================================================================================
"""
    (RELEASE_TEST_DIR / "HUONG_DAN_SU_DUNG.txt").write_text(guide_txt, encoding="utf-8")

    troubleshoot_txt = f"""================================================================================
HƯỚNG DẪN CHẨN ĐOÁN VÀ KHẮC PHỤC SỰ CỐ T-TTS v{APP_VERSION}
================================================================================
1. LỖI THIẾU DLL (VCRUNTIME140.dll hoặc MSVCP140.dll):
   - Bản phát hành đã tích hợp sẵn các DLL này trong thư mục _internal.
   - Nếu vẫn báo lỗi, hãy cài đặt gói "Visual C++ Redistributable 2015-2022 x64" từ Microsoft.

2. MÔ HÌNH BÁO "KHỞI TẠO MÔ HÌNH THẤT BẠI":
   - Kiểm tra thư mục "models/" ngay cạnh file T-TTS.exe.
   - Phải có đầy đủ 2 thư mục con: "v3turbo_onnx" và "moss_codec" cùng các tệp .onnx, .data.

3. PHẦN MỀM BÁO "CHƯA KÍCH HOẠT" HOẶC "BẢN QUYỀN HẾT HẠN":
   - Vào mục "Bản quyền & Giấy phép" -> Bấm "Kích Hoạt / Nhập Key Mới".
   - Sao chép Mã Máy (Machine ID) gửi cho Nguyễn Văn Tiệp để nhận key mới.
   - Dán chuỗi key hoặc nạp file .lic được cấp và bấm "Kích Hoạt".

4. KHÔNG NGHE THẤY ÂM THANH:
   - Kiểm tra âm lượng hệ thống Windows và loa ngoài/tai nghe.
   - Bấm nút "Mở thư mục" để mở trực tiếp file .wav bằng phần mềm nghe nhạc Windows.
================================================================================
"""
    (RELEASE_TEST_DIR / "CHAN_DOAN_VA_KHAC_PHUC_SU_CO.txt").write_text(troubleshoot_txt, encoding="utf-8")

    elapsed = time.time() - start_time
    log("================================================================================")
    log(f"🎉 BUILD THÀNH CÔNG BẢN T-TTS v2.0 DESKTOP TRONG {elapsed:.1f} GIÂY!")
    log(f"📁 Thư mục xuất: {RELEASE_TEST_DIR}")
    log(f"🚀 File chạy: {RELEASE_TEST_DIR / 'T-TTS.exe'}")
    log("================================================================================")


if __name__ == "__main__":
    main()
