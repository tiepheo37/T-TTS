"""gui/dialog_text_processor.py — HỘP THOẠI CHUẨN HÓA VĂN BẢN & ĐỌC SỐ TIẾNG VIỆT
=============================================================================
Giao diện điều khiển cấu hình xử lý văn bản chuyên sâu cho T-TTS v3.1.0:
- Tùy chọn bật/tắt từng quy tắc đọc số tiếng Việt (số nguyên, thập phân, âm, phần trăm, tiền tệ, thứ tự, điện thoại, số hiệu văn bản, đơn vị quân sự).
- Xem trước so sánh Trước (Original) và Sau (Normalized).
- Bảng thống kê chi tiết: số ký tự, số từ, số đoạn, thời lượng đọc ước tính và số phân đoạn TTS dự kiến.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QTextEdit,
    QFrame,
    QTabWidget,
    QMessageBox,
)

from backend.text_processor import (
    VietnameseTextProcessor,
    TextProcessingConfig,
)


class TextProcessorDialog(QDialog):
    """Hộp thoại chuẩn hóa văn bản thông minh trước khi chuyển thành giọng nói."""

    def __init__(self, current_text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.raw_text = current_text
        self.final_text = current_text
        self.setWindowTitle("⚙️ Chuẩn Hóa Văn Bản & Đọc Số Tiếng Việt — T-TTS")
        self.setMinimumSize(840, 640)
        self.resize(880, 680)
        self.setStyleSheet("""
            QDialog { background-color: #0F1710; color: #FFFFFF; }
            QLabel { color: #E2E8F0; font-size: 12px; }
            QCheckBox { color: #CBD5E1; font-size: 12px; }
            QTextEdit {
                background-color: #162419; color: #FFFFFF; border: 1px solid #2D5A34;
                border-radius: 4px; padding: 8px; font-size: 13px;
            }
            QPushButton {
                background-color: #1E3A24; color: #FFFFFF; border: 1px solid #3B6B44;
                border-radius: 4px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2D5A34; }
        """)
        self._init_ui()
        self._update_preview()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(12)

        # 1. TIÊU ĐỀ
        lbl_title = QLabel("⚙️ <b>CẤU HÌNH TIỀN XỬ LÝ VĂN BẢN & ĐỌC SỐ TIẾNG VIỆT CHO TTS</b>")
        lbl_title.setStyleSheet("color: #4ADE80; font-size: 14px;")
        main_layout.addWidget(lbl_title)

        # 2. KHU VỰC CẤU HÌNH QUY TẮC CHUẨN HÓA
        cfg_frame = QFrame()
        cfg_frame.setStyleSheet("background-color: #122215; border: 1px solid #27472A; border-radius: 6px; padding: 10px;")
        cfg_layout = QGridLayout(cfg_frame)
        cfg_layout.setSpacing(10)

        # Cột 1: Ngày tháng & Số học
        self.chk_dates = QCheckBox("1. Đọc ngày tháng năm (22/12/1944 -> chữ)")
        self.chk_dates.setChecked(True)
        self.chk_dates.toggled.connect(self._update_preview)
        cfg_layout.addWidget(self.chk_dates, 0, 0)

        self.chk_times = QCheckBox("2. Đọc giờ phút (08:30 -> tám giờ rưỡi)")
        self.chk_times.setChecked(True)
        self.chk_times.toggled.connect(self._update_preview)
        cfg_layout.addWidget(self.chk_times, 1, 0)

        self.chk_percent = QCheckBox("3. Đọc phần trăm (100% -> một trăm phần trăm)")
        self.chk_percent.setChecked(True)
        self.chk_percent.toggled.connect(self._update_preview)
        cfg_layout.addWidget(self.chk_percent, 2, 0)

        self.chk_currency = QCheckBox("4. Đọc tiền tệ (500.000 VNĐ, $100)")
        self.chk_currency.setChecked(True)
        self.chk_currency.toggled.connect(self._update_preview)
        cfg_layout.addWidget(self.chk_currency, 3, 0)

        # Cột 2: Thứ tự, Đơn vị & Quân sự
        self.chk_ordinals = QCheckBox("5. Đọc số thứ tự (thứ 1 -> thứ nhất, hạng 1)")
        self.chk_ordinals.setChecked(True)
        self.chk_ordinals.toggled.connect(self._update_preview)
        cfg_layout.addWidget(self.chk_ordinals, 0, 1)

        self.chk_phone = QCheckBox("6. Đọc số điện thoại (10 chữ số)")
        self.chk_phone.setChecked(True)
        self.chk_phone.toggled.connect(self._update_preview)
        cfg_layout.addWidget(self.chk_phone, 1, 1)

        self.chk_doc_num = QCheckBox("7. Đọc số hiệu văn bản chỉ thị (Số 123/QĐ-BQP)")
        self.chk_doc_num.setChecked(True)
        self.chk_doc_num.toggled.connect(self._update_preview)
        cfg_layout.addWidget(self.chk_doc_num, 2, 1)

        self.chk_mil_units = QCheckBox("8. Đọc số hiệu đơn vị quân sự (f324, e1, d4, c1)")
        self.chk_mil_units.setChecked(True)
        self.chk_mil_units.toggled.connect(self._update_preview)
        cfg_layout.addWidget(self.chk_mil_units, 3, 1)

        # Cột 3: Viết tắt & Định dạng văn bản
        self.chk_acronyms = QCheckBox("9. Mở rộng từ viết tắt quân sự (QĐNDVN, BTL...)")
        self.chk_acronyms.setChecked(True)
        self.chk_acronyms.toggled.connect(self._update_preview)
        cfg_layout.addWidget(self.chk_acronyms, 0, 2)

        self.chk_decimals = QCheckBox("10. Đọc số thập phân & số âm (3,5 kg, -5)")
        self.chk_decimals.setChecked(True)
        self.chk_decimals.toggled.connect(self._update_preview)
        cfg_layout.addWidget(self.chk_decimals, 1, 2)

        self.chk_punct = QCheckBox("11. Chuẩn hóa khoảng cách dấu câu & khoảng trắng")
        self.chk_punct.setChecked(True)
        self.chk_punct.toggled.connect(self._update_preview)
        cfg_layout.addWidget(self.chk_punct, 2, 2)

        self.chk_nfc = QCheckBox("12. Chuẩn hóa Unicode NFC tiếng Việt chuẩn")
        self.chk_nfc.setChecked(True)
        self.chk_nfc.toggled.connect(self._update_preview)
        cfg_layout.addWidget(self.chk_nfc, 3, 2)

        main_layout.addWidget(cfg_frame)

        # 3. THẺ THỐNG KÊ THÔNG SỐ
        stats_frame = QFrame()
        stats_frame.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 8px;")
        sf_layout = QHBoxLayout(stats_frame)
        sf_layout.setSpacing(20)

        self.lbl_stat_chars = QLabel("Ký tự: 0")
        sf_layout.addWidget(self.lbl_stat_chars)

        self.lbl_stat_words = QLabel("Số từ: 0")
        sf_layout.addWidget(self.lbl_stat_words)

        self.lbl_stat_paras = QLabel("Số đoạn: 0")
        sf_layout.addWidget(self.lbl_stat_paras)

        self.lbl_stat_duration = QLabel("Thời lượng đọc: ~0 phút")
        self.lbl_stat_duration.setStyleSheet("color: #4ADE80; font-weight: bold;")
        sf_layout.addWidget(self.lbl_stat_duration)

        self.lbl_stat_segments = QLabel("Phân đoạn TTS dự kiến: 0")
        self.lbl_stat_segments.setStyleSheet("color: #60A5FA; font-weight: bold;")
        sf_layout.addWidget(self.lbl_stat_segments)

        sf_layout.addStretch()
        main_layout.addWidget(stats_frame)

        # 4. TAB XEM TRƯỚC (BEFORE / AFTER PREVIEW)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #27472A; background-color: #0F1710; }
            QTabBar::tab { background-color: #162419; color: #94A3B8; padding: 6px 16px; font-weight: bold; }
            QTabBar::tab:selected { background-color: #1E3A24; color: #4ADE80; border-bottom: 2px solid #4ADE80; }
        """)

        # Tab 1: Kết quả sau chuẩn hóa (Cho phép sửa trực tiếp)
        tab_after = QWidget()
        ta_layout = QVBoxLayout(tab_after)
        ta_layout.addWidget(QLabel("<b>Văn bản sau khi chuẩn hóa (Sẵn sàng đưa vào TTS):</b>"))
        self.txt_preview = QTextEdit()
        ta_layout.addWidget(self.txt_preview)
        self.tabs.addTab(tab_after, "✨ Kết Quả Chuẩn Hóa")

        # Tab 2: Văn bản gốc ban đầu
        tab_before = QWidget()
        tb_layout = QVBoxLayout(tab_before)
        tb_layout.addWidget(QLabel("<b>Văn bản gốc ban đầu (Chưa xử lý):</b>"))
        self.txt_original = QTextEdit()
        self.txt_original.setReadOnly(True)
        self.txt_original.setPlainText(self.raw_text)
        tb_layout.addWidget(self.txt_original)
        self.tabs.addTab(tab_before, "📄 Văn Bản Gốc")

        main_layout.addWidget(self.tabs, 1)

        # 5. NÚT ĐIỀU KHIỂN DƯỚI CÙNG
        btn_row = QHBoxLayout()
        self.btn_cancel = QPushButton("Hủy Bỏ")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        btn_row.addStretch()

        self.btn_apply = QPushButton("✅ Áp Dụng Chuẩn Hóa Vào Ô Soạn Thảo")
        self.btn_apply.setStyleSheet("background-color: #15803D; color: #FFF; font-size: 13px; font-weight: bold; padding: 8px 20px;")
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        btn_row.addWidget(self.btn_apply)

        main_layout.addLayout(btn_row)

    def _get_config(self) -> TextProcessingConfig:
        return TextProcessingConfig(
            enable_nfc=self.chk_nfc.isChecked(),
            normalize_whitespace=True,
            normalize_punctuation=self.chk_punct.isChecked(),
            expand_acronyms=self.chk_acronyms.isChecked(),
            normalize_dates=self.chk_dates.isChecked(),
            normalize_times=self.chk_times.isChecked(),
            normalize_percentages=self.chk_percent.isChecked(),
            normalize_currencies=self.chk_currency.isChecked(),
            normalize_decimals=self.chk_decimals.isChecked(),
            normalize_negative_numbers=self.chk_decimals.isChecked(),
            normalize_ordinals=self.chk_ordinals.isChecked(),
            normalize_phone_numbers=self.chk_phone.isChecked(),
            normalize_document_numbers=self.chk_doc_num.isChecked(),
            normalize_military_units=self.chk_mil_units.isChecked(),
        )

    def _update_preview(self):
        cfg = self._get_config()
        normalized = VietnameseTextProcessor.full_normalize(self.raw_text, config=cfg)
        self.txt_preview.setPlainText(normalized)

        # Cập nhật thống kê
        stats = VietnameseTextProcessor.calculate_statistics(normalized)
        self.lbl_stat_chars.setText(f"Ký tự: <b>{stats['char_count']:,}</b>")
        self.lbl_stat_words.setText(f"Số từ: <b>{stats['word_count']:,}</b>")
        self.lbl_stat_paras.setText(f"Số đoạn: <b>{stats['paragraph_count']}</b>")
        self.lbl_stat_duration.setText(f"Thời lượng đọc: <b>~{stats['estimated_minutes']} phút</b>")
        self.lbl_stat_segments.setText(f"Phân đoạn TTS: <b>{stats['estimated_segments']} đoạn</b>")

    def _on_apply_clicked(self):
        self.final_text = self.txt_preview.toPlainText().strip()
        self.accept()
