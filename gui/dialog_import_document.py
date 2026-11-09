"""gui/dialog_import_document.py — HỘP THOẠI NHẬP TÀI LIỆU WORD, PDF, TXT
=====================================================================
Giao diện nhập tài liệu văn bản chuyên nghiệp cho T-TTS v3.1.0:
- Hỗ trợ DOCX, PDF, TXT, hướng dẫn tệp DOC cũ.
- Trích xuất ngầm bằng Worker Thread không làm treo UI.
- Thanh tiến trình thực tế kèm nút Hủy an toàn.
- Thống kê chi tiết: số trang, số từ, số ký tự, thời lượng đọc ước tính.
- Hiển thị cảnh báo nếu tài liệu PDF là bản scan thiếu text layer.
- Xem trước và cho phép chỉnh sửa nội dung trước khi chèn vào Text Editor.
- 3 tùy chọn: Thay thế (Replace), Nối tiếp (Append), hoặc Tạo dự án mới.
- Bảo toàn 100% nội dung đang nhập nếu người dùng bấm Hủy.
"""

from __future__ import annotations

import sys
import time
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
    QTextEdit,
    QProgressBar,
    QRadioButton,
    QButtonGroup,
    QFileDialog,
    QMessageBox,
    QFrame,
    QScrollArea,
)

from backend.document_reader import extract_document_text


# =============================================================================
# WORKER THREAD TRÍCH XUẤT TÀI LIỆU CHẠY NGẦM
# =============================================================================
class DocumentExtractionWorker(QThread):
    """Tiểu trình xử lý trích xuất văn bản tài liệu không gây đứng UI."""

    progress_updated = Signal(int, int, str)  # current, total, message
    finished_success = Signal(dict)           # result_dict
    finished_error = Signal(str)             # error_msg

    def __init__(self, file_path: Path, strip_header_footer: bool = False):
        super().__init__()
        self.file_path = file_path
        self.strip_header_footer = strip_header_footer
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            def _progress_cb(curr, total, msg):
                self.progress_updated.emit(curr, total, msg)

            def _cancel_check():
                return self._is_cancelled

            res = extract_document_text(
                file_path=self.file_path,
                strip_header_footer=self.strip_header_footer,
                progress_callback=_progress_cb,
                cancel_check=_cancel_check,
            )

            if self._is_cancelled:
                self.finished_error.emit("Đã hủy quá trình nhập tài liệu.")
            elif not res.get("success", False):
                self.finished_error.emit(res.get("error") or "Không thể trích xuất tài liệu.")
            else:
                self.finished_success.emit(res)

        except Exception as e:
            self.finished_error.emit(f"Lỗi ngoại lệ khi đọc tài liệu: {e}")


# =============================================================================
# HỘP THOẠI NHẬP TÀI LIỆU CHÍNH (DOCUMENT IMPORT DIALOG)
# =============================================================================
class DocumentImportDialog(QDialog):
    """Hộp thoại giao diện người dùng nhập tài liệu thông minh."""

    def __init__(self, parent: Optional[QWidget] = None, initial_file: Optional[Path] = None):
        super().__init__(parent)
        self.setWindowTitle("📂 Nhập Tài Liệu Văn Bản (Word, PDF, TXT) — T-TTS")
        self.setMinimumSize(780, 640)
        self.resize(840, 680)

        self.selected_file_path: Optional[Path] = initial_file
        self.extraction_result: Optional[Dict[str, Any]] = None
        self.worker: Optional[DocumentExtractionWorker] = None

        # Kết quả đầu ra trả về cho PageSynthesize
        self.final_text: str = ""
        self.selected_action: str = "replace"  # 'replace' | 'append' | 'new_project'
        self.document_meta: Dict[str, Any] = {}

        self._apply_styling()
        self._build_ui()

        if self.selected_file_path and self.selected_file_path.is_file():
            self._start_extraction(self.selected_file_path)

    def _apply_styling(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #112213;
                color: #FFFFFF;
            }
            QLabel {
                color: #E2ECE1;
                font-size: 13px;
            }
            QFrame.Card {
                background-color: #172D1B;
                border: 1px solid #27472A;
                border-radius: 8px;
            }
            QTextEdit {
                background-color: #0B190D;
                color: #FFFFFF;
                border: 1px solid #2D5A27;
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
                line-height: 1.5;
            }
            QPushButton {
                background-color: #244727;
                color: #FFFFFF;
                border: 1px solid #365739;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2F5C33;
                border-color: #4ADE80;
            }
            QPushButton.PrimaryBtn {
                background-color: #2D5A27;
                color: #FFFFFF;
                border: 1px solid #4ADE80;
                padding: 10px 22px;
                font-size: 14px;
            }
            QPushButton.PrimaryBtn:hover {
                background-color: #386E31;
            }
            QProgressBar {
                background-color: #0B190D;
                border: 1px solid #27472A;
                border-radius: 4px;
                text-align: center;
                color: #FFFFFF;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #22C55E;
                border-radius: 3px;
            }
            QRadioButton {
                color: #CBD5E1;
                font-size: 13px;
                spacing: 8px;
            }
            QRadioButton:checked {
                color: #4ADE80;
                font-weight: bold;
            }
        """)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 18, 20, 18)
        main_layout.setSpacing(14)

        # 1. TIÊU ĐỀ & NÚT CHỌN FILE
        header_card = QFrame()
        header_card.setProperty("class", "Card")
        hc_layout = QVBoxLayout(header_card)
        hc_layout.setContentsMargins(16, 14, 16, 14)
        hc_layout.setSpacing(10)

        title_row = QHBoxLayout()
        lbl_title = QLabel("<b>TRÍCH XUẤT VĂN BẢN TỪ TÀI LIỆU</b>")
        lbl_title.setStyleSheet("color: #4ADE80; font-size: 15px; font-weight: bold;")
        title_row.addWidget(lbl_title)
        title_row.addStretch()

        self.btn_browse = QPushButton("📁 Chọn tài liệu khác...")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.clicked.connect(self._on_browse_clicked)
        title_row.addWidget(self.btn_browse)
        hc_layout.addLayout(title_row)

        self.lbl_file_info = QLabel("Chưa chọn tệp. Hỗ trợ định dạng: Word (.docx), PDF (.pdf), Văn bản (.txt)")
        self.lbl_file_info.setStyleSheet("color: #94A3B8; font-size: 12px;")
        self.lbl_file_info.setWordWrap(True)
        hc_layout.addWidget(self.lbl_file_info)

        main_layout.addWidget(header_card)

        # 2. KHU VỰC TIẾN TRÌNH TRÍCH XUẤT (PROGRESS VIEW)
        self.progress_frame = QFrame()
        self.progress_frame.setProperty("class", "Card")
        pf_layout = QVBoxLayout(self.progress_frame)
        pf_layout.setContentsMargins(16, 12, 16, 12)
        pf_layout.setSpacing(8)

        self.lbl_progress_status = QLabel("Đang chuẩn bị trích xuất...")
        self.lbl_progress_status.setStyleSheet("color: #EAB308; font-weight: 500;")
        pf_layout.addWidget(self.lbl_progress_status)

        p_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(14)
        p_row.addWidget(self.progress_bar)

        self.btn_cancel_extract = QPushButton("✕ Hủy")
        self.btn_cancel_extract.setFixedSize(70, 26)
        self.btn_cancel_extract.setStyleSheet("background-color: #451A1A; border: 1px solid #EF4444; color: #FCA5A5; font-size: 11px;")
        self.btn_cancel_extract.clicked.connect(self._on_cancel_extraction)
        p_row.addWidget(self.btn_cancel_extract)
        pf_layout.addLayout(p_row)

        self.progress_frame.setVisible(False)
        main_layout.addWidget(self.progress_frame)

        # 3. KHU VỰC CẢNH BÁO (WARNING BANNER)
        self.warning_frame = QFrame()
        self.warning_frame.setStyleSheet("""
            background-color: #2A240E;
            border: 1px solid #EAB308;
            border-radius: 6px;
            padding: 8px 12px;
        """)
        wf_layout = QHBoxLayout(self.warning_frame)
        wf_layout.setContentsMargins(10, 8, 10, 8)
        self.lbl_warning_text = QLabel()
        self.lbl_warning_text.setStyleSheet("color: #FDE047; font-size: 12px;")
        self.lbl_warning_text.setWordWrap(True)
        wf_layout.addWidget(self.lbl_warning_text)
        self.warning_frame.setVisible(False)
        main_layout.addWidget(self.warning_frame)

        # 4. THẺ THỐNG KÊ TÀI LIỆU (STATS BADGES)
        self.stats_frame = QFrame()
        self.stats_frame.setProperty("class", "Card")
        sf_layout = QHBoxLayout(self.stats_frame)
        sf_layout.setContentsMargins(16, 10, 16, 10)
        sf_layout.setSpacing(20)

        self.lbl_stat_format = QLabel("Định dạng: --")
        self.lbl_stat_format.setStyleSheet("font-weight: bold; color: #60A5FA;")
        sf_layout.addWidget(self.lbl_stat_format)

        self.lbl_stat_pages = QLabel("Số trang: --")
        sf_layout.addWidget(self.lbl_stat_pages)

        self.lbl_stat_words = QLabel("Số từ: --")
        sf_layout.addWidget(self.lbl_stat_words)

        self.lbl_stat_chars = QLabel("Ký tự: --")
        sf_layout.addWidget(self.lbl_stat_chars)

        self.lbl_stat_time = QLabel("Thời lượng đọc ước tính: --")
        self.lbl_stat_time.setStyleSheet("color: #4ADE80; font-weight: bold;")
        sf_layout.addWidget(self.lbl_stat_time)

        sf_layout.addStretch()
        self.stats_frame.setVisible(False)
        main_layout.addWidget(self.stats_frame)

        # 5. KHUNG XEM TRƯỚC VÀ CHỈNH SỬA VĂN BẢN (PREVIEW AREA)
        self.preview_label = QLabel("<b>NỘI DUNG VĂN BẢN TRÍCH XUẤT (Có thể chỉnh sửa trực tiếp trước khi nhập):</b>")
        self.preview_label.setStyleSheet("color: #CBD5E1; font-size: 12px;")
        self.preview_label.setVisible(False)
        main_layout.addWidget(self.preview_label)

        self.txt_preview = QTextEdit()
        self.txt_preview.setPlaceholderText("Nội dung văn bản sau khi trích xuất sẽ hiển thị tại đây...")
        self.txt_preview.textChanged.connect(self._on_preview_text_changed)
        self.txt_preview.setVisible(False)
        main_layout.addWidget(self.txt_preview, 1)

        # 6. TÙY CHỌN HÀNH ĐỘNG (ACTION CHOICES)
        self.action_card = QFrame()
        self.action_card.setProperty("class", "Card")
        ac_layout = QVBoxLayout(self.action_card)
        ac_layout.setContentsMargins(16, 12, 16, 12)
        ac_layout.setSpacing(8)

        lbl_action_title = QLabel("<b>Tùy chọn đưa vào Trình soạn thảo:</b>")
        lbl_action_title.setStyleSheet("color: #E2ECE1; font-size: 13px;")
        ac_layout.addWidget(lbl_action_title)

        action_row = QHBoxLayout()
        action_row.setSpacing(24)

        self.rb_replace = QRadioButton("Thay thế toàn bộ nội dung hiện tại")
        self.rb_replace.setChecked(True)
        action_row.addWidget(self.rb_replace)

        self.rb_append = QRadioButton("Chèn tiếp vào cuối nội dung hiện tại")
        action_row.addWidget(self.rb_append)

        self.rb_new_project = QRadioButton("Nhập và lưu thành Dự án tài liệu mới")
        action_row.addWidget(self.rb_new_project)

        self.action_group = QButtonGroup(self)
        self.action_group.addButton(self.rb_replace, 1)
        self.action_group.addButton(self.rb_append, 2)
        self.action_group.addButton(self.rb_new_project, 3)

        ac_layout.addLayout(action_row)
        self.action_card.setVisible(False)
        main_layout.addWidget(self.action_card)

        # 7. NÚT ĐIỀU KHIỂN DƯỚI CÙNG (BOTTOM BUTTONS)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        self.btn_close = QPushButton("Hủy bỏ")
        self.btn_close.clicked.connect(self.reject)
        self.btn_cancel = self.btn_close  # alias for cancel
        bottom_row.addWidget(self.btn_close)

        bottom_row.addStretch()

        self.btn_confirm = QPushButton("✅ Xác nhận đưa vào soạn thảo")
        self.btn_confirm.setProperty("class", "PrimaryBtn")
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.clicked.connect(self._on_confirm_clicked)
        bottom_row.addWidget(self.btn_confirm)

        main_layout.addLayout(bottom_row)

    # =========================================================================
    # XỬ LÝ SỰ KIỆN GIAO DIỆN
    # =========================================================================
    def _on_browse_clicked(self):
        """Mở hộp thoại chọn tệp tài liệu máy tính."""
        fn, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn tệp tài liệu văn bản",
            "",
            "Tài liệu hỗ trợ (*.docx *.pdf *.txt);;Microsoft Word (*.docx);;Tài liệu PDF (*.pdf);;Văn bản thuần (*.txt);;Tệp Word cũ (*.doc);;Tất cả tệp (*.*)",
        )
        if not fn:
            return

        p = Path(fn).resolve()
        self._start_extraction(p)

    def _start_extraction(self, p: Path):
        """Bắt đầu tiến trình trích xuất ngầm bằng worker."""
        self.selected_file_path = p
        self.lbl_file_info.setText(f"<b>Tệp đang xử lý:</b> {p.name}<br><span style='color: #64748B;'>Đường dẫn: {p}</span>")

        # Ẩn kết quả cũ
        self.stats_frame.setVisible(False)
        self.warning_frame.setVisible(False)
        self.preview_label.setVisible(False)
        self.txt_preview.setVisible(False)
        self.action_card.setVisible(False)
        self.btn_confirm.setEnabled(False)

        # Hiện thanh tiến trình
        self.progress_frame.setVisible(True)
        self.progress_bar.setValue(5)
        self.lbl_progress_status.setText(f"Đang phân tích định dạng tệp {p.suffix.upper()}...")
        self.btn_browse.setEnabled(False)

        # Khởi chạy Worker Thread
        self.worker = DocumentExtractionWorker(file_path=p, strip_header_footer=True)
        self.worker.progress_updated.connect(self._on_worker_progress)
        self.worker.finished_success.connect(self._on_worker_success)
        self.worker.finished_error.connect(self._on_worker_error)
        self.worker.start()

    def _on_cancel_extraction(self):
        """Hủy quá trình trích xuất đang chạy."""
        if self.worker and self.worker.isRunning():
            self.lbl_progress_status.setText("Đang yêu cầu hủy...")
            self.worker.cancel()
            self.worker.wait(1000)

        self.progress_frame.setVisible(False)
        self.btn_browse.setEnabled(True)

    def _on_worker_progress(self, current: int, total: int, message: str):
        self.progress_bar.setValue(int(current))
        self.lbl_progress_status.setText(message)

    def _on_worker_success(self, res: dict):
        """Trích xuất thành công: hiển thị thông số và nội dung xem trước."""
        self.progress_frame.setVisible(False)
        self.btn_browse.setEnabled(True)
        self.extraction_result = res
        self.document_meta = dict(res)

        # 1. Cập nhật thống kê
        fmt = res.get("format", "").upper()
        self.lbl_stat_format.setText(f"Định dạng: <b>{fmt}</b>")
        self.lbl_stat_pages.setText(f"Số trang: <b>{res.get('page_count', 1)}</b>")
        self.lbl_stat_words.setText(f"Số từ: <b>{res.get('word_count', 0):,}</b>")
        self.lbl_stat_chars.setText(f"Ký tự: <b>{res.get('char_count', 0):,}</b>")

        # Ước tính thời lượng phát thanh (trung bình 160 từ/phút)
        words = res.get("word_count", 0)
        est_minutes = max(0.1, round(words / 160.0, 1)) if words > 0 else 0.0
        self.lbl_stat_time.setText(f"Thời lượng đọc: <b>~{est_minutes} phút</b>")
        self.stats_frame.setVisible(True)

        # 2. Cảnh báo nếu có
        warning_msg = res.get("warning")
        if warning_msg:
            self.lbl_warning_text.setText(warning_msg)
            self.warning_frame.setVisible(True)
        else:
            self.warning_frame.setVisible(False)

        # 3. Hiển thị nội dung xem trước
        raw_text = res.get("raw_text", "")
        self.txt_preview.setPlainText(raw_text)
        self.preview_label.setVisible(True)
        self.txt_preview.setVisible(True)
        self.action_card.setVisible(True)
        self.btn_confirm.setEnabled(bool(raw_text.strip()))

    def _on_worker_error(self, err_msg: str):
        """Báo lỗi khi trích xuất thất bại."""
        self.progress_frame.setVisible(False)
        self.btn_browse.setEnabled(True)

        QMessageBox.warning(
            self,
            "Thông Báo Nhập Tài Liệu",
            f"Không thể hoàn thành trích xuất tài liệu:\n\n{err_msg}",
        )

    def _on_preview_text_changed(self):
        """Cập nhật đếm ký tự và thời lượng nếu người dùng sửa văn bản xem trước."""
        txt = self.txt_preview.toPlainText()
        words = len(txt.split()) if txt else 0
        chars = len(txt)
        est_minutes = max(0.1, round(words / 160.0, 1)) if words > 0 else 0.0

        self.lbl_stat_words.setText(f"Số từ: <b>{words:,}</b>")
        self.lbl_stat_chars.setText(f"Ký tự: <b>{chars:,}</b>")
        self.lbl_stat_time.setText(f"Thời lượng đọc: <b>~{est_minutes} phút</b>")
        self.btn_confirm.setEnabled(bool(txt.strip()))

    def _on_confirm_clicked(self):
        """Người dùng xác nhận đưa nội dung vào soạn thảo."""
        self.final_text = self.txt_preview.toPlainText().strip()
        if not self.final_text:
            QMessageBox.information(self, "Thông báo", "Nội dung văn bản đang rỗng.")
            return

        if self.rb_replace.isChecked():
            self.selected_action = "replace"
        elif self.rb_append.isChecked():
            self.selected_action = "append"
        elif self.rb_new_project.isChecked():
            self.selected_action = "new_project"

        self.accept()
