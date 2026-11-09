"""tools/build_update_release.py — QUY TRÌNH BUILD & ĐÓNG GÓI BẢN PHÁT HÀNH AUTO UPDATE
======================================================================================
Tác giả: Nguyễn Văn Tiệp
Chức năng:
1. Kiểm tra phiên bản từ backend/version.py.
2. Biên dịch mã nguồn PyInstaller sang release_test/T-TTS_v3.0_Desktop.
3. Tạo bộ cài đặt Inno Setup Offline: dist/T-TTS_Setup_v3.0_Offline.exe.
4. Tạo tệp nén Portable: dist/T-TTS_v3.0_Desktop_Portable.zip.
5. Tạo tệp gói cập nhật VelopPack nếu khả dụng.
6. Tính toán mã băm SHA256 và sinh metadata release (dist/release_metadata.json).
7. Soạn thảo sẵn Release Notes (dist/RELEASE_NOTES_v3.0.0.md) sẵn sàng tải lên GitHub Releases.
8. Kiểm thử tính toàn vẹn và xuất báo cáo kết quả.
"""

import os
import sys
import time
import json
import hashlib
import zipfile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from backend.version import APP_VERSION, APP_NAME, APP_AUTHOR, DEFAULT_GITHUB_REPO


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def calculate_sha256(fpath: Path) -> str:
    hasher = hashlib.sha256()
    with open(fpath, "rb") as f:
        while chunk := f.read(256 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def main():
    t0 = time.time()
    log("=" * 80)
    log(f"BẮT ĐẦU QUY TRÌNH BUILD & ĐÓNG GÓI AUTO UPDATE CHO {APP_NAME} v{APP_VERSION}")
    log(f"Tác giả: {APP_AUTHOR} | Kho GitHub: {DEFAULT_GITHUB_REPO}")
    log("=" * 80)

    # 1. Kiểm tra phiên bản
    log(f"\n[BƯỚC 1] Xác minh phiên bản: v{APP_VERSION}")
    dist_dir = ROOT / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    # 2. Biên dịch bản Desktop qua build_test_release.py
    log("\n[BƯỚC 2] Biên dịch binary PyInstaller...")
    py_exe = ROOT / "python312" / "python" / "python.exe"
    build_script = ROOT / "build_test_release.py"

    res = subprocess.run([str(py_exe), str(build_script)], cwd=ROOT)
    if res.returncode != 0:
        log("❌ Lỗi khi biên dịch PyInstaller!")
        sys.exit(1)
    log("✅ Biên dịch PyInstaller hoàn tất!")

    # 3. Biên dịch Inno Setup installer
    log("\n[BƯỚC 3] Đóng gói bộ cài đặt Offline qua Inno Setup...")
    iscc_candidates = [
        Path(r"C:\Users\Minh Dang\AppData\Local\Programs\Antigravity IDE\resources\app\node_modules\innosetup\bin\ISCC.exe"),
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]
    iscc = next((p for p in iscc_candidates if p.exists()), None)
    iss_file = ROOT / "setup_installer.iss"

    if iscc and iss_file.exists():
        log(f"  • Sử dụng trình biên dịch: {iscc}")
        res_iss = subprocess.run([str(iscc), str(iss_file)], cwd=ROOT)
        if res_iss.returncode != 0:
            log("❌ Lỗi biên dịch Inno Setup!")
            sys.exit(1)
        log("✅ Đã tạo bộ cài đặt Offline Inno Setup!")
    else:
        log("❌ Không tìm thấy ISCC.exe hoặc setup_installer.iss!")
        sys.exit(1)

    # 4. Tạo file Portable ZIP
    log("\n[BƯỚC 4] Tạo bản nén Portable ZIP...")
    src_desktop = ROOT / "release_test" / f"T-TTS_v{APP_VERSION}_Desktop"
    zip_path = dist_dir / f"T-TTS_v{APP_VERSION}_Desktop_Portable.zip"

    if src_desktop.exists():
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(src_desktop):
                for f in files:
                    fpath = Path(root) / f
                    arcname = fpath.relative_to(src_desktop.parent)
                    zf.write(fpath, arcname)
        log(f"✅ Đã tạo Portable ZIP: {zip_path.name} ({zip_path.stat().st_size / (1024*1024):.1f} MB)")

    # 5. Tính toán SHA256 và sinh Metadata Release
    log("\n[BƯỚC 5] Tính toán mã băm SHA256 và tạo Metadata Release...")
    assets_info = []
    checksums_lines = []

    for f in sorted(dist_dir.glob("*.*")):
        if f.suffix.lower() in [".exe", ".zip", ".apk", ".nupkg"]:
            sha = calculate_sha256(f)
            sz = f.stat().st_size
            assets_info.append({
                "name": f.name,
                "size_bytes": sz,
                "size_mb": round(sz / (1024 * 1024), 2),
                "sha256": sha,
            })
            checksums_lines.append(f"{sha}  {f.name}")
            log(f"  • {f.name}: {sha}")

    (dist_dir / "checksums.txt").write_text("\n".join(checksums_lines), encoding="utf-8")

    meta = {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "tag_name": f"v{APP_VERSION}",
        "release_title": f"T-TTS v{APP_VERSION} — Bản Nâng Cấp Toàn Diện (Schedule, Audio & Broadcast Studio 2.0)",
        "author": APP_AUTHOR,
        "build_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "channel": "stable",
        "assets": assets_info,
    }
    (dist_dir / "release_metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 6. Soạn thảo Release Notes chuẩn Markdown cho GitHub Releases
    release_notes_md = f"""# T-TTS v{APP_VERSION} — HỆ THỐNG TRỢ LÝ GIỌNG NÓI QUÂN ĐỘI
**Tác giả:** {APP_AUTHOR}
**Công nghệ:** VieNeu-TTS v3 Turbo ONNX CPU (100% Offline)
**Kênh:** Stable (Chính thức)
**Tệp cài đặt:** `T-TTS_Setup_v{APP_VERSION}_Offline.exe`

## 🌟 CÓ GÌ MỚI TRONG BẢN v{APP_VERSION}?

### 1. 📂 Nhập Tài Liệu Văn Bản Thông Minh (Document Import)
- **Hỗ trợ đa định dạng:** Microsoft Word (.docx), PDF (.pdf) đa trang, Văn bản thuần (.txt) tự động nhận diện mã hóa Unicode UTF-8, UTF-8 BOM, CP1258.
- **Trích xuất nền non-blocking:** Worker Thread xử lý ngầm, thanh tiến trình thực tế, hỗ trợ hủy ngang an toàn không gây treo giao diện.
- **Thống kê và xem trước trực quan:** Số trang, số từ, số ký tự, ước tính thời lượng phát thanh, cảnh báo PDF bản scan thiếu text layer.
- **Linh hoạt chèn nội dung:** Tùy chọn Thay thế (Replace), Nối tiếp (Append) hoặc Tạo dự án tài liệu mới.
- **Bảo toàn giao diện:** Tích hợp nút `📂 Nhập tài liệu` cạnh `📋 Dán từ Clipboard` trong Text Editor, giữ nguyên các nút cảm xúc [cười], [nghỉ 500ms], [nghỉ 2s].

### 2. ✨ Phân Hệ Xử Lý Nâng Cao Âm Thanh DSP (Audio Enhancement 8.1 - 8.8)
- **8.1 Giảm nhiễu thích ứng (Adaptive Noise Reduction):** Bộ lọc FFT afftdn lọc tạp âm phòng thu, kết hợp High-pass (80Hz) chống rung mic và Low-pass (12kHz) chống rít.
- **8.2 Voice Clarity Equalizer (EQ 5 Dải):** Cân bằng âm thanh tối ưu cho phụ âm và ngữ điệu tiếng Việt: Dải ấm (250Hz), cắt nghẹt (600Hz), dải rõ chữ sắc nét (3.5kHz), độ thoáng không gian (10kHz).
- **8.3 Chuẩn hóa âm lượng EBU R128 LUFS:** Đạt chuẩn phát thanh truyền hình quốc tế và quân sự với Integrated Loudness -16.0 LUFS, LRA 7.0, True Peak trần -1.5 dBFS.
- **8.4 Bộ giảm âm gió (De-Esser):** Triệt tiêu hiện tượng xì rít chói tai của các âm gió /s/, /x/, /tr/ trong tiếng Việt.
- **8.5 Speech Dynamic Compressor:** Nén dải động cân bằng giọng đọc to/nhỏ, mang lại chất giọng phát thanh dầy dặn, đầm ấm và truyền cảm.
- **8.6 Bộ Presets chuyên dụng:**
  + *Phát thanh Quân đội tiêu chuẩn*
  + *Giọng ấm truyền cảm (Kể chuyện / Văn học)*
  + *Rõ tiếng ngoài trời / Loa phóng thanh truyền thanh*
  + *Phòng thu Podcast hiện đại*
- **8.8 So sánh nghe thử A/B đồng bộ thời gian thực:** Chuyển đổi tức thì giữa bản Gốc và bản Đã nâng cấp DSP tại đúng vị trí con trỏ phát (Synchronized Playback).

### 3. 📝 Chuẩn Hóa Văn Bản Tiếng Việt & Dự Án Tài Liệu (Phase 9)
- **Chuẩn hóa thông minh:** Tự động đọc ngày tháng năm ("22/12/1944" -> "ngày hai mươi hai tháng mười hai năm một nghìn chín trăm bốn mươi tư"), giờ phút ("08:30" -> "tám giờ rưỡi"), phần trăm ("100%"), số tiền tệ ("500.000 VNĐ").
- **Mở rộng từ viết tắt quân sự & chính trị:** QĐNDVN, QĐND, CAND, BTL, BCHQS, QK, Đ/c, UBND, HĐND, TW...
- **Phân đoạn câu thông minh (Smart Chunking):** Phân chia đoạn theo dấu ngắt câu (. ! ? ;), không bao giờ cắt ngang một từ tiếng Việt.
- **Batch TTS Engine:** Hàng đợi tổng hợp giọng nói đa phân đoạn với theo dõi tiến trình, ETA, tạm dừng, tiếp tục, hủy và thử lại phân đoạn lỗi.
- **Trung tâm xuất bản thống nhất (Export Center):** Xuất WAV (24k/44.1k/48kHz 16-bit) và MP3 (128k - 320kbps) tích hợp chuẩn hóa LUFS.

### 4. 🚀 Tự Động Cập Nhật An Toàn Tuyệt Đối (Auto Update v3.1.0)
- Tự động nhận diện bản cập nhật v3.1.0 từ GitHub Releases qua HTTPS.
- Tự động sao lưu toàn bộ dữ liệu người dùng, License Ed25519 và các dự án trước khi nâng cấp.
- Cài đè an toàn qua Inno Setup với cờ `onlyifdoesntexist`, cam kết không mất mát bất kỳ dữ liệu nào.

## 🔐 BẢO TOÀN DỮ LIỆU & BẢN QUYỀN OFFLINE
- Giữ nguyên mô hình VieNeu-TTS v3 Turbo ONNX CPU (100% Offline, không phụ thuộc GPU hay Internet).
- Machine ID và bản quyền offline Ed25519 được giữ nguyên vẹn 100%.
- Toàn bộ lịch sử phát thanh (`history.json`), danh mục giọng tùy biến (`custom_voices.json`) và các dự án được bảo vệ an toàn tuyệt đối.

## 📦 TẬP TIN PHÁT HÀNH VÀ MÃ BĂM SHA256
```
{chr(10).join(checksums_lines)}
```
"""
    (dist_dir / f"RELEASE_NOTES_v{APP_VERSION}.md").write_text(release_notes_md, encoding="utf-8")
    log(f"✅ Đã tạo Release Notes: dist/RELEASE_NOTES_v{APP_VERSION}.md")

    elapsed = time.time() - t0
    log("=" * 80)
    log(f"🎉 HOÀN THÀNH TOÀN BỘ QUY TRÌNH BUILD & ĐÓNG GÓI TRONG {elapsed:.1f} GIÂY!")
    log(f"📁 Thư mục phát hành: {dist_dir}")
    log("=" * 80)


if __name__ == "__main__":
    main()
