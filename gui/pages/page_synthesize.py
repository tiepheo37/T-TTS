"""gui/pages/page_synthesize.py — TAB 1: TẠO GIỌNG NÓI TIẾNG VIỆT (VOICE CARDS CHUẨN)
=================================================================================
Màn hình chính của T-TTS:
- Danh sách chọn giọng dạng THẺ (Cards) trực quan, chia theo Nữ/Nam/Nhân bản giống bản gốc.
- Thanh chèn nhanh thẻ cảm xúc & mốc nghỉ: [cười], [hắng giọng], [thở dài], [nghỉ 500ms], [nghỉ 2s].
- Ô soạn thảo văn bản lớn, đếm ký tự, dán nhanh, xóa nội dung.
- Điều chỉnh tốc độ đọc (0.75x - 1.50x), định dạng xuất WAV/MP3.
- Nút bấm tạo giọng nổi bật, chạy ngầm bằng QThread không gây treo giao diện.
- Trình phát nghe thử native trực tiếp sau khi hoàn thành.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional, List, Dict

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QMimeData, QUrl
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QComboBox,
    QSlider,
    QFileDialog,
    QMessageBox,
    QFrame,
    QScrollArea,
    QProgressBar,
)

from backend.service import tts_service
from backend.audio_player import audio_player
from gui.dialog_import_document import DocumentImportDialog


class SynthesisWorker(QThread):
    """Tiểu trình chạy ngầm xử lý tổng hợp giọng nói."""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        text: str,
        voice_id: str,
        speed: float,
        out_format: str,
        filename_prefix: str,
        custom_out_dir: Optional[Path] = None,
    ):
        super().__init__()
        self.text = text
        self.voice_id = voice_id
        self.speed = speed
        self.out_format = out_format
        self.filename_prefix = filename_prefix
        self.custom_out_dir = custom_out_dir

    def run(self):
        try:
            res = tts_service.synthesize_text(
                text=self.text,
                voice_id=self.voice_id,
                speed=self.speed,
                out_format=self.out_format,
                filename_prefix=self.filename_prefix,
                custom_out_dir=self.custom_out_dir,
            )
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class VoicePreviewWorker(QThread):
    """Tiểu trình phát thử âm thanh mẫu của giọng được chọn."""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, voice_id: str):
        super().__init__()
        self.voice_id = voice_id

    def run(self):
        try:
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


class VoiceCardWidget(QFrame):
    """Thẻ hiển thị thông tin từng giọng đọc trực quan (như bản cũ)."""
    clicked = Signal(str)
    preview_requested = Signal(str)

    def __init__(self, voice_info: dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.voice_id = voice_info.get("id", "")
        self.voice_name = voice_info.get("name", self.voice_id)
        self.gender = voice_info.get("gender", "Nam")
        self.region = voice_info.get("region", "Miền Bắc")
        self.voice_style = voice_info.get("style", "Tự nhiên")
        self.desc = voice_info.get("description", "")
        self.is_custom = voice_info.get("is_custom", False)
        self.is_selected = False

        self.setProperty("class", "VoiceCard")
        self.setCursor(Qt.PointingHandCursor)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Hàng 1: Icon, Tên giọng, Badge vùng miền, Checkmark
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        icon_char = "🎤" if self.is_custom else ("👩" if "Nữ" in self.gender else "👨")
        self.lbl_icon = QLabel(icon_char)
        self.lbl_icon.setStyleSheet("font-size: 15px;")
        top_row.addWidget(self.lbl_icon)

        self.lbl_name = QLabel(self.voice_name)
        self.lbl_name.setStyleSheet("font-weight: bold; font-size: 13px;")
        top_row.addWidget(self.lbl_name)

        top_row.addStretch()

        self.lbl_region = QLabel(self.region.replace("Miền ", ""))
        self.lbl_region.setStyleSheet(
            "background-color: rgba(234, 179, 8, 0.15); color: #EAB308; "
            "border: 1px solid rgba(234, 179, 8, 0.3); border-radius: 4px; "
            "padding: 1px 6px; font-size: 11px; font-weight: 600;"
        )
        top_row.addWidget(self.lbl_region)

        self.lbl_check = QLabel("✓")
        self.lbl_check.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 14px;")
        self.lbl_check.setVisible(False)
        top_row.addWidget(self.lbl_check)

        layout.addLayout(top_row)

        # Hàng 2: Mô tả phong cách & Nút nghe thử
        bot_row = QHBoxLayout()
        bot_row.setSpacing(4)

        summary_text = f"{self.gender} · {self.voice_style}"
        self.lbl_desc = QLabel(summary_text)
        self.lbl_desc.setStyleSheet("color: #9EB39B; font-size: 11px;")
        bot_row.addWidget(self.lbl_desc, 1)

        self.btn_preview = QPushButton("▶ Thử")
        self.btn_preview.setFixedSize(50, 22)
        self.btn_preview.setStyleSheet(
            "background-color: transparent; border: 1px solid #365739; "
            "border-radius: 4px; font-size: 11px; padding: 0px;"
        )
        self.btn_preview.setToolTip(f"Nghe thử giọng mẫu: {self.voice_name}")
        self.btn_preview.clicked.connect(self._on_preview_clicked)
        bot_row.addWidget(self.btn_preview)

        layout.addLayout(bot_row)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.voice_id)
        super().mousePressEvent(event)

    def _on_preview_clicked(self):
        self.preview_requested.emit(self.voice_id)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.lbl_check.setVisible(selected)
        if selected:
            self.lbl_name.setStyleSheet("font-weight: bold; font-size: 13px; color: #FFD700;")
        else:
            self.lbl_name.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.style().unpolish(self)
        self.style().polish(self)


class PageSynthesize(QWidget):
    """Trang Tạo Giọng Nói Chính (Giao diện Thẻ chuẩn Quân Đội)."""

    audio_generated = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.synthesis_worker: Optional[SynthesisWorker] = None
        self.preview_worker: Optional[VoicePreviewWorker] = None
        self.current_result: Optional[dict] = None
        self.custom_output_dir: Optional[Path] = None
        self.selected_voice_id = "Hải Đăng"
        self.all_voices: List[dict] = []
        self.card_widgets: Dict[str, VoiceCardWidget] = {}
        self.current_filter = "all"

        self._build_ui()
        self.refresh_voices()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 14)
        main_layout.setSpacing(12)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # =========================================================================
        # KHU VỰC 1: BẢNG CHỌN GIỌNG ĐỌC DẠNG CARD LIST (GIỐNG BẢN CŨ)
        # =========================================================================
        voice_card_frame = QFrame()
        voice_card_frame.setProperty("class", "CardFrame")
        vcf_layout = QVBoxLayout(voice_card_frame)
        vcf_layout.setContentsMargins(14, 12, 14, 12)
        vcf_layout.setSpacing(8)

        # Tiêu đề & Bộ lọc nhanh
        header_filter_row = QHBoxLayout()
        header_filter_row.setSpacing(8)

        lbl_vcf_title = QLabel("🎙️ CHỌN GIỌNG ĐỌC (25 GIỌNG VIENEU PRESET & GIỌNG NHÂN BẢN)")
        lbl_vcf_title.setProperty("class", "CardTitle")
        header_filter_row.addWidget(lbl_vcf_title)

        header_filter_row.addStretch()

        self.btn_filter_all = QPushButton("Tất cả")
        self.btn_filter_all.setProperty("class", "SecondaryBtn")
        self.btn_filter_all.clicked.connect(lambda: self._set_gender_filter("all"))
        header_filter_row.addWidget(self.btn_filter_all)

        self.btn_filter_female = QPushButton("👩 Nữ")
        self.btn_filter_female.setProperty("class", "SecondaryBtn")
        self.btn_filter_female.clicked.connect(lambda: self._set_gender_filter("Nữ"))
        header_filter_row.addWidget(self.btn_filter_female)

        self.btn_filter_male = QPushButton("👨 Nam")
        self.btn_filter_male.setProperty("class", "SecondaryBtn")
        self.btn_filter_male.clicked.connect(lambda: self._set_gender_filter("Nam"))
        header_filter_row.addWidget(self.btn_filter_male)

        self.btn_filter_custom = QPushButton("🎤 Nhân bản")
        self.btn_filter_custom.setProperty("class", "SecondaryBtn")
        self.btn_filter_custom.clicked.connect(lambda: self._set_gender_filter("custom"))
        header_filter_row.addWidget(self.btn_filter_custom)

        self.txt_search_voice = QLineEdit()
        self.txt_search_voice.setPlaceholderText("🔍 Tìm giọng...")
        self.txt_search_voice.setMaximumWidth(130)
        self.txt_search_voice.textChanged.connect(self._apply_voice_filter)
        header_filter_row.addWidget(self.txt_search_voice)

        vcf_layout.addLayout(header_filter_row)

        # Scroll Area chứa danh sách các thẻ giọng đọc
        self.voice_scroll = QScrollArea()
        self.voice_scroll.setWidgetResizable(True)
        self.voice_scroll.setMinimumHeight(220)
        self.voice_scroll.setMaximumHeight(270)
        self.voice_scroll.setFrameShape(QFrame.NoFrame)

        self.cards_container = QWidget()
        self.cards_grid = QGridLayout(self.cards_container)
        self.cards_grid.setContentsMargins(2, 2, 2, 2)
        self.cards_grid.setSpacing(8)

        self.voice_scroll.setWidget(self.cards_container)
        vcf_layout.addWidget(self.voice_scroll)

        layout.addWidget(voice_card_frame)

        # =========================================================================
        # KHU VỰC 2: Ô NHẬP VĂN BẢN VÀ CÁC THẺ CHÈN NHANH CẢM XÚC / NGHỈ
        # =========================================================================
        text_card = QFrame()
        text_card.setProperty("class", "CardFrame")
        tc_layout = QVBoxLayout(text_card)
        tc_layout.setContentsMargins(14, 12, 14, 12)
        tc_layout.setSpacing(8)

        tc_title_row = QHBoxLayout()
        tc_title = QLabel("📝 NỘI DUNG VĂN BẢN CẦN CHUYỂN THÀNH GIỌNG NÓI")
        tc_title.setProperty("class", "CardTitle")
        tc_title_row.addWidget(tc_title)
        tc_title_row.addStretch()

        self.lbl_char_count = QLabel("0 ký tự | 0 từ")
        self.lbl_char_count.setStyleSheet("color: #9EB39B; font-size: 11px;")
        tc_title_row.addWidget(self.lbl_char_count)

        btn_import_doc = QPushButton("📂 Nhập tài liệu")
        btn_import_doc.setProperty("class", "SecondaryBtn")
        btn_import_doc.setToolTip("Nhập văn bản từ tài liệu Word (.docx), PDF, hoặc Text (.txt)")
        btn_import_doc.clicked.connect(self._import_document)
        tc_title_row.addWidget(btn_import_doc)

        btn_paste = QPushButton("📋 Dán từ Clipboard")
        btn_paste.setProperty("class", "SecondaryBtn")
        btn_paste.setToolTip("Dán nội dung từ bộ nhớ tạm (Clipboard)")
        btn_paste.clicked.connect(self._paste_text)
        tc_title_row.addWidget(btn_paste)

        btn_clear = QPushButton("🗑 Xóa")
        btn_clear.setProperty("class", "SecondaryBtn")
        btn_clear.clicked.connect(self._clear_text)
        tc_title_row.addWidget(btn_clear)

        tc_layout.addLayout(tc_title_row)

        # Thanh chèn nhanh thẻ cảm xúc & mốc nghỉ (Tag Pills Bar giống bản gốc)
        tags_bar = QHBoxLayout()
        tags_bar.setSpacing(6)

        lbl_tags = QLabel("Chèn nhanh:")
        lbl_tags.setStyleSheet("color: #EAB308; font-weight: bold; font-size: 11px;")
        tags_bar.addWidget(lbl_tags)

        tag_list = [
            ("[cười]", "😊 Cười"),
            ("[hắng giọng]", "🗣️ Hắng giọng"),
            ("[thở dài]", "😮💨 Thở dài"),
            ("[nghỉ 500ms]", "⏸ Nghỉ 500ms"),
            ("[nghỉ 2s]", "⏸ Nghỉ 2s"),
        ]
        for tag_code, tag_label in tag_list:
            btn_tag = QPushButton(tag_label)
            btn_tag.setProperty("class", "TagPill")
            btn_tag.setCursor(Qt.PointingHandCursor)
            btn_tag.clicked.connect(lambda checked=False, t=tag_code: self._insert_tag(t))
            tags_bar.addWidget(btn_tag)

        tags_bar.addStretch()
        tc_layout.addLayout(tags_bar)

        # Ô soạn thảo văn bản chính
        self.txt_input = QTextEdit()
        self.txt_input.setPlaceholderText(
            "Nhập nội dung văn bản tiếng Việt tại đây...\n"
            "Mẹo: Bấm các nút icon ở trên để chèn nhanh mốc [cười], [nghỉ 500ms], [nghỉ 2s] vào vị trí con trỏ."
        )
        self.txt_input.setMinimumHeight(130)
        self.txt_input.textChanged.connect(self._on_text_changed)
        tc_layout.addWidget(self.txt_input)

        layout.addWidget(text_card)

        # =========================================================================
        # KHU VỰC 3: THIẾT LẬP TỐC ĐỘ, ĐỊNH DẠNG & THƯ MỤC LƯU
        # =========================================================================
        settings_card = QFrame()
        settings_card.setProperty("class", "CardFrame")
        sc_layout = QHBoxLayout(settings_card)
        sc_layout.setContentsMargins(14, 12, 14, 12)
        sc_layout.setSpacing(16)

        # Tốc độ đọc
        speed_box = QVBoxLayout()
        speed_box.setSpacing(4)
        self.lbl_speed = QLabel("Tốc độ đọc: 1.00x")
        self.lbl_speed.setStyleSheet("font-weight: 600; color: #E2ECE1;")
        speed_box.addWidget(self.lbl_speed)

        self.slider_speed = QSlider(Qt.Horizontal)
        self.slider_speed.setRange(75, 150)
        self.slider_speed.setValue(100)
        self.slider_speed.valueChanged.connect(self._on_speed_changed)
        speed_box.addWidget(self.slider_speed)
        sc_layout.addLayout(speed_box, 1)

        # Định dạng xuất
        fmt_box = QVBoxLayout()
        fmt_box.setSpacing(4)
        lbl_fmt = QLabel("Định dạng xuất:")
        lbl_fmt.setStyleSheet("font-weight: 600; color: #E2ECE1;")
        fmt_box.addWidget(lbl_fmt)

        self.combo_fmt = QComboBox()
        self.combo_fmt.addItem("WAV 48kHz 16-bit PCM (Chất lượng gốc)", "wav")
        self.combo_fmt.addItem("MP3 192kbps (Dung lượng nhẹ)", "mp3")
        fmt_box.addWidget(self.combo_fmt)
        sc_layout.addLayout(fmt_box, 1)

        # Nút chọn thư mục lưu
        dir_box = QVBoxLayout()
        dir_box.setSpacing(4)
        lbl_dir = QLabel("Thư mục lưu file:")
        lbl_dir.setStyleSheet("font-weight: 600; color: #E2ECE1;")
        dir_box.addWidget(lbl_dir)

        dir_btn_row = QHBoxLayout()
        dir_btn_row.setSpacing(6)

        btn_select_dir = QPushButton("📁 Chọn thư mục...")
        btn_select_dir.setProperty("class", "SecondaryBtn")
        btn_select_dir.clicked.connect(self._select_output_dir)
        dir_btn_row.addWidget(btn_select_dir)

        btn_quick_open_dir = QPushButton("📂 Mở")
        btn_quick_open_dir.setProperty("class", "SecondaryBtn")
        btn_quick_open_dir.setToolTip("Mở thư mục lưu âm thanh hiện tại")
        btn_quick_open_dir.clicked.connect(self._open_output_folder)
        dir_btn_row.addWidget(btn_quick_open_dir)
        dir_box.addLayout(dir_btn_row)

        self.lbl_current_out_dir = QLabel(str(tts_service.default_out_dir))
        self.lbl_current_out_dir.setStyleSheet("color: #94A3B8; font-size: 11px;")
        self.lbl_current_out_dir.setWordWrap(True)
        dir_box.addWidget(self.lbl_current_out_dir)

        sc_layout.addLayout(dir_box, 1)

        layout.addWidget(settings_card)

        # =========================================================================
        # NÚT TẠO GIỌNG NÓI & THANH TIẾN TRÌNH
        # =========================================================================
        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)

        self.btn_generate = QPushButton("▶ TẠO GIỌNG NÓI")
        self.btn_generate.setObjectName("BtnGenerate")
        self.btn_generate.setProperty("class", "PrimaryBtn")
        self.btn_generate.setCursor(Qt.PointingHandCursor)
        self.btn_generate.setMinimumHeight(44)
        self.btn_generate.clicked.connect(self.start_synthesis)
        action_layout.addWidget(self.btn_generate, 2)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background-color: #111F13; border: 1px solid #2F4D32; border-radius: 4px; }"
            "QProgressBar::chunk { background-color: #EAB308; }"
        )

        layout.addLayout(action_layout)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-size: 12px; font-weight: 500;")
        self.lbl_status.setVisible(False)
        layout.addWidget(self.lbl_status)

        # =========================================================================
        # KHU VỰC 4: TRÌNH PHÁT NATIVE KẾT QUẢ ÂM THANH
        # =========================================================================
        self.player_card = QFrame()
        self.player_card.setProperty("class", "CardFrame")
        self.player_card.setVisible(False)
        pc_layout = QVBoxLayout(self.player_card)
        pc_layout.setContentsMargins(14, 12, 14, 12)
        pc_layout.setSpacing(8)

        pc_title = QLabel("🎵 KẾT QUẢ PHÁT ÂM THANH")
        pc_title.setProperty("class", "CardTitle")
        pc_layout.addWidget(pc_title)

        self.lbl_result_info = QLabel("")
        self.lbl_result_info.setStyleSheet("color: #E2ECE1; font-size: 12px; line-height: 1.5;")
        self.lbl_result_info.setTextFormat(Qt.RichText)
        self.lbl_result_info.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.lbl_result_info.linkActivated.connect(self._on_result_link_clicked)
        pc_layout.addWidget(self.lbl_result_info)

        player_btn_row = QHBoxLayout()
        player_btn_row.setSpacing(8)

        self.btn_play_pause = QPushButton("▶ Phát")
        self.btn_play_pause.setProperty("class", "GoldBtn")
        self.btn_play_pause.clicked.connect(self._toggle_playback)
        player_btn_row.addWidget(self.btn_play_pause)

        self.btn_stop = QPushButton("⏹ Dừng")
        self.btn_stop.setProperty("class", "SecondaryBtn")
        self.btn_stop.clicked.connect(self._stop_playback)
        player_btn_row.addWidget(self.btn_stop)

        btn_open_file = QPushButton("📂 Xem file")
        btn_open_file.setToolTip("Mở thư mục và chọn đúng file này trong Windows Explorer")
        btn_open_file.setProperty("class", "SecondaryBtn")
        btn_open_file.clicked.connect(self._open_file_in_explorer)
        player_btn_row.addWidget(btn_open_file)

        btn_open_folder = QPushButton("📁 Mở thư mục")
        btn_open_folder.setProperty("class", "SecondaryBtn")
        btn_open_folder.clicked.connect(self._open_output_folder)
        player_btn_row.addWidget(btn_open_folder)

        btn_copy_file = QPushButton("📋 Sao chép file")
        btn_copy_file.setToolTip("Sao chép file vào Clipboard để dán (Ctrl+V) vào thư mục khác hoặc gửi qua Zalo")
        btn_copy_file.setProperty("class", "SecondaryBtn")
        btn_copy_file.clicked.connect(self._copy_file_to_clipboard)
        player_btn_row.addWidget(btn_copy_file)

        btn_save_as = QPushButton("💾 Lưu thành...")
        btn_save_as.setToolTip("Lưu file ra vị trí khác (Desktop, USB, v.v.)")
        btn_save_as.setProperty("class", "SecondaryBtn")
        btn_save_as.clicked.connect(self._save_as_file)
        player_btn_row.addWidget(btn_save_as)

        player_btn_row.addStretch()
        pc_layout.addLayout(player_btn_row)

        layout.addWidget(self.player_card)

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

    def _insert_tag(self, tag: str):
        """Chèn thẻ cảm xúc / mốc nghỉ vào đúng vị trí con trỏ."""
        cursor = self.txt_input.textCursor()
        cursor.insertText(tag + " ")
        self.txt_input.setFocus()

    def _paste_text(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            self.txt_input.insertPlainText(text)

    def _clear_text(self):
        self.txt_input.clear()

    def _import_document(self):
        """Mở hộp thoại trích xuất nội dung từ tài liệu (DOCX, PDF, TXT)."""
        dlg = DocumentImportDialog(self)
        if dlg.exec() == DocumentImportDialog.Accepted:
            new_text = getattr(dlg, "final_text", "")
            action = getattr(dlg, "selected_action", "replace")
            meta = getattr(dlg, "document_meta", {})
            if not new_text:
                return

            if action == "append":
                curr = self.txt_input.toPlainText()
                if curr.strip():
                    self.txt_input.setPlainText(curr.rstrip() + "\n\n" + new_text)
                else:
                    self.txt_input.setPlainText(new_text)
            else:  # "replace" or "new_project"
                self.txt_input.setPlainText(new_text)

            fmt = meta.get("format", "").upper()
            chars = len(new_text)
            words = len(new_text.split())
            self.lbl_status.setVisible(True)
            self.lbl_status.setStyleSheet("color: #4ADE80;")
            self.lbl_status.setText(f"✅ Đã nhập tài liệu {fmt} ({words:,} từ | {chars:,} ký tự)")

    def _on_text_changed(self):
        text = self.txt_input.toPlainText()
        char_count = len(text)
        word_count = len(text.split())
        self.lbl_char_count.setText(f"{char_count:,} ký tự | {word_count:,} từ")

    def _on_speed_changed(self, val: int):
        speed = val / 100.0
        self.lbl_speed.setText(f"Tốc độ đọc: {speed:.2f}x")

    def _select_output_dir(self):
        curr = str(self.custom_output_dir or tts_service.default_out_dir)
        chosen = QFileDialog.getExistingDirectory(self, "Chọn Thư Mục Lưu Âm Thanh", curr)
        if chosen:
            self.custom_output_dir = Path(chosen)
            tts_service.set_default_out_dir(chosen)
            if hasattr(self, "lbl_current_out_dir"):
                self.lbl_current_out_dir.setText(str(chosen))
            QMessageBox.information(self, "Đã Đổi Thư Mục", f"Các file âm thanh tiếp theo sẽ được lưu vào:\n{chosen}")

    def refresh_voices(self):
        """Nạp danh sách 25 giọng chuẩn + giọng tùy biến vào danh sách Card."""
        try:
            self.all_voices = tts_service.list_voices()
        except Exception:
            self.all_voices = []

        # Xóa các widget cũ
        for w in self.card_widgets.values():
            w.deleteLater()
        self.card_widgets.clear()

        # Tạo mới các card
        for v in self.all_voices:
            vid = v.get("id", "")
            card = VoiceCardWidget(v)
            card.clicked.connect(self._on_card_selected)
            card.preview_requested.connect(self._preview_voice)
            self.card_widgets[vid] = card

        # Đặt lại giọng mặc định nếu có
        if self.selected_voice_id not in self.card_widgets and self.all_voices:
            self.selected_voice_id = self.all_voices[0]["id"]

        self._apply_voice_filter()

    def _set_gender_filter(self, gender: str):
        self.current_filter = gender
        self._apply_voice_filter()

    def _apply_voice_filter(self):
        search_query = self.txt_search_voice.text().strip().lower()

        # Xóa layout grid
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        visible_cards = []
        for v in self.all_voices:
            vid = v.get("id", "")
            card = self.card_widgets.get(vid)
            if not card:
                continue

            # Kiểm tra bộ lọc giới tính / loại
            if self.current_filter == "Nữ" and "Nữ" not in card.gender:
                card.setVisible(False)
                continue
            elif self.current_filter == "Nam" and ("Nam" not in card.gender or card.is_custom):
                card.setVisible(False)
                continue
            elif self.current_filter == "custom" and not card.is_custom:
                card.setVisible(False)
                continue

            # Kiểm tra tìm kiếm
            if search_query:
                combined_text = f"{card.voice_name} {card.region} {card.voice_style} {card.desc}".lower()
                if search_query not in combined_text:
                    card.setVisible(False)
                    continue

            card.setVisible(True)
            card.set_selected(vid == self.selected_voice_id)
            visible_cards.append(card)

        # Sắp xếp theo lưới 3 cột hiển thị nhiều giọng đồng thời
        cols = 3
        for idx, card in enumerate(visible_cards):
            r = idx // cols
            c = idx % cols
            self.cards_grid.addWidget(card, r, c)

    def _on_card_selected(self, voice_id: str):
        self.selected_voice_id = voice_id
        for vid, card in self.card_widgets.items():
            card.set_selected(vid == voice_id)

    def _preview_voice(self, voice_id: str):
        if self.preview_worker and self.preview_worker.isRunning():
            return
        self.lbl_status.setVisible(True)
        self.lbl_status.setStyleSheet("color: #EAB308;")
        self.lbl_status.setText(f"⏳ Đang nạp và phát thử giọng: {voice_id}...")

        self.preview_worker = VoicePreviewWorker(voice_id)
        self.preview_worker.finished.connect(self._on_preview_finished)
        self.preview_worker.error.connect(self._on_preview_error)
        self.preview_worker.start()

    def _on_preview_finished(self, res: dict):
        self.lbl_status.setStyleSheet("color: #4ADE80;")
        self.lbl_status.setText("✅ Đã phát giọng thử nghiệm.")
        filepath = res.get("file_path", "")
        if filepath and Path(filepath).exists():
            audio_player.play(filepath)

    def _on_preview_error(self, err: str):
        self.lbl_status.setStyleSheet("color: #F87171;")
        self.lbl_status.setText(f"❌ Lỗi nghe thử giọng: {err}")

    def start_synthesis(self):
        text = self.txt_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Chưa Nhập Văn Bản", "Vui lòng nhập văn bản tiếng Việt cần chuyển sang giọng nói!")
            return

        if not self.selected_voice_id:
            QMessageBox.warning(self, "Chưa Chọn Giọng", "Vui lòng chọn một giọng đọc từ danh mục!")
            return

        speed = self.slider_speed.value() / 100.0
        fmt = self.combo_fmt.currentData() or "wav"

        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("⏳ Đang xử lý tạo giọng...")
        self.progress_bar.setVisible(True)
        self.lbl_status.setVisible(True)
        self.lbl_status.setStyleSheet("color: #EAB308;")
        self.lbl_status.setText(f"Đang tổng hợp với giọng '{self.selected_voice_id}' (Tốc độ {speed:.2f}x)...")

        self.synthesis_worker = SynthesisWorker(
            text=text,
            voice_id=self.selected_voice_id,
            speed=speed,
            out_format=fmt,
            filename_prefix="speech",
            custom_out_dir=self.custom_output_dir,
        )
        self.synthesis_worker.finished.connect(self._on_synthesis_finished)
        self.synthesis_worker.error.connect(self._on_synthesis_error)
        self.synthesis_worker.start()

    def _on_synthesis_finished(self, result: dict):
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("▶ TẠO GIỌNG NÓI")
        self.progress_bar.setVisible(False)

        if not result.get("success", False):
            err_msg = result.get("error", "Lỗi tạo giọng nói.")
            self._on_synthesis_error(err_msg)
            return

        self.current_result = result
        file_path = result.get("file_path") or result.get("main_file") or result.get("wav_path") or ""
        p_file = Path(file_path).resolve()
        duration = float(result.get("duration") or result.get("duration_sec") or 0.0)
        size_bytes = int(result.get("size_bytes") or result.get("file_size_bytes") or 0)
        fmt = str(result.get("format") or "wav").upper()

        self.lbl_status.setStyleSheet("color: #4ADE80;")
        self.lbl_status.setText(f"✅ Tạo giọng nói thành công! Thời lượng: {duration:.2f}s | Kích thước: {size_bytes / 1024:.1f} KB")

        self.player_card.setVisible(True)
        self.lbl_result_info.setText(
            f"🎵 File: <b>{p_file.name}</b> ({fmt} | {size_bytes / 1024:.1f} KB)<br>"
            f"📁 Lưu tại: <a href='open_folder' style='color: #EAB308; text-decoration: underline;'><b>{p_file.parent}</b></a>"
        )

        # Tự động phát âm thanh vừa sinh ra
        if file_path and Path(file_path).exists():
            audio_player.play(file_path)
            self.btn_play_pause.setText("⏸ Tạm dừng")
        self.audio_generated.emit(result)

    def _on_result_link_clicked(self, link: str):
        if link == "open_folder":
            self._open_output_folder()

    def _on_synthesis_error(self, err: str):
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("▶ TẠO GIỌNG NÓI")
        self.progress_bar.setVisible(False)
        self.lbl_status.setStyleSheet("color: #F87171;")
        self.lbl_status.setText(f"❌ Lỗi: {err}")
        QMessageBox.critical(self, "Lỗi Tổng Hợp Giọng Nói", f"Đã xảy ra lỗi:\n{err}")

    def _toggle_playback(self):
        if not self.current_result:
            return
        filepath = self.current_result.get("file_path") or self.current_result.get("main_file") or self.current_result.get("wav_path") or ""
        if not filepath or not Path(filepath).exists():
            return

        if audio_player.state == "playing":
            audio_player.pause()
            self.btn_play_pause.setText("▶ Tiếp tục")
        elif audio_player.state == "paused":
            audio_player.resume()
            self.btn_play_pause.setText("⏸ Tạm dừng")
        else:
            audio_player.play(filepath)
            self.btn_play_pause.setText("⏸ Tạm dừng")

    def _stop_playback(self):
        audio_player.stop()
        self.btn_play_pause.setText("▶ Phát")

    def _open_file_in_explorer(self):
        if not self.current_result:
            return
        fp = self.current_result.get("file_path") or self.current_result.get("main_file") or self.current_result.get("wav_path") or ""
        if fp:
            ok = tts_service.open_file_in_explorer(fp)
            if not ok:
                QMessageBox.warning(self, "Thông báo", f"Không tìm thấy file trên ổ cứng:\n{fp}")

    def _open_output_folder(self):
        out_dir = self.custom_output_dir or tts_service.default_out_dir
        ok = tts_service.open_output_folder(out_dir)
        if not ok:
            QMessageBox.warning(self, "Thông báo", f"Không thể mở thư mục:\n{out_dir}")

    def _copy_file_to_clipboard(self):
        """Sao chép tệp âm thanh thực tế vào Clipboard để dán trực tiếp vào thư mục hoặc Zalo/Telegram."""
        if not self.current_result:
            return
        fp = self.current_result.get("file_path") or self.current_result.get("main_file") or self.current_result.get("wav_path") or ""
        if not fp:
            return
        p = Path(fp).resolve()
        if not p.exists():
            QMessageBox.warning(self, "Không tìm thấy file", f"Tệp không tồn tại:\n{p}")
            return

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p))])
        mime.setText(str(p))
        QApplication.clipboard().setMimeData(mime)
        QMessageBox.information(
            self,
            "Đã Sao Chép File",
            f"✅ Đã sao chép file '{p.name}' vào bộ nhớ tạm!\n\n"
            "Bạn có thể mở bất kỳ thư mục nào trên máy tính, hoặc mở Zalo / Telegram và nhấn Ctrl + V để dán file trực tiếp.",
        )

    def _save_as_file(self):
        """Cho phép người dùng lưu file sang vị trí khác (Desktop, USB, Downloads, v.v.)."""
        if not self.current_result:
            return
        fp = self.current_result.get("file_path") or self.current_result.get("main_file") or self.current_result.get("wav_path") or ""
        if not fp:
            return
        src = Path(fp).resolve()
        if not src.exists():
            QMessageBox.warning(self, "Không tìm thấy file", f"Tệp nguồn không tồn tại:\n{src}")
            return

        fmt = src.suffix.lower()
        filter_str = f"Tệp {fmt.upper()} (*{fmt});;Tất cả tệp (*.*)"
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu tệp âm thanh thành...",
            str(Path.home() / "Desktop" / src.name),
            filter_str,
        )
        if dest:
            try:
                import shutil
                shutil.copy2(str(src), dest)
                QMessageBox.information(self, "Lưu Thành Công", f"Đã lưu tệp âm thanh vào:\n{dest}")
            except Exception as e:
                QMessageBox.critical(self, "Lỗi Lưu Tệp", f"Không thể lưu tệp: {e}")
