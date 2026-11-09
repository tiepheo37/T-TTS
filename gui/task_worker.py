"""gui/task_worker.py — TIỂU TRÌNH XỬ LÝ NỀN CHUẨN HÓA CHO CÁC TÁC VỤ DÀI
=============================================================================
Cung cấp BaseTaskWorker và FunctionTaskWorker để chạy tác vụ âm thanh,
tổng hợp, biên tập và lịch phát thanh mà không làm treo GUI (Non-blocking).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional
from PySide6.QtCore import QThread, Signal


class BaseTaskWorker(QThread):
    """Lớp cơ sở cho các tiểu trình tác vụ ngầm trong T-TTS."""

    started_task = Signal()
    progress = Signal(int, int, str)  # current, total, status_message
    finished_task = Signal(object)    # result payload
    result_ready = finished_task      # alias tương thích
    error_task = Signal(str)          # error message
    cancelled_task = Signal()         # cancelled notification

    def __init__(self, parent: Optional[Any] = None):
        super().__init__(parent)
        self._is_cancelled = False

    def request_cancel(self):
        """Yêu cầu hủy tác vụ một cách an toàn."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        """Kiểm tra xem tác vụ đã nhận tín hiệu yêu cầu hủy hay chưa."""
        return self._is_cancelled

    def stop_and_wait(self, timeout_ms: int = 3000) -> bool:
        """Yêu cầu hủy tác vụ và đợi tiểu trình kết thúc an toàn, tránh QThread crash."""
        self.request_cancel()
        if self.isRunning():
            return self.wait(timeout_ms)
        return True


class FunctionTaskWorker(BaseTaskWorker):
    """Tiểu trình thực thi một hàm Python bất kỳ trong luồng nền có kiểm soát hủy."""

    def __init__(
        self,
        target_fn: Callable[..., Any],
        *args,
        parent: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(parent)
        self.target_fn = target_fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        import inspect
        self.started_task.emit()
        try:
            # Truyền callback progress và check_cancel nếu hàm đích hỗ trợ
            kwargs = dict(self.kwargs)
            try:
                sig = inspect.signature(self.target_fn)
                accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                if accepts_var_kw or "progress_callback" in sig.parameters:
                    if "progress_callback" not in kwargs:
                        kwargs["progress_callback"] = lambda curr, total, msg="": self.progress.emit(curr, total, msg)
                if accepts_var_kw or "cancel_check" in sig.parameters:
                    if "cancel_check" not in kwargs:
                        kwargs["cancel_check"] = self.is_cancelled
            except Exception:
                pass

            res = self.target_fn(*self.args, **kwargs)

            if self.is_cancelled():
                self.cancelled_task.emit()
            else:
                self.finished_task.emit(res)
        except Exception as e:
            if self.is_cancelled():
                self.cancelled_task.emit()
            else:
                self.error_task.emit(str(e))
