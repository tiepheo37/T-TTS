"""
backend/vieneu_adapter.py — ADAPTER ĐỘC LẬP CẤU HÌNH PROVIDER TỪNG SESSION
=============================================================================
Mục đích:
  Cung cấp lớp Adapter / Subclass an toàn cho VieNeu-TTS v3 Turbo (OnnxV3LiteEngine).
  Cho phép cấu hình độc lập Execution Provider cho từng session ONNX mà KHÔNG
  sửa đổi mã nguồn site-packages và KHÔNG sử dụng monkey-patch toàn cục.

Thiết kế kiến trúc thử nghiệm:
  - sess_codec_dec: Chạy bằng CUDAExecutionProvider (tăng tốc Vocoder song song lớn).
  - sess_pre, sess_dec, sess_ac: Giữ trên CPUExecutionProvider (tránh độ trễ PCIe
    sao chép Host-to-Device liên tục 1,600+ lần trong vòng lặp sampling NumPy).
"""

from __future__ import annotations

import gc
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger("VieNeuAdapter")


class VieNeuHybridEngineAdapter:
    """
    Adapter an toàn bọc và điều phối các session ONNX của VieNeu-TTS v3 Turbo.
    Hỗ trợ cả 2 chế độ:
      1. Khởi tạo và thay thế session có kiểm tra nghiêm ngặt (Safe Session Replacement).
      2. Kiểm tra và báo cáo trạng thái provider thực tế từng session.
    """

    def __init__(
        self,
        checkpoint_path: str = "pnnbao-ump/VieNeu-TTS-v3-Turbo",
        onnx_dir: Optional[Union[str, Path]] = None,
        codec_dir: Optional[Union[str, Path]] = None,
        onnx_subfolder: str = "onnx_update",
        threads: int = 0,
        providers_codec: Optional[List[str]] = None,
        providers_ar: Optional[List[str]] = None,
        allow_silent_fallback: bool = False,
        **kwargs: Any,
    ):
        """
        Khởi tạo VieNeu engine với cấu hình provider phân tách:
          - providers_codec: Providers cho sess_codec_dec (mặc định ['CUDAExecutionProvider']).
          - providers_ar: Providers cho sess_pre, sess_dec, sess_ac (mặc định ['CPUExecutionProvider']).
          - allow_silent_fallback: Nếu False, báo lỗi ngay khi session không nạp đúng provider yêu cầu.
        """
        import onnxruntime as ort
        from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine

        self.allow_silent_fallback = allow_silent_fallback
        self.target_providers_codec = providers_codec or ["CUDAExecutionProvider"]
        self.target_providers_ar = providers_ar or ["CPUExecutionProvider"]

        logger.info("Khởi tạo OnnxV3LiteEngine nền tảng...")
        self.engine = OnnxV3LiteEngine(
            checkpoint_path=checkpoint_path,
            onnx_dir=str(onnx_dir) if onnx_dir else None,
            codec_dir=str(codec_dir) if codec_dir else None,
            onnx_subfolder=onnx_subfolder,
            threads=threads,
            **kwargs,
        )

        self._onnx_dir = Path(onnx_dir) if onnx_dir else Path(self.engine.checkpoint_path)
        self._codec_dir = Path(codec_dir) if codec_dir else Path(self.engine.checkpoint_path)

        # Cấu hình lại sess_codec_dec theo provider mong muốn nếu khác CPU
        self._configure_codec_session()

        # Kiểm tra trạng thái thực tế sau cấu hình
        self.provider_report = self.get_session_providers()
        logger.info(f"Cấu hình Session Providers hoàn tất: {self.provider_report}")

    def _configure_codec_session(self) -> None:
        """Cấu hình lại sess_codec_dec với providers_codec."""
        import onnxruntime as ort

        if self.target_providers_codec == ["CPUExecutionProvider"]:
            logger.info("sess_codec_dec được cấu hình chạy CPU thuần.")
            return

        codec_model_path = self._codec_dir / "moss_audio_tokenizer_decode_full.onnx"
        if not codec_model_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy file mô hình codec tại: {codec_model_path}")

        logger.info(f"Đang cấu hình sess_codec_dec với providers: {self.target_providers_codec}...")

        # Tạo SessionOptions kế thừa từ engine
        so = getattr(self.engine, "_so", ort.SessionOptions())

        # Giải phóng session CPU cũ trước khi tạo session mới
        if hasattr(self.engine, "sess_codec_dec"):
            del self.engine.sess_codec_dec
            gc.collect()

        try:
            new_codec_sess = ort.InferenceSession(
                str(codec_model_path),
                so,
                providers=self.target_providers_codec,
            )
            actual_providers = new_codec_sess.get_providers()
            logger.info(f"sess_codec_dec nạp thành công. Providers thực tế: {actual_providers}")

            # Kiểm tra xem có bị im lặng fallback sang CPU không
            expected_primary = self.target_providers_codec[0]
            if not self.allow_silent_fallback and expected_primary not in actual_providers:
                raise RuntimeError(
                    f"sess_codec_dec bị tự động fallback về {actual_providers} "
                    f"thay vì {expected_primary} theo yêu cầu nghiêm ngặt!"
                )

            self.engine.sess_codec_dec = new_codec_sess

        except Exception as e:
            logger.error(f"Lỗi khởi tạo sess_codec_dec với {self.target_providers_codec}: {e}")
            raise

    def get_session_providers(self) -> Dict[str, List[str]]:
        """Trả về danh sách Execution Provider thực tế của từng session."""
        report = {}
        for s_name in ["sess_pre", "sess_dec", "sess_ac", "sess_codec_dec"]:
            sess = getattr(self.engine, s_name, None)
            if sess is not None and hasattr(sess, "get_providers"):
                report[s_name] = sess.get_providers()
            else:
                report[s_name] = ["NOT_INITIALIZED"]
        return report

    def infer(self, *args: Any, **kwargs: Any) -> np.ndarray:
        """Thực hiện suy luận qua engine đã được cấu hình hybrid."""
        return self.engine.infer(*args, **kwargs)

    def decode_codes(self, codes: np.ndarray) -> np.ndarray:
        """Giải mã trực tiếp mã âm học thành waveform qua sess_codec_dec."""
        return self.engine._decode_codes(codes)

    @classmethod
    def test_codec_standalone(
        cls,
        codec_dir: Union[str, Path],
        providers: List[str],
        allow_fallback: bool = False,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Kiểm tra độc lập khả năng chạy của codec ONNX với providers chỉ định.
        Không cần nạp toàn bộ 3 session autoregressive.
        """
        import time
        import onnxruntime as ort

        codec_path = Path(codec_dir) / "moss_audio_tokenizer_decode_full.onnx"
        res: Dict[str, Any] = {
            "model_path": str(codec_path),
            "target_providers": providers,
            "actual_providers": [],
            "load_time_s": 0.0,
            "inference_time_s": 0.0,
            "success": False,
            "error": None,
        }

        if not codec_path.is_file():
            res["error"] = f"Tệp không tồn tại: {codec_path}"
            return False, res

        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        t0 = time.perf_counter()
        try:
            sess = ort.InferenceSession(str(codec_path), so, providers=providers)
            res["load_time_s"] = time.perf_counter() - t0
            actual = sess.get_providers()
            res["actual_providers"] = actual

            expected_primary = providers[0]
            if not allow_fallback and expected_primary not in actual:
                res["error"] = f"Bị tự động fallback về {actual} dù yêu cầu {expected_primary}."
                return False, res

            # Thử nghiệm giải mã một tensor token giả lập hợp lệ (T=50 frames ~ 1.0 giây âm thanh)
            # codes: (1, T, 16) int32, giá trị token trong khoảng 0..1023
            t_frames = 50
            dummy_codes = np.random.randint(0, 1024, size=(1, t_frames, 16), dtype=np.int32)
            dummy_lens = np.array([t_frames], dtype=np.int32)

            t_inf0 = time.perf_counter()
            out = sess.run(None, {"audio_codes": dummy_codes, "audio_code_lengths": dummy_lens})
            res["inference_time_s"] = time.perf_counter() - t_inf0

            wav = out[0][0].mean(0).astype(np.float32)
            res["wav_samples"] = len(wav)
            res["wav_duration_s"] = len(wav) / 48000.0
            res["success"] = True

            del sess
            gc.collect()
            return True, res

        except Exception as e:
            res["load_time_s"] = time.perf_counter() - t0
            res["error"] = str(e)
            return False, res
