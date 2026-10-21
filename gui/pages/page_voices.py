"""gui/pages/page_voices.py — TAB 4: QUẢN LÝ GIỌNG ĐỌC (VOICE MANAGEMENT)
========================================================================
Quản lý 25 giọng đọc VieNeu-TTS v3 Turbo chuẩn hóa và các giọng nhân bản cá nhân:
- Bảng danh mục chi tiết: Tên giọng, Giới tính, Vùng miền, Phong cách, Phân loại, Mô tả.
- Bộ lọc nhanh: Tất cả, Giọng Nam, Giọng Nữ, Giọng Nhân Bản.
- Nghe thử mẫu phát âm chuẩn của từng giọng.
- Xóa an toàn giọng nhân bản với hộp thoại xác nhận (không làm ảnh hưởng tệp gốc).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QThread
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
    QComboBox,
)

from backend.service import tts_service
from backend.audio_player import audio_player


class VoicePreviewWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, voice_id: str):
        super().__init__()
        self.voice_id = voice_id

    def run(self):
        try:
            # Câu mẫu nghe thử chuẩn
            sample_text = "Xin chào, đây là giọng đọc thử nghiệm của hệ thống chuyển văn bản thành giọng nói T-TTS."
            res = tts_service.synthesize_text(
                text=sample_text,
                voice_id=self.voice_id,
                speed=1.0,
                out_format="wav",
                filename_prefix=f"preview_{self.voice_id}",
            )
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class PageVoices(QWidget):
    """Trang Quản Lý Giọng Đọc."""

    voices_updated = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.preview_worker: Optional[VoicePreviewWorker] = None
        self._build_ui()
        self.reload_voices()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Thanh tiêu đề & bộ lọc
        header_card = QFrame()
        header_card.setProperty("class", "CardFrame")
        hc_layout = QHBoxLayout(header_card)
        hc_layout.setContentsMargins(14, 10, 14, 10)

        title = QLabel("👥 DANH MỤC 25 GIỌNG CHUẨN & GIỌNG NHÂN BẢN")
        title.setProperty("class", "CardTitle")
        hc_layout.addWidget(title)
        hc_layout.addStretch()

        lbl_filter = QLabel("Lọc theo loại:")
        lbl_filter.setStyleSheet("color: #94A3B8; font-weight: 500;")
        hc_layout.addWidget(lbl_filter)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Tất cả", "Giọng Nam", "Giọng Nữ", "Giọng Nhân Bản (Custom)"])
        self.filter_combo.currentIndexChanged.connect(self._apply_filter)
        hc_layout.addWidget(self.filter_combo)

        btn_refresh = QPushButton("🔄 Làm mới")
        btn_refresh.setProperty("class", "SecondaryBtn")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self.reload_voices)
        hc_layout.addWidget(btn_refresh)

        layout.addWidget(header_card)

        # Bảng danh mục giọng
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Tên Giọng", "Giới Tính", "Vùng Miền", "Phong Cách", "Phân Loại", "Mô Tả", "Thao Tác"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(self.status_lbl)

    def reload_voices(self):
        self._apply_filter()

    def _apply_filter(self):
        filter_type = self.filter_combo.currentText()
        all_voices = tts_service.list_voices()

        filtered = []
        for v in all_voices:
            is_custom = v.get("is_custom", False)
            gender = v.get("gender", "")
            if filter_type == "Giọng Nam" and gender != "Nam":
                continue
            elif filter_type == "Giọng Nữ" and gender != "Nữ":
                continue
            elif filter_type == "Giọng Nhân Bản (Custom)" and not is_custom:
                continue
            filtered.append(v)

        self.table.setRowCount(len(filtered))

        for row, v in enumerate(filtered):
            vid = v["id"]
            name = v["name"]
            gender = v.get("gender", "Khác")
            region = v.get("region", "Toàn quốc")
            style = v.get("style", "Tự nhiên")
            is_custom = v.get("is_custom", False)
            desc = v.get("description", "")

            # Cột 0: Tên giọng
            item_name = QTableWidgetItem(f"🎤 {name}" if is_custom else name)
            item_name.setFont(QFont("Segoe UI", 10, QFont.Bold))
            if is_custom:
                item_name.setForeground(QColor("#22D3EE"))
            self.table.setItem(row, 0, item_name)

            # Cột 1: Giới tính
            self.table.setItem(row, 1, QTableWidgetItem(gender))

            # Cột 2: Vùng miền
            self.table.setItem(row, 2, QTableWidgetItem(region))

            # Cột 3: Phong cách
            self.table.setItem(row, 3, QTableWidgetItem(style))

            # Cột 4: Phân loại
            kind_item = QTableWidgetItem("Nhân bản" if is_custom else "Hệ thống")
            kind_item.setForeground(QColor("#22D3EE" if is_custom else "#94A3B8"))
            self.table.setItem(row, 4, kind_item)

            # Cột 5: Mô tả
            self.table.setItem(row, 5, QTableWidgetItem(desc))

            # Cột 6: Thao tác (Nghe thử / Xóa)
            action_box = QWidget()
            ab_layout = QHBoxLayout(action_box)
            ab_layout.setContentsMargins(4, 2, 4, 2)
            ab_layout.setSpacing(6)

            btn_preview = QPushButton("▶ Nghe")
            btn_preview.setProperty("class", "SecondaryBtn")
            btn_preview.setCursor(Qt.PointingHandCursor)
            btn_preview.clicked.connect(lambda _, vid=name: self._preview_voice(vid))
            ab_layout.addWidget(btn_preview)

            if is_custom:
                btn_del = QPushButton("🗑️")
                btn_del.setProperty("class", "DangerBtn")
                btn_del.setToolTip(f"Xóa giọng nhân bản '{name}'")
                btn_del.setCursor(Qt.PointingHandCursor)
                btn_del.clicked.connect(lambda _, vname=name: self._delete_custom_voice(vname))
                ab_layout.addWidget(btn_del)

            self.table.setCellWidget(row, 6, action_box)

        total_custom = sum(1 for v in all_voices if v.get("is_custom"))
        total_presets = len(all_voices) - total_custom
        self.status_lbl.setText(
            f"Tổng: {len(all_voices)} giọng đọc  (25 giọng chuẩn allowlist VieNeu-TTS v3 Turbo  ·  {total_custom} giọng nhân bản)"
        )

    def _preview_voice(self, voice_name: str):
        lic = tts_service.get_license_info()
        if not lic["is_active"]:
            QMessageBox.critical(self, "Bản quyền bị khóa", lic["status_message"])
            return

        self.status_lbl.setText(f"⏳ Đang tạo âm thanh nghe thử cho giọng: '{voice_name}'...")
        self.preview_worker = VoicePreviewWorker(voice_name)
        self.preview_worker.finished.connect(self._on_preview_finished)
        self.preview_worker.error.connect(lambda e: QMessageBox.critical(self, "Lỗi nghe thử", str(e)))
        self.preview_worker.start()

    def _on_preview_finished(self, res: dict):
        if res.get("success") and res.get("main_file"):
            self.status_lbl.setText(f"▶ Đang phát âm thanh thử nghiệm giọng: '{res.get('voice')}'")
            if audio_player.is_playing():
                audio_player.stop()
            audio_player.play(res["main_file"])
        else:
            QMessageBox.warning(self, "Lỗi nghe thử", res.get("error", "Không thể tạo âm thanh."))

    def _delete_custom_voice(self, voice_name: str):
        ans = QMessageBox.question(
            self,
            "Xác nhận xóa giọng",
            f"Bạn có chắc chắn muốn xóa giọng nhân bản '{voice_name}' không?\n\n"
            "Sau khi xóa, giọng này sẽ không còn xuất hiện trong danh sách lựa chọn.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            res = tts_service.delete_custom_voice(voice_name)
            if res.get("success"):
                QMessageBox.information(self, "Đã xóa", f"Đã xóa thành công giọng nhân bản '{voice_name}'.")
                self.reload_voices()
                self.voices_updated.emit()
            else:
                QMessageBox.critical(self, "Lỗi", f"Không thể xóa: {res.get('error')}")
