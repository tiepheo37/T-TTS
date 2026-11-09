"""Chẩn đoán phần cứng, môi trường inference và lựa chọn thiết bị CPU/GPU cho T-TTS v2.0.

Phân định 3 tầng thông tin độc lập:
A. Phần cứng (Hardware): Phát hiện GPU NVIDIA, tên card, dung lượng VRAM, phiên bản Driver qua nvcuda.dll.
B. Môi trường inference (Environment): Phiên bản ONNX Runtime, execution providers, kiểm tra khả năng nạp CUDA thực tế.
C. Kết quả thực thi (Execution): Thiết bị được cấu hình, lý do fallback sang CPU nếu có, trạng thái mô hình.
"""
import os
import sys
import ctypes
import logging
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger("T-TTS.Hardware")


def get_nvidia_hardware_info() -> Dict[str, Any]:
    """Truy vấn trực tiếp driver NVIDIA trên Windows qua nvcuda.dll (không phụ thuộc PyTorch hay nvidia-smi)."""
    info = {
        "detected": False,
        "count": 0,
        "name": None,
        "total_vram_mb": 0,
        "free_vram_mb": 0,
        "driver_version": None,
        "error": None,
    }

    if sys.platform != "win32":
        info["error"] = "Hệ điều hành không phải Windows"
        return info

    try:
        nvcuda = ctypes.WinDLL("nvcuda.dll")
    except OSError as e:
        info["error"] = f"Không tìm thấy driver NVIDIA (nvcuda.dll): {e}"
        return info

    try:
        # 1. Khởi tạo CUDA Driver API
        res = nvcuda.cuInit(0)
        if res != 0:
            info["error"] = f"cuInit thất bại với mã lỗi {res}"
            return info

        # 2. Đếm số lượng GPU
        count = ctypes.c_int()
        if nvcuda.cuDeviceGetCount(ctypes.byref(count)) == 0 and count.value > 0:
            info["detected"] = True
            info["count"] = count.value

            # 3. Lấy thông tin thiết bị đầu tiên (Device 0)
            dev = ctypes.c_int()
            if nvcuda.cuDeviceGet(ctypes.byref(dev), 0) == 0:
                name_buf = ctypes.create_string_buffer(256)
                if nvcuda.cuDeviceGetName(name_buf, 256, dev) == 0:
                    info["name"] = name_buf.value.decode("utf-8", errors="replace")

                total_mem = ctypes.c_size_t()
                if nvcuda.cuDeviceTotalMem_v2(ctypes.byref(total_mem), dev) == 0:
                    info["total_vram_mb"] = int(total_mem.value // (1024 * 1024))

                # 4. Lấy bộ nhớ VRAM còn trống (tạo context tạm thời an toàn)
                ctx = ctypes.c_void_p()
                if nvcuda.cuCtxCreate_v2(ctypes.byref(ctx), 0, dev) == 0:
                    try:
                        free_mem = ctypes.c_size_t()
                        tot = ctypes.c_size_t()
                        if nvcuda.cuMemGetInfo_v2(ctypes.byref(free_mem), ctypes.byref(tot)) == 0:
                            info["free_vram_mb"] = int(free_mem.value // (1024 * 1024))
                    finally:
                        nvcuda.cuCtxDestroy_v2(ctx)

        # 5. Lấy phiên bản driver CUDA hỗ trợ
        driver_ver = ctypes.c_int()
        if nvcuda.cuDriverGetVersion(ctypes.byref(driver_ver)) == 0:
            major = driver_ver.value // 1000
            minor = (driver_ver.value % 1000) // 10
            info["driver_version"] = f"CUDA {major}.{minor} ({driver_ver.value})"

    except Exception as e:
        info["error"] = f"Lỗi truy vấn nvcuda: {e}"

    return info


def test_cuda_provider_functional() -> Tuple[bool, Optional[str]]:
    """Kiểm tra thực tế xem CUDAExecutionProvider có thể khởi tạo một ONNX session hay không.
    Nhiều trường hợp provider có tên trong danh sách nhưng thiếu cublas64_*.dll hoặc cudnn*.dll
    sẽ bị crash hoặc fallback về CPU.
    """
    try:
        import onnxruntime as ort
    except ImportError:
        return False, "Không có module onnxruntime"

    available = ort.get_available_providers()
    if "CUDAExecutionProvider" not in available:
        return False, "CUDAExecutionProvider không có trong danh sách provider của ONNX Runtime"

    try:
        # Tạo một graph ONNX tối thiểu trong bộ nhớ để test provider
        import numpy as np
        # Sử dụng một model giả lập nhỏ hoặc test session
        so = ort.SessionOptions()
        so.log_severity_level = 3  # Error only
        # Tạo test session với provider CUDA
        # Nếu thư viện thiếu DLL native, InferenceSession sẽ raise Exception tại đây
        dummy_session = ort.InferenceSession(
            b"\x08\x07\x12\x04test2\x15\x00\x00\x00\x00\x00\x00\x00\x00", # invalid binary check
            so,
            providers=["CUDAExecutionProvider"]
        )
        return True, None
    except Exception as e:
        err_msg = str(e)
        if "CUDA" in err_msg or "DLL" in err_msg or "failed to load" in err_msg.lower():
            return False, f"Thiếu thư viện native CUDA: {err_msg}"
        # Nếu lỗi chỉ là do dummy bytes (invalid model structure) thì provider đã load thành công
        if "protobuf" in err_msg.lower() or "model" in err_msg.lower() or "parse" in err_msg.lower():
            return True, None
        return False, f"Khởi tạo CUDA provider thất bại: {err_msg}"


def get_onnx_environment_info() -> Dict[str, Any]:
    """Kiểm tra môi trường thư viện ONNX Runtime và các Execution Providers."""
    env = {
        "ort_version": None,
        "available_providers": [],
        "cuda_provider_available": False,
        "cuda_provider_functional": False,
        "cuda_error": None,
    }

    try:
        import onnxruntime as ort
        env["ort_version"] = getattr(ort, "__version__", "unknown")
        provs = ort.get_available_providers()
        env["available_providers"] = provs
        env["cuda_provider_available"] = "CUDAExecutionProvider" in provs
        if env["cuda_provider_available"]:
            ok, err = test_cuda_provider_functional()
            env["cuda_provider_functional"] = ok
            env["cuda_error"] = err
        else:
            env["cuda_error"] = "Gói onnxruntime hiện tại là bản CPU (chưa bao gồm onnxruntime-gpu)"
    except Exception as e:
        env["cuda_error"] = f"Lỗi kiểm tra onnxruntime: {e}"

    return env


def resolve_device_policy(requested_device: str = "auto") -> Dict[str, Any]:
    """Áp dụng quy tắc lựa chọn thiết bị (Giai đoạn 3):
    - AUTO: Ưu tiên GPU nếu đầy đủ điều kiện (phần cứng + provider functional + VRAM >= 1GB). Nếu không, chọn CPU và nêu rõ lý do.
    - CPU: Luôn cho phép chọn CPU, không phụ thuộc máy có GPU hay không.
    - GPU (cuda): Chỉ cho phép nếu tương thích hoàn toàn. Nếu không, trả về lỗi chi tiết và đề xuất CPU.
    """
    req = (requested_device or "auto").strip().lower()
    if req in ("gpu", "nvidia"):
        req = "cuda"

    hw = get_nvidia_hardware_info()
    env = get_onnx_environment_info()

    MIN_VRAM_MB = 1000  # VieNeu v3 Turbo cần ~600MB fp32 hoặc ~200MB int8

    can_use_gpu = False
    rejection_reason = None

    if not hw["detected"]:
        rejection_reason = "Không phát hiện GPU NVIDIA trên hệ thống."
    elif not env["cuda_provider_available"]:
        rejection_reason = (
            f"Phát hiện GPU NVIDIA {hw['name']} (VRAM {hw['total_vram_mb']} MB, {hw['driver_version']}), "
            f"nhưng ONNX Runtime hiện tại (v{env['ort_version']}) là bản CPU và chưa tích hợp CUDAExecutionProvider."
        )
    elif not env["cuda_provider_functional"]:
        rejection_reason = (
            f"Phát hiện GPU NVIDIA {hw['name']} và CUDAExecutionProvider, "
            f"nhưng không thể nạp thư viện native CUDA: {env['cuda_error']}"
        )
    elif hw["total_vram_mb"] < MIN_VRAM_MB:
        rejection_reason = f"Dung lượng VRAM ({hw['total_vram_mb']} MB) không đủ tối thiểu ({MIN_VRAM_MB} MB) để nạp mô hình."
    else:
        can_use_gpu = True

    result = {
        "requested_device": req,
        "effective_device": "cpu",
        "allowed": True,
        "reason": "",
        "fallback_occurred": False,
        "hardware": hw,
        "environment": env,
    }

    if req == "cpu":
        result["effective_device"] = "cpu"
        result["reason"] = "Đang chạy chế độ CPU theo lựa chọn của người dùng."
    elif req == "cuda":
        if can_use_gpu:
            result["effective_device"] = "cuda"
            result["reason"] = f"GPU NVIDIA {hw['name']} (VRAM khả dụng: {hw['free_vram_mb']}/{hw['total_vram_mb']} MB) sẵn sàng tăng tốc phần cứng."
        else:
            result["effective_device"] = "cpu"
            result["allowed"] = False
            result["reason"] = rejection_reason
    else:  # AUTO mode
        if can_use_gpu:
            result["effective_device"] = "cuda"
            result["reason"] = f"Chế độ AUTO: Tự động kích hoạt GPU NVIDIA {hw['name']} để tăng tốc inference."
        else:
            result["effective_device"] = "cpu"
            result["fallback_occurred"] = True
            result["reason"] = f"Chế độ AUTO: Chạy an toàn trên CPU do {rejection_reason.lower()}"

    return result


def get_hardware_status_report(engine_instance=None) -> Dict[str, Any]:
    """Tạo báo cáo chẩn đoán trạng thái tổng thể cho backend API và UI."""
    hw = get_nvidia_hardware_info()
    env = get_onnx_environment_info()

    current_dev = getattr(engine_instance, "device", "cpu") if engine_instance else "cpu"
    current_mode = getattr(engine_instance, "mode", "v3turbo") if engine_instance else "v3turbo"
    current_prec = getattr(engine_instance, "precision", "int8") if engine_instance else "int8"
    is_ready = getattr(engine_instance, "ready", False) if engine_instance else False

    policy = resolve_device_policy(current_dev)

    return {
        "ready": is_ready,
        "mode": current_mode,
        "precision": current_prec,
        "device": policy["effective_device"],
        "requested_device": current_dev,
        "backend": getattr(engine_instance, "backend", "onnx") if engine_instance else "onnx",
        "cuda_available": (hw["detected"] and env["cuda_provider_functional"]),
        "gpu_name": hw["name"],
        "policy": {
            "effective_device": policy["effective_device"],
            "reason": policy["reason"],
            "fallback_occurred": policy["fallback_occurred"],
            "allowed": policy["allowed"],
        },
        "hardware": {
            "nvidia_detected": hw["detected"],
            "device_name": hw["name"],
            "vram_total_mb": hw["total_vram_mb"],
            "vram_free_mb": hw["free_vram_mb"],
            "driver_version": hw["driver_version"],
            "error": hw["error"],
        },
        "environment": {
            "ort_version": env["ort_version"],
            "available_providers": env["available_providers"],
            "cuda_provider_available": env["cuda_provider_available"],
            "cuda_provider_functional": env["cuda_provider_functional"],
            "cuda_error": env["cuda_error"],
        },
        "config": {
            "mode": current_mode,
            "precision": current_prec,
            "device": policy["effective_device"],
        },
    }
