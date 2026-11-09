"""
test_gpu_codec_experiment.py — THỬ NGHIỆM ĐỘC LẬP TĂNG TỐC CODEC BẰNG GPU
=============================================================================
Mục tiêu:
  Xác minh khả năng tăng tốc phần giải mã âm thanh Vocoder (sess_codec_dec)
  của VieNeu-TTS v3 Turbo bằng NVIDIA RTX 2060, trong khi giữ các session
  autoregressive (sess_pre, sess_dec, sess_ac) trên CPU.

Nguyên tắc:
  1. Không monkey-patch toàn cục — sử dụng VieNeuHybridEngineAdapter.
  2. Xác minh nghiêm ngặt sự hiện diện của CUDAExecutionProvider và DLL runtime.
  3. Tuyệt đối không cho phép im lặng fallback sang CPU khi yêu cầu GPU.
  4. Nếu thiếu provider hoặc DLL, dừng và ghi rõ nguyên nhân gốc; đo benchmark
     CPU codec baseline để đối chứng.
  5. Nếu chạy được GPU thật, chạy warm-up, đo ít nhất 3 lượt và so sánh trung vị.
  6. Ghi log đầy đủ ra file test_gpu_codec_experiment.log và xuất JSON kết quả.
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

# Thiết lập đường dẫn gốc
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Cấu hình UTF-8 an toàn cho console Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LOG_FILE = ROOT_DIR / "test_gpu_codec_experiment.log"
logger = logging.getLogger("GPU_CODEC_TEST")
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
    logger.info("=" * 72)
    logger.info(f"  {title}")
    logger.info("=" * 72)


def check_gpu_hardware() -> Dict[str, Any]:
    """Kiểm tra phần cứng NVIDIA qua driver và ctypes."""
    hw_info: Dict[str, Any] = {
        "detected": False,
        "name": None,
        "vram_total_mb": None,
        "vram_free_mb": None,
        "driver_version": None,
        "cuda_driver_version": None,
    }

    try:
        import ctypes
        nvcuda = ctypes.WinDLL("nvcuda.dll")
        if nvcuda.cuInit(0) == 0:
            count = ctypes.c_int()
            if nvcuda.cuDeviceGetCount(ctypes.byref(count)) == 0 and count.value > 0:
                dev = ctypes.c_int()
                nvcuda.cuDeviceGet(ctypes.byref(dev), 0)
                name_buf = ctypes.create_string_buffer(256)
                nvcuda.cuDeviceGetName(name_buf, 256, dev)
                hw_info["name"] = name_buf.value.decode("utf-8", errors="ignore")
                hw_info["detected"] = True

                total_mem = ctypes.c_size_t()
                if nvcuda.cuDeviceTotalMem_v2(ctypes.byref(total_mem), dev) == 0:
                    hw_info["vram_total_mb"] = total_mem.value // (1024 * 1024)

                driver_ver = ctypes.c_int()
                if nvcuda.cuDriverGetVersion(ctypes.byref(driver_ver)) == 0:
                    major = driver_ver.value // 1000
                    minor = (driver_ver.value % 1000) // 10
                    hw_info["cuda_driver_version"] = f"{major}.{minor}"
    except Exception as e:
        logger.debug(f"Không thể đọc thông tin qua nvcuda: {e}")

    try:
        import subprocess
        cmd = ["nvidia-smi", "--query-gpu=driver_version,memory.free,memory.total", "--format=csv,noheader,nounits"]
        out = subprocess.check_output(cmd, creationflags=0x08000000).decode("utf-8").strip()
        parts = [p.strip() for p in out.split(",")]
        if len(parts) >= 3:
            hw_info["driver_version"] = parts[0]
            hw_info["vram_free_mb"] = int(float(parts[1]))
            if not hw_info["vram_total_mb"]:
                hw_info["vram_total_mb"] = int(float(parts[2]))
    except Exception:
        pass

    return hw_info


def inspect_ort_and_dlls() -> Tuple[Dict[str, Any], Dict[str, bool]]:
    """Kiểm tra môi trường ONNX Runtime và các DLL CUDA/cuDNN."""
    import onnxruntime as ort

    ort_info = {
        "version": ort.__version__,
        "location": str(Path(ort.__file__).parent),
        "available_providers": ort.get_available_providers(),
        "has_cuda_provider": "CUDAExecutionProvider" in ort.get_available_providers(),
    }

    required_dlls = [
        "cudart64_12.dll",
        "cublas64_12.dll",
        "cublasLt64_12.dll",
        "cudnn64_9.dll",
        "cufft64_11.dll",
        "curand64_10.dll",
    ]

    dll_status = {}
    search_paths = [
        Path("C:/Windows/System32"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA"),
    ]
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if p and Path(p).is_dir():
            search_paths.append(Path(p))

    for dll in required_dlls:
        found = any((sp / dll).is_file() for sp in search_paths)
        dll_status[dll] = found

    return ort_info, dll_status


def benchmark_codec_standalone(codec_dir: Path, provider: str, iterations: int = 3) -> Dict[str, Any]:
    """
    Đo lường chi tiết tốc độ xử lý của riêng vocoder codec (moss_audio_tokenizer_decode_full.onnx)
    trên provider chỉ định (CPU hoặc CUDA).
    """
    import onnxruntime as ort

    codec_path = codec_dir / "moss_audio_tokenizer_decode_full.onnx"
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    logger.info(f"Khởi tạo phiên Codec Standalone với provider: ['{provider}']...")
    t_load0 = time.perf_counter()
    sess = ort.InferenceSession(str(codec_path), so, providers=[provider])
    load_time = time.perf_counter() - t_load0

    actual_providers = sess.get_providers()
    logger.info(f"  -> Nạp trong {load_time:.3f}s. Providers thực tế: {actual_providers}")

    if provider not in actual_providers:
        raise RuntimeError(f"Session bị fallback về {actual_providers} thay vì {provider}!")

    # Giả lập mã âm học hợp lệ cho một câu dài vừa phải: T=150 frames (~3.0 giây âm thanh)
    # Vocoder MOSS Audio Tokenizer sử dụng n_vq=16
    t_frames = 150
    dummy_codes = np.random.randint(0, 1024, size=(1, t_frames, 16), dtype=np.int32)
    dummy_lens = np.array([t_frames], dtype=np.int32)

    # 1. Warm-up
    logger.info("  -> Chạy warm-up codec 1 lượt...")
    _ = sess.run(None, {"audio_codes": dummy_codes, "audio_code_lengths": dummy_lens})

    # 2. Đo 3 lượt chính thức
    latencies = []
    durations = []
    logger.info(f"  -> Bắt đầu đo {iterations} lượt chính thức...")
    for i in range(iterations):
        t0 = time.perf_counter()
        out = sess.run(None, {"audio_codes": dummy_codes, "audio_code_lengths": dummy_lens})
        dt = time.perf_counter() - t0
        latencies.append(dt)

        wav = out[0][0].mean(0).astype(np.float32)
        dur = len(wav) / 48000.0
        durations.append(dur)
        rtf = dt / dur if dur > 0 else 0
        logger.info(f"     Lượt {i+1}: Latency = {dt*1000:.2f} ms | WAV = {dur:.2f} s | RTF Codec = {rtf:.4f}x")

    median_lat = float(np.median(latencies))
    avg_dur = float(np.mean(durations))
    median_rtf = median_lat / avg_dur if avg_dur > 0 else 0

    del sess
    gc.collect()

    return {
        "provider": provider,
        "actual_providers": actual_providers,
        "load_time_s": load_time,
        "latencies_s": latencies,
        "median_latency_ms": median_lat * 1000,
        "wav_duration_s": avg_dur,
        "median_rtf": median_rtf,
    }


def run_experiment() -> Dict[str, Any]:
    """Chạy toàn bộ thí nghiệm kiểm thử Codec GPU vs CPU."""
    log_header("BẮT ĐẦU THỬ NGHIỆM TĂNG TỐC CODEC BẰNG GPU (test_gpu_codec_experiment.py)")

    results: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware": {},
        "ort_info": {},
        "dll_status": {},
        "codec_cpu_baseline": None,
        "codec_gpu_test": None,
        "hybrid_e2e_test": None,
        "status": "CHƯA_ĐẠT",
        "reason": "",
    }

    # 1. Kiểm tra phần cứng
    logger.info("1. Kiểm tra phần cứng GPU NVIDIA...")
    hw = check_gpu_hardware()
    results["hardware"] = hw
    if hw["detected"]:
        logger.info(f"  [OK] GPU: {hw['name']} (VRAM: {hw['vram_total_mb']} MB, Free: {hw['vram_free_mb']} MB)")
        logger.info(f"  [OK] Driver: {hw['driver_version']} | CUDA Driver Version: {hw['cuda_driver_version']}")
    else:
        logger.warning("  [CẢNH BÁO] Không phát hiện GPU NVIDIA qua driver.")

    # 2. Kiểm tra ONNX Runtime & DLLs
    logger.info("2. Kiểm tra ONNX Runtime và các DLL CUDA/cuDNN...")
    ort_info, dll_status = inspect_ort_and_dlls()
    results["ort_info"] = ort_info
    results["dll_status"] = dll_status

    logger.info(f"  Phiên bản ONNX Runtime: {ort_info['version']}")
    logger.info(f"  Danh sách Providers: {ort_info['available_providers']}")

    for dll, found in dll_status.items():
        st = "[CÓ]" if found else "[THIẾU]"
        logger.info(f"  {st} {dll}")

    # 3. Định vị mô hình local
    logger.info("3. Định vị thư mục mô hình VieNeu-TTS local...")
    try:
        from backend.models_bootstrap import ensure_local_models
        onnx_dir, codec_dir = ensure_local_models(precision="fp32")
        onnx_dir = Path(onnx_dir)
        codec_dir = Path(codec_dir)
        logger.info(f"  onnx_dir: {onnx_dir}")
        logger.info(f"  codec_dir: {codec_dir}")
    except Exception as e:
        logger.error(f"  [LỖI] Không thể nạp đường dẫn mô hình: {e}")
        results["status"] = "CHƯA_ĐẠT"
        results["reason"] = f"Lỗi nạp mô hình: {e}"
        return results

    # 4. Đo Benchmark Baseline của Codec trên CPU
    logger.info("4. Đo Baseline xử lý Vocoder Codec trên CPU (3 lượt chuẩn)...")
    try:
        cpu_bench = benchmark_codec_standalone(codec_dir, "CPUExecutionProvider", iterations=3)
        results["codec_cpu_baseline"] = cpu_bench
        logger.info(f"  [CPU BASELINE] Trung vị Latency Codec: {cpu_bench['median_latency_ms']:.2f} ms "
                    f"cho {cpu_bench['wav_duration_s']:.2f}s âm thanh (RTF: {cpu_bench['median_rtf']:.4f}x)")
    except Exception as e:
        logger.error(f"  [LỖI] Không thể đo baseline CPU codec: {e}")
        results["status"] = "CHƯA_ĐẠT"
        results["reason"] = f"Lỗi CPU codec: {e}"
        return results

    # 5. Kiểm tra điều kiện chạy CUDA
    logger.info("5. Kiểm tra điều kiện thực thi CUDA cho sess_codec_dec...")
    if not ort_info["has_cuda_provider"]:
        logger.error("=" * 72)
        logger.error("DỪNG THỬ NGHIỆM: Không thể chạy CUDAExecutionProvider!")
        logger.error("Nguyên nhân gốc rễ:")
        logger.error(f"  1. Gói onnxruntime hiện hành (v{ort_info['version']}) là bản CPU thuần.")
        logger.error("  2. Chưa có gói onnxruntime-gpu tương thích trong môi trường.")
        logger.error("  3. Thiếu các thư viện động runtime trên Windows:")
        for dll, found in dll_status.items():
            if not found:
                logger.error(f"     - {dll}")
        logger.error("Không được phép tự ý fallback sang CPU trong bài test này.")
        logger.error("=" * 72)

        results["status"] = "CHƯA_ĐẠT"
        results["reason"] = (
            f"Thiếu CUDAExecutionProvider trong onnxruntime (v{ort_info['version']}) "
            f"và thiếu các runtime DLL (cudart64_12.dll, cublas64_12.dll, cudnn64_9.dll)."
        )
        return results

    # 6. Thử nghiệm chạy Codec trên GPU nếu có provider
    logger.info("6. Thử nghiệm khởi tạo sess_codec_dec trên GPU qua Adapter...")
    try:
        from backend.vieneu_adapter import VieNeuHybridEngineAdapter

        # Thử nghiệm standalone codec với CUDA
        ok, codec_res = VieNeuHybridEngineAdapter.test_codec_standalone(
            codec_dir=codec_dir,
            providers=["CUDAExecutionProvider"],
            allow_fallback=False,
        )
        results["codec_gpu_test"] = codec_res

        if not ok:
            logger.error(f"  [LỖI] Codec CUDA không khởi tạo được: {codec_res.get('error')}")
            results["status"] = "CHƯA_ĐẠT"
            results["reason"] = f"Codec CUDA thất bại: {codec_res.get('error')}"
            return results

        logger.info(f"  [THÀNH CÔNG] Codec chạy được trên CUDA! Latency đơn: {codec_res['inference_time_s']*1000:.2f} ms")

        # Đo 3 lượt chính thức trên GPU
        gpu_bench = benchmark_codec_standalone(codec_dir, "CUDAExecutionProvider", iterations=3)
        results["codec_gpu_benchmark"] = gpu_bench
        logger.info(f"  [GPU CODEC] Trung vị Latency Codec: {gpu_bench['median_latency_ms']:.2f} ms "
                    f"(So với CPU: {cpu_bench['median_latency_ms']:.2f} ms)")

        # 7. Thử nghiệm toàn trình Hybrid Engine (sess_codec_dec = CUDA, sess_ar = CPU)
        logger.info("7. Thử nghiệm toàn trình End-to-End với Hybrid Adapter...")
        hybrid_adapter = VieNeuHybridEngineAdapter(
            onnx_dir=onnx_dir,
            codec_dir=codec_dir,
            providers_codec=["CUDAExecutionProvider"],
            providers_ar=["CPUExecutionProvider"],
            allow_silent_fallback=False,
        )

        test_text = "Xin chào, đây là bài kiểm thử cấu hình Hybrid GPU Vocoder của VieNeu-TTS."
        logger.info(f"  Suy luận văn bản: '{test_text}'")
        t_infer0 = time.perf_counter()
        wav = hybrid_adapter.infer(test_text, voice="Nu-Thao")
        total_time = time.perf_counter() - t_infer0

        import soundfile as sf
        out_wav = ROOT_DIR / "test_gpu_codec_experiment_output.wav"
        sf.write(str(out_wav), wav, 48000)
        dur = len(wav) / 48000.0

        results["hybrid_e2e_test"] = {
            "success": True,
            "text": test_text,
            "total_time_s": total_time,
            "wav_duration_s": dur,
            "rtf": total_time / dur if dur > 0 else 0,
            "output_file": str(out_wav),
            "session_providers": hybrid_adapter.provider_report,
        }
        results["status"] = "ĐẠT"
        results["reason"] = "Inference CUDA cho sess_codec_dec thành công, tạo WAV hợp lệ."

    except Exception as e:
        logger.error(f"  [LỖI] Lỗi trong quá trình thử nghiệm GPU codec: {e}", exc_info=True)
        results["status"] = "CHƯA_ĐẠT"
        results["reason"] = str(e)

    return results


if __name__ == "__main__":
    res = run_experiment()
    log_header("KẾT THÚC THỬ NGHIỆM")
    logger.info(f"Trạng thái chính thức: {res['status']}")
    logger.info(f"Chi tiết: {res['reason']}")

    # Lưu kết quả JSON
    out_json = ROOT_DIR / "test_gpu_codec_experiment_results.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    logger.info(f"Đã lưu kết quả chi tiết tại: {out_json}")

    if res["status"] == "ĐẠT":
        sys.exit(0)
    else:
        sys.exit(2)
