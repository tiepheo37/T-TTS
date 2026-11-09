"""backend/ffmpeg_bootstrap.py — KHỞI TẠO TẬP TRUNG FFMPEG CHO TOÀN BỘ HỆ THỐNG
=============================================================================
Đóng gói quy trình khởi tạo FFmpeg tập trung duy nhất cho T-TTS v3.0.1:
1. Phát hiện và xác thực executable FFmpeg từ imageio-ffmpeg đóng gói sẵn.
2. Kiểm tra tính hợp lệ và khả năng thực thi thực tế (subprocess -version).
3. Thiết lập biến môi trường PATH không bị trùng lặp (idempotent).
4. Thiết lập AudioSegment.converter, AudioSegment.ffmpeg, AudioSegment.ffprobe cho pydub.
5. Tạo bí danh ffmpeg.exe trên Windows nếu cần để pydub không phát cảnh báo RuntimeWarning.
6. Ghi log chuẩn hóa, xử lý lỗi an toàn không làm crash ứng dụng nếu thiếu FFmpeg.
"""

from __future__ import annotations

import os
import sys
import shutil
import logging
import threading
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("T-TTS.FFmpegBootstrap")

_BOOTSTRAP_LOCK = threading.Lock()
_FFMPEG_INITIALIZED: bool = False
_FFMPEG_STATUS: Dict[str, Any] = {
    "initialized": False,
    "available": False,
    "executable_path": None,
    "version_info": None,
    "in_path": False,
    "error": None,
}


def initialize_ffmpeg(force_reinit: bool = False) -> Dict[str, Any]:
    """Khởi tạo tập trung FFmpeg cho toàn bộ ứng dụng và cấu hình pydub.
    - Idempotent: Gọi nhiều lần không bị duplicate PATH hay lặp lại kiểm tra.
    - An toàn: Không bao giờ gây crash ứng dụng nếu gặp sự cố.
    """
    global _FFMPEG_INITIALIZED, _FFMPEG_STATUS

    with _BOOTSTRAP_LOCK:
        if _FFMPEG_INITIALIZED and not force_reinit:
            return dict(_FFMPEG_STATUS)

        status: Dict[str, Any] = {
            "initialized": True,
            "available": False,
            "executable_path": None,
            "version_info": None,
            "in_path": False,
            "error": None,
        }

        # 1. Import imageio_ffmpeg
        try:
            import imageio_ffmpeg
        except ImportError as e:
            err_msg = f"Không tìm thấy thư viện imageio-ffmpeg: {e}"
            logger.error(err_msg)
            status["error"] = err_msg
            _FFMPEG_STATUS = status
            _FFMPEG_INITIALIZED = True
            return dict(status)

        # 2. Lấy đường dẫn thực thi
        try:
            raw_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            err_msg = f"Lỗi truy vấn executable từ imageio-ffmpeg: {e}"
            logger.error(err_msg)
            status["error"] = err_msg
            _FFMPEG_STATUS = status
            _FFMPEG_INITIALIZED = True
            return dict(status)

        if not raw_exe:
            err_msg = "imageio_ffmpeg.get_ffmpeg_exe() trả về None hoặc rỗng"
            logger.warning(err_msg)
            status["error"] = err_msg
            _FFMPEG_STATUS = status
            _FFMPEG_INITIALIZED = True
            return dict(status)

        exe_path = Path(raw_exe).resolve()

        # 3. Kiểm tra file thực sự tồn tại
        if not exe_path.is_file():
            err_msg = f"Tệp binary FFmpeg không tồn tại trên đĩa: {exe_path}"
            logger.error(err_msg)
            status["error"] = err_msg
            _FFMPEG_STATUS = status
            _FFMPEG_INITIALIZED = True
            return dict(status)

        # 4. Kiểm tra khả năng thực thi thực tế
        try:
            test_res = subprocess.run(
                [str(exe_path), "-version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if test_res.returncode != 0:
                err_msg = f"FFmpeg trả về mã lỗi {test_res.returncode}: {test_res.stderr.strip()[:200]}"
                logger.error(err_msg)
                status["error"] = err_msg
                _FFMPEG_STATUS = status
                _FFMPEG_INITIALIZED = True
                return dict(status)

            # Lấy thông tin phiên bản từ dòng đầu tiên
            first_line = test_res.stdout.splitlines()[0] if test_res.stdout else "FFmpeg (unknown)"
            status["version_info"] = first_line.strip()
            status["available"] = True
            status["executable_path"] = str(exe_path)
            logger.info(f"Đã phát hiện FFmpeg hợp lệ: {status['version_info']} tại {exe_path}")

        except Exception as e:
            err_msg = f"Không thể thực thi lệnh kiểm tra FFmpeg: {e}"
            logger.error(err_msg)
            status["error"] = err_msg
            _FFMPEG_STATUS = status
            _FFMPEG_INITIALIZED = True
            return dict(status)

        # 5. Tạo bí danh ffmpeg.exe trong cùng thư mục (nếu tên file có đuôi phiên bản)
        bin_dir = exe_path.parent
        target_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        alias_path = bin_dir / target_name
        effective_converter = exe_path

        if not alias_path.is_file():
            try:
                # Ưu tiên tạo hardlink (0 byte dung lượng thêm trên NTFS)
                os.link(str(exe_path), str(alias_path))
                effective_converter = alias_path
                logger.info(f"Đã tạo hardlink '{alias_path.name}' cho pydub.")
            except Exception:
                try:
                    shutil.copy2(str(exe_path), str(alias_path))
                    effective_converter = alias_path
                    logger.info(f"Đã sao chép '{alias_path.name}' cho pydub.")
                except Exception as copy_err:
                    logger.debug(f"Không thể tạo alias {alias_path.name}: {copy_err}")
                    effective_converter = exe_path
        else:
            effective_converter = alias_path

        # 6. Thêm thư mục FFmpeg vào biến môi trường PATH nếu chưa có
        current_path_entries = [os.path.normcase(os.path.normpath(p)) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
        norm_bin_dir = os.path.normcase(os.path.normpath(str(bin_dir)))

        if norm_bin_dir not in current_path_entries:
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            status["in_path"] = True
            logger.info(f"Đã thêm thư mục FFmpeg vào PATH: {bin_dir}")
        else:
            status["in_path"] = True

        # 7. Thiết lập pydub AudioSegment
        try:
            import pydub
            from pydub import AudioSegment

            AudioSegment.converter = str(effective_converter)
            if hasattr(AudioSegment, "ffmpeg"):
                AudioSegment.ffmpeg = str(effective_converter)

            # Kiểm tra ffprobe
            ffprobe_candidates = [
                bin_dir / "ffprobe.exe",
                bin_dir / "ffprobe",
            ]
            for ffp in ffprobe_candidates:
                if ffp.is_file():
                    if hasattr(AudioSegment, "ffprobe"):
                        AudioSegment.ffprobe = str(ffp)
                    break

            logger.info(f"Đã cấu hình pydub converter -> {effective_converter}")
        except Exception as e:
            logger.warning(f"Lỗi khi liên kết pydub với FFmpeg: {e}")

        _FFMPEG_STATUS = status
        _FFMPEG_INITIALIZED = True
        return dict(status)


def is_ffmpeg_ready() -> bool:
    """Kiểm tra nhanh xem FFmpeg đã được khởi tạo và sẵn sàng sử dụng hay chưa."""
    if not _FFMPEG_INITIALIZED:
        initialize_ffmpeg()
    return bool(_FFMPEG_STATUS.get("available", False))


def get_ffmpeg_path() -> Optional[str]:
    """Trả về đường dẫn tệp thực thi FFmpeg đang hoạt động."""
    if not _FFMPEG_INITIALIZED:
        initialize_ffmpeg()
    return _FFMPEG_STATUS.get("executable_path")


def get_ffmpeg_status() -> Dict[str, Any]:
    """Trả về bản sao thông tin trạng thái FFmpeg chi tiết."""
    if not _FFMPEG_INITIALIZED:
        initialize_ffmpeg()
    return dict(_FFMPEG_STATUS)
