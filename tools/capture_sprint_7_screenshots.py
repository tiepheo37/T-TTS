"""tools/capture_sprint_7_screenshots.py — CHỤP ẢNH GIAO DIỆN SPRINT 7 AUTO UPDATE
================================================================================
Tác giả: Nguyễn Văn Tiệp
Giao diện: UpdateDialog Dark Military K20
"""

import sys
import shutil
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.updater import UpdateInfoData, UpdateManager
from gui.dialog_update import UpdateDialog

ARTIFACT_DIR = Path(r"C:\Users\Minh Dang\.gemini\antigravity\brain\d6a22ea3-cf3a-46e7-8bfd-850b7f7adf9d")
SCREENSHOTS_DIR = REPO_ROOT / "docs" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def capture_screenshots():
    app = QApplication.instance() or QApplication(sys.argv)

    updater = UpdateManager(current_version="3.0.0")
    update_info = UpdateInfoData(
        available=True,
        current_version="3.0.0",
        latest_version="3.1.0",
        release_title="T-TTS v3.1.0 — Bản Phát Hành Đột Phá Xử Lý Tài Liệu & Âm Thanh Quân Đội",
        release_notes=(
            "★ NÂNG CẤP TRỰC TIẾP v3.0.0 ➔ v3.1.0 (BỎ QUA HOÀN TOÀN v3.0.1)\n\n"
            "1. Nhập liệu tài liệu đa định dạng (DOCX, PDF, TXT) tích hợp trực tiếp vào Text Editor.\n"
            "2. Chuẩn hóa tiếng Việt NFC, quy tắc chuyển đổi cách đọc số quân đội, phân đoạn thông minh.\n"
            "3. Bộ xử lý âm thanh Core DSP: Giảm nhiễu (Noise Reduction), Voice EQ, Chuẩn hóa âm lượng LUFS.\n"
            "4. Bộ xử lý âm thanh Nâng cao: De-Esser khử âm xì, Compressor nén động học, Brickwall Limiter.\n"
            "5. Xử lý âm thanh Thông minh (AI Analysis): Phân tích chất lượng giọng, Presets quân đội tối ưu, Smart Broadcast Mixing.\n"
            "6. Bảo toàn 100% dữ liệu: Bản quyền offline Ed25519, Machine ID, từ điển phát âm và toàn bộ dự án cũ."
        ),
        published_at="2026-11-09T10:00:00Z",
        asset_name="T-TTS_v3.1.0_Setup.exe",
        asset_size=165 * 1024 * 1024,
        sha256="9a4b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b",
    )

    # 1. Chụp màn hình trạng thái sẵn sàng nâng cấp (Ready State)
    dlg = UpdateDialog(updater, update_info)
    dlg.show()
    app.processEvents()

    pix_ready = dlg.grab()
    out_ready = SCREENSHOTS_DIR / "sprint_7_update_dialog_military_k20.png"
    pix_ready.save(str(out_ready))
    print(f"Saved: {out_ready}")

    if ARTIFACT_DIR.is_dir():
        shutil.copy2(out_ready, ARTIFACT_DIR / out_ready.name)
        print(f"Copied to artifact dir: {ARTIFACT_DIR / out_ready.name}")

    # 2. Chụp màn hình trạng thái đang tải tiến trình (Downloading State)
    dlg._set_state_downloading()
    dlg._on_download_progress(68, 112.2, 165.0, 18.5)
    app.processEvents()

    pix_progress = dlg.grab()
    out_progress = SCREENSHOTS_DIR / "sprint_7_update_progress_downloading.png"
    pix_progress.save(str(out_progress))
    print(f"Saved: {out_progress}")

    if ARTIFACT_DIR.is_dir():
        shutil.copy2(out_progress, ARTIFACT_DIR / out_progress.name)
        print(f"Copied to artifact dir: {ARTIFACT_DIR / out_progress.name}")

    dlg.close()
    print("Capture complete!")


if __name__ == "__main__":
    capture_screenshots()
