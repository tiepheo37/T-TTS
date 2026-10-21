"""desktop_main.py — ĐIỀU PHỐI KHỞI CHẠY ỨNG DỤNG WINDOWS DESKTOP NATIVE T-TTS v1.0.1
=====================================================================================
KIẾN TRÚC THUẦN DESKTOP NATIVE (PYSIDE6):
- Khởi chạy trực tiếp cửa sổ ứng dụng Modern Dark bằng PySide6.
- Gọi trực tiếp nghiệp vụ Python và mô hình VieNeu-TTS v3 Turbo ONNX CPU.
- LOẠI BỎ HOÀN TOÀN:
  * Không chạy Flask local server.
  * Không dùng cổng 8001 hay socket loopback nội bộ.
  * Không dùng localhost hoặc 127.0.0.1 để phục vụ giao diện.
  * Không mở Chrome, Edge, Cốc Cốc, Brave hay bất kỳ trình duyệt nào.
  * Không sử dụng Chrome App Mode.
  * Không sử dụng WebView2.
  * Không còn bảng Google Translate hay lỗi tự dịch của trình duyệt.
"""

from __future__ import annotations

import io
import os
import sys
import logging
import traceback
from pathlib import Path

# Đảm bảo đường dẫn gốc được nhận diện chính xác kể cả khi đóng gói PyInstaller
if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys.executable).resolve().parent
    INTERNAL_DIR = Path(getattr(sys, "_MEIPASS", APP_ROOT / "_internal"))
else:
    APP_ROOT = Path(__file__).resolve().parent
    INTERNAL_DIR = APP_ROOT

# Bổ sung vào sys.path
for p in [str(APP_ROOT), str(INTERNAL_DIR), str(APP_ROOT / "backend"), str(INTERNAL_DIR / "backend"), str(APP_ROOT / "gui"), str(INTERNAL_DIR / "gui")]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Xử lý stdout/stderr an toàn khi chạy chế độ Windows GUI (noconsole / console=False)
if sys.stdout is None or sys.stderr is None:
    log_dir = APP_ROOT / "output"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        gui_log = open(str(log_dir / "desktop_app.log"), "a", encoding="utf-8")
        sys.stdout = gui_log
        sys.stderr = gui_log
    except Exception:
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
else:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("T_TTS_Desktop")


def setup_windows_dpi():
    """Thiết lập độ phân giải cao High-DPI trên Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            # PROCESS_PER_MONITOR_DPI_AWARE_V2 = 2, PROCESS_SYSTEM_DPI_AWARE = 1
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def show_fatal_error_dialog(title: str, message: str) -> None:
    """Hiển thị hộp thoại lỗi nghiêm trọng Windows native."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x0)
    except Exception:
        logger.error(f"{title}: {message}")


def main():
    logger.info("====================================================================")
    logger.info("KHỞI ĐỘNG T-TTS v1.0.1 — NATIVE DESKTOP WINDOWS (OFFLINE)")
    logger.info("====================================================================")

    setup_windows_dpi()

    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont, QIcon
        from gui.main_window import MainWindow
    except Exception as e:
        err_msg = f"Không thể nạp thư viện đồ họa Desktop:\n\n{e}\n\n{traceback.format_exc()}"
        logger.error(err_msg)
        show_fatal_error_dialog("Lỗi Khởi Động T-TTS", err_msg)
        sys.exit(1)

    # Khởi tạo đối tượng ứng dụng PySide6
    app = QApplication(sys.argv)
    app.setApplicationName("T-TTS")
    app.setApplicationDisplayName("T-TTS v1.0.1 — Chuyển Văn Bản Thành Giọng Nói Tiếng Việt")
    app.setOrganizationName("NguyenVanTiep")

    # Đặt icon cho toàn bộ ứng dụng
    icon_candidates = [
        APP_ROOT / "app_icon.ico",
        INTERNAL_DIR / "app_icon.ico",
    ]
    for cand in icon_candidates:
        if cand.is_file():
            app.setWindowIcon(QIcon(str(cand)))
            break

    # Khởi tạo và hiển thị cửa sổ chính
    try:
        main_win = MainWindow()
        main_win.show()
    except Exception as e:
        err_msg = f"Lỗi khởi tạo giao diện chính:\n\n{e}\n\n{traceback.format_exc()}"
        logger.error(err_msg)
        show_fatal_error_dialog("Lỗi Giao Diện T-TTS", err_msg)
        sys.exit(1)

    logger.info("Cửa sổ chính đã sẵn sàng. Bắt đầu vòng lặp sự kiện Qt...")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
