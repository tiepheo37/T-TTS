"""gui/pages/page_history.py — TAB 5: LỊCH SỬ TẠO GIỌNG NÓI (HISTORY)
===================================================================
Hiển thị toàn bộ lịch sử tạo âm thanh từ cơ sở dữ liệu History hiện có của người dùng:
- Bảo toàn 100% dữ liệu lịch sử cũ, không xóa dữ liệu người dùng.
- Bảng chi tiết: Thời gian, Văn bản đọc, Giọng đọc, Tốc độ, Tệp xuất, Dung lượng.
- Các nút hành động: Phát lại âm thanh, Mở tệp trong Windows Explorer, Xóa từng mục.
- Thống kê tổng số bản ghi và tổng dung lượng lưu trữ trên đĩa.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
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
    QApplication,
)

from backend.service import tts_service
from backend.audio_player import audio_player


class PageHistory(QWidget):
    """Trang Lịch Sử Tạo Âm Thanh."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._build_ui()
        self.reload_history()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Thanh tiêu đề & thống kê
        header_card = QFrame()
        header_card.setProperty("class", "CardFrame")
        hc_layout = QHBoxLayout(header_card)
        hc_layout.setContentsMargins(14, 10, 14, 10)

        title = QLabel("📜 LỊCH SỬ TẠO GIỌNG NÓI")
        title.setProperty("class", "CardTitle")
        hc_layout.addWidget(title)

        self.stats_lbl = QLabel("")
        self.stats_lbl.setStyleSheet("color: #22D3EE; font-weight: bold; margin-left: 12px;")
        hc_layout.addWidget(self.stats_lbl)
        hc_layout.addStretch()

        # Ô tìm kiếm
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Tìm kiếm nội dung / giọng...")
        self.search_edit.setMaximumWidth(220)
        self.search_edit.textChanged.connect(self._filter_history)
        hc_layout.addWidget(self.search_edit)

        btn_open_out_dir = QPushButton("📂 Mở thư mục đầu ra")
        btn_open_out_dir.setProperty("class", "SecondaryBtn")
        btn_open_out_dir.setCursor(Qt.PointingHandCursor)
        btn_open_out_dir.clicked.connect(self._open_output_folder)
        hc_layout.addWidget(btn_open_out_dir)

        btn_clear_all = QPushButton("🗑️ Xóa toàn bộ")
        btn_clear_all.setProperty("class", "DangerBtn")
        btn_clear_all.setCursor(Qt.PointingHandCursor)
        btn_clear_all.clicked.connect(self._clear_all_history)
        hc_layout.addWidget(btn_clear_all)

        btn_refresh = QPushButton("🔄")
        btn_refresh.setProperty("class", "SecondaryBtn")
        btn_refresh.setToolTip("Làm mới danh sách")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self.reload_history)
        hc_layout.addWidget(btn_refresh)

        layout.addWidget(header_card)

        # Bảng lịch sử
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Thời Gian", "Văn Bản Đọc", "Giọng Đọc", "Tốc Độ", "Tệp Âm Thanh", "Thao Tác"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

    def reload_history(self):
        self._filter_history()

    def _filter_history(self):
        keyword = self.search_edit.text().strip().lower()
        items = tts_service.get_history()
        stats = tts_service.get_history_stats()

        filtered = []
        for it in items:
            txt = (it.get("text") or "").lower()
            v = (it.get("voice") or "").lower()
            if keyword and (keyword not in txt and keyword not in v):
                continue
            filtered.append(it)

        self.table.setRowCount(len(filtered))
        out_dir = tts_service.default_out_dir

        for row, it in enumerate(filtered):
            item_id = it.get("id")
            created_at = it.get("created_at", "")
            text = it.get("text", "")
            voice = it.get("voice", "")
            speed = it.get("speed", 1.0)
            fname = it.get("wav") or it.get("mp3") or ""
            file_path = out_dir / fname if fname else None

            # Cột 0: Thời gian
            item_time = QTableWidgetItem(created_at)
            item_time.setForeground(QColor("#94A3B8"))
            self.table.setItem(row, 0, item_time)

            # Cột 1: Văn bản
            item_text = QTableWidgetItem(text[:100] + ("..." if len(text) > 100 else ""))
            self.table.setItem(row, 1, item_text)

            # Cột 2: Giọng đọc
            item_voice = QTableWidgetItem(voice)
            item_voice.setForeground(QColor("#22D3EE"))
            self.table.setItem(row, 2, item_voice)

            # Cột 3: Tốc độ
            self.table.setItem(row, 3, QTableWidgetItem(f"{speed}x"))

            # Cột 4: Tệp âm thanh
            self.table.setItem(row, 4, QTableWidgetItem(fname))

            # Cột 5: Thao tác
            action_box = QWidget()
            ab_layout = QHBoxLayout(action_box)
            ab_layout.setContentsMargins(4, 2, 4, 2)
            ab_layout.setSpacing(6)

            if file_path and file_path.exists():
                btn_play = QPushButton("▶ Nghe")
                btn_play.setProperty("class", "SecondaryBtn")
                btn_play.setCursor(Qt.PointingHandCursor)
                btn_play.clicked.connect(lambda _, p=str(file_path): self._play_audio(p))
                ab_layout.addWidget(btn_play)

                btn_loc = QPushButton("📂")
                btn_loc.setProperty("class", "SecondaryBtn")
                btn_loc.setToolTip("Mở vị trí tệp trong Explorer")
                btn_loc.setCursor(Qt.PointingHandCursor)
                btn_loc.clicked.connect(lambda _, p=str(file_path): self._open_file_in_explorer(p))
                ab_layout.addWidget(btn_loc)
            else:
                lbl_missing = QLabel("(Tệp không còn)")
                lbl_missing.setStyleSheet("color: #64748B; font-size: 11px;")
                ab_layout.addWidget(lbl_missing)

            btn_del = QPushButton("🗑️")
            btn_del.setProperty("class", "DangerBtn")
            btn_del.setToolTip("Xóa bản ghi này")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.clicked.connect(lambda _, iid=item_id: self._delete_item(iid))
            ab_layout.addWidget(btn_del)

            self.table.setCellWidget(row, 5, action_box)

        self.stats_lbl.setText(
            f"Tổng: {stats['count']} bản ghi  ·  Dung lượng: {stats['size_mb']} MB"
        )

    def _play_audio(self, fpath: str):
        if audio_player.is_playing():
            audio_player.stop()
        audio_player.play(fpath)

    def _open_file_in_explorer(self, fpath: str):
        tts_service.open_file_in_explorer(fpath)

    def _open_output_folder(self):
        tts_service.open_output_folder()

    def _delete_item(self, item_id: str):
        ans = QMessageBox.question(
            self,
            "Xác nhận xóa",
            "Bạn có chắc muốn xóa bản ghi lịch sử này không?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            tts_service.delete_history_item(item_id)
            self.reload_history()

    def _clear_all_history(self):
        ans = QMessageBox.question(
            self,
            "Xác nhận xóa toàn bộ",
            "CẢNH BÁO: Thao tác này sẽ dọn dẹp toàn bộ lịch sử tạo âm thanh.\n"
            "Bạn có chắc chắn muốn xóa không?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            tts_service.clear_history()
            self.reload_history()
