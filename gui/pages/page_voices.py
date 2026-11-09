"""gui/pages/page_voices.py — TAB 4: QUẢN LÝ GIỌNG ĐỌC ĐƠN GIẢN & TÔN VINH TÁC GIẢ
================================================================================
Thiết kế lại tối giản, trực quan, không còn bảng số liệu phức tạp:
- Banner tôn vinh tác giả Nguyễn Văn Tiệp kèm Quốc huy / Phù hiệu Quân đội Nhân dân Việt Nam.
- Danh mục giọng dạng danh sách thẻ gọn gàng: Tên giọng, Vùng miền, Phong cách và nút Nghe thử.
- Thao tác xóa an toàn chỉ dành cho các giọng do người dùng tự nhân bản.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QFrame,
    QScrollArea,
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
            sample_text = "Xin chào, đây là giọng đọc chuẩn của hệ thống trợ lý chuyển văn bản thành giọng nói T-TTS."
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


class SimpleVoiceRowWidget(QFrame):
    """Một dòng hiển thị giọng đọc đơn giản, tinh gọn."""
    preview_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, voice_info: dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.voice_id = voice_info.get("id", "")
        self.voice_name = voice_info.get("name", self.voice_id)
        self.gender = voice_info.get("gender", "Nam")
        self.region = voice_info.get("region", "Miền Bắc")
        self.voice_style = voice_info.get("style", "Tự nhiên")
        self.desc = voice_info.get("description", "")
        self.is_custom = voice_info.get("is_custom", False)

        self.setProperty("class", "CardFrame")
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        # Icon giới tính
        icon_str = "🎤" if self.is_custom else ("👩" if "Nữ" in self.gender else "👨")
        lbl_icon = QLabel(icon_str)
        lbl_icon.setStyleSheet("font-size: 20px;")
        layout.addWidget(lbl_icon)

        # Thông tin Tên và Phong cách
        info_box = QVBoxLayout()
        info_box.setSpacing(2)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)

        lbl_name = QLabel(self.voice_name)
        lbl_name.setStyleSheet("font-weight: bold; font-size: 14px; color: #FFD700;")
        name_row.addWidget(lbl_name)

        lbl_badge = QLabel(f"[{self.gender} · {self.region}]")
        lbl_badge.setStyleSheet("color: #EAB308; font-size: 11px; font-weight: 600;")
        name_row.addWidget(lbl_badge)

        if self.is_custom:
            lbl_custom = QLabel("Giọng Nhân Bản")
            lbl_custom.setStyleSheet(
                "background-color: rgba(220, 38, 38, 0.2); color: #F87171; "
                "border: 1px solid #DC2626; border-radius: 4px; padding: 1px 6px; font-size: 10px;"
            )
            name_row.addWidget(lbl_custom)

        name_row.addStretch()
        info_box.addLayout(name_row)

        lbl_desc = QLabel(self.desc or f"Phong cách: {self.voice_style}")
        lbl_desc.setStyleSheet("color: #9EB39B; font-size: 12px;")
        info_box.addWidget(lbl_desc)

        layout.addLayout(info_box, 1)

        # Nút Nghe thử
        btn_preview = QPushButton("▶ Nghe thử")
        btn_preview.setProperty("class", "SecondaryBtn")
        btn_preview.clicked.connect(lambda: self.preview_requested.emit(self.voice_id))
        layout.addWidget(btn_preview)

        # Nút Xóa (chỉ hiện khi là giọng custom)
        if self.is_custom:
            btn_delete = QPushButton("🗑 Xóa")
            btn_delete.setStyleSheet(
                "background-color: rgba(220, 38, 38, 0.15); color: #F87171; "
                "border: 1px solid #DC2626; border-radius: 6px; padding: 8px 12px; font-weight: bold;"
            )
            btn_delete.clicked.connect(lambda: self.delete_requested.emit(self.voice_id))
            layout.addWidget(btn_delete)


class PageVoices(QWidget):
    """Trang Quản Lý Giọng Đọc Đơn Giản & Nổi Bật Tác Giả."""

    voices_updated = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.preview_worker: Optional[VoicePreviewWorker] = None
        self.all_voices: List[dict] = []
        self.current_filter = "all"
        self._build_ui()
        self.reload_voices()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        # =========================================================================
        # BANNER TÔN VINH TÁC GIẢ & LOGO QUÂN ĐỘI NHÂN DÂN VIỆT NAM
        # =========================================================================
        hero_card = QFrame()
        hero_card.setObjectName("HeroCardVoices")
        hero_card.setProperty("class", "CardFrame")
        hero_card.setStyleSheet(
            "#HeroCardVoices { background-color: #244628; border: 1px solid #3F7545; border-radius: 8px; }"
        )
        hero_layout = QHBoxLayout(hero_card)
        hero_layout.setContentsMargins(16, 12, 16, 12)
        hero_layout.setSpacing(16)

        # Logo Quân đội Nhân dân Việt Nam
        lbl_logo = QLabel()
        logo_path = Path(__file__).resolve().parent.parent / "assets" / "logo_quan_doi.png"
        if not logo_path.exists():
            logo_path = Path.cwd() / "gui" / "assets" / "logo_quan_doi.png"
        if logo_path.exists():
            pm = QPixmap(str(logo_path)).scaled(58, 76, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_logo.setPixmap(pm)
        else:
            lbl_logo.setText("⭐")
            lbl_logo.setStyleSheet("font-size: 36px; color: #FFD700;")
        hero_layout.addWidget(lbl_logo)

        # Chữ tôn vinh tác giả
        author_text_layout = QVBoxLayout()
        author_text_layout.setSpacing(3)

        lbl_header = QLabel("HỆ THỐNG QUẢN LÝ THƯ VIỆN GIỌNG ĐỌC QUÂN ĐỘI")
        lbl_header.setStyleSheet("color: #FFD700; font-weight: 800; font-size: 15px; letter-spacing: 0.5px;")
        author_text_layout.addWidget(lbl_header)

        lbl_author = QLabel("TÁC GIẢ: NGUYỄN VĂN TIỆP")
        lbl_author.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: 800; letter-spacing: 0.5px;")
        author_text_layout.addWidget(lbl_author)

        lbl_desc = QLabel(
            "Tập hợp 25 giọng đọc chuẩn hóa VieNeu-TTS v3 Turbo cùng các giọng nhân bản cá nhân chất lượng cao 48kHz."
        )
        lbl_desc.setStyleSheet("color: #A2BCA0; font-size: 11px;")
        author_text_layout.addWidget(lbl_desc)

        hero_layout.addLayout(author_text_layout, 1)

        layout.addWidget(hero_card)

        # =========================================================================
        # THANH BỘ LỌC ĐƠN GIẢN
        # =========================================================================
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        lbl_f = QLabel("Lọc giọng:")
        lbl_f.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 12px;")
        filter_bar.addWidget(lbl_f)

        self.btn_f_all = QPushButton("Tất cả")
        self.btn_f_all.setProperty("class", "SecondaryBtn")
        self.btn_f_all.clicked.connect(lambda: self._set_filter("all"))
        filter_bar.addWidget(self.btn_f_all)

        self.btn_f_female = QPushButton("👩 Giọng Nữ")
        self.btn_f_female.setProperty("class", "SecondaryBtn")
        self.btn_f_female.clicked.connect(lambda: self._set_filter("Nữ"))
        filter_bar.addWidget(self.btn_f_female)

        self.btn_f_male = QPushButton("👨 Giọng Nam")
        self.btn_f_male.setProperty("class", "SecondaryBtn")
        self.btn_f_male.clicked.connect(lambda: self._set_filter("Nam"))
        filter_bar.addWidget(self.btn_f_male)

        self.btn_f_custom = QPushButton("🎤 Giọng Nhân Bản")
        self.btn_f_custom.setProperty("class", "SecondaryBtn")
        self.btn_f_custom.clicked.connect(lambda: self._set_filter("custom"))
        filter_bar.addWidget(self.btn_f_custom)

        filter_bar.addStretch()

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 Tìm tên giọng...")
        self.txt_search.setMaximumWidth(160)
        self.txt_search.textChanged.connect(self._render_rows)
        filter_bar.addWidget(self.txt_search)

        btn_reload = QPushButton("🔄 Tải lại")
        btn_reload.setProperty("class", "SecondaryBtn")
        btn_reload.clicked.connect(self.reload_voices)
        filter_bar.addWidget(btn_reload)

        layout.addLayout(filter_bar)

        # Trạng thái nghe thử
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-size: 12px; font-weight: 500;")
        self.lbl_status.setVisible(False)
        layout.addWidget(self.lbl_status)

        # =========================================================================
        # DANH SÁCH GIỌNG DẠNG THẺ DỄ NHÌN
        # =========================================================================
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)

        scroll.setWidget(self.rows_container)
        layout.addWidget(scroll, 1)

    def _set_filter(self, filter_type: str):
        self.current_filter = filter_type
        self._render_rows()

    def reload_voices(self):
        try:
            self.all_voices = tts_service.list_voices()
        except Exception:
            self.all_voices = []
        self._render_rows()

    def _render_rows(self):
        # Dọn sạch các widget cũ
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        query = self.txt_search.text().strip().lower()

        count = 0
        for v in self.all_voices:
            gender = v.get("gender", "Nam")
            is_custom = v.get("is_custom", False)

            if self.current_filter == "Nữ" and "Nữ" not in gender:
                continue
            elif self.current_filter == "Nam" and ("Nam" not in gender or is_custom):
                continue
            elif self.current_filter == "custom" and not is_custom:
                continue

            name = v.get("name", "")
            desc = v.get("description", "")
            combined = f"{name} {desc} {gender} {v.get('region', '')}".lower()
            if query and query not in combined:
                continue

            row_widget = SimpleVoiceRowWidget(v)
            row_widget.preview_requested.connect(self._preview_voice)
            row_widget.delete_requested.connect(self._delete_custom_voice)
            self.rows_layout.addWidget(row_widget)
            count += 1

        if count == 0:
            lbl_empty = QLabel("Không tìm thấy giọng đọc phù hợp.")
            lbl_empty.setStyleSheet("color: #9EB39B; font-style: italic; padding: 20px;")
            lbl_empty.setAlignment(Qt.AlignCenter)
            self.rows_layout.addWidget(lbl_empty)

        self.rows_layout.addStretch()

    def _preview_voice(self, voice_id: str):
        if self.preview_worker and self.preview_worker.isRunning():
            return

        self.lbl_status.setVisible(True)
        self.lbl_status.setStyleSheet("color: #EAB308;")
        self.lbl_status.setText(f"⏳ Đang phát mẫu giọng: {voice_id}...")

        self.preview_worker = VoicePreviewWorker(voice_id)
        self.preview_worker.finished.connect(self._on_preview_finished)
        self.preview_worker.error.connect(self._on_preview_error)
        self.preview_worker.start()

    def _on_preview_finished(self, res: dict):
        self.lbl_status.setStyleSheet("color: #4ADE80;")
        self.lbl_status.setText("✅ Đã phát giọng thử nghiệm.")
        fp = res.get("file_path", "")
        if fp and Path(fp).exists():
            audio_player.play(fp)

    def _on_preview_error(self, err: str):
        self.lbl_status.setStyleSheet("color: #F87171;")
        self.lbl_status.setText(f"❌ Lỗi nghe thử: {err}")

    def _delete_custom_voice(self, voice_id: str):
        reply = QMessageBox.question(
            self,
            "Xác Nhận Xóa Giọng",
            f"Đồng chí có chắc chắn muốn xóa giọng nhân bản '{voice_id}'?\nThao tác này không thể hoàn tác.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            success = tts_service.delete_custom_voice(voice_id)
            if success:
                QMessageBox.information(self, "Đã Xóa", f"Đã xóa thành công giọng nhân bản '{voice_id}'.")
                self.reload_voices()
                self.voices_updated.emit()
            else:
                QMessageBox.critical(self, "Lỗi", f"Không thể xóa giọng '{voice_id}'.")
