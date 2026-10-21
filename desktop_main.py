"""
desktop_main.py — ĐIỀU PHỐI KHỞI CHẠY ỨNG DỤNG WINDOWS DESKTOP T-TTS v1.0.1
=============================================================================
Tính năng:
  1. Tự động cấp phát cổng mạng (mặc định 8001, tự đổi cổng nếu bị chiếm).
  2. Khởi chạy ngầm Flask server trong tiến trình ứng dụng.
  3. Khởi tạo mô hình VieNeu-TTS v3 Turbo ngay trong nền.
  4. Hiển thị giao diện trực tiếp trong cửa sổ ứng dụng Windows:
     - Ưu tiên 1: Edge WebView2 Runtime (nếu máy có cài đặt WebView2).
     - Ưu tiên 2: Chromium App Window (Chrome / Cốc Cốc / Edge / Brave độc lập, không URL bar, không tab).
  5. Đóng sạch toàn bộ server và tiến trình khi người dùng tắt cửa sổ ứng dụng.
  6. Xử lý an toàn khi stdout/stderr bị None (chế độ windowed không có console).
  7. Hỗ trợ cờ --server để chạy chế độ máy chủ nền nếu cần.
"""

from __future__ import annotations

import io
import os
import sys
import time
import socket
import logging
import threading
import subprocess
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
for p in [str(APP_ROOT), str(INTERNAL_DIR), str(APP_ROOT / "backend"), str(INTERNAL_DIR / "backend")]:
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


def find_available_port(default_port: int = 8001, max_tries: int = 50) -> int:
    """Tìm cổng mạng khả dụng bắt đầu từ default_port."""
    for port in range(default_port, default_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            res = s.connect_ex(("127.0.0.1", port))
            if res != 0:
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def show_error_dialog(title: str, message: str) -> None:
    """Hiển thị hộp thoại thông báo lỗi native trên Windows."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x0)
    except Exception:
        logger.error(f"{title}: {message}")


def is_webview2_installed() -> bool:
    """Kiểm tra máy Windows có cài đặt Microsoft Edge WebView2 Runtime hay không."""
    try:
        import winreg
        subkeys = [
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-F55F-4E4E-9A04-433B3C008ED7}",
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-F55F-4E4E-9A04-433B3C008ED7}",
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-F55F-4E4E-9A04-433B3C008ED7}",
        ]
        for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for sub in subkeys:
                try:
                    with winreg.OpenKey(root, sub) as key:
                        val, _ = winreg.QueryValueEx(key, "pv")
                        if val and str(val).strip() not in ("0.0.0.0", ""):
                            return True
                except Exception:
                    pass
    except Exception:
        pass
    return False


def find_chromium_browser() -> str | None:
    """Tìm trình duyệt nhân Chromium hỗ trợ App Mode (--app) trên máy người dùng."""
    app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path(app_data) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        r"C:\Program Files\CocCoc\Browser\Application\browser.exe",
        r"C:\Program Files (x86)\CocCoc\Browser\Application\browser.exe",
        str(Path(app_data) / "CocCoc" / "Browser" / "Application" / "browser.exe"),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        str(Path(app_data) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def run_chromium_app_window(browser_exe: str, url: str, server) -> None:
    """Khởi chạy ứng dụng trong cửa sổ độc lập (App Mode) qua Chromium."""
    app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    profile_dir = Path(app_data) / "T-TTS" / "desktop_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        browser_exe,
        f"--app={url}",
        "--window-size=1280,850",
        f"--user-data-dir={str(profile_dir)}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        "--disable-extensions",
        "--disable-component-update",
    ]
    logger.info(f"Đang khởi chạy cửa sổ ứng dụng qua: {browser_exe}")
    proc = subprocess.Popen(cmd)

    try:
        proc.wait()
    except Exception:
        pass
    finally:
        logger.info("Cửa sổ ứng dụng đã đóng. Đang dọn dẹp và dừng server...")
        try:
            server.shutdown()
        except Exception:
            pass
        os._exit(0)


def run_desktop_app():
    # Kiểm tra cờ --server nếu người dùng muốn chạy dạng nền
    if "--server" in sys.argv or os.environ.get("T_TTS_SERVER_MODE") == "1":
        logger.info("Chạy chế độ máy chủ nền (--server)...")
        from backend.app import main as server_main
        server_main()
        return

    port = find_available_port(8001)
    logger.info(f"Cấp phát cổng giao diện: {port}")

    # Import backend app
    try:
        from backend.app import app, engine
    except Exception as e:
        err_msg = f"Không thể nạp backend T-TTS:\n\n{e}\n\n{traceback.format_exc()}"
        logger.error(err_msg)
        show_error_dialog("Lỗi Khởi Động T-TTS", err_msg)
        sys.exit(1)

    # Khởi động server Werkzeug trong daemon thread
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", port, app, threaded=True)

    def _run_server():
        logger.info(f"Flask server bắt đầu phục vụ tại http://127.0.0.1:{port}")
        server.serve_forever()

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    # Nạp trước mô hình VieNeu-TTS v3 Turbo trong nền
    def _bg_load_model():
        try:
            logger.info("Bắt đầu nạp trước mô hình VieNeu-TTS v3 Turbo...")
            engine.load()
            logger.info("Mô hình VieNeu-TTS v3 Turbo đã sẵn sàng!")
        except Exception as e:
            logger.warning(f"Chưa hoàn tất nạp model trong nền: {e}")

    threading.Thread(target=_bg_load_model, daemon=True).start()

    # Chờ server phản hồi endpoint /health (tối đa 10 giây)
    t0 = time.time()
    server_ready = False
    import urllib.request
    health_url = f"http://127.0.0.1:{port}/health"

    while time.time() - t0 < 10.0:
        try:
            with urllib.request.urlopen(health_url, timeout=0.5) as resp:
                if resp.status == 200:
                    server_ready = True
                    break
        except Exception:
            time.sleep(0.1)

    if not server_ready:
        logger.warning("Server chưa phản hồi endpoint /health sau 10s, vẫn tiếp tục mở giao diện...")

    # Tìm icon file
    icon_candidates = [
        APP_ROOT / "app_icon.ico",
        INTERNAL_DIR / "app_icon.ico",
        APP_ROOT / "web" / "favicon.ico",
        INTERNAL_DIR / "web" / "favicon.ico",
    ]
    app_icon = None
    for cand in icon_candidates:
        if cand.is_file():
            app_icon = str(cand)
            break

    window_title = "T-TTS v1.0.1 — Chuyển Văn Bản Thành Giọng Nói Tiếng Việt"
    app_url = f"http://127.0.0.1:{port}"

    # LỰA CHỌN GIAO DIỆN CỬA SỔ PHÙ HỢP:
    # 1. Nếu có WebView2 Runtime -> Khởi chạy qua pywebview (Edge WebView2)
    has_webview2 = is_webview2_installed()
    logger.info(f"Trạng thái kiểm tra Edge WebView2 Runtime: {has_webview2}")

    if has_webview2:
        try:
            import webview
            logger.info(f"Khởi chạy giao diện qua Microsoft Edge WebView2: {app_url}")

            window = webview.create_window(
                title=window_title,
                url=app_url,
                width=1280,
                height=850,
                min_size=(1024, 700),
                resizable=True,
                text_select=True,
                confirm_close=False,
            )

            def on_closed():
                logger.info("Cửa sổ ứng dụng đã đóng. Đang dọn dẹp và dừng server...")
                try:
                    server.shutdown()
                except Exception:
                    pass
                os._exit(0)

            window.events.closed += on_closed
            webview.start(gui="edgechromium", icon=app_icon)
            return
        except Exception as e:
            logger.warning(f"Thử nghiệm WebView2 gặp sự cố ({e}), chuyển sang phương án Chromium App Mode...")

    # 2. Nếu không có WebView2 Runtime (hoặc WebView2 lỗi) -> Khởi chạy qua Chromium App Mode
    chromium_exe = find_chromium_browser()
    if chromium_exe:
        logger.info(f"Sử dụng cửa sổ ứng dụng độc lập qua Chromium App Mode: {chromium_exe}")
        run_chromium_app_window(chromium_exe, app_url, server)
        return

    # 3. Phương án dự phòng cuối cùng nếu máy hoàn toàn không có trình duyệt Chromium
    logger.warning("Không tìm thấy WebView2 hoặc Chromium. Mở trình duyệt mặc định của hệ thống...")
    import webbrowser
    webbrowser.open(app_url)
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        server.shutdown()
        os._exit(0)


if __name__ == "__main__":
    run_desktop_app()
