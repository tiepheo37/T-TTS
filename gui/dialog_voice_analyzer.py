"""gui/dialog_voice_analyzer.py — HỘP THOẠI PHÂN TÍCH CHẤT LƯỢNG GIỌNG NÓI THÔNG MINH (PHASE 9)
========================================================================================
Giao diện trực quan phân tích các chỉ số âm học và đề xuất giải pháp tối ưu:
- Bảng điểm chất lượng giọng nói tổng thể (Quality Score 0 - 100, Xếp hạng).
- 8 Thẻ đo lường âm học: LUFS, True Peak, RMS, Dynamic Range, Clipping, Sàn nhiễu, Khoảng lặng, Thời lượng.
- Danh sách cảnh báo vấn đề phát hiện (Clipping, Noise, Silence...).
- Gợi ý cấu hình DSP & Preset thông minh (Intelligent Presets).
- Tùy chọn làm sạch khoảng lặng (Smart Audio Cleanup) non-destructive.
- Tiểu trình Worker Thread chạy ngầm không gây đơ giao diện.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QFrame,
    QScrollArea,
    QMessageBox,
)

from backend.intelligent_audio import (
    VoiceQualityMetrics,
    voice_quality_analyzer,
    intelligent_voice_enhancer,
    smart_audio_cleanup,
)
from backend.audio_enhancement import AudioEnhancementConfig


# =============================================================================
# WORKER THREAD PHÂN TÍCH ÂM HỌC
# =============================================================================
class VoiceAnalyzerWorker(QThread):
    """Tiểu trình phân tích âm thanh chạy ngầm."""

    finished_analysis = Signal(object, dict)
    failed_analysis = Signal(str)

    def __init__(self, file_path: Path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            metrics = voice_quality_analyzer.analyze_file(self.file_path)
            rec = intelligent_voice_enhancer.evaluate_and_recommend(metrics)
            self.finished_analysis.emit(metrics, rec)
        except Exception as e:
            self.failed_analysis.emit(str(e))


# =============================================================================
# HỘP THOẠI PHÂN TÍCH CHẤT LƯỢNG GIỌNG NÓI CHÍNH
# =============================================================================
class VoiceQualityAnalyzerDialog(QDialog):
    """Hộp thoại hiển thị kết quả phân tích chất lượng âm thanh và khuyến nghị thông minh."""

    def __init__(self, input_wav_path: str | Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.input_path = Path(input_wav_path).resolve()
        self.setWindowTitle("🔍 Phân Tích Chất Lượng Âm Thanh & Gợi Ý Thông Minh — T-TTS")
        self.setFixedSize(820, 680)

        self.metrics: Optional[VoiceQualityMetrics] = None
        self.recommendations: Optional[Dict[str, Any]] = None
        self.applied_suggested_config: Optional[AudioEnhancementConfig] = None
        self.should_open_dsp: bool = False

        self._init_ui()
        self._start_analysis()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        self.setStyleSheet("""
            QDialog { background-color: #0F1E11; color: #FFFFFF; }
            QLabel { color: #CBD5E1; font-size: 13px; }
            QFrame { border-radius: 6px; }
            QPushButton { background-color: #1E3A24; color: #FFFFFF; border: 1px solid #3B533E; padding: 6px 14px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #274D30; }
        """)

        # 1. HEADER & TIẾN TRÌNH
        header_row = QHBoxLayout()
        lbl_title = QLabel("🔍 <b>PHÂN TÍCH ÂM HỌC & ĐÁNH GIÁ CHẤT LƯỢNG GIỌNG NÓI</b>")
        lbl_title.setStyleSheet("color: #4ADE80; font-size: 14px;")
        header_row.addWidget(lbl_title)
        header_row.addStretch()

        self.lbl_status = QLabel("⏳ Đang phân tích âm thanh...")
        self.lbl_status.setStyleSheet("color: #94A3B8; font-size: 12px;")
        header_row.addWidget(self.lbl_status)
        layout.addLayout(header_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #22C55E; }")
        layout.addWidget(self.progress_bar)

        # 2. KHUNG ĐIỂM CHẤT LƯỢNG TỔNG QUAN (QUALITY SCORE CARD)
        self.score_card = QFrame()
        self.score_card.setStyleSheet("background-color: #142817; border: 1px solid #27472A; padding: 12px;")
        sc_layout = QHBoxLayout(self.score_card)

        # Vòng tròn điểm số
        self.lbl_score_num = QLabel("--")
        self.lbl_score_num.setFont(QFont("Segoe UI", 26, QFont.Bold))
        self.lbl_score_num.setStyleSheet("color: #22C55E; padding-right: 15px;")
        sc_layout.addWidget(self.lbl_score_num)

        # Thông tin xếp hạng
        score_info_col = QVBoxLayout()
        self.lbl_grade = QLabel("Đang tính điểm chất lượng...")
        self.lbl_grade.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.lbl_grade.setStyleSheet("color: #F8FAFC;")
        score_info_col.addWidget(self.lbl_grade)

        self.lbl_summary = QLabel("Đang quét phân tích dải động, độ to LUFS, clipping và tạp âm nền...")
        self.lbl_summary.setStyleSheet("color: #94A3B8; font-size: 11px;")
        score_info_col.addWidget(self.lbl_summary)
        sc_layout.addLayout(score_info_col)

        sc_layout.addStretch()
        layout.addWidget(self.score_card)

        # 3. LƯỚI 8 THÔNG SỐ ÂM HỌC (8 METRIC CARDS)
        grid_metrics = QGridLayout()
        grid_metrics.setSpacing(10)

        self.card_lufs = self._create_metric_card("Độ To Tích Hợp (LUFS)", "-- LUFS", "Chuẩn: -16 LUFS")
        self.card_tp = self._create_metric_card("Biên Độ Đỉnh (True Peak)", "-- dBFS", "Trần an toàn: ≤ -1.0 dBFS")
        self.card_rms = self._create_metric_card("Năng Lượng RMS", "-- dBFS", "Mức năng lượng hiệu dụng")
        self.card_crest = self._create_metric_card("Dải Động (Crest Factor)", "-- dB", "Tỷ lệ đỉnh trên RMS")

        self.card_noise = self._create_metric_card("Sàn Nhiễu Nền", "-- dBFS", "Lý tưởng: < -50 dBFS")
        self.card_clip = self._create_metric_card("Kiểm Tra Méo (Clipping)", "--", "Mẫu vượt trần biên độ")
        self.card_silence = self._create_metric_card("Tỷ Lệ Khoảng Lặng", "-- %", "Bao gồm đầu và cuối")
        self.card_dur = self._create_metric_card("Thời Lượng Tệp", "-- s", "Thời gian phát sóng")

        grid_metrics.addWidget(self.card_lufs["frame"], 0, 0)
        grid_metrics.addWidget(self.card_tp["frame"], 0, 1)
        grid_metrics.addWidget(self.card_rms["frame"], 0, 2)
        grid_metrics.addWidget(self.card_crest["frame"], 0, 3)

        grid_metrics.addWidget(self.card_noise["frame"], 1, 0)
        grid_metrics.addWidget(self.card_clip["frame"], 1, 1)
        grid_metrics.addWidget(self.card_silence["frame"], 1, 2)
        grid_metrics.addWidget(self.card_dur["frame"], 1, 3)

        layout.addLayout(grid_metrics)

        # 4. DANH SÁCH VẤN ĐỀ & ĐỀ XUẤT THÔNG MINH (RECOMMENDATIONS CARD)
        rec_card = QFrame()
        rec_card.setStyleSheet("background-color: #122215; border: 1px solid #1E3A24; padding: 12px;")
        rc_layout = QVBoxLayout(rec_card)
        rc_layout.setSpacing(8)

        lbl_rec_title = QLabel("💡 <b>KHUYẾN NGHỊ TỐI ƯU HÓA TỰ ĐỘNG (INTELLIGENT RECOMMENDATION):</b>")
        lbl_rec_title.setStyleSheet("color: #F59E0B; font-size: 13px;")
        rc_layout.addWidget(lbl_rec_title)

        self.lbl_rec_preset = QLabel("Đang xác định cấu hình mẫu phù hợp...")
        self.lbl_rec_preset.setStyleSheet("color: #4ADE80; font-size: 13px; font-weight: bold;")
        rc_layout.addWidget(self.lbl_rec_preset)

        self.lbl_rec_explain = QLabel("--")
        self.lbl_rec_explain.setStyleSheet("color: #CBD5E1; font-size: 12px;")
        self.lbl_rec_explain.setWordWrap(True)
        rc_layout.addWidget(self.lbl_rec_explain)

        self.lbl_issues = QLabel("Không phát hiện lỗi nghiêm trọng.")
        self.lbl_issues.setStyleSheet("color: #94A3B8; font-size: 11px;")
        self.lbl_issues.setWordWrap(True)
        rc_layout.addWidget(self.lbl_issues)

        layout.addWidget(rec_card)

        # 5. HÀNG NÚT ĐIỀU KHIỂN DƯỚI CÙNG
        bottom_row = QHBoxLayout()
        self.btn_close = QPushButton("Đóng")
        self.btn_close.clicked.connect(self.reject)
        bottom_row.addWidget(self.btn_close)

        self.btn_cleanup = QPushButton("🧹 Làm Sạch Khoảng Lặng")
        self.btn_cleanup.setVisible(False)
        self.btn_cleanup.clicked.connect(self._apply_smart_cleanup)
        bottom_row.addWidget(self.btn_cleanup)

        bottom_row.addStretch()

        self.btn_apply_rec = QPushButton("✨ Áp Dụng Khuyến Nghị & Mở DSP")
        self.btn_apply_rec.setProperty("class", "PrimaryBtn")
        self.btn_apply_rec.setStyleSheet("""
            QPushButton { background-color: #2D5A27; color: #FFFFFF; border: 1px solid #4ADE80; padding: 8px 18px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #386E31; }
        """)
        self.btn_apply_rec.clicked.connect(self._apply_and_open_dsp)
        bottom_row.addWidget(self.btn_apply_rec)

        layout.addLayout(bottom_row)

    def _create_metric_card(self, title: str, init_val: str, subtitle: str) -> Dict[str, Any]:
        """Tạo thẻ hiển thị thông số âm học."""
        frame = QFrame()
        frame.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; padding: 6px;")
        fl = QVBoxLayout(frame)
        fl.setSpacing(2)
        fl.setContentsMargins(8, 6, 8, 6)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        fl.addWidget(t_lbl)

        v_lbl = QLabel(init_val)
        v_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        v_lbl.setStyleSheet("color: #F8FAFC;")
        fl.addWidget(v_lbl)

        s_lbl = QLabel(subtitle)
        s_lbl.setStyleSheet("color: #64748B; font-size: 10px;")
        fl.addWidget(s_lbl)

        return {"frame": frame, "val_lbl": v_lbl, "sub_lbl": s_lbl}

    def _start_analysis(self):
        """Khởi động Worker Thread phân tích tệp âm thanh."""
        self.worker = VoiceAnalyzerWorker(self.input_path)
        self.worker.finished_analysis.connect(self._on_analysis_done)
        self.worker.failed_analysis.connect(self._on_analysis_failed)
        self.worker.start()

    def _on_analysis_done(self, metrics: VoiceQualityMetrics, rec: dict):
        self.metrics = metrics
        self.recommendations = rec
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("✅ Phân tích hoàn tất.")

        # Cập nhật điểm số
        score = metrics.quality_score
        self.lbl_score_num.setText(f"{score}")
        if score >= 85:
            self.lbl_score_num.setStyleSheet("color: #22C55E;")
        elif score >= 70:
            self.lbl_score_num.setStyleSheet("color: #60A5FA;")
        elif score >= 50:
            self.lbl_score_num.setStyleSheet("color: #F59E0B;")
        else:
            self.lbl_score_num.setStyleSheet("color: #EF4444;")

        self.lbl_grade.setText(f"Xếp Hạng: {metrics.quality_grade}")
        self.lbl_summary.setText(f"Tệp: {Path(metrics.file_path).name} | Tần số lấy mẫu: {metrics.sample_rate}Hz | Số kênh: {metrics.channels}")

        # Cập nhật 8 thẻ đo
        self.card_lufs["val_lbl"].setText(f"{metrics.integrated_lufs:.1f} LUFS")
        self.card_tp["val_lbl"].setText(f"{metrics.true_peak_dbfs:.1f} dBFS")
        self.card_rms["val_lbl"].setText(f"{metrics.rms_dbfs:.1f} dBFS")
        self.card_crest["val_lbl"].setText(f"{metrics.crest_factor_db:.1f} dB")

        self.card_noise["val_lbl"].setText(f"{metrics.noise_level_dbfs:.1f} dBFS")

        if metrics.clipping_detected:
            self.card_clip["val_lbl"].setText(f"⚠️ {metrics.clipping_count} mẫu vỡ")
            self.card_clip["val_lbl"].setStyleSheet("color: #EF4444;")
        else:
            self.card_clip["val_lbl"].setText("✅ 0 mẫu (An toàn)")
            self.card_clip["val_lbl"].setStyleSheet("color: #22C55E;")

        self.card_silence["val_lbl"].setText(f"{metrics.silence_ratio_pct:.1f}%")
        self.card_dur["val_lbl"].setText(f"{metrics.duration_sec:.2f} s")

        # Cập nhật khuyến nghị
        preset_name = rec.get("recommended_preset_name", "Clean Voice")
        self.lbl_rec_preset.setText(f"⭐ Cấu hình đề xuất tối ưu: {preset_name}")
        self.lbl_rec_explain.setText(rec.get("explanation", ""))

        issues = metrics.issues_found
        if issues:
            self.lbl_issues.setText("⚠️ Các vấn đề phát hiện:\n• " + "\n• ".join(issues))
            self.lbl_issues.setStyleSheet("color: #FCA5A5; font-size: 11px;")
        else:
            self.lbl_issues.setText("✅ Âm thanh trong trẻo, không có lỗi clipping hay tạp âm nền đáng kể.")
            self.lbl_issues.setStyleSheet("color: #4ADE80; font-size: 11px;")

        # Hiển thị nút làm sạch khoảng lặng nếu thừa nhiều
        if metrics.leading_silence_sec > 0.8 or metrics.trailing_silence_sec > 1.0:
            self.btn_cleanup.setVisible(True)

    def _on_analysis_failed(self, error_msg: str):
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("❌ Lỗi phân tích.")
        QMessageBox.critical(self, "Lỗi phân tích", f"Không thể phân tích tệp âm thanh:\n\n{error_msg}")

    def _apply_and_open_dsp(self):
        """Người dùng chấp thuận cấu hình đề xuất."""
        if not self.recommendations:
            return
        self.applied_suggested_config = self.recommendations.get("suggested_config")
        self.should_open_dsp = True
        self.accept()

    def _apply_smart_cleanup(self):
        """Thực hiện cắt gọt khoảng lặng thừa an toàn sang file tạm."""
        if not self.metrics:
            return
        clean_temp = Path(self.input_path).parent / f"cleaned_{os.getpid()}_{Path(self.input_path).name}"
        res = smart_audio_cleanup.apply_cleanup(
            input_file=self.input_path,
            output_file=clean_temp,
            trim_leading=True,
            trim_trailing=True,
        )
        if res.get("success"):
            saved_ms = res.get("trimmed_leading_ms", 0) + res.get("trimmed_trailing_ms", 0)
            QMessageBox.information(
                self, "Làm sạch thành công",
                f"Đã cắt bớt khoảng lặng thừa: {saved_ms} ms.\nTệp đã làm sạch: {clean_temp.name}"
            )
            # Nạp lại đường dẫn tệp mới và phân tích lại
            self.input_path = clean_temp
            self.progress_bar.setVisible(True)
            self._start_analysis()
        else:
            QMessageBox.warning(self, "Lỗi làm sạch", res.get("error", "Không thể làm sạch tệp."))
