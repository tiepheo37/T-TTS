"""backend/__init__.py — GÓI NGHIỆP VỤ HẬU TẦNG T-TTS
===================================================
Tự động khởi tạo môi trường FFmpeg tập trung cho toàn bộ ứng dụng.
"""

from .ffmpeg_bootstrap import (
    initialize_ffmpeg,
    is_ffmpeg_ready,
    get_ffmpeg_path,
    get_ffmpeg_status,
)

# Khởi tạo FFmpeg tập trung ngay khi package backend được import
initialize_ffmpeg()
