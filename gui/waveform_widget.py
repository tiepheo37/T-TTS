"""gui/waveform_widget.py — WIDGET VẼ DẠNG SÓNG ÂM THANH (WAVEFORM & TIMELINE)
=============================================================================
Thành phần hiển thị waveform chuyên nghiệp, hiệu năng cao, hỗ trợ:
- Downsampling hiệu năng cao bằng NumPy (không giật lag, không tốn RAM).
- Zoom dạng sóng mượt mà:
  + Cuộn chuột (Wheel) / Ctrl+Wheel: Zoom ngang (Horizontal Zoom) quanh vị trí con trỏ chuột.
  + Shift + Cuộn chuột: Zoom dọc (Vertical Zoom / biên độ dạng sóng 0.2x -> 5.0x).
  + Kéo chuột phải / chuột giữa để trượt (Pan) timeline khi đang zoom.
  + Giữ nguyên Playhead và Vùng chọn (Selection), không lệch âm thanh gốc.
- Thước thời gian Timeline (mm:ss.ms) với vạch chia thông minh theo mức zoom.
- Đầu đọc Playhead thời gian thực và vùng chọn âm thanh trực quan.
- Tích hợp phát thanh, cắt, ghép, xóa, trim ở mọi cấp độ zoom.
- Phong cách Dark Green & Gold quân đội chuẩn T-TTS.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple
import numpy as np

from PySide6.QtCore import Qt, Signal, QRectF, QPoint
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QFont,
    QMouseEvent,
    QPaintEvent,
    QWheelEvent,
    QCursor,
)
from PySide6.QtWidgets import QWidget


def format_ms_to_time(ms: int) -> str:
    """Đổi mili-giây thành định dạng MM:SS hoặc MM:SS.mmm."""
    total_sec = max(0, ms) / 1000.0
    mins = int(total_sec // 60)
    secs = int(total_sec % 60)
    millis = int(ms % 1000)
    return f"{mins:02d}:{secs:02d}.{millis//100:01d}"


class WaveformWidget(QWidget):
    """Widget vẽ waveform chuyên nghiệp và điều khiển vùng chọn âm thanh trực quan."""

    playhead_moved = Signal(int)             # new_pos_ms
    selection_changed = Signal(int, int)     # start_ms, end_ms
    view_range_changed = Signal(int, int, int)  # view_start_ms, view_end_ms, duration_ms

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

        self.samples: Optional[np.ndarray] = None
        self.sample_rate: int = 44100
        self.duration_ms: int = 0

        self.playhead_ms: int = 0
        self.sel_start_ms: int = 0
        self.sel_end_ms: int = 0

        # Quản lý Zoom & Cửa sổ hiển thị (Visible Window)
        self.zoom_level: float = 1.0       # 1.0 = Fit to window, 2.0 = 2x, etc.
        self.vertical_zoom: float = 1.0    # 1.0 = biên độ gốc, 0.2 -> 5.0
        self.view_start_ms: int = 0
        self.view_end_ms: int = 0

        # Trạng thái kéo chuột chọn vùng & Pan
        self._is_selecting: bool = False
        self._drag_start_pos: int = 0

        self._is_panning: bool = False
        self._pan_start_x: float = 0.0
        self._pan_start_view_start: int = 0

        # Cache đỉnh sóng (peaks)
        self._peaks_cache: Optional[Tuple[np.ndarray, np.ndarray]] = None
        self._cached_key: Optional[Tuple[int, int, int]] = None  # (start_ms, end_ms, width)

    def set_audio_data(self, samples_np: Optional[np.ndarray], sample_rate: int = 44100):
        """Nạp dữ liệu mẫu numpy float32 [-1, 1] hoặc int16."""
        if samples_np is None or len(samples_np) == 0:
            self.samples = None
            self.sample_rate = sample_rate
            self.duration_ms = 0
            self.playhead_ms = 0
            self.sel_start_ms = 0
            self.sel_end_ms = 0
            self.view_start_ms = 0
            self.view_end_ms = 0
            self.zoom_level = 1.0
            self.vertical_zoom = 1.0
            self._peaks_cache = None
            self._cached_key = None
            self.view_range_changed.emit(0, 0, 0)
            self.update()
            return

        # Chuẩn hóa về float32 [-1.0, 1.0] mono
        arr = np.asarray(samples_np, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr.mean(axis=1)

        # Nếu là dạng int16 chuyển về float32
        max_val = np.max(np.abs(arr)) if len(arr) > 0 else 1.0
        if max_val > 1.0:
            arr = arr / 32768.0

        self.samples = arr
        self.sample_rate = sample_rate
        self.duration_ms = int(len(arr) * 1000.0 / sample_rate)
        self.playhead_ms = 0
        self.sel_start_ms = 0
        self.sel_end_ms = 0

        # Khởi tạo view toàn màn hình
        self.view_start_ms = 0
        self.view_end_ms = self.duration_ms
        self.zoom_level = 1.0
        self.vertical_zoom = 1.0
        self._peaks_cache = None
        self._cached_key = None

        self.view_range_changed.emit(self.view_start_ms, self.view_end_ms, self.duration_ms)
        self.update()

    def set_playhead_ms(self, pos_ms: int):
        """Cập nhật vị trí playhead (đầu phát)."""
        self.playhead_ms = max(0, min(int(pos_ms), self.duration_ms))
        self.update()

    def set_selection_range(self, start_ms: int, end_ms: int):
        """Đặt vùng chọn thời gian (start_ms -> end_ms)."""
        s = max(0, min(start_ms, self.duration_ms))
        e = max(0, min(end_ms, self.duration_ms))
        if s > e:
            s, e = e, s
        self.sel_start_ms = s
        self.sel_end_ms = e
        self.selection_changed.emit(s, e)
        self.update()

    def clear_selection(self):
        """Xóa vùng chọn."""
        self.sel_start_ms = 0
        self.sel_end_ms = 0
        self.selection_changed.emit(0, 0)
        self.update()

    # -------------------------------------------------------------
    # CÁC HÀM ĐIỀU KHIỂN ZOOM & VIEWPORT
    # -------------------------------------------------------------
    def zoom_in(self, center_ms: Optional[int] = None, factor: float = 1.25):
        """Phóng to trục ngang xung quanh vị trí center_ms (hoặc giữa màn hình)."""
        if self.duration_ms <= 0:
            return

        current_span = max(1, self.view_end_ms - self.view_start_ms)
        min_span = 50  # Tối thiểu 50ms (khoảng 2200 mẫu)
        if current_span <= min_span:
            return

        new_span = max(min_span, int(current_span / factor))
        if new_span >= current_span:
            return

        if center_ms is None:
            # Ưu tiên lấy playhead nếu đang nằm trong vùng nhìn thấy
            if self.view_start_ms <= self.playhead_ms <= self.view_end_ms:
                center_ms = self.playhead_ms
            else:
                center_ms = (self.view_start_ms + self.view_end_ms) // 2

        # Tỷ lệ của center_ms trong span cũ
        ratio = (center_ms - self.view_start_ms) / float(current_span)
        new_start = int(center_ms - ratio * new_span)
        new_start = max(0, min(self.duration_ms - new_span, new_start))
        new_end = new_start + new_span

        self.view_start_ms = new_start
        self.view_end_ms = new_end
        self.zoom_level = self.duration_ms / float(new_span)
        self._peaks_cache = None
        self._cached_key = None

        self.view_range_changed.emit(self.view_start_ms, self.view_end_ms, self.duration_ms)
        self.update()

    def zoom_out(self, center_ms: Optional[int] = None, factor: float = 1.25):
        """Thu nhỏ trục ngang."""
        if self.duration_ms <= 0:
            return

        current_span = max(1, self.view_end_ms - self.view_start_ms)
        if current_span >= self.duration_ms:
            self.zoom_fit()
            return

        new_span = min(self.duration_ms, int(current_span * factor))
        if new_span >= self.duration_ms:
            self.zoom_fit()
            return

        if center_ms is None:
            if self.view_start_ms <= self.playhead_ms <= self.view_end_ms:
                center_ms = self.playhead_ms
            else:
                center_ms = (self.view_start_ms + self.view_end_ms) // 2

        ratio = (center_ms - self.view_start_ms) / float(current_span)
        new_start = int(center_ms - ratio * new_span)
        new_start = max(0, min(self.duration_ms - new_span, new_start))
        new_end = new_start + new_span

        self.view_start_ms = new_start
        self.view_end_ms = new_end
        self.zoom_level = self.duration_ms / float(new_span)
        self._peaks_cache = None
        self._cached_key = None

        self.view_range_changed.emit(self.view_start_ms, self.view_end_ms, self.duration_ms)
        self.update()

    def zoom_fit(self):
        """Đưa toàn bộ dạng sóng về vừa khít khung nhìn (Fit to window)."""
        self.view_start_ms = 0
        self.view_end_ms = self.duration_ms
        self.zoom_level = 1.0
        self._peaks_cache = None
        self._cached_key = None
        self.view_range_changed.emit(self.view_start_ms, self.view_end_ms, self.duration_ms)
        self.update()

    def reset_zoom(self):
        """Đặt lại toàn bộ zoom trục ngang và zoom biên độ trục dọc."""
        self.vertical_zoom = 1.0
        self.zoom_fit()

    def set_vertical_zoom(self, factor: float):
        """Điều chỉnh hệ số phóng to biên độ dạng sóng (0.2x đến 5.0x)."""
        self.vertical_zoom = max(0.2, min(5.0, float(factor)))
        self.update()

    def scroll_to_ms(self, start_ms: int):
        """Di chuyển cửa sổ nhìn thấy đến vị trí thời gian start_ms."""
        if self.duration_ms <= 0:
            return
        span = self.view_end_ms - self.view_start_ms
        if span >= self.duration_ms:
            return

        new_start = max(0, min(self.duration_ms - span, int(start_ms)))
        new_end = new_start + span
        if new_start != self.view_start_ms or new_end != self.view_end_ms:
            self.view_start_ms = new_start
            self.view_end_ms = new_end
            self._peaks_cache = None
            self._cached_key = None
            self.view_range_changed.emit(self.view_start_ms, self.view_end_ms, self.duration_ms)
            self.update()

    # -------------------------------------------------------------
    # ÁNH XẠ TỌA ĐỘ PIXEL <-> THỜI GIAN THEO KHUNG NHÌN HIỆN TẠI
    # -------------------------------------------------------------
    def _ms_to_x(self, ms: int, width: int) -> float:
        """Đổi mili-giây sang tọa độ X pixel trên widget."""
        span = self.view_end_ms - self.view_start_ms
        if span <= 0 or width <= 0:
            return 0.0
        return ((ms - self.view_start_ms) / float(span)) * width

    def _x_to_ms(self, x: float, width: int) -> int:
        """Đổi tọa độ X pixel sang mili-giây tương ứng."""
        span = self.view_end_ms - self.view_start_ms
        if width <= 0 or span <= 0:
            return self.view_start_ms
        ratio = max(0.0, min(1.0, x / float(width)))
        return int(self.view_start_ms + ratio * span)

    # -------------------------------------------------------------
    # SỰ KIỆN CHUỘT: ZOOM, PAN, SELECTION, PLAYHEAD
    # -------------------------------------------------------------
    def wheelEvent(self, event: QWheelEvent):
        """Xử lý phóng to / thu nhỏ bằng con lăn chuột."""
        if self.duration_ms <= 0:
            return

        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.angleDelta().x()
        if delta == 0:
            return

        mods = event.modifiers()
        if mods & Qt.ShiftModifier:
            # Shift + Wheel: Zoom biên độ sóng (Vertical Zoom)
            if delta > 0:
                self.vertical_zoom = min(5.0, self.vertical_zoom * 1.2)
            else:
                self.vertical_zoom = max(0.2, self.vertical_zoom / 1.2)
            self.update()
        else:
            # Con lăn chuột hoặc Ctrl + Wheel: Zoom ngang quanh vị trí con trỏ chuột
            x = event.position().x()
            cursor_ms = self._x_to_ms(x, self.width())
            factor = 1.25 if abs(delta) >= 120 else 1.10
            if delta > 0:
                self.zoom_in(center_ms=cursor_ms, factor=factor)
            else:
                self.zoom_out(center_ms=cursor_ms, factor=factor)

        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        if self.duration_ms <= 0:
            return

        x = event.position().x()

        if event.button() == Qt.RightButton or event.button() == Qt.MiddleButton:
            # Bắt đầu kéo trượt Timeline (Pan)
            self._is_panning = True
            self._pan_start_x = x
            self._pan_start_view_start = self.view_start_ms
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            click_ms = self._x_to_ms(x, self.width())
            self._is_selecting = True
            self._drag_start_pos = click_ms
            self.playhead_ms = click_ms
            self.sel_start_ms = click_ms
            self.sel_end_ms = click_ms
            self.playhead_moved.emit(click_ms)
            self.selection_changed.emit(click_ms, click_ms)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.duration_ms <= 0:
            return

        x = event.position().x()

        if self._is_panning:
            # Thực hiện dịch chuyển khung nhìn (Pan)
            span = self.view_end_ms - self.view_start_ms
            dx = x - self._pan_start_x
            d_ms = -int((dx / float(max(1, self.width()))) * span)

            new_start = self._pan_start_view_start + d_ms
            new_start = max(0, min(self.duration_ms - span, new_start))
            new_end = new_start + span

            if new_start != self.view_start_ms or new_end != self.view_end_ms:
                self.view_start_ms = new_start
                self.view_end_ms = new_end
                self._peaks_cache = None
                self._cached_key = None
                self.view_range_changed.emit(self.view_start_ms, self.view_end_ms, self.duration_ms)
                self.update()
            return

        if self._is_selecting:
            curr_ms = self._x_to_ms(x, self.width())
            s = min(self._drag_start_pos, curr_ms)
            e = max(self._drag_start_pos, curr_ms)
            self.sel_start_ms = s
            self.sel_end_ms = e
            self.selection_changed.emit(s, e)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() in (Qt.RightButton, Qt.MiddleButton):
            self._is_panning = False
            self.setCursor(Qt.CrossCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            self._is_selecting = False
            self.update()

    # -------------------------------------------------------------
    # VẼ GIAO DIỆN (WAVEFORM, RULER, SELECTION, PLAYHEAD)
    # -------------------------------------------------------------
    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()
        h = self.height()
        timeline_h = 24
        wave_top = timeline_h
        wave_h = h - timeline_h

        # 1. Vẽ nền tối Deep Green quân đội
        painter.fillRect(0, 0, w, h, QColor("#08140A"))
        painter.fillRect(0, 0, w, timeline_h, QColor("#102414"))

        # Đường viền ngăn cách timeline và waveform
        painter.setPen(QPen(QColor("#27472A"), 1))
        painter.drawLine(0, timeline_h, w, timeline_h)

        if self.samples is None or len(self.samples) == 0 or self.duration_ms <= 0:
            painter.setPen(QColor("#64748B"))
            painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
            painter.drawText(
                QRectF(0, wave_top, w, wave_h),
                Qt.AlignCenter,
                "Chưa nạp tệp âm thanh nào\n(Bấm 'Nhập Tệp Âm Thanh' hoặc kéo thả tệp vào đây)",
            )
            return

        # Đảm bảo phạm vi view hợp lệ
        if self.view_end_ms <= self.view_start_ms:
            self.view_start_ms = 0
            self.view_end_ms = self.duration_ms

        span_ms = max(1, self.view_end_ms - self.view_start_ms)
        span_sec = span_ms / 1000.0

        # 2. Vẽ thước thời gian Timeline (Ruler) thông minh
        painter.setPen(QColor("#94A3B8"))
        painter.setFont(QFont("Segoe UI", 8))

        # Chọn bước chia ticks dựa trên span hiển thị
        if span_sec <= 0.2:
            step_sec = 0.02
        elif span_sec <= 0.5:
            step_sec = 0.05
        elif span_sec <= 1.0:
            step_sec = 0.1
        elif span_sec <= 2.5:
            step_sec = 0.25
        elif span_sec <= 5.0:
            step_sec = 0.5
        elif span_sec <= 15.0:
            step_sec = 1.0
        elif span_sec <= 30.0:
            step_sec = 2.0
        elif span_sec <= 60.0:
            step_sec = 5.0
        elif span_sec <= 180.0:
            step_sec = 10.0
        elif span_sec <= 600.0:
            step_sec = 30.0
        else:
            step_sec = 60.0

        v_start_sec = self.view_start_ms / 1000.0
        v_end_sec = self.view_end_ms / 1000.0

        first_tick = math.floor(v_start_sec / step_sec) * step_sec
        curr_tick = first_tick
        while curr_tick <= v_end_sec + step_sec:
            if curr_tick >= v_start_sec:
                ms_val = int(curr_tick * 1000)
                x_pos = self._ms_to_x(ms_val, w)
                if 0 <= x_pos <= w:
                    painter.setPen(QColor("#3B533E"))
                    painter.drawLine(int(x_pos), timeline_h - 8, int(x_pos), timeline_h)
                    painter.setPen(QColor("#CBD5E1"))
                    painter.drawText(int(x_pos) + 2, timeline_h - 6, format_ms_to_time(ms_val))
            curr_tick += step_sec

        # 3. Tính toán downsampling và vẽ dạng sóng (Waveform)
        mid_y = wave_top + (wave_h / 2.0)
        amplitude_scale = (wave_h / 2.0) * 0.92 * self.vertical_zoom

        # Kiểm tra cache
        cache_key = (self.view_start_ms, self.view_end_ms, w)
        if self._peaks_cache is None or self._cached_key != cache_key:
            mins, maxs = self._compute_peaks(w)
            self._peaks_cache = (mins, maxs)
            self._cached_key = cache_key
        else:
            mins, maxs = self._peaks_cache

        # Vẽ đường trung tâm số 0
        painter.setPen(QPen(QColor("#1A381F"), 1))
        painter.drawLine(0, int(mid_y), w, int(mid_y))

        # Vẽ các cột sóng âm thanh (Xanh lá quân đội & Vàng Gold)
        pen_wave = QPen(QColor("#4ADE80"), 1)
        pen_wave_neg = QPen(QColor("#22C55E"), 1)

        for col in range(min(w, len(mins))):
            min_val = mins[col]
            max_val = maxs[col]

            y_top = mid_y - (max_val * amplitude_scale)
            y_bot = mid_y - (min_val * amplitude_scale)

            # Giới hạn vẽ trong wave_h
            y_top = max(float(wave_top), min(float(h - 1), y_top))
            y_bot = max(float(wave_top), min(float(h - 1), y_bot))

            # Đảm bảo tối thiểu 1 pixel
            if abs(y_bot - y_top) < 1.0:
                y_top = mid_y - 1
                y_bot = mid_y + 1

            painter.setPen(pen_wave)
            painter.drawLine(col, int(y_top), col, int(mid_y))
            painter.setPen(pen_wave_neg)
            painter.drawLine(col, int(mid_y), col, int(y_bot))

        # 4. Vẽ vùng chọn (Selection Region Overlay)
        if self.sel_end_ms > self.sel_start_ms:
            # Kiểm tra xem vùng chọn có giao với view hiện tại không
            sel_s = max(self.sel_start_ms, self.view_start_ms)
            sel_e = min(self.sel_end_ms, self.view_end_ms)
            if sel_e > sel_s:
                x_s = self._ms_to_x(sel_s, w)
                x_e = self._ms_to_x(sel_e, w)
                sel_rect = QRectF(x_s, wave_top, max(1.0, x_e - x_s), wave_h)
                painter.fillRect(sel_rect, QColor(56, 189, 248, 60))

                # Viền vùng chọn
                painter.setPen(QPen(QColor("#38BDF8"), 1, Qt.DashLine))
                if self.sel_start_ms >= self.view_start_ms:
                    painter.drawLine(int(x_s), wave_top, int(x_s), h)
                if self.sel_end_ms <= self.view_end_ms:
                    painter.drawLine(int(x_e), wave_top, int(x_e), h)

        # 5. Vẽ đầu phát Playhead
        if self.view_start_ms <= self.playhead_ms <= self.view_end_ms:
            x_play = self._ms_to_x(self.playhead_ms, w)
            painter.setPen(QPen(QColor("#EF4444"), 2))
            painter.drawLine(int(x_play), 0, int(x_play), h)

            # Đầu tam giác Playhead trên thanh Timeline
            painter.setBrush(QBrush(QColor("#EF4444")))
            painter.drawPolygon([
                QPoint(int(x_play) - 5, 0),
                QPoint(int(x_play) + 5, 0),
                QPoint(int(x_play), 8),
            ])

        # 6. Hiển thị Badge Zoom Level ở góc trên bên phải nếu đang zoom
        if self.zoom_level > 1.05 or abs(self.vertical_zoom - 1.0) > 0.05:
            zoom_badge = f"Zoom: {self.zoom_level:.1f}x | Dọc: {self.vertical_zoom:.1f}x"
            painter.setPen(QColor("#D4AF37"))
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.drawText(w - 145, timeline_h - 6, zoom_badge)

    def _compute_peaks(self, num_cols: int) -> Tuple[np.ndarray, np.ndarray]:
        """Tính toán đỉnh min/max theo từng cột pixel bằng NumPy cho vùng nhìn thấy."""
        if self.samples is None or len(self.samples) == 0:
            return np.zeros(num_cols, dtype=np.float32), np.zeros(num_cols, dtype=np.float32)

        cols = max(1, num_cols)
        total_len = len(self.samples)

        # Cắt slice theo view_start_ms và view_end_ms
        s_idx = max(0, int(self.view_start_ms * self.sample_rate / 1000.0))
        e_idx = min(total_len, int(self.view_end_ms * self.sample_rate / 1000.0))

        if e_idx <= s_idx:
            e_idx = min(total_len, s_idx + 1)

        slice_data = self.samples[s_idx:e_idx]
        n_samples = len(slice_data)

        if n_samples == 0:
            return np.zeros(cols, dtype=np.float32), np.zeros(cols, dtype=np.float32)

        if n_samples >= cols:
            chunk_size = max(1, n_samples // cols)
            usable_samples = cols * chunk_size
            reshaped = slice_data[:usable_samples].reshape(cols, chunk_size)
            mins = reshaped.min(axis=1)
            maxs = reshaped.max(axis=1)
        else:
            # Khi zoom cực sâu vào mức vài chục mẫu
            indices = np.linspace(0, n_samples - 1, cols).astype(int)
            mins = slice_data[indices]
            maxs = slice_data[indices]

        return mins, maxs

    def _get_downsampled_peaks(self, num_cols: int) -> Tuple[np.ndarray, np.ndarray]:
        """Bí danh hỗ trợ API kiểm thử và downsampling ngoại vi."""
        return self._compute_peaks(num_cols)
