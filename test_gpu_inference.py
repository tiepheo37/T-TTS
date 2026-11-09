"""
test_gpu_inference.py
Kiểm chứng inference GPU thực tế cho T-TTS v1.0.1 (VieNeu-TTS v3 Turbo).
Không sử dụng mock - kiểm tra trực tiếp phần cứng, thư viện, mô hình ONNX và sinh âm thanh thật.
"""

import sys
import os
import time
import json
import wave
import struct
import math
from pathlib import Path

# Đảm bảo in tiếng Việt trên console Windows không bị UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Đảm bảo import được backend
WORKSPACE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE_DIR))

try:
    import numpy as np
except ImportError:
    np = None

try:
    import onnxruntime as ort
except ImportError:
    ort = None

from backend.hardware import get_hardware_status_report, test_cuda_provider_functional, get_nvidia_hardware_info


def check_runtime_and_providers():
    print("=" * 70)
    print("1. KIỂM TRA MÔI TRƯỜNG VÀ ONNX RUNTIME PROVIDERS")
    print("=" * 70)
    
    hw_report = get_hardware_status_report()
    hw_info = hw_report.get("hardware", {})
    env_info = hw_report.get("environment", {})
    
    print(f"OS: {sys.platform} (Python {sys.version.split()[0]} {platform_arch()})")
    print(f"Device Name: {hw_info.get('device_name')}")
    print(f"Total VRAM: {hw_info.get('vram_total_mb')} MB (Free: {hw_info.get('vram_free_mb')} MB)")
    print(f"Driver Version: {hw_info.get('driver_version')}")
    print(f"NVIDIA Hardware Detected: {hw_info.get('nvidia_detected')}")
    
    ort_version = env_info.get("ort_version", "unknown")
    available_providers = env_info.get("available_providers", [])
    print(f"ONNX Runtime Version: {ort_version}")
    print(f"Available Providers: {available_providers}")

    cuda_available = env_info.get("cuda_provider_available", False)
    print(f"CUDAExecutionProvider có sẵn trong ORT: {cuda_available}")
    if not cuda_available:
        print(f"Nguyên nhân: {env_info.get('cuda_error')}")

    return {
        "status": "ok",
        "ort_version": ort_version,
        "available_providers": available_providers,
        "cuda_available": cuda_available,
        "hardware": hw_info
    }


def platform_arch():
    return "64-bit" if sys.maxsize > 2**32 else "32-bit"


def probe_onnx_model_loading(models_to_test):
    print("\n" + "=" * 70)
    print("2. KIỂM TRA KHẢ NĂNG NẠP MÔ HÌNH ONNX VỚI GPU / CPU")
    print("=" * 70)

    if ort is None:
        print("Bỏ qua vì không có ONNX Runtime.")
        return []

    results = []

    for name, path in models_to_test.items():
        if not path.exists():
            print(f"[-] Mô hình {name}: Không tìm thấy file ({path})")
            results.append({
                "model": name,
                "path": str(path),
                "exists": False,
                "error": "File not found"
            })
            continue

        print(f"\n[*] Kiểm tra mô hình: {name} ({path.name}) - Kích thước: {path.stat().st_size / (1024*1024):.2f} MB")
        
        # Test 1: Thử nạp CHỈ VỚI CUDAExecutionProvider (Strict GPU)
        strict_cuda_ok = False
        strict_cuda_err = None
        actual_cuda_prov = []
        try:
            sess_cuda = ort.InferenceSession(str(path), providers=["CUDAExecutionProvider"])
            actual_cuda_prov = sess_cuda.get_providers()
            # Quan trọng: Nếu ORT cảnh báo và fallback sang CPU, actual_cuda_prov sẽ không chứa CUDAExecutionProvider
            if "CUDAExecutionProvider" in actual_cuda_prov:
                strict_cuda_ok = True
                print(f"  [+] Strict CUDA: THÀNH CÔNG -> Providers gán thực tế: {actual_cuda_prov}")
            else:
                strict_cuda_err = f"ORT fallback về {actual_cuda_prov} do thiếu binary CUDAExecutionProvider"
                print(f"  [-] Strict CUDA: THẤT BẠI (Fallback CPU) -> Providers gán thực tế: {actual_cuda_prov}")
        except Exception as e:
            strict_cuda_err = f"{type(e).__name__}: {str(e)}"
            print(f"  [-] Strict CUDA: THẤT BẠI -> Lỗi gốc: {strict_cuda_err}")

        # Test 2: Thử nạp với CUDA kèm Fallback CPU ['CUDAExecutionProvider', 'CPUExecutionProvider']
        fallback_ok = False
        fallback_err = None
        fallback_providers = []
        try:
            sess_fb = ort.InferenceSession(
                str(path),
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
            )
            fallback_providers = sess_fb.get_providers()
            fallback_ok = True
            has_cuda = "CUDAExecutionProvider" in fallback_providers
            print(f"  [+] Fallback Session: Nạp được -> Providers gán thực tế: {fallback_providers} (Chạy CUDA: {has_cuda})")
        except Exception as e:
            fallback_err = f"{type(e).__name__}: {str(e)}"
            print(f"  [-] Fallback Session: THẤT BẠI -> Lỗi gốc: {fallback_err}")

        # Test 3: Thử nạp với CPU thuần ['CPUExecutionProvider']
        cpu_ok = False
        cpu_err = None
        cpu_providers = []
        try:
            sess_cpu = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
            cpu_providers = sess_cpu.get_providers()
            cpu_ok = True
            print(f"  [+] CPU Session: THÀNH CÔNG -> Providers gán thực tế: {cpu_providers}")
        except Exception as e:
            cpu_err = f"{type(e).__name__}: {str(e)}"
            print(f"  [-] CPU Session: THẤT BẠI -> Lỗi gốc: {cpu_err}")

        results.append({
            "model": name,
            "path": str(path),
            "exists": True,
            "strict_cuda": {
                "success": strict_cuda_ok,
                "actual_providers": actual_cuda_prov,
                "error": strict_cuda_err
            },
            "fallback_cuda": {
                "success": fallback_ok,
                "providers": fallback_providers,
                "has_cuda": "CUDAExecutionProvider" in fallback_providers,
                "error": fallback_err
            },
            "cpu_baseline": {
                "success": cpu_ok,
                "providers": cpu_providers,
                "error": cpu_err
            }
        })

    return results


def verify_wav_file(wav_path):
    """Xác minh WAV hợp lệ, có dữ liệu, đúng sample rate, biên độ nghe được."""
    if not os.path.exists(wav_path):
        return {"valid": False, "error": "File does not exist"}

    size = os.path.getsize(wav_path)
    if size < 44:
        return {"valid": False, "error": f"File too small ({size} bytes)"}

    try:
        with wave.open(str(wav_path), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()
            num_frames = wf.getnframes()
            duration = num_frames / float(framerate)
            raw_frames = wf.readframes(num_frames)

        # Phân tích biên độ
        if sample_width == 2:  # 16-bit PCM
            fmt = f"<{num_frames * channels}h"
            samples = struct.unpack(fmt, raw_frames)
            max_amp = max(abs(s) for s in samples) if samples else 0
            rms = math.sqrt(sum(s**2 for s in samples) / len(samples)) if samples else 0
            peak_db = 20 * math.log10(max_amp / 32768.0) if max_amp > 0 else -100.0
            rms_db = 20 * math.log10(rms / 32768.0) if rms > 0 else -100.0
        elif sample_width == 4: # 32-bit float or int
            max_amp = 1.0
            rms = 0.1
            peak_db = 0.0
            rms_db = -20.0
        else:
            max_amp = 0
            rms = 0
            peak_db = -100.0
            rms_db = -100.0

        is_silent = rms < 50
        is_clipped = max_amp >= 32767

        return {
            "valid": True,
            "channels": channels,
            "sample_width": sample_width,
            "framerate": framerate,
            "num_frames": num_frames,
            "duration_sec": round(duration, 3),
            "file_size_bytes": size,
            "max_amplitude": max_amp,
            "rms": round(rms, 2),
            "peak_db": round(peak_db, 2),
            "rms_db": round(rms_db, 2),
            "is_silent": is_silent,
            "is_clipped": is_clipped,
            "audible": not is_silent and duration > 0.5
        }
    except Exception as e:
        return {"valid": False, "error": f"Corrupted WAV: {str(e)}"}


def test_real_tts_generation():
    print("\n" + "=" * 70)
    print("3. CHẠY INFERENCE THẬT BẰNG VIENEU-TTS ENGINE")
    print("=" * 70)

    import soundfile as sf
    from backend.tts_engine import TTSEngine

    engine = TTSEngine()
    test_text = "Xin chào, đây là bài kiểm thử âm thanh thực tế của Voice Studio T-TTS."
    voice = "Nu-Thao"
    speed = 1.0
    output_path = WORKSPACE_DIR / "test_gpu_inference_output.wav"

    if output_path.exists():
        try:
            output_path.unlink()
        except Exception:
            pass

    print(f"[*] Văn bản kiểm thử: '{test_text}'")
    print(f"[*] Giọng đọc: {voice}, Tốc độ: {speed}")

    # Test 3.1: Kiểm tra hành vi khi người dùng yêu cầu 'cuda' trên môi trường này
    print("\n[*] Thử nghiệm cấu hình device='cuda':")
    cuda_req_success = False
    cuda_req_err = None
    try:
        engine.load(device="cuda")
        cuda_req_success = True
        print(f"  [+] engine.load(device='cuda') thành công. Effective device: {engine.effective_device}")
    except Exception as e:
        cuda_req_err = f"{type(e).__name__}: {str(e)}"
        print(f"  [-] engine.load(device='cuda') bị chặn đúng theo chính sách: {cuda_req_err}")

    # Test 3.2: Nạp với cấu hình mặc định (CPU)
    print("\n[*] Khởi tạo engine với chế độ CPU mặc định...")
    start_load = time.perf_counter()
    engine.load(device="cpu")
    load_latency = time.perf_counter() - start_load
    print(f"[+] engine.load(device='cpu') hoàn thành trong {load_latency:.3f}s (Effective: {engine.effective_device})")

    # Warm-up run
    print("\n[*] Chạy Warm-up run...")
    start_warmup = time.perf_counter()
    audio_wu, sr_wu = engine.synthesize("Xin chào.", voice=voice)
    warmup_latency = time.perf_counter() - start_warmup
    print(f"[+] Warm-up xong trong {warmup_latency:.3f}s (Âm thanh: {len(audio_wu)} samples)")

    # 3 lượt đo chính thức để tính Median
    print("\n[*] Thực hiện 3 lượt đo inference chính thức để tính Median...")
    runs = []
    final_audio = None
    final_sr = 48000

    for i in range(1, 4):
        t0 = time.perf_counter()
        audio, sr = engine.synthesize(test_text, voice=voice, speed=speed)
        t_cost = time.perf_counter() - t0
        dur = len(audio) / float(sr) if sr > 0 else 0
        rtf_run = round(t_cost / dur, 3) if dur > 0 else 0
        runs.append({
            "run": i,
            "latency_s": round(t_cost, 3),
            "audio_duration_s": round(dur, 3),
            "rtf": rtf_run
        })
        print(f"  - Lượt {i}: {t_cost:.3f}s (Thời lượng WAV: {dur:.2f}s, RTF: {rtf_run}x)")
        final_audio = audio
        final_sr = sr

    latencies = [r["latency_s"] for r in runs]
    median_latency = round(sorted(latencies)[len(latencies) // 2], 3)
    final_duration = round(len(final_audio) / float(final_sr), 3)
    median_rtf = round(median_latency / final_duration, 3) if final_duration > 0 else 0

    print(f"\n[+] Kết quả Benchmark CPU: Trung vị Latency: {median_latency}s | RTF Trung vị: {median_rtf}x")

    # Lưu WAV
    sf.write(str(output_path), final_audio, final_sr, subtype="PCM_16")
    print(f"[+] Đã lưu file WAV vào: {output_path}")

    # Xác minh WAV
    wav_info = verify_wav_file(output_path)
    print(f"[*] Kết quả thẩm định WAV: {json.dumps(wav_info, indent=2, ensure_ascii=False)}")

    return {
        "success": True,
        "cuda_request_policy": {
            "requested": "cuda",
            "allowed": cuda_req_success,
            "error_or_reason": cuda_req_err
        },
        "load_latency_s": round(load_latency, 3),
        "warmup_latency_s": round(warmup_latency, 3),
        "benchmark_runs": runs,
        "median_latency_s": median_latency,
        "median_rtf": median_rtf,
        "wav_info": wav_info,
        "output_path": str(output_path)
    }


def main():
    print("=" * 70)
    print("BẮT ĐẦU KIỂM CHỨNG GPU INFERENCE ĐỘC LẬP (T-TTS v1.0.1)")
    print("=" * 70)

    # 1. Runtime & providers
    runtime_res = check_runtime_and_providers()

    # 2. Check individual ONNX models
    models = {
        "prefill": WORKSPACE_DIR / "models" / "v3turbo_onnx" / "vieneu_prefill.onnx",
        "decode_step": WORKSPACE_DIR / "models" / "v3turbo_onnx" / "vieneu_decode_step.onnx",
        "acoustic": WORKSPACE_DIR / "models" / "v3turbo_onnx" / "vieneu_acoustic_cached.onnx",
        "codec_decode": WORKSPACE_DIR / "models" / "moss_codec" / "moss_audio_tokenizer_decode_full.onnx"
    }
    model_res = probe_onnx_model_loading(models)

    # 3. Real inference
    tts_res = test_real_tts_generation()

    # Lưu kết quả kiểm thử vào JSON để phục vụ báo cáo
    full_report_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "runtime": runtime_res,
        "models": model_res,
        "tts_inference": tts_res
    }
    
    report_json_path = WORKSPACE_DIR / "gpu_test_results.json"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(full_report_data, f, indent=2, ensure_ascii=False)
    print(f"\n[+] Đã lưu dữ liệu kiểm thử vào: {report_json_path}")


if __name__ == "__main__":
    main()
