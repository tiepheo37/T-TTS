"""backend/diagnostic.py — CHẨN ĐOÁN HỆ THỐNG, ĐO LƯỜNG HIỆU NĂNG & LOGGING CHUẨN HÓA
=============================================================================
Module chẩn đoán và theo dõi sức khỏe ứng dụng T-TTS v3.0.1:
- Đo lường RAM (Working Set, Private Bytes, Peak RAM) qua Windows Native API (không cần psutil).
- Kiểm tra toàn vẹn tài nguyên (mô hình ONNX, thư mục dữ liệu, quyền ghi).
- Chuẩn hóa nhật ký chẩn đoán (Diagnostic Logger) ra tệp data/logs/diagnostic.log.
- Tự động phục hồi và báo cáo lỗi chi tiết.
"""

from __future__ import annotations

import os
import sys
import time
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .storage import init_storage
from .version import APP_VERSION, APP_AUTHOR, APP_NAME

_STORAGE = init_storage()
DATA_DIR: Path = _STORAGE["data_dir"]
LOGS_DIR: Path = DATA_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DIAGNOSTIC_LOG_FILE: Path = LOGS_DIR / "diagnostic.log"

# Cấu hình logging file
_logger = logging.getLogger("T-TTS.Diagnostic")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    try:
        fh = logging.FileHandler(str(DIAGNOSTIC_LOG_FILE), encoding="utf-8")
        fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"))
        _logger.addHandler(fh)
    except Exception:
        pass


def get_process_memory_info() -> Dict[str, float]:
    """Lấy số liệu tiêu thụ bộ nhớ RAM thực tế của tiến trình hiện tại (Đơn vị: MB).
    Sử dụng trực tiếp Windows Native API K32GetProcessMemoryInfo qua ctypes.
    Hoạt động 100% offline, chuẩn xác, không phụ thuộc thư viện bên ngoài.
    """
    res = {
        "working_set_mb": 0.0,
        "private_usage_mb": 0.0,
        "peak_working_set_mb": 0.0,
    }

    if sys.platform != "win32":
        # Fallback trên Linux / macOS nếu chạy test
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            res["working_set_mb"] = round(usage / 1024.0, 2)
            res["peak_working_set_mb"] = res["working_set_mb"]
        except Exception:
            pass
        return res

    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        fn = ctypes.windll.kernel32.K32GetProcessMemoryInfo
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX), wintypes.DWORD]
        fn.restype = wintypes.BOOL

        pmc = PROCESS_MEMORY_COUNTERS_EX()
        pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        h = ctypes.windll.kernel32.GetCurrentProcess()

        if fn(h, ctypes.byref(pmc), pmc.cb):
            res["working_set_mb"] = round(pmc.WorkingSetSize / (1024.0 * 1024.0), 2)
            res["private_usage_mb"] = round(pmc.PrivateUsage / (1024.0 * 1024.0), 2)
            res["peak_working_set_mb"] = round(pmc.PeakWorkingSetSize / (1024.0 * 1024.0), 2)
    except Exception as e:
        log_event("MEMORY_METRIC_ERROR", f"Không thể lấy chỉ số RAM: {e}", level="WARNING")

    return res


def log_event(category: str, message: str, level: str = "INFO"):
    """Ghi nhận sự kiện chẩn đoán có cấu trúc vào tệp nhật ký."""
    log_msg = f"[{category}] {message}"
    if level == "ERROR":
        _logger.error(log_msg)
    elif level == "WARNING":
        _logger.warning(log_msg)
    else:
        _logger.info(log_msg)


def run_system_health_check() -> Dict[str, Any]:
    """Thực hiện kiểm tra sức khỏe và khả năng sẵn sàng của toàn hệ thống."""
    checks = {}
    is_healthy = True

    # 1. Kiểm tra thư mục dữ liệu và quyền ghi
    try:
        test_file = DATA_DIR / ".write_test_tmp"
        test_file.write_text("health_check_ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        checks["storage_write_permission"] = {"status": "OK", "detail": str(DATA_DIR)}
    except Exception as e:
        is_healthy = False
        checks["storage_write_permission"] = {"status": "ERROR", "detail": str(e)}

    # 2. Kiểm tra tài nguyên mô hình VieNeu-TTS ONNX
    from .storage import get_app_dir
    models_dir = get_app_dir() / "models"
    required_models = [
        models_dir / "moss_codec" / "moss_audio_tokenizer_decode_full.onnx",
        models_dir / "v3turbo_onnx" / "vieneu_prefill.onnx",
        models_dir / "v3turbo_onnx" / "vieneu_decode_step.onnx",
        models_dir / "v3turbo_onnx" / "voices_v3_turbo.json",
    ]
    missing_models = [str(m.relative_to(models_dir)) for m in required_models if not m.is_file()]

    if not missing_models:
        checks["ai_models"] = {"status": "OK", "detail": f"Đầy đủ {len(required_models)} mô hình & cấu hình ONNX"}
    else:
        is_healthy = False
        checks["ai_models"] = {"status": "MISSING", "detail": f"Thiếu: {', '.join(missing_models)}"}

    # 3. Kiểm tra bản quyền offline Ed25519
    from .license import license_manager, get_machine_id
    mid = get_machine_id()
    lic_active = license_manager.is_active()
    checks["offline_license"] = {
        "status": "OK" if lic_active else "EXPIRED_OR_TRIAL",
        "machine_id": mid,
        "active": lic_active,
    }

    # 4. Kiểm tra bộ nhớ RAM tiến trình
    mem = get_process_memory_info()
    checks["process_memory"] = {
        "status": "OK" if mem["working_set_mb"] < 1500.0 else "WARNING_HIGH_RAM",
        "working_set_mb": mem["working_set_mb"],
        "private_mb": mem["private_usage_mb"],
        "peak_mb": mem["peak_working_set_mb"],
    }

    # 5. Thông tin nền tảng
    report = {
        "healthy": is_healthy,
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "author": APP_AUTHOR,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "checks": checks,
    }

    log_event("HEALTH_CHECK", f"Health status: {'HEALTHY' if is_healthy else 'DEGRADED'}")
    return report
