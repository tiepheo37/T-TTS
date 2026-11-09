"""tests/test_phase_7_9_ffmpeg_bootstrap.py — KIỂM THỬ KHỞI TẠO TẬP TRUNG FFMPEG
=============================================================================
Đồng bộ chuyển tiếp từ tools/test_phase_7_9_ffmpeg_bootstrap.py
"""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Import toàn bộ bộ test từ tools
from tools.test_phase_7_9_ffmpeg_bootstrap import TestPhase79FFmpegBootstrap

if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
