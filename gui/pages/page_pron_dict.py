"""gui/pages/page_pron_dict.py — TAB TỪ ĐIỂN PHÁT ÂM NGƯỜI DÙNG
===================================================================
Định nghĩa cách đọc cho các từ viết tắt, tên riêng hoặc thuật ngữ chuyên ngành:
- Lưu persistent trong thư mục dữ liệu người dùng (data/pronunciation-dict.json).
- Tự động thay thế văn bản trước khi đưa vào mô hình VieNeu-TTS v3 Turbo.
- Bảng danh sách trực quan, tìm kiếm nhanh, sửa/xóa từng mục hoặc xóa toàn bộ.
- Khung thử nghiệm tức thì: Kiểm tra ngay câu văn sau khi áp dụng từ điển.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QFrame,
    QScrollArea,
)

from backend.service import tts_service


class PagePronDict(QWidget):
    """Trang Từ Điển Phát Âm Người Dùng."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._dict_cache: dict[str, str] = {}
        self._build_ui()
        self.reload_dict()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # 1. TIÊU ĐỀ & MÔ TẢ
        header_card = QFrame()
        header_card.setProperty("class", "CardFrame")
        hc_layout = QVBoxLayout(header_card)
        hc_layout.setContentsMargins(14, 12, 14, 12)
        hc_layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_icon = QLabel("📖")
        title_icon.setStyleSheet("font-size: 20px; border: none;")
        title_row.addWidget(title_icon)

        title = QLabel("TỪ ĐIỂN PHÁT ÂM NGƯỜI DÙNG")
        title.setProperty("class", "CardTitle")
        title.setStyleSheet("color: #FFD700; font-size: 16px; font-weight: 800; border: none;")
        title_row.addWidget(title)

        title_row.addStretch()

        self.lbl_count = QLabel("Đang tải...")
        self.lbl_count.setStyleSheet("color: #86EFAC; font-size: 12px; font-weight: bold; border: none;")
        title_row.addWidget(self.lbl_count)
        hc_layout.addLayout(title_row)

        desc = QLabel(
            "Định nghĩa cách đọc cho các từ viết tắt, tên riêng nước ngoài hoặc thuật ngữ chuyên môn "
            "(Ví dụ: <b>KTX</b> → <i>ký túc xá</i>, <b>QĐNDVN</b> → <i>quân đội nhân dân việt nam</i>). "
            "Dữ liệu được lưu vĩnh viễn trên máy và tự động thay thế khi bạn bấm Tạo giọng nói."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #A2BCA0; font-size: 12px; line-height: 1.4; border: none;")
        hc_layout.addWidget(desc)
        main_layout.addWidget(header_card)

        # 2. KHU VỰC NHẬP TỪ MỚI (FORM)
        input_card = QFrame()
        input_card.setProperty("class", "CardFrame")
        ic_layout = QVBoxLayout(input_card)
        ic_layout.setContentsMargins(14, 12, 14, 12)
        ic_layout.setSpacing(10)

        ic_title = QLabel("➕ THÊM / CẬP NHẬT TỪ VÀO TỪ ĐIỂN")
        ic_title.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 13px; border: none;")
        ic_layout.addWidget(ic_title)

        form_row = QHBoxLayout()
        form_row.setSpacing(10)

        # Ô nhập Từ gốc / Viết tắt
        w_box = QVBoxLayout()
        w_box.setSpacing(3)
        lbl_w = QLabel("Từ viết tắt / Thuật ngữ:")
        lbl_w.setStyleSheet("color: #CBD5E1; font-size: 11px; font-weight: bold; border: none;")
        w_box.addWidget(lbl_w)
        self.txt_word = QLineEdit()
        self.txt_word.setPlaceholderText("VD: KTX, QĐNDVN, AI, UNESCO...")
        self.txt_word.setStyleSheet("padding: 7px 10px; font-size: 13px;")
        w_box.addWidget(self.txt_word)
        form_row.addLayout(w_box, 1)

        # Ô nhập Cách đọc thay thế
        r_box = QVBoxLayout()
        r_box.setSpacing(3)
        lbl_r = QLabel("Cách đọc thay thế:")
        lbl_r.setStyleSheet("color: #CBD5E1; font-size: 11px; font-weight: bold; border: none;")
        r_box.addWidget(lbl_r)
        self.txt_reading = QLineEdit()
        self.txt_reading.setPlaceholderText("VD: ký túc xá, quân đội nhân dân việt nam...")
        self.txt_reading.setStyleSheet("padding: 7px 10px; font-size: 13px;")
        r_box.addWidget(self.txt_reading)
        form_row.addLayout(r_box, 2)

        # Nút Lưu
        btn_box = QVBoxLayout()
        btn_box.setSpacing(3)
        lbl_dummy = QLabel(" ")
        lbl_dummy.setStyleSheet("font-size: 11px; border: none;")
        btn_box.addWidget(lbl_dummy)
        
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_save = QPushButton("💾 Lưu Vào Từ Điển")
        self.btn_save.setProperty("class", "PrimaryBtn")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.clicked.connect(self._save_word)
        btn_row.addWidget(self.btn_save)

        self.btn_clear_form = QPushButton("🧹 Xóa Trắng")
        self.btn_clear_form.setProperty("class", "SecondaryBtn")
        self.btn_clear_form.setCursor(Qt.PointingHandCursor)
        self.btn_clear_form.clicked.connect(self._clear_form)
        btn_row.addWidget(self.btn_clear_form)

        btn_box.addLayout(btn_row)
        form_row.addLayout(btn_box)

        ic_layout.addLayout(form_row)
        main_layout.addWidget(input_card)

        # 3. BẢNG DANH SÁCH & TÌM KIẾM
        table_card = QFrame()
        table_card.setProperty("class", "CardFrame")
        tc_layout = QVBoxLayout(table_card)
        tc_layout.setContentsMargins(14, 12, 14, 12)
        tc_layout.setSpacing(10)

        tb_top = QHBoxLayout()
        tb_title = QLabel("📋 DANH SÁCH TỪ ĐIỂN")
        tb_title.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 13px; border: none;")
        tb_top.addWidget(tb_title)

        tb_top.addStretch()

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 Tìm kiếm từ...")
        self.txt_search.setFixedWidth(220)
        self.txt_search.textChanged.connect(self._filter_dict)
        tb_top.addWidget(self.txt_search)

        self.btn_reload = QPushButton("🔄 Tải lại")
        self.btn_reload.setProperty("class", "SecondaryBtn")
        self.btn_reload.setCursor(Qt.PointingHandCursor)
        self.btn_reload.clicked.connect(self.reload_dict)
        tb_top.addWidget(self.btn_reload)

        tc_layout.addLayout(tb_top)

        # Bảng hiển thị
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["STT", "Từ Viết Tắt / Thuật Ngữ", "Cách Đọc Thay Thế", "Thao Tác"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(3, 140)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        tc_layout.addWidget(self.table)

        main_layout.addWidget(table_card, 1)

        # 4. KHUNG KIỂM TRA THỬ THAY THẾ (QUICK PREVIEW)
        preview_card = QFrame()
        preview_card.setProperty("class", "CardFrame")
        pc_layout = QVBoxLayout(preview_card)
        pc_layout.setContentsMargins(14, 10, 14, 10)
        pc_layout.setSpacing(6)

        p_row = QHBoxLayout()
        p_lbl = QLabel("🔍 Thử nghiệm thay thế nhanh:")
        p_lbl.setStyleSheet("color: #FFD700; font-size: 12px; font-weight: bold; border: none;")
        p_row.addWidget(p_lbl)

        self.txt_test_sentence = QLineEdit()
        self.txt_test_sentence.setPlaceholderText("Nhập câu có chứa từ viết tắt (VD: Đồng chí đến UBND và KTX để làm việc)...")
        self.txt_test_sentence.setStyleSheet("padding: 5px 8px;")
        p_row.addWidget(self.txt_test_sentence, 1)

        btn_test = QPushButton("Kiểm tra")
        btn_test.setProperty("class", "SecondaryBtn")
        btn_test.setCursor(Qt.PointingHandCursor)
        btn_test.clicked.connect(self._run_preview_test)
        p_row.addWidget(btn_test)
        pc_layout.addLayout(p_row)

        self.lbl_test_result = QLabel("")
        self.lbl_test_result.setWordWrap(True)
        self.lbl_test_result.setStyleSheet("color: #86EFAC; font-size: 12px; font-weight: 500; padding: 2px 0; border: none;")
        pc_layout.addWidget(self.lbl_test_result)

        main_layout.addWidget(preview_card)

    def reload_dict(self):
        """Tải lại danh sách từ điển từ backend."""
        try:
            self._dict_cache = tts_service.get_pron_dict()
        except Exception:
            self._dict_cache = {}
        self._populate_table(self._dict_cache)

    def _populate_table(self, data: dict[str, str]):
        self.table.setRowCount(0)
        items = sorted(data.items(), key=lambda kv: kv[0].lower())
        self.lbl_count.setText(f"Tổng số: {len(items)} từ")

        for idx, (word, reading) in enumerate(items):
            row = self.table.rowCount()
            self.table.insertRow(row)

            # STT
            stt_item = QTableWidgetItem(str(idx + 1))
            stt_item.setTextAlignment(Qt.AlignCenter)
            stt_item.setFlags(stt_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, stt_item)

            # Từ gốc
            word_item = QTableWidgetItem(word)
            word_item.setForeground(QColor("#FFD700"))
            word_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            word_item.setFlags(word_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, word_item)

            # Cách đọc
            reading_item = QTableWidgetItem(reading)
            reading_item.setForeground(QColor("#FFFFFF"))
            reading_item.setFlags(reading_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, reading_item)

            # Nút Thao tác (Sửa, Xóa)
            action_box = QWidget()
            ab_layout = QHBoxLayout(action_box)
            ab_layout.setContentsMargins(4, 2, 4, 2)
            ab_layout.setSpacing(6)

            btn_edit = QPushButton("✏️ Sửa")
            btn_edit.setProperty("class", "SecondaryBtn")
            btn_edit.setStyleSheet("padding: 2px 6px; font-size: 11px;")
            btn_edit.setCursor(Qt.PointingHandCursor)
            btn_edit.clicked.connect(lambda _, w=word, r=reading: self._load_to_form(w, r))
            ab_layout.addWidget(btn_edit)

            btn_del = QPushButton("🗑️ Xóa")
            btn_del.setProperty("class", "SecondaryBtn")
            btn_del.setStyleSheet("padding: 2px 6px; font-size: 11px; color: #F87171;")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.clicked.connect(lambda _, w=word: self._delete_word(w))
            ab_layout.addWidget(btn_del)

            self.table.setCellWidget(row, 3, action_box)
            self.table.setRowHeight(row, 38)

    def _filter_dict(self, keyword: str):
        kw = keyword.strip().lower()
        if not kw:
            self._populate_table(self._dict_cache)
            return

        filtered = {
            w: r for w, r in self._dict_cache.items()
            if kw in w.lower() or kw in r.lower()
        }
        self._populate_table(filtered)

    def _save_word(self):
        word = self.txt_word.text().strip()
        reading = self.txt_reading.text().strip()

        if not word:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập Từ viết tắt hoặc Thuật ngữ.")
            self.txt_word.setFocus()
            return

        if not reading:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập Cách đọc thay thế.")
            self.txt_reading.setFocus()
            return

        try:
            tts_service.set_pron_dict_entry(word, reading)
            self._clear_form()
            self.reload_dict()
            QMessageBox.information(
                self,
                "Thành công",
                f"Đã lưu thành công vào từ điển:\n<b>{word}</b> → <i>{reading}</i>"
            )
        except Exception as e:
            QMessageBox.critical(self, "Lỗi lưu từ điển", f"Không thể lưu từ điển: {e}")

    def _load_to_form(self, word: str, reading: str):
        self.txt_word.setText(word)
        self.txt_reading.setText(reading)
        self.txt_reading.setFocus()

    def _delete_word(self, word: str):
        ans = QMessageBox.question(
            self,
            "Xác nhận xóa",
            f"Bạn có chắc muốn xóa từ '<b>{word}</b>' khỏi từ điển phát âm?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            try:
                tts_service.delete_pron_dict_entry(word)
                self.reload_dict()
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không thể xóa từ: {e}")

    def _clear_form(self):
        self.txt_word.clear()
        self.txt_reading.clear()

    def _run_preview_test(self):
        test_txt = self.txt_test_sentence.text().strip()
        if not test_txt:
            self.lbl_test_result.setText("<i>Vui lòng nhập câu thử nghiệm ở trên.</i>")
            return

        res = tts_service.preview_pron_text(test_txt)
        self.lbl_test_result.setText(f"👉 <b>Sau khi thay thế:</b> \"{res}\"")
