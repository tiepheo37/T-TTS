"""tests/test_phase_7_10_endurance.py — KIỂM THỬ SỨC BỀN & MEMORY LEAK
======================================================================
Đồng bộ chuyển tiếp từ tools/test_phase_7_10_endurance.py
"""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Import bộ test từ tools
from tools.test_phase_7_10_endurance import TestPhase710Endurance

if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
