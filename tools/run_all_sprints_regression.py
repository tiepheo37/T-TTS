"""tools/run_all_sprints_regression.py — CHẠY KIỂM THỬ HỒI QUY TOÀN BỘ 8 SPRINTS
=============================================================================
"""

import sys
import time
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

test_suites = [
    ("Sprint 1 (Document Reader)", "tools/test_sprint_1_document_import.py", 13),
    ("Sprint 2 (Text Normalization)", "tools/test_sprint_2_document_processing.py", 16),
    ("Sprint 3 (Core Audio DSP)", "tools/test_sprint_3_audio_enhancement.py", 16),
    ("Sprint 4 (Advanced DSP)", "tools/test_sprint_4_advanced_audio_enhancement.py", 16),
    ("Sprint 5 (Intelligent Audio)", "tools/test_sprint_5_intelligent_audio.py", 16),
    ("Sprint 6 (Full Studio Integration)", "tools/test_sprint_6_full_integration.py", 16),
    ("Sprint 7 (Auto Update Engine)", "tools/test_sprint_7_auto_update.py", 16),
    ("Sprint 8 (Packaging & Release)", "tools/test_sprint_8_release.py", 7),
]

def main():
    print("=" * 80)
    print("T-TTS v3.1.0 — KIỂM THỬ HỒI QUY TOÀN BỘ 8 SPRINTS (MASTER REGRESSION SUITE)")
    print("Tác giả: Nguyễn Văn Tiệp | Kiến trúc: VieNeu-TTS v3 Turbo ONNX CPU")
    print("=" * 80)

    total_tests = sum(cnt for _, _, cnt in test_suites)
    passed_tests = 0
    start_time = time.time()

    for idx, (name, script, count) in enumerate(test_suites, 1):
        print(f"\n[{idx}/8] Đang thực thi {name} ({count} tests)...", flush=True)
        t0 = time.time()
        res = subprocess.run(
            [sys.executable, str(REPO_ROOT / script)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        elapsed = time.time() - t0
        if res.returncode == 0:
            passed_tests += count
            print(f"  --> [PASS] {name}: {count}/{count} tests ({elapsed:.1f}s)")
        else:
            print(f"  --> [FAIL] {name} (code {res.returncode}) ({elapsed:.1f}s)")
            print(res.stderr[-300:] if res.stderr else res.stdout[-300:])

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"KẾT QUẢ TỔNG HỢP: {passed_tests}/{total_tests} TESTS ĐẠT ({passed_tests/total_tests*100:.1f}%)")
    print(f"Thời gian thực thi: {total_elapsed:.1f} giây")
    if passed_tests == total_tests:
        print("TẤT CẢ 8 SPRINTS (116/116 TESTS) ĐẠT 100% HOÀN HẢO!")
    else:
        print("CÓ BỘ KIỂM THỬ THẤT BẠI!")
    print("=" * 80)

    return passed_tests == total_tests

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
