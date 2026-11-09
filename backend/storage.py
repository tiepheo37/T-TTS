"""Quản lý đường dẫn lưu trữ và bảo đảm quyền ghi cho T-TTS v2.0.

Quy tắc phân định thư mục lưu trữ:
1. Nếu có biến môi trường T_TTS_DATA_DIR: ưu tiên sử dụng.
2. Bản Portable (có cờ portable.txt ngoài Program Files và có quyền ghi):
   lưu tại thư mục chứa file thực thi (data, output ngay cạnh T-TTS.exe).
3. Khi cài đặt vào Windows (Program Files / Program Files (x86)) hoặc thư mục không có quyền ghi:
   lưu vào thư mục dữ liệu người dùng (%LOCALAPPDATA%\\T-TTS), tránh hoàn toàn lỗi PermissionError (Access Denied).
4. Tự động sao chép (migrate) từ điển và lịch sử hiện có từ thư mục cài đặt sang thư mục người dùng,
   bảo đảm dữ liệu cá nhân không bao giờ bị mất khi cài mới hoặc cập nhật.
"""
import os
import sys
import shutil
import time
from pathlib import Path


def get_app_dir() -> Path:
    """Trả về thư mục gốc ứng dụng (thư mục chứa file exe khi đóng gói, hoặc root mã nguồn)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_user_data_dir() -> Path:
    """Trả về thư mục dữ liệu cá nhân người dùng có toàn quyền ghi."""
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            local_app_data = str(Path.home() / "AppData" / "Local")
        return Path(local_app_data) / "T-TTS"
    return Path.home() / ".local" / "share" / "t-tts"


def is_in_program_files(path: Path) -> bool:
    """Kiểm tra đường dẫn có nằm trong Program Files hay không."""
    try:
        resolved_str = str(path.resolve()).lower()
        for env_var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432"):
            env_val = os.environ.get(env_var)
            if env_val and resolved_str.startswith(str(Path(env_val).resolve()).lower()):
                return True
        return "program files" in resolved_str
    except Exception:
        return False


def is_dir_writable(path: Path) -> bool:
    """Kiểm tra quyền ghi thực tế vào thư mục."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / f".write_test_{os.getpid()}_{int(time.time()*1000)}.tmp"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        return True
    except Exception:
        return False


_INITIALIZED_STORAGE = None


def init_storage() -> dict:
    """Khởi tạo và trả về dictionary các đường dẫn lưu trữ chuẩn hoá cho toàn bộ backend."""
    global _INITIALIZED_STORAGE
    if _INITIALIZED_STORAGE is not None:
        return _INITIALIZED_STORAGE

    app_dir = get_app_dir()
    env_dir = os.environ.get("T_TTS_DATA_DIR")
    is_portable_flag = (app_dir / "portable.txt").exists() or os.environ.get("T_TTS_PORTABLE") == "1"

    if env_dir:
        storage_root = Path(env_dir).resolve()
    elif is_portable_flag and is_dir_writable(app_dir / "data"):
        # Có cờ portable.txt và có quyền ghi: luôn lưu tại thư mục app
        storage_root = app_dir
    elif not is_in_program_files(app_dir) and is_dir_writable(app_dir / "data"):
        # Chạy ngoài Program Files (Desktop, Downloads, ổ D, v.v.): luôn lưu tại thư mục app
        storage_root = app_dir
    elif is_dir_writable(app_dir / "output") and is_dir_writable(app_dir / "data"):
        # Nằm trong Program Files nhưng đã được cấp quyền ghi: lưu tại thư mục app
        storage_root = app_dir
    else:
        # Trường hợp bị hạn chế quyền ghi: ưu tiên thư mục Music hiển thị rõ ràng của User
        user_music_dir = Path.home() / "Music" / "T-TTS"
        if is_dir_writable(user_music_dir):
            storage_root = user_music_dir
        else:
            storage_root = get_user_data_dir()

    data_dir = storage_root / "data"
    out_dir = storage_root / "output"
    upload_dir = out_dir / "uploads"
    legacy_upload_dir = out_dir / "_uploads"

    data_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Tự động di trú các tệp âm thanh và dữ liệu từ LocalAppData sang storage_root nếu có
    user_data_root = get_user_data_dir()
    if user_data_root.resolve() != storage_root.resolve() and user_data_root.exists():
        old_out = user_data_root / "output"
        if old_out.exists() and old_out.is_dir():
            for f in old_out.glob("*.*"):
                if f.is_file() and not (out_dir / f.name).exists():
                    try:
                        shutil.copy2(str(f), str(out_dir / f.name))
                    except Exception:
                        pass
        old_data = user_data_root / "data"
        if old_data.exists() and old_data.is_dir():
            for f in old_data.glob("*.json"):
                if f.is_file() and not (data_dir / f.name).exists():
                    try:
                        shutil.copy2(str(f), str(data_dir / f.name))
                    except Exception:
                        pass

    # Tương thích ngược: di trú các file upload cũ từ _uploads sang uploads nếu có
    if legacy_upload_dir.exists() and legacy_upload_dir.is_dir():
        for old_f in legacy_upload_dir.glob("*"):
            if old_f.is_file() and not (upload_dir / old_f.name).exists():
                try:
                    shutil.move(str(old_f), str(upload_dir / old_f.name))
                except Exception:
                    pass

    dict_path = data_dir / "pronunciation-dict.json"
    history_index = data_dir / "history.json"

    # Di trú / bảo toàn dữ liệu mẫu hoặc dữ liệu cũ từ app_dir nếu sang storage_root mới
    if storage_root.resolve() != app_dir.resolve():
        bundled_dict = app_dir / "data" / "pronunciation-dict.json"
        if bundled_dict.exists() and not dict_path.exists():
            try:
                shutil.copy2(bundled_dict, dict_path)
            except Exception:
                pass

        bundled_hist = app_dir / "data" / "history.json"
        if bundled_hist.exists() and not history_index.exists():
            try:
                shutil.copy2(bundled_hist, history_index)
            except Exception:
                pass

    _INITIALIZED_STORAGE = {
        "app_dir": app_dir,
        "storage_root": storage_root,
        "data_dir": data_dir,
        "out_dir": out_dir,
        "upload_dir": upload_dir,
        "history_index": history_index,
        "dict_path": dict_path,
        "is_user_data": (storage_root.resolve() != app_dir.resolve()),
    }
    return _INITIALIZED_STORAGE


def native_save_file_dialog(default_name="audio.wav", default_dir=None, filter_str="WAV Audio (*.wav)|*.wav|All Files (*.*)|*.*") -> str | None:
    """Mở hộp thoại Save As native của Windows để người dùng chọn vị trí lưu file."""
    # Ưu tiên WinForms qua pythonnet (chuẩn native Windows Explorer)
    try:
        import clr
        clr.AddReference('System.Windows.Forms')
        import System.Windows.Forms as WinForms
        import System.Threading as Threading

        res = [None]
        def _show():
            sfd = WinForms.SaveFileDialog()
            sfd.FileName = default_name
            if default_dir:
                sfd.InitialDirectory = str(default_dir)
            sfd.Filter = filter_str
            sfd.Title = "Chọn nơi lưu file âm thanh — T-TTS"
            sfd.RestoreDirectory = True
            if sfd.ShowDialog() == WinForms.DialogResult.OK:
                res[0] = sfd.FileName

        t = Threading.Thread(Threading.ThreadStart(_show))
        t.SetApartmentState(Threading.ApartmentState.STA)
        t.Start()
        t.Join()
        if res[0]:
            return res[0]
    except Exception:
        pass

    # Dự phòng qua Tkinter filedialog
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.asksaveasfilename(
            initialdir=str(default_dir) if default_dir else None,
            initialfile=default_name,
            defaultextension=".wav",
            filetypes=[("WAV Audio", "*.wav"), ("All Files", "*.*")]
        )
        root.destroy()
        return path if path else None
    except Exception:
        return None
