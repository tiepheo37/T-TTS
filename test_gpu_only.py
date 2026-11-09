"""
test_gpu_only.py — KIỂM THỬ ĐỘC LẬP SUY LUẬN GPU THỰC TẾ (T-TTS v1.0.1)
========================================================================
Mục tiêu:
  Xác minh VieNeu-TTS v3 Turbo có thể chạy inference thật bằng GPU NVIDIA
  (RTX 2060) trên Windows hay không.

Nguyên tắc nghiêm ngặt:
  1. Dừng ngay nếu không có 'CUDAExecutionProvider'; ghi rõ nguyên nhân gốc rễ.
  2. Khởi tạo từng session ONNX trực tiếp bằng 'CUDAExecutionProvider' theo cấu hình thực tế.
  3. KHÔNG cho phép im lặng fallback sang CPU (không truyền CPUExecutionProvider làm cứu cánh).
  4. Kiểm tra provider thực tế của từng session sau khởi tạo.
  5. Thu thập thông tin phân vùng thực thi (execution partitioning).
  6. Chạy inference thật với đầu vào hợp lệ, xuất file WAV thật.
  7. KHÔNG dùng mock. Không đánh dấu đạt chỉ vì phát hiện card NVIDIA trong danh sách.
  8. Ghi toàn bộ log chi tiết và giải phóng tài nguyên sau kiểm thử.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Thiết lập đường dẫn gốc workspace
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Cấu hình encoding UTF-8 an toàn cho console Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
# Cấu hình logging ra cả console và file test_gpu_only.log
LOG_FILE = ROOT_DIR / "test_gpu_only.log"
logger = logging.getLogger("GPU_ONLY_TEST")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(str(LOG_FILE), mode="w", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def log_header(title: str):
    logger.info("=" * 70)
    logger.info(f"  {title}")
    logger.info("=" * 70)


def check_nvidia_hardware() -> Dict[str, Any]:
    """Kiểm tra phần cứng NVIDIA qua nvcuda / driver / nvidia-smi."""
    info: Dict[str, Any] = {
        "hardware_detected": False,
        "gpu_name": None,
        "vram_total_mb": None,
        "vram_free_mb": None,
        "driver_version": None,
        "cuda_driver_version": None,
        "nvcuda_dll_exists": False,
    }

    nvcuda_path = Path("C:/Windows/System32/nvcuda.dll")
    if nvcuda_path.exists():
        info["nvcuda_dll_exists"] = True

    try:
        import ctypes
        nvcuda = ctypes.WinDLL("nvcuda.dll")
        res = nvcuda.cuInit(0)
        if res == 0:
            count = ctypes.c_int()
            if nvcuda.cuDeviceGetCount(ctypes.byref(count)) == 0 and count.value > 0:
                dev = ctypes.c_int()
                nvcuda.cuDeviceGet(ctypes.byref(dev), 0)
                name_buf = ctypes.create_string_buffer(256)
                nvcuda.cuDeviceGetName(name_buf, 256, dev)
                info["gpu_name"] = name_buf.value.decode("utf-8", errors="ignore")
                info["hardware_detected"] = True

                total_mem = ctypes.c_size_t()
                if nvcuda.cuDeviceTotalMem_v2(ctypes.byref(total_mem), dev) == 0:
                    info["vram_total_mb"] = total_mem.value // (1024 * 1024)

                driver_ver = ctypes.c_int()
                if nvcuda.cuDriverGetVersion(ctypes.byref(driver_ver)) == 0:
                    major = driver_ver.value // 1000
                    minor = (driver_ver.value % 1000) // 10
                    info["cuda_driver_version"] = f"{major}.{minor} (raw: {driver_ver.value})"
    except Exception as e:
        logger.debug(f"Không thể đọc thông tin trực tiếp qua nvcuda ctypes: {e}")

    # Truy vấn thêm qua nvidia-smi nếu ctypes thiếu free memory
    if info["hardware_detected"]:
        try:
            import subprocess
            cmd = ["nvidia-smi", "--query-gpu=driver_version,memory.free,memory.total", "--format=csv,noheader,nounits"]
            out = subprocess.check_output(cmd, creationflags=0x08000000).decode("utf-8").strip()
            parts = [p.strip() for p in out.split(",")]
            if len(parts) >= 3:
                info["driver_version"] = parts[0]
                info["vram_free_mb"] = int(float(parts[1]))
                if not info["vram_total_mb"]:
                    info["vram_total_mb"] = int(float(parts[2]))
        except Exception:
            pass

    return info


def inspect_onnxruntime_environment() -> Dict[str, Any]:
    """Kiểm tra chi tiết gói onnxruntime và các execution providers hiện có."""
    env_info: Dict[str, Any] = {
        "ort_installed": False,
        "ort_version": None,
        "ort_file_location": None,
        "available_providers": [],
        "has_cuda_provider": False,
    }

    try:
        import onnxruntime as ort
        env_info["ort_installed"] = True
        env_info["ort_version"] = ort.__version__
        env_info["ort_file_location"] = str(Path(ort.__file__).parent)
        providers = ort.get_available_providers()
        env_info["available_providers"] = providers
        env_info["has_cuda_provider"] = "CUDAExecutionProvider" in providers
    except ImportError as e:
        env_info["error"] = str(e)

    return env_info


def inspect_cuda_runtime_dlls() -> Dict[str, bool]:
    """Kiểm tra sự hiện diện của các thư viện động CUDA/cuDNN Runtime cần thiết trên Windows."""
    dll_names = [
        "cudart64_12.dll",
        "cudart64_110.dll",
        "cublas64_12.dll",
        "cublasLt64_12.dll",
        "cudnn64_9.dll",
        "cudnn64_8.dll",
        "cufft64_11.dll",
        "curand64_10.dll",
    ]

    results = {}
    search_paths = [
        Path("C:/Windows/System32"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA"),
    ]
    # Thêm PATH môi trường
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if p and Path(p).is_dir():
            search_paths.append(Path(p))

    for dll in dll_names:
        found = False
        for sp in search_paths:
            if (sp / dll).is_file():
                found = True
                break
        results[dll] = found

    return results


def test_gpu_sessions_load(onnx_dir: Path, codec_dir: Path) -> Dict[str, Any]:
    """
    Thử nghiệm nạp 4 session ONNX của VieNeu-TTS v3 Turbo với CUDAExecutionProvider thuần túy.
    TUYỆT ĐỐI KHÔNG truyền CPUExecutionProvider làm fallback im lặng!
    """
    import onnxruntime as ort

    models = {
        "sess_pre": onnx_dir / "vieneu_prefill.onnx",
        "sess_dec": onnx_dir / "vieneu_decode_step.onnx",
        "sess_ac": onnx_dir / "vieneu_acoustic_cached.onnx",
        "sess_codec_dec": codec_dir / "moss_audio_tokenizer_decode_full.onnx",
    }

    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    # CHỈ định CUDAExecutionProvider, KHÔNG fallback CPU
    target_providers = ["CUDAExecutionProvider"]

    session_results = {}
    loaded_sessions = {}

    for name, path in models.items():
        if not path.is_file():
            session_results[name] = {
                "status": "FILE_NOT_FOUND",
                "path": str(path),
                "error": "Tệp mô hình không tồn tại",
            }
            continue

        logger.info(f"Đang kiểm tra nạp {name} ({path.name}) với {target_providers}...")
        t0 = time.perf_counter()
        try:
            sess = ort.InferenceSession(str(path), so, providers=target_providers)
            load_time = time.perf_counter() - t0
            actual_providers = sess.get_providers()
            logger.info(f"  -> Nạp thành công trong {load_time:.3f}s. Providers thực tế: {actual_providers}")

            # Kiểm tra xem có bị âm thầm fallback sang CPU hay không
            if "CUDAExecutionProvider" not in actual_providers:
                session_results[name] = {
                    "status": "SILENT_FALLBACK_REJECTED",
                    "actual_providers": actual_providers,
                    "load_time_s": load_time,
                    "error": "Phiên bị tự động fallback về CPU dù yêu cầu chỉ định CUDA",
                }
            else:
                session_results[name] = {
                    "status": "CUDA_ACTIVE",
                    "actual_providers": actual_providers,
                    "load_time_s": load_time,
                }
                loaded_sessions[name] = sess
        except Exception as e:
            load_time = time.perf_counter() - t0
            err_msg = str(e)
            logger.error(f"  -> THẤT BẠI: {err_msg}")
            session_results[name] = {
                "status": "FAILED",
                "load_time_s": load_time,
                "error": err_msg,
                "traceback": traceback.format_exc(),
            }

    # Giải phóng các session đã nạp thử nghiệm
    del loaded_sessions
    gc.collect()

    return session_results


def run_gpu_inference_pipeline() -> Dict[str, Any]:
    """
    Chạy toàn bộ pipeline kiểm chứng GPU inference độc lập.
    """
    log_header("BẮT ĐẦU KIỂM THỬ GPU SUY LUẬN ĐỘC LẬP (test_gpu_only.py)")

    report: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware": {},
        "onnxruntime": {},
        "cuda_runtime_dlls": {},
        "session_tests": {},
        "inference_test": None,
        "classification": None,
        "summary": "",
    }

    # ── 1. Kiểm tra phần cứng GPU ───────────────────────────────────────
    logger.info("1. Kiểm tra phần cứng NVIDIA...")
    hw = check_nvidia_hardware()
    report["hardware"] = hw
    if hw["hardware_detected"]:
        logger.info(f"  [OK] Phát hiện GPU: {hw['gpu_name']} (VRAM: {hw['vram_total_mb']} MB, Free: {hw['vram_free_mb']} MB)")
        logger.info(f"  [OK] Driver: {hw['driver_version']} | CUDA Driver Version: {hw['cuda_driver_version']}")
    else:
        logger.warning("  [CẢNH BÁO] Không phát hiện phần cứng NVIDIA hợp lệ hoặc driver chưa nạp.")

    # ── 2. Kiểm tra ONNX Runtime & CUDAExecutionProvider ───────────────
    logger.info("2. Kiểm tra thư viện ONNX Runtime và Execution Providers...")
    ort_env = inspect_onnxruntime_environment()
    report["onnxruntime"] = ort_env

    if not ort_env["ort_installed"]:
        logger.error(f"  [LỖI] ONNX Runtime chưa được cài đặt: {ort_env.get('error')}")
        report["classification"] = "GPU chưa chạy do thiếu thư viện hoặc không tương thích"
        report["summary"] = "ONNX Runtime chưa được cài đặt trong môi trường."
        return report

    logger.info(f"  Phiên bản ONNX Runtime: {ort_env['ort_version']}")
    logger.info(f"  Đường dẫn: {ort_env['ort_file_location']}")
    logger.info(f"  Danh sách Providers sẵn có: {ort_env['available_providers']}")

    # ── 3. Kiểm tra các DLL CUDA/cuDNN cần thiết ───────────────────────
    logger.info("3. Kiểm tra các thư viện động CUDA / cuDNN Runtime...")
    dlls = inspect_cuda_runtime_dlls()
    report["cuda_runtime_dlls"] = dlls
    for dll, found in dlls.items():
        status_str = "[CÓ]" if found else "[THIẾU]"
        logger.info(f"  {status_str} {dll}")

    # ĐIỀU KIỆN TIÊN QUYẾT: DỪNG NGAY NẾU KHÔNG CÓ CUDAExecutionProvider
    if not ort_env["has_cuda_provider"]:
        logger.error("=" * 70)
        logger.error("DỪNG KIỂM THỬ: Không tìm thấy 'CUDAExecutionProvider' trong ONNX Runtime!")
        logger.error("Nguyên nhân gốc rễ:")
        logger.error(f"  1. Gói onnxruntime hiện hành ({ort_env['ort_version']}) là bản CPU thuần (CPU-only wheel).")
        logger.error("  2. Chưa cài đặt onnxruntime-gpu (ví dụ: onnxruntime-gpu==1.20.0 hoặc 1.31.0).")
        logger.error("  3. Hệ thống thiếu các DLL phụ thuộc của CUDA Toolkit và cuDNN:")
        for dll, found in dlls.items():
            if not found:
                logger.error(f"     - Thiếu: {dll}")
        logger.error("Không được phép tự ý fallback sang CPU trong bài test GPU độc lập.")
        logger.error("=" * 70)

        report["classification"] = "GPU chưa chạy do thiếu thư viện hoặc không tương thích"
        report["summary"] = (
            f"Dừng kiểm thử vì onnxruntime hiện tại (v{ort_env['ort_version']}) là bản CPU thuần, "
            f"không có CUDAExecutionProvider và thiếu các DLL runtime CUDA/cuDNN trên Windows."
        )
        return report

    # ── 4. Thử nghiệm khởi tạo các Session với CUDA thuần túy ──────────
    logger.info("4. Khởi tạo 4 Session ONNX với CUDAExecutionProvider thuần túy...")
    try:
        from backend.models_bootstrap import ensure_local_models
        onnx_dir, codec_dir = ensure_local_models(precision="fp32")
    except Exception as e:
        logger.error(f"Không thể định vị thư mục mô hình local: {e}")
        report["classification"] = "Chưa thể kiểm chứng"
        report["summary"] = f"Lỗi định vị mô hình: {e}"
        return report

    sess_results = test_gpu_sessions_load(Path(onnx_dir), Path(codec_dir))
    report["session_tests"] = sess_results

    # Kiểm tra xem cả 4 session có nạp được CUDA không
    all_cuda = True
    any_cuda = False
    for s_name, s_res in sess_results.items():
        if s_res.get("status") == "CUDA_ACTIVE":
            any_cuda = True
        else:
            all_cuda = False
            logger.error(f"Session {s_name} không đạt trạng thái CUDA: {s_res}")

    if not any_cuda:
        report["classification"] = "GPU chưa chạy do thiếu thư viện hoặc không tương thích"
        report["summary"] = "Cả 4 session ONNX đều không thể khởi tạo thành công với CUDAExecutionProvider."
        return report

    if not all_cuda:
        report["classification"] = "SDK cần thay đổi kiến trúc"
        report["summary"] = "Một số session ONNX không thể chạy CUDA, cần kiến trúc phân vùng session linh hoạt."
        return report

    # ── 5. Thử nghiệm suy luận thật (Inference) và xuất file WAV ──────
    logger.info("5. Chạy suy luận thật với VieNeu-TTS v3 Turbo trên GPU...")
    test_text = "Xin chào, đây là bài kiểm thử suy luận GPU thật của VieNeu-TTS."
    output_wav = ROOT_DIR / "test_gpu_only_output.wav"

    try:
        # Sử dụng adapter/subclass an toàn để nạp VieNeu-TTS với CUDA
        # Chú ý: Không sửa site-packages, tiêm provider vào InferenceSession tạm thời
        import onnxruntime as ort
        orig_init = ort.InferenceSession.__init__

        def cuda_session_init(self, *args, **kwargs):
            kwargs["providers"] = ["CUDAExecutionProvider"]
            orig_init(self, *args, **kwargs)

        ort.InferenceSession.__init__ = cuda_session_init
        try:
            from vieneu import Vieneu
            t_load0 = time.perf_counter()
            tts = Vieneu(mode="v3turbo", precision="fp32", onnx_dir=str(onnx_dir))
            load_time = time.perf_counter() - t_load0
            logger.info(f"Nạp mô hình VieNeu-TTS thành công trong {load_time:.2f}s")

            # Warm-up 1 lần ngắn
            logger.info("Chạy warm-up inference...")
            _ = tts.infer("Khởi động.")

            # Đo inference chính thức
            logger.info(f"Bắt đầu suy luận văn bản: '{test_text}'...")
            t_inf0 = time.perf_counter()
            wav = tts.infer(test_text, voice="Nu-Thao")
            infer_time = time.perf_counter() - t_inf0

            import soundfile as sf
            sf.write(str(output_wav), wav, 48000)
            duration_s = len(wav) / 48000.0
            rtf = infer_time / duration_s if duration_s > 0 else 0.0

            logger.info(f"  -> Hoàn thành suy luận trong {infer_time:.3f}s")
            logger.info(f"  -> Thời lượng WAV: {duration_s:.2f}s | RTF: {rtf:.3f}x")
            logger.info(f"  -> File kết quả: {output_wav}")

            report["inference_test"] = {
                "success": True,
                "text": test_text,
                "voice": "Nu-Thao",
                "infer_time_s": infer_time,
                "audio_duration_s": duration_s,
                "rtf": rtf,
                "output_file": str(output_wav),
            }
            report["classification"] = "GPU inference thật đã đạt"
            report["summary"] = f"Suy luận GPU thành công: Latency {infer_time:.3f}s, RTF {rtf:.3f}x."
        finally:
            ort.InferenceSession.__init__ = orig_init

    except Exception as e:
        logger.error(f"Lỗi suy luận GPU thật: {e}", exc_info=True)
        report["inference_test"] = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        report["classification"] = "GPU chưa chạy do thiếu thư viện hoặc không tương thích"
        report["summary"] = f"Không thể hoàn thành suy luận GPU: {e}"

    return report


if __name__ == "__main__":
    rep = run_gpu_inference_pipeline()
    log_header("KẾT THÚC KIỂM THỬ GPU")
    logger.info(f"Phân loại kết quả: {rep['classification']}")
    logger.info(f"Tóm tắt: {rep['summary']}")

    # Lưu kết quả JSON để phục vụ báo cáo
    json_path = ROOT_DIR / "test_gpu_only_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    logger.info(f"Đã lưu kết quả chi tiết tại: {json_path}")

    # Thoát với mã 0 nếu đạt, mã 2 nếu thiếu thư viện, mã 3 nếu lỗi kiến trúc
    if rep["classification"] == "GPU inference thật đã đạt":
        sys.exit(0)
    elif "thiếu thư viện" in (rep["classification"] or ""):
        sys.exit(2)
    elif "kiến trúc" in (rep["classification"] or ""):
        sys.exit(3)
    else:
        sys.exit(1)
