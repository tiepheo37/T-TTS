"""gui/dialog_find_replace.py — HỘP THOẠI TÌM KIẾM & THAY THẾ VĂN BẢN (FIND & REPLACE)
==================================================================================
Tích hợp cho Text Editor của T-TTS v3.1.0:
- Tìm kiếm từ / cụm từ với tùy chọn khớp chữ hoa/thường (Case Sensitive) và Regex.
- Đếm số lượng kết quả tìm thấy theo thời gian thực.
- Thay thế từng mục hoặc Thay thế tất cả (Replace All).
- Nhảy tiêu điểm (highlight) trực tiếp trên ô soạn thảo QTextEdit.
"""

from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QMessageBox,
    QTextEdit,
)

from backend.text_processor import VietnameseTextProcessor


class FindReplaceDialog(QDialog):
    """Hộp thoại tìm kiếm và thay thế văn bản thông minh."""

    def __init__(self, editor: QTextEdit, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("🔍 Tìm Kiếm & Thay Thế Văn Bản — T-TTS")
        self.setFixedWidth(460)
        self.setStyleSheet("""
            QDialog { background-color: #0F1710; color: #FFFFFF; }
            QLabel { color: #E2E8F0; font-size: 12px; }
            QLineEdit {
                background-color: #162419; color: #FFFFFF; border: 1px solid #2D5A34;
                border-radius: 4px; padding: 6px; font-size: 13px;
            }
            QPushButton {
                background-color: #1E3A24; color: #FFFFFF; border: 1px solid #3B6B44;
                border-radius: 4px; padding: 6px 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2D5A34; }
            QCheckBox { color: #CBD5E1; font-size: 12px; }
        """)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        grid = QGridLayout()
        grid.setSpacing(8)

        grid.addWidget(QLabel("Tìm kiếm:"), 0, 0)
        self.edit_find = QLineEdit()
        self.edit_find.setPlaceholderText("Nhập từ hoặc cụm từ cần tìm...")
        self.edit_find.textChanged.connect(self._on_find_changed)
        grid.addWidget(self.edit_find, 0, 1)

        grid.addWidget(QLabel("Thay thế bằng:"), 1, 0)
        self.edit_replace = QLineEdit()
        self.edit_replace.setPlaceholderText("Nội dung thay thế...")
        grid.addWidget(self.edit_replace, 1, 1)
        layout.addLayout(grid)

        # Tùy chọn tìm kiếm
        opt_layout = QHBoxLayout()
        self.chk_case = QCheckBox("Khớp chữ hoa/thường")
        self.chk_case.toggled.connect(self._on_find_changed)
        opt_layout.addWidget(self.chk_case)

        self.chk_regex = QCheckBox("Biểu thức Regex")
        self.chk_regex.toggled.connect(self._on_find_changed)
        opt_layout.addWidget(self.chk_regex)
        layout.addLayout(opt_layout)

        # Trạng thái đếm kết quả
        self.lbl_match_count = QLabel("Kết quả: Chưa tìm")
        self.lbl_match_count.setStyleSheet("color: #60A5FA; font-weight: bold;")
        layout.addWidget(self.lbl_match_count)

        # Nút thao tác
        btn_layout = QHBoxLayout()
        self.btn_find_next = QPushButton("Tìm Tiếp")
        self.btn_find_next.clicked.connect(self.find_next)
        btn_layout.addWidget(self.btn_find_next)

        self.btn_replace = QPushButton("Thay Thế")
        self.btn_replace.clicked.connect(self.replace_one)
        btn_layout.addWidget(self.btn_replace)

        self.btn_replace_all = QPushButton("Thay Tất Cả")
        self.btn_replace_all.setProperty("class", "PrimaryBtn")
        self.btn_replace_all.setStyleSheet("background-color: #15803D; color: #FFF;")
        self.btn_replace_all.clicked.connect(self.replace_all)
        btn_layout.addWidget(self.btn_replace_all)

        layout.addLayout(btn_layout)

    def _on_find_changed(self):
        query = self.edit_find.text()
        if not query:
            self.lbl_match_count.setText("Kết quả: Chưa tìm")
            return
        text = self.editor.toPlainText()
        matches = VietnameseTextProcessor.find_text(
            text=text,
            query=query,
            case_sensitive=self.chk_case.isChecked(),
            use_regex=self.chk_regex.isChecked(),
        )
        self.lbl_match_count.setText(f"Kết quả: Tìm thấy {len(matches)} vị trí")

    def find_next(self) -> bool:
        query = self.edit_find.text()
        if not query:
            return False

        flags = QTextDocument.FindFlags()
        if self.chk_case.isChecked():
            flags |= QTextDocument.FindCaseSensitively

        found = self.editor.find(query, flags)
        if not found:
            # Quay lại từ đầu văn bản
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.editor.setTextCursor(cursor)
            found = self.editor.find(query, flags)

        if not found:
            QMessageBox.information(self, "Thông báo", f"Không tìm thấy '{query}' trong văn bản.")
        return found

    def replace_one(self):
        query = self.edit_find.text()
        replace_with = self.edit_replace.text()
        if not query:
            return

        cursor = self.editor.textCursor()
        if cursor.hasSelection() and (
            (self.chk_case.isChecked() and cursor.selectedText() == query)
            or (not self.chk_case.isChecked() and cursor.selectedText().lower() == query.lower())
        ):
            cursor.insertText(replace_with)
            self.find_next()
        else:
            if self.find_next():
                self.editor.textCursor().insertText(replace_with)

        self._on_find_changed()

    def replace_all(self):
        query = self.edit_find.text()
        replace_with = self.edit_replace.text()
        if not query:
            return

        text = self.editor.toPlainText()
        new_text, count = VietnameseTextProcessor.replace_text(
            text=text,
            query=query,
            replacement=replace_with,
            case_sensitive=self.chk_case.isChecked(),
            use_regex=self.chk_regex.isChecked(),
        )
        if count > 0:
            self.editor.setPlainText(new_text)
            self.lbl_match_count.setText(f"Đã thay thế thành công {count} vị trí.")
            QMessageBox.information(self, "Thành công", f"Đã thay thế {count} vị trí xuất hiện của '{query}'.")
        else:
            QMessageBox.information(self, "Thông báo", f"Không tìm thấy '{query}' để thay thế.")
