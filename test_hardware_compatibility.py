"""Bộ kiểm thử độc lập độ tương thích phần cứng và lựa chọn CPU/GPU (Giai đoạn 4).

Chạy trực tiếp mà không cần build lại ứng dụng.
Bao gồm 10 bài test kiểm tra đa dạng tình huống phần cứng (thực tế và mock).
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import io
import wave
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.hardware import (
    get_nvidia_hardware_info,
    get_onnx_environment_info,
    resolve_device_policy,
    get_hardware_status_report,
)
from backend.tts_engine import TTSEngine


class TestHardwareCompatibility(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 80)
        print("BẮT ĐẦU KIỂM THỬ TƯƠNG THÍCH PHẦN CỨNG CPU/GPU CHO T-TTS v1.0.1")
        print("=" * 80)

    # --------------------------------------------------------------------------
    # TEST 1: Không có GPU NVIDIA hoặc không phát hiện được GPU (Mock)
    # --------------------------------------------------------------------------
    def test_01_no_nvidia_gpu_detected(self):
        print("\n[TEST 1] Tình huống: Máy không có GPU NVIDIA (Mock)...", flush=True)
        mock_hw = {
            "detected": False,
            "count": 0,
            "name": None,
            "total_vram_mb": 0,
            "free_vram_mb": 0,
            "driver_version": None,
            "error": "Không tìm thấy driver NVIDIA (nvcuda.dll)",
        }
        with patch("backend.hardware.get_nvidia_hardware_info", return_value=mock_hw):
            res_cuda = resolve_device_policy("cuda")
            self.assertFalse(res_cuda["allowed"])
            self.assertEqual(res_cuda["effective_device"], "cpu")
            self.assertIn("Không phát hiện GPU NVIDIA", res_cuda["reason"])

            res_auto = resolve_device_policy("auto")
            self.assertEqual(res_auto["effective_device"], "cpu")
            self.assertTrue(res_auto["fallback_occurred"])
            print("  -> Kết quả: Chặn yêu cầu GPU và fallback CPU an toàn. [PASSED]")

    # --------------------------------------------------------------------------
    # TEST 2: Có GPU NVIDIA nhưng thiếu CUDA provider (Thực tế trên máy hiện tại)
    # --------------------------------------------------------------------------
    def test_02_has_nvidia_but_missing_cuda_provider(self):
        print("\n[TEST 2] Tình huống: Có GPU NVIDIA RTX 2060 nhưng thiếu CUDA provider (Thực tế máy hiện tại)...", flush=True)
        hw = get_nvidia_hardware_info()
        env = get_onnx_environment_info()

        # Kiểm tra trạng thái thực tế
        self.assertTrue(hw["detected"], "Máy phát triển hiện tại phải phát hiện được RTX 2060")
        self.assertFalse(env["cuda_provider_available"], "ONNX Runtime 1.31.0 hiện tại là bản CPU")

        res_cuda = resolve_device_policy("cuda")
        self.assertFalse(res_cuda["allowed"], "Không được phép bật GPU khi thiếu CUDA provider")
        self.assertEqual(res_cuda["effective_device"], "cpu")
        self.assertIn("chưa tích hợp CUDAExecutionProvider", res_cuda["reason"])

        res_auto = resolve_device_policy("auto")
        self.assertEqual(res_auto["effective_device"], "cpu")
        self.assertTrue(res_auto["fallback_occurred"])
        print(f"  -> Kết quả: Báo đúng tên GPU '{hw['name']}' và lý do thiếu CUDAExecutionProvider. [PASSED]")

    # --------------------------------------------------------------------------
    # TEST 3: Có GPU và provider CUDA nhưng thiếu thư viện native (cublas/cudnn) (Mock)
    # --------------------------------------------------------------------------
    def test_03_cuda_provider_present_but_missing_native_dlls(self):
        print("\n[TEST 3] Tình huống: Có CUDA provider nhưng thiếu thư viện native DLL (Mock)...", flush=True)
        mock_hw = {
            "detected": True,
            "count": 1,
            "name": "NVIDIA GeForce RTX 2060",
            "total_vram_mb": 6144,
            "free_vram_mb": 4000,
            "driver_version": "CUDA 13.0",
            "error": None,
        }
        mock_env = {
            "ort_version": "1.31.0",
            "available_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            "cuda_provider_available": True,
            "cuda_provider_functional": False,
            "cuda_error": "Thiếu thư viện native: cublas64_12.dll not found",
        }
        with patch("backend.hardware.get_nvidia_hardware_info", return_value=mock_hw), \
             patch("backend.hardware.get_onnx_environment_info", return_value=mock_env):
            res_cuda = resolve_device_policy("cuda")
            self.assertFalse(res_cuda["allowed"])
            self.assertIn("không thể nạp thư viện native CUDA", res_cuda["reason"])

            res_auto = resolve_device_policy("auto")
            self.assertEqual(res_auto["effective_device"], "cpu")
            self.assertTrue(res_auto["fallback_occurred"])
            print("  -> Kết quả: Phát hiện lỗi thiếu thư viện native và bảo vệ không bị crash. [PASSED]")

    # --------------------------------------------------------------------------
    # TEST 4: Có GPU và provider nhưng mô hình không khởi tạo được (Mock)
    # --------------------------------------------------------------------------
    def test_04_model_initialization_failure_handling(self):
        print("\n[TEST 4] Tình huống: Mô hình gặp lỗi khởi tạo khi bật GPU (Mock)...", flush=True)
        engine = TTSEngine(device="cpu")
        with patch("backend.hardware.resolve_device_policy", return_value={
            "requested_device": "cuda",
            "effective_device": "cuda",
            "allowed": True,
            "reason": "OK",
            "fallback_occurred": False,
        }):
            with patch("vieneu.Vieneu", side_effect=RuntimeError("CUDA out of device memory during graph load")):
                with self.assertRaises(RuntimeError) as ctx:
                    engine.load(device="cuda")
                self.assertIn("CUDA out of device memory", str(ctx.exception))
                # Xác nhận engine không bị corrupt
                self.assertFalse(engine.ready)
        print("  -> Kết quả: Bắt và truyền đúng thông điệp lỗi gốc, không che giấu lỗi. [PASSED]")

    # --------------------------------------------------------------------------
    # TEST 5: GPU khởi tạo được nhưng thiếu VRAM (< 1000 MB) (Mock)
    # --------------------------------------------------------------------------
    def test_05_insufficient_vram_guard(self):
        print("\n[TEST 5] Tình huống: GPU phát hiện nhưng VRAM không đủ 1GB (Mock)...", flush=True)
        mock_hw = {
            "detected": True,
            "count": 1,
            "name": "NVIDIA GeForce MX150",
            "total_vram_mb": 512,  # 512 MB < 1000 MB
            "free_vram_mb": 400,
            "driver_version": "CUDA 12.0",
            "error": None,
        }
        mock_env = {
            "ort_version": "1.31.0",
            "available_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            "cuda_provider_available": True,
            "cuda_provider_functional": True,
            "cuda_error": None,
        }
        with patch("backend.hardware.get_nvidia_hardware_info", return_value=mock_hw), \
             patch("backend.hardware.get_onnx_environment_info", return_value=mock_env):
            res_cuda = resolve_device_policy("cuda")
            self.assertFalse(res_cuda["allowed"])
            self.assertIn("không đủ tối thiểu", res_cuda["reason"])
            print("  -> Kết quả: Guard VRAM hoạt động chính xác, từ chối nạp để tránh OOM crash. [PASSED]")

    # --------------------------------------------------------------------------
    # TEST 6: Chạy CPU bình thường (Thực tế máy hiện tại)
    # --------------------------------------------------------------------------
    def test_06_cpu_mode_normal_operation(self):
        print("\n[TEST 6] Tình huống: Chế độ CPU hoạt động chuẩn xác (Thực tế máy hiện tại)...", flush=True)
        res_cpu = resolve_device_policy("cpu")
        self.assertTrue(res_cpu["allowed"])
        self.assertEqual(res_cpu["effective_device"], "cpu")

        engine = TTSEngine(mode="v3turbo", precision="int8", device="cpu")
        engine.ensure()
        self.assertTrue(engine.ready)
        self.assertEqual(engine.device, "cpu")
        st = engine.get_hardware_status()
        self.assertTrue(st["ready"])
        self.assertEqual(st["device"], "cpu")
        print("  -> Kết quả: Chế độ CPU nạp mô hình ONNX Lite thành công. [PASSED]")

    # --------------------------------------------------------------------------
    # TEST 7: Chạy GPU bình thường nếu môi trường tương thích (Mock)
    # --------------------------------------------------------------------------
    def test_07_gpu_mode_when_environment_compatible(self):
        print("\n[TEST 7] Tình huống: Môi trường có đầy đủ GPU và ONNX CUDA functional (Mock)...", flush=True)
        mock_hw = {
            "detected": True,
            "count": 1,
            "name": "NVIDIA GeForce RTX 2060",
            "total_vram_mb": 6144,
            "free_vram_mb": 5100,
            "driver_version": "CUDA 13.0",
            "error": None,
        }
        mock_env = {
            "ort_version": "1.31.0",
            "available_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            "cuda_provider_available": True,
            "cuda_provider_functional": True,
            "cuda_error": None,
        }
        with patch("backend.hardware.get_nvidia_hardware_info", return_value=mock_hw), \
             patch("backend.hardware.get_onnx_environment_info", return_value=mock_env):
            # Test AUTO mode
            res_auto = resolve_device_policy("auto")
            self.assertEqual(res_auto["effective_device"], "cuda")
            self.assertFalse(res_auto["fallback_occurred"])
            self.assertIn("Tự động kích hoạt GPU", res_auto["reason"])

            # Test GPU mode
            res_cuda = resolve_device_policy("cuda")
            self.assertTrue(res_cuda["allowed"])
            self.assertEqual(res_cuda["effective_device"], "cuda")
            print("  -> Kết quả: Chế độ AUTO và GPU kích hoạt chính xác khi tương thích 100%. [PASSED]")

    # --------------------------------------------------------------------------
    # TEST 8: Chuyển về CPU sau lỗi GPU (Thực tế máy hiện tại)
    # --------------------------------------------------------------------------
    def test_08_recover_to_cpu_after_gpu_rejection(self):
        print("\n[TEST 8] Tình huống: Chuyển về CPU sau khi yêu cầu GPU bị từ chối (Thực tế máy hiện tại)...", flush=True)
        engine = TTSEngine(mode="v3turbo", precision="int8", device="cpu")
        engine.ensure()

        # Thử chuyển sang cuda (phải bị ném ValueError vì ONNX hiện tại thiếu CUDA provider)
        with self.assertRaises(ValueError) as ctx:
            engine.load(device="cuda")
        self.assertIn("chưa tích hợp CUDAExecutionProvider", str(ctx.exception))

        # Phục hồi về CPU
        engine.load(device="cpu")
        self.assertTrue(engine.ready)
        self.assertEqual(engine.device, "cpu")
        print("  -> Kết quả: Phục hồi hoàn hảo về CPU, engine tiếp tục hoạt động trơn tru. [PASSED]")

    # --------------------------------------------------------------------------
    # TEST 9: Đóng và nạp lại mô hình / Reload engine (Thực tế máy hiện tại)
    # --------------------------------------------------------------------------
    def test_09_reload_engine_consistency(self):
        print("\n[TEST 9] Tình huống: Nạp lại mô hình từ đầu và kiểm tra tính nhất quán (Thực tế)...", flush=True)
        engine = TTSEngine(mode="v3turbo", precision="int8", device="cpu")
        engine.load()
        self.assertTrue(engine.ready)
        voices_1 = engine.list_voices()
        self.assertGreaterEqual(len(voices_1), 25)

        # Reload
        engine.load(mode="v3turbo", precision="int8", device="cpu")
        self.assertTrue(engine.ready)
        voices_2 = engine.list_voices()
        self.assertEqual(len(voices_1), len(voices_2))
        print("  -> Kết quả: Khởi tạo lại nhất quán 100%, danh sách giọng toàn vẹn. [PASSED]")

    # --------------------------------------------------------------------------
    # TEST 10: Kiểm tra file WAV hợp lệ sau khi tạo giọng trên CPU (Thực tế máy hiện tại)
    # --------------------------------------------------------------------------
    def test_10_generate_valid_wav_after_tests(self):
        print("\n[TEST 10] Tình huống: Tạo file WAV thực tế và kiểm tra đặc tính âm học (Thực tế)...", flush=True)
        engine = TTSEngine(mode="v3turbo", precision="int8", device="cpu")
        engine.ensure()

        audio_arr, sr = engine.synthesize(
            text="Kiểm tra âm thanh chất lượng cao trên chế độ CPU của T-TTS.",
            voice="Hải Đăng",
            speed=1.0,
        )
        self.assertEqual(sr, 48000, "Tần số lấy mẫu VieNeu v3 Turbo phải là 48kHz")
        self.assertGreater(len(audio_arr), 24000, "Độ dài mẫu âm thanh phải vượt quá 0.5s")

        # Kiểm tra đóng gói sang WAV hợp lệ
        from backend.audio_utils import save_wav
        out_buf = io.BytesIO()
        test_wav_path = ROOT / "output" / "test_compatibility_sample.wav"
        save_wav(test_wav_path, audio_arr, sr)
        self.assertTrue(test_wav_path.exists())

        with wave.open(str(test_wav_path), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)  # 16-bit
            self.assertEqual(wf.getframerate(), 48000)
            duration = wf.getnframes() / wf.getframerate()
            self.assertGreater(duration, 1.0)
            print(f"  -> Kết quả: File WAV hợp lệ: {test_wav_path.name} ({duration:.2f}s, {wf.getnframes()} frames, 48kHz 16-bit). [PASSED]")


if __name__ == "__main__":
    unittest.main()
