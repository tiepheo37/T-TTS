"""gui/pages/page_broadcast.py — BROADCAST STUDIO 2.0 (XƯỞNG SẢN XUẤT BẢN TIN PHÁT THANH ĐA TẦNG)
===================================================================================================
Kiến trúc nâng cấp Broadcast Studio 2.0:
- Multi-segment Timeline: Lời dẫn (lead_in), Tin tức (news), Thông báo (announcement),
  Nhạc mở đầu (intro_music), Nhạc kết thúc (outro_music), Âm thanh chèn/Jingle (jingle), Khoảng lặng (silence).
- Biên tập phân đoạn: Thêm, xóa, nhân bản, sắp xếp (lên/xuống), sửa văn bản, đổi giọng đọc, chỉnh tốc độ.
- Tạo giọng đọc VieNeu-TTS v3 Turbo độc lập cho từng phân đoạn (chỉ regenerate đoạn sửa, bảo toàn đoạn khác).
- Background Music Studio: Lồng bài hát nền, loop, fade in/out, điều chỉnh âm lượng và tự động hạ nhạc khi có giọng đọc (Auto-Ducking).
- Preview & Timeline: Nghe thử từng phân đoạn, nghe thử toàn bộ chương trình (preview đa tầng), đo đếm thời lượng.
- Quản lý dự án: Lưu/Mở dự án JSON chuẩn hóa qua ProjectManager (data/projects/broadcast/), cơ chế Relink nguồn an toàn.
- Xuất bản chương trình: Xuất WAV PCM 16-bit 48kHz hoặc MP3 192kbps chuẩn phát thanh quân đội.
"""

from __future__ import annotations

import os
import sys
import time
import shutil
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QMimeData
from PySide6.QtGui import QFont, QColor, QCursor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QCheckBox,
    QSlider,
    QDoubleSpinBox,
    QSpinBox,
    QComboBox,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QProgressBar,
    QScrollArea,
    QApplication,
    QDialog,
    QTextEdit,
)

from backend.service import tts_service
from backend.audio_player import audio_player
from backend.project_manager import project_manager
from backend.audio_utils import (
    stitch_broadcast_project,
    load_audio_segment_safe,
    get_audio_duration_safe,
    apply_audio_gain_and_fade,
)
from gui.task_worker import FunctionTaskWorker
from gui.notification_hub import notification_hub


SEGMENT_TYPES = {
    "lead_in": ("🎙️ Lời Dẫn", "#38BDF8"),
    "news": ("📰 Tin Tức", "#4ADE80"),
    "announcement": ("📢 Thông Báo", "#FACC15"),
    "intro_music": ("🎺 Nhạc Mở Đầu", "#F472B6"),
    "outro_music": ("🎼 Nhạc Kết Thúc", "#C084FC"),
    "jingle": ("🔔 Âm Hiệu / Jingle", "#FB923C"),
    "silence": ("⏸️ Khoảng Lặng", "#94A3B8"),
    "speech": ("🎙️ Đoạn Đọc", "#38BDF8"),
}


class SegmentEditorDialog(QDialog):
    """Hộp thoại chỉnh sửa chi tiết nội dung phân đoạn trong bản tin."""

    def __init__(self, segment_data: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Biên Tập Phân Đoạn Bản Tin")
        self.setMinimumWidth(560)
        self.setStyleSheet("""
            QDialog { background-color: #0F1710; color: #FFFFFF; }
            QLabel { color: #E2E8F0; font-size: 12px; }
            QLineEdit, QTextEdit, QComboBox, QDoubleSpinBox, QSpinBox {
                background-color: #162419; color: #FFFFFF; border: 1px solid #2D5A34;
                border-radius: 4px; padding: 6px;
            }
            QPushButton { border-radius: 4px; padding: 6px 14px; font-weight: bold; }
        """)
        self.seg = dict(segment_data)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Loại phân đoạn
        row_type = QHBoxLayout()
        row_type.addWidget(QLabel("Loại phân đoạn:"))
        self.combo_type = QComboBox()
        for k, (name, _) in SEGMENT_TYPES.items():
            if k != "speech":  # dùng lead_in thay thế
                self.combo_type.addItem(name, k)
        cur_type = self.seg.get("type", "news")
        idx = self.combo_type.findData(cur_type)
        if idx >= 0:
            self.combo_type.setCurrentIndex(idx)
        self.combo_type.currentIndexChanged.connect(self._on_type_changed)
        row_type.addWidget(self.combo_type, 1)
        layout.addLayout(row_type)

        # Tiêu đề
        row_title = QHBoxLayout()
        row_title.addWidget(QLabel("Tiêu đề / Nhãn:"))
        self.edit_title = QLineEdit(self.seg.get("title", ""))
        row_title.addWidget(self.edit_title, 1)
        layout.addLayout(row_title)

        # Khung văn bản (cho các loại speech)
        self.speech_frame = QFrame()
        sf_layout = QVBoxLayout(self.speech_frame)
        sf_layout.setContentsMargins(0, 0, 0, 0)
        sf_layout.setSpacing(8)

        sf_layout.addWidget(QLabel("Nội dung văn bản cần đọc:"))
        self.edit_text = QTextEdit()
        self.edit_text.setPlaceholderText("Nhập nội dung cho phân đoạn này...")
        self.edit_text.setPlainText(self.seg.get("text", ""))
        self.edit_text.setMinimumHeight(110)
        sf_layout.addWidget(self.edit_text)

        row_voice = QHBoxLayout()
        row_voice.addWidget(QLabel("Giọng đọc:"))
        self.combo_voice = QComboBox()
        try:
            voices = tts_service.list_voices()
            for v in voices:
                self.combo_voice.addItem(f"{v['name']} ({v.get('gender', '')})", v["id"])
            cur_voice = self.seg.get("voice_id", "hn_nam_quan_doi")
            v_idx = self.combo_voice.findData(cur_voice)
            if v_idx >= 0:
                self.combo_voice.setCurrentIndex(v_idx)
        except Exception:
            self.combo_voice.addItem("Mặc định Quân đội", "hn_nam_quan_doi")
        row_voice.addWidget(self.combo_voice, 1)

        row_voice.addWidget(QLabel("Tốc độ:"))
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.7, 1.6)
        self.spin_speed.setSingleStep(0.05)
        self.spin_speed.setValue(float(self.seg.get("speed", 1.0)))
        row_voice.addWidget(self.spin_speed)
        sf_layout.addLayout(row_voice)

        layout.addWidget(self.speech_frame)

        # Khung tệp âm thanh (cho nhạc hiệu / jingle / tệp ngoài)
        self.audio_frame = QFrame()
        af_layout = QVBoxLayout(self.audio_frame)
        af_layout.setContentsMargins(0, 0, 0, 0)
        af_layout.setSpacing(8)

        af_layout.addWidget(QLabel("Tệp âm thanh nguồn:"))
        row_file = QHBoxLayout()
        self.edit_file = QLineEdit(self.seg.get("file_path", ""))
        self.edit_file.setReadOnly(True)
        row_file.addWidget(self.edit_file, 1)
        btn_browse = QPushButton("📁 Chọn tệp...")
        btn_browse.setStyleSheet("background-color: #1E3A21; color: #FFD700;")
        btn_browse.clicked.connect(self._browse_file)
        row_file.addWidget(btn_browse)
        af_layout.addLayout(row_file)
        layout.addWidget(self.audio_frame)

        # Khung khoảng lặng (cho silence)
        self.silence_frame = QFrame()
        sif_layout = QHBoxLayout(self.silence_frame)
        sif_layout.setContentsMargins(0, 0, 0, 0)
        sif_layout.addWidget(QLabel("Thời gian khoảng lặng (giây):"))
        self.spin_silence = QDoubleSpinBox()
        self.spin_silence.setRange(0.2, 30.0)
        self.spin_silence.setSingleStep(0.5)
        self.spin_silence.setValue(float(self.seg.get("duration_sec", 1.0)))
        sif_layout.addWidget(self.spin_silence, 1)
        layout.addWidget(self.silence_frame)

        # Tùy chỉnh nâng cao (Gain dB, Pause sau đoạn, Fade In/Out)
        adv_card = QFrame()
        adv_card.setStyleSheet("background-color: #142217; border-radius: 4px; padding: 6px;")
        adv_layout = QGridLayout(adv_card)
        adv_layout.setSpacing(8)

        adv_layout.addWidget(QLabel("Thời gian nghỉ sau (s):"), 0, 0)
        self.spin_pause = QDoubleSpinBox()
        self.spin_pause.setRange(0.0, 10.0)
        self.spin_pause.setSingleStep(0.5)
        self.spin_pause.setValue(float(self.seg.get("pause_after", 1.0)))
        adv_layout.addWidget(self.spin_pause, 0, 1)

        adv_layout.addWidget(QLabel("Độ lợi âm lượng (Gain dB):"), 0, 2)
        self.spin_gain = QDoubleSpinBox()
        self.spin_gain.setRange(-20.0, 20.0)
        self.spin_gain.setSingleStep(0.5)
        self.spin_gain.setValue(float(self.seg.get("gain_db", 0.0)))
        adv_layout.addWidget(self.spin_gain, 0, 3)

        adv_layout.addWidget(QLabel("Fade In (ms):"), 1, 0)
        self.spin_fade_in = QSpinBox()
        self.spin_fade_in.setRange(0, 5000)
        self.spin_fade_in.setSingleStep(100)
        self.spin_fade_in.setValue(int(self.seg.get("fade_in_ms", 0)))
        adv_layout.addWidget(self.spin_fade_in, 1, 1)

        adv_layout.addWidget(QLabel("Fade Out (ms):"), 1, 2)
        self.spin_fade_out = QSpinBox()
        self.spin_fade_out.setRange(0, 5000)
        self.spin_fade_out.setSingleStep(100)
        self.spin_fade_out.setValue(int(self.seg.get("fade_out_ms", 0)))
        adv_layout.addWidget(self.spin_fade_out, 1, 3)

        layout.addWidget(adv_card)

        # Nút xác nhận
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.setStyleSheet("background-color: #334155; color: #FFFFFF;")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_ok = QPushButton("Lưu Phân Đoạn")
        btn_ok.setStyleSheet("background-color: #15803D; color: #FFFFFF;")
        btn_ok.clicked.connect(self._save_and_accept)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

        self._on_type_changed()

    def _on_type_changed(self):
        stype = self.combo_type.currentData()
        is_speech = stype in ("lead_in", "news", "announcement", "speech")
        is_audio = stype in ("intro_music", "outro_music", "jingle")
        is_silence = stype == "silence"

        self.speech_frame.setVisible(is_speech)
        self.audio_frame.setVisible(is_audio)
        self.silence_frame.setVisible(is_silence)

    def _browse_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Chọn tệp âm thanh phân đoạn", "",
            "Tệp Âm Thanh (*.wav *.mp3 *.flac *.ogg *.m4a);;Tất cả (*.*)"
        )
        if f:
            self.edit_file.setText(f)
            if not self.edit_title.text().strip():
                self.edit_title.setText(Path(f).stem.replace("_", " "))

    def _save_and_accept(self):
        stype = self.combo_type.currentData()
        title = self.edit_title.text().strip() or "Phân đoạn"
        self.seg["type"] = stype
        self.seg["title"] = title
        self.seg["pause_after"] = self.spin_pause.value()
        self.seg["gain_db"] = self.spin_gain.value()
        self.seg["fade_in_ms"] = self.spin_fade_in.value()
        self.seg["fade_out_ms"] = self.spin_fade_out.value()

        if stype in ("lead_in", "news", "announcement", "speech"):
            new_text = self.edit_text.toPlainText().strip()
            new_voice = self.combo_voice.currentData()
            new_speed = self.spin_speed.value()

            # Kiểm tra nếu người dùng đã thay đổi text/voice/speed
            if (
                new_text != self.seg.get("text", "")
                or new_voice != self.seg.get("voice_id")
                or abs(new_speed - float(self.seg.get("speed", 1.0))) > 0.01
            ):
                self.seg["is_modified"] = True
                self.seg["status"] = "pending"

            self.seg["text"] = new_text
            self.seg["voice_id"] = new_voice
            self.seg["speed"] = new_speed
        elif stype in ("intro_music", "outro_music", "jingle"):
            fpath = self.edit_file.text().strip()
            self.seg["file_path"] = fpath
            if fpath and Path(fpath).is_file():
                self.seg["duration_sec"] = get_audio_duration_safe(Path(fpath))
                self.seg["status"] = "ready"
        elif stype == "silence":
            dur = self.spin_silence.value()
            self.seg["duration_sec"] = dur
            self.seg["status"] = "ready"

        self.accept()

    def get_segment_data(self) -> Dict[str, Any]:
        return self.seg


class PageBroadcast(QWidget):
    """Giao diện Phân Hệ Phát Thanh Đa Tầng (Broadcast Studio 2.0)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.segments: List[Dict[str, Any]] = []
        self.current_project_id: Optional[str] = None
        self.current_project_name: str = "Bản tin phát thanh mới"
        self.current_output_file: Optional[Path] = None
        self.active_workers: Dict[str, FunctionTaskWorker] = {}

        # Trình phát âm thanh
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(150)
        self.play_timer.timeout.connect(self._update_player_progress)

        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        # 1. KHUNG HEADER & QUẢN LÝ DỰ ÁN (PROJECT TOOLBAR)
        header_card = QFrame()
        header_card.setProperty("class", "CardFrame")
        hc_layout = QVBoxLayout(header_card)
        hc_layout.setContentsMargins(14, 12, 14, 12)
        hc_layout.setSpacing(10)

        top_row = QHBoxLayout()
        self.lbl_main_title = QLabel("📻 BROADCAST STUDIO 2.0 — XƯỞNG SẢN XUẤT BẢN TIN PHÁT THANH ĐA TẦNG")
        self.lbl_main_title.setStyleSheet("color: #FFD700; font-size: 15px; font-weight: 900; letter-spacing: 0.5px;")
        top_row.addWidget(self.lbl_main_title)
        top_row.addStretch()

        self.lbl_proj_info = QLabel("Dự án: <b style='color:#38BDF8;'>Bản tin mới</b>")
        self.lbl_proj_info.setStyleSheet("color: #94A3B8; font-size: 12px;")
        top_row.addWidget(self.lbl_proj_info)
        hc_layout.addLayout(top_row)

        proj_btns_row = QHBoxLayout()
        btn_new_proj = QPushButton("📄 Dự Án Mới")
        btn_new_proj.setProperty("class", "SecondaryBtn")
        btn_new_proj.clicked.connect(self.new_project)
        proj_btns_row.addWidget(btn_new_proj)

        btn_open_proj = QPushButton("📂 Mở Dự Án...")
        btn_open_proj.setProperty("class", "SecondaryBtn")
        btn_open_proj.clicked.connect(self.open_project_dialog)
        proj_btns_row.addWidget(btn_open_proj)

        btn_save_proj = QPushButton("💾 Lưu Dự Án")
        btn_save_proj.setProperty("class", "SecondaryBtn")
        btn_save_proj.clicked.connect(self.save_project)
        proj_btns_row.addWidget(btn_save_proj)

        proj_btns_row.addSpacing(16)

        btn_import_files = QPushButton("📁 Nhập File Âm Thanh...")
        btn_import_files.setProperty("class", "SecondaryBtn")
        btn_import_files.clicked.connect(self._add_audio_files)
        proj_btns_row.addWidget(btn_import_files)

        btn_gen_all = QPushButton("⚡ Tạo Giọng Tất Cả Đoạn")
        btn_gen_all.setProperty("class", "SecondaryBtn")
        btn_gen_all.setToolTip("Tự động tạo giọng đọc cho tất cả các phân đoạn chưa có audio")
        btn_gen_all.clicked.connect(self.generate_all_pending_speech)
        proj_btns_row.addWidget(btn_gen_all)

        proj_btns_row.addStretch()
        hc_layout.addLayout(proj_btns_row)
        layout.addWidget(header_card)

        # 2. KHUNG MULTI-SEGMENT TIMELINE VÀ BẢNG PHÂN ĐOẠN
        list_card = QFrame()
        list_card.setProperty("class", "CardFrame")
        lc_layout = QVBoxLayout(list_card)
        lc_layout.setContentsMargins(14, 12, 14, 12)
        lc_layout.setSpacing(10)

        tb_row = QHBoxLayout()
        lbl_list_title = QLabel("DANH SÁCH CÁC PHÂN ĐOẠN PHÁT THANH (MULTI-SEGMENT TIMELINE)")
        lbl_list_title.setStyleSheet("color: #FFD700; font-size: 13px; font-weight: bold;")
        tb_row.addWidget(lbl_list_title)
        tb_row.addStretch()

        btn_add_lead = QPushButton("➕ Lời Dẫn")
        btn_add_lead.setProperty("class", "SecondaryBtn")
        btn_add_lead.clicked.connect(lambda: self._quick_add_segment("lead_in"))
        tb_row.addWidget(btn_add_lead)

        btn_add_news = QPushButton("➕ Tin Tức")
        btn_add_news.setProperty("class", "SecondaryBtn")
        btn_add_news.clicked.connect(lambda: self._quick_add_segment("news"))
        tb_row.addWidget(btn_add_news)

        btn_add_ann = QPushButton("➕ Thông Báo")
        btn_add_ann.setProperty("class", "SecondaryBtn")
        btn_add_ann.clicked.connect(lambda: self._quick_add_segment("announcement"))
        tb_row.addWidget(btn_add_ann)

        btn_add_jingle = QPushButton("➕ Nhạc Hiệu")
        btn_add_jingle.setProperty("class", "SecondaryBtn")
        btn_add_jingle.clicked.connect(lambda: self._quick_add_segment("jingle"))
        tb_row.addWidget(btn_add_jingle)

        btn_add_silence = QPushButton("➕ Khoảng Lặng")
        btn_add_silence.setProperty("class", "SecondaryBtn")
        btn_add_silence.clicked.connect(lambda: self._quick_add_segment("silence"))
        tb_row.addWidget(btn_add_silence)

        tb_row.addSpacing(10)

        self.btn_move_up = QPushButton("🔼")
        self.btn_move_up.setProperty("class", "SecondaryBtn")
        self.btn_move_up.clicked.connect(self._move_up)
        tb_row.addWidget(self.btn_move_up)

        self.btn_move_down = QPushButton("🔽")
        self.btn_move_down.setProperty("class", "SecondaryBtn")
        self.btn_move_down.clicked.connect(self._move_down)
        tb_row.addWidget(self.btn_move_down)

        self.btn_clear_list = QPushButton("🧹 Xóa hết")
        self.btn_clear_list.setProperty("class", "SecondaryBtn")
        self.btn_clear_list.clicked.connect(self.clear_all_segments)
        tb_row.addWidget(self.btn_clear_list)

        lc_layout.addLayout(tb_row)

        # Bảng danh sách phân đoạn
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "STT", "Loại", "Nội Dung / Tệp Nguồn", "Giọng Đọc & Tốc Độ", "Thời Lượng", "Trạng Thái", "Thao Tác"
        ])
        self.table.setColumnWidth(0, 48)   # STT
        self.table.setColumnWidth(1, 130)  # Loại
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch) # Nội dung
        self.table.setColumnWidth(3, 160)  # Giọng & Speed
        self.table.setColumnWidth(4, 90)   # Thời lượng
        self.table.setColumnWidth(5, 110)  # Trạng thái
        self.table.setColumnWidth(6, 210)  # Thao tác
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setMinimumHeight(280)
        lc_layout.addWidget(self.table)

        self.lbl_list_status = QLabel("Chưa có phân đoạn nào. Nhấn các nút phía trên để tạo kịch bản phát thanh.")
        self.lbl_list_status.setStyleSheet("color: #94A3B8; font-size: 12px;")
        lc_layout.addWidget(self.lbl_list_status)

        layout.addWidget(list_card)

        # 3. BACKGROUND MUSIC STUDIO & AUTO-DUCKING
        bg_card = QFrame()
        bg_card.setProperty("class", "CardFrame")
        bc_layout = QVBoxLayout(bg_card)
        bc_layout.setContentsMargins(14, 12, 14, 12)
        bc_layout.setSpacing(10)

        # Checkbox bật nhạc nền
        self.chk_enable_bg = QCheckBox("🎶 Lồng bài hát / Nhạc nền (Background Music) phát ngầm xuyên suốt bản tin")
        self.chk_enable_bg.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 13px;")
        self.chk_enable_bg.toggled.connect(self._on_bg_toggle)
        bc_layout.addWidget(self.chk_enable_bg)

        self.bg_ctrl_frame = QFrame()
        self.bg_ctrl_frame.setEnabled(False)
        bcf_layout = QVBoxLayout(self.bg_ctrl_frame)
        bcf_layout.setContentsMargins(0, 4, 0, 0)
        bcf_layout.setSpacing(8)

        # Hàng chọn bài nhạc nền chính
        bg_file_row = QHBoxLayout()
        self.bg_path_edit = QLineEdit()
        self.bg_path_edit.setReadOnly(True)
        self.bg_path_edit.setPlaceholderText("Chưa chọn bài nhạc nền (MP3 hoặc WAV)...")
        bg_file_row.addWidget(self.bg_path_edit, 1)

        btn_browse_bg = QPushButton("📁 Chọn bài nhạc...")
        btn_browse_bg.setProperty("class", "SecondaryBtn")
        btn_browse_bg.clicked.connect(self._browse_bg_music)
        bg_file_row.addWidget(btn_browse_bg)

        btn_preview_bg = QPushButton("▶ Nghe thử")
        btn_preview_bg.setProperty("class", "SecondaryBtn")
        btn_preview_bg.clicked.connect(self._preview_bg_music)
        bg_file_row.addWidget(btn_preview_bg)
        bcf_layout.addLayout(bg_file_row)

        # Hàng điều khiển volume, loop, auto-ducking
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Âm lượng nhạc nền:"))
        self.bg_vol_slider = QSlider(Qt.Horizontal)
        self.bg_vol_slider.setRange(5, 50)
        self.bg_vol_slider.setValue(15)
        self.bg_vol_slider.setMaximumWidth(180)
        self.bg_vol_slider.valueChanged.connect(self._on_bg_vol_changed)
        vol_row.addWidget(self.bg_vol_slider)

        self.lbl_vol_val = QLabel("15% (vừa phải, không át tiếng nói)")
        self.lbl_vol_val.setStyleSheet("color: #22D3EE; font-weight: bold;")
        vol_row.addWidget(self.lbl_vol_val)

        vol_row.addSpacing(16)
        self.chk_loop_bg = QCheckBox("Tự động lặp lại nếu bản tin dài hơn bài hát")
        self.chk_loop_bg.setChecked(True)
        vol_row.addWidget(self.chk_loop_bg)

        self.chk_ducking = QCheckBox("Tự động hạ âm lượng khi có lời đọc (Auto-Ducking)")
        self.chk_ducking.setChecked(True)
        vol_row.addWidget(self.chk_ducking)

        self.btn_smart_mix = QPushButton("🧠 Cân Bằng Thông Minh (Smart Mix)")
        self.btn_smart_mix.setProperty("class", "SecondaryBtn")
        self.btn_smart_mix.setToolTip("Tự động phân tích giọng đọc và nhạc nền để đề xuất tỷ lệ âm lượng và Ducking hoàn hảo")
        self.btn_smart_mix.clicked.connect(self._smart_broadcast_mix_dialog)
        vol_row.addWidget(self.btn_smart_mix)
        vol_row.addStretch()
        bcf_layout.addLayout(vol_row)

        # Nhạc mở đầu & Nhạc kết thúc (Jingle / Outro)
        io_row = QHBoxLayout()
        io_row.addWidget(QLabel("🎺 Nhạc mở đầu (Intro):"))
        self.edit_intro_music = QLineEdit()
        self.edit_intro_music.setReadOnly(True)
        self.edit_intro_music.setPlaceholderText("Tùy chọn nhạc chào đầu...")
        io_row.addWidget(self.edit_intro_music, 1)
        btn_intro = QPushButton("📁")
        btn_intro.setProperty("class", "SecondaryBtn")
        btn_intro.clicked.connect(self._browse_intro_music)
        io_row.addWidget(btn_intro)

        io_row.addSpacing(12)
        io_row.addWidget(QLabel("🎼 Nhạc kết thúc (Outro):"))
        self.edit_outro_music = QLineEdit()
        self.edit_outro_music.setReadOnly(True)
        self.edit_outro_music.setPlaceholderText("Tùy chọn nhạc chào kết...")
        io_row.addWidget(self.edit_outro_music, 1)
        btn_outro = QPushButton("📁")
        btn_outro.setProperty("class", "SecondaryBtn")
        btn_outro.clicked.connect(self._browse_outro_music)
        io_row.addWidget(btn_outro)

        bcf_layout.addLayout(io_row)
        bc_layout.addWidget(self.bg_ctrl_frame)
        layout.addWidget(bg_card)

        # 4. KHUNG XUẤT BẢN TIN VÀ ĐỊNH DẠNG
        export_card = QFrame()
        export_card.setProperty("class", "CardFrame")
        ec_layout = QVBoxLayout(export_card)
        ec_layout.setContentsMargins(14, 12, 14, 12)
        ec_layout.setSpacing(10)

        cfg_row = QHBoxLayout()
        cfg_row.addWidget(QLabel("Tên bản tin:"))
        self.title_edit = QLineEdit("Ban_tin_phat_thanh")
        cfg_row.addWidget(self.title_edit, 1)

        cfg_row.addWidget(QLabel("Nghỉ mặc định giữa các đoạn:"))
        self.spin_default_pause = QDoubleSpinBox()
        self.spin_default_pause.setRange(0.0, 5.0)
        self.spin_default_pause.setSingleStep(0.5)
        self.spin_default_pause.setValue(1.0)
        self.spin_default_pause.setSuffix("s")
        cfg_row.addWidget(self.spin_default_pause)

        self.radio_wav = QRadioButton("WAV (Chuẩn Studio)")
        self.radio_wav.setChecked(True)
        self.radio_mp3 = QRadioButton("MP3 (192kbps)")
        self.fmt_group = QButtonGroup(self)
        self.fmt_group.addButton(self.radio_wav)
        self.fmt_group.addButton(self.radio_mp3)
        cfg_row.addWidget(self.radio_wav)
        cfg_row.addWidget(self.radio_mp3)

        self.chk_dsp_mastering = QCheckBox("✨ Nâng cấp DSP:")
        self.chk_dsp_mastering.setChecked(True)
        self.chk_dsp_mastering.setToolTip("Tự động áp dụng bộ lọc phát thanh chuẩn hóa âm lượng EBU R128 và khử nhiễu trước khi xuất tệp")
        cfg_row.addWidget(self.chk_dsp_mastering)

        self.combo_dsp_preset = QComboBox()
        self.combo_dsp_preset.addItem("🎖️ Phát thanh Quân đội", "military_narration")
        self.combo_dsp_preset.addItem("📡 Chuẩn EBU R128 (-23 LUFS)", "broadcast")
        self.combo_dsp_preset.addItem("🎵 Giọng đọc + Nhạc nền", "voice_bgm")
        self.combo_dsp_preset.addItem("🎙️ Thuyết minh Studio", "studio_voice")
        cfg_row.addWidget(self.combo_dsp_preset)

        ec_layout.addLayout(cfg_row)

        action_row = QHBoxLayout()
        btn_preview_full = QPushButton("🎧 NGHE THỬ TOÀN BỘ CHƯƠNG TRÌNH")
        btn_preview_full.setProperty("class", "SecondaryBtn")
        btn_preview_full.setFixedHeight(44)
        btn_preview_full.setFont(QFont("Segoe UI", 11, QFont.Bold))
        btn_preview_full.clicked.connect(self.preview_full_program)
        action_row.addWidget(btn_preview_full, 1)

        self.btn_export = QPushButton("📻 XUẤT BẢN TIN PHÁT THANH HOÀN CHỈNH")
        self.btn_export.setProperty("class", "PrimaryBtn")
        self.btn_export.setFixedHeight(44)
        self.btn_export.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_export.clicked.connect(self.export_broadcast_program)
        action_row.addWidget(self.btn_export, 2)
        ec_layout.addLayout(action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setVisible(False)
        ec_layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setStyleSheet("font-size: 13px; font-weight: 500;")
        ec_layout.addWidget(self.status_lbl)
        layout.addWidget(export_card)

        # 5. KHUNG TRÌNH PHÁT BẢN TIN TÍCH HỢP
        self.player_card = QFrame()
        self.player_card.setProperty("class", "CardFrame")
        self.player_card.setVisible(False)
        pc_layout = QVBoxLayout(self.player_card)
        pc_layout.setContentsMargins(14, 12, 14, 12)
        pc_layout.setSpacing(10)

        p_header = QHBoxLayout()
        self.lbl_playing_title = QLabel("📻 BẢN TIN ĐÃ XUẤT:")
        self.lbl_playing_title.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 13px;")
        p_header.addWidget(self.lbl_playing_title)
        p_header.addStretch()

        btn_copy = QPushButton("📋 Sao chép file")
        btn_copy.setProperty("class", "SecondaryBtn")
        btn_copy.clicked.connect(self._copy_output_to_clipboard)
        p_header.addWidget(btn_copy)

        btn_save_as = QPushButton("💾 Lưu thành...")
        btn_save_as.setProperty("class", "SecondaryBtn")
        btn_save_as.clicked.connect(self._save_output_as)
        p_header.addWidget(btn_save_as)

        btn_view_file = QPushButton("📂 Xem file")
        btn_view_file.setProperty("class", "SecondaryBtn")
        btn_view_file.clicked.connect(self._open_output_file_folder)
        p_header.addWidget(btn_view_file)
        pc_layout.addLayout(p_header)

        play_ctrl_row = QHBoxLayout()
        self.btn_play_pause = QPushButton("▶ Phát Bản Tin")
        self.btn_play_pause.setProperty("class", "PrimaryBtn")
        self.btn_play_pause.setFixedWidth(140)
        self.btn_play_pause.setFixedHeight(36)
        self.btn_play_pause.clicked.connect(self._toggle_playback)
        play_ctrl_row.addWidget(self.btn_play_pause)

        self.timeline_slider = QSlider(Qt.Horizontal)
        self.timeline_slider.setRange(0, 1000)
        self.timeline_slider.setValue(0)
        self.timeline_slider.sliderMoved.connect(self._on_seek_moved)
        play_ctrl_row.addWidget(self.timeline_slider)

        self.lbl_time_display = QLabel("00:00 / 00:00")
        self.lbl_time_display.setStyleSheet("color: #22D3EE; font-weight: bold; font-size: 13px; min-width: 90px;")
        play_ctrl_row.addWidget(self.lbl_time_display)
        pc_layout.addLayout(play_ctrl_row)
        layout.addWidget(self.player_card)

        layout.addStretch()
        scroll.setWidget(content_widget)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    # =========================================================================
    # QUẢN LÝ DỰ ÁN (PROJECT MANAGEMENT)
    # =========================================================================
    def new_project(self, confirm: bool = True):
        """Khởi tạo dự án bản tin mới sạch sẽ."""
        if confirm and self.segments:
            ans = QMessageBox.question(
                self, "Tạo dự án mới", "Bạn có chắc muốn tạo dự án mới? Kịch bản hiện tại chưa lưu sẽ bị xóa.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ans != QMessageBox.Yes:
                return

        self.stop_playback()
        self.segments.clear()
        self.current_project_id = None
        self.current_project_name = "Bản tin mới"
        self.title_edit.setText("Ban_tin_phat_thanh")
        self.bg_path_edit.clear()
        self.edit_intro_music.clear()
        self.edit_outro_music.clear()
        self.chk_enable_bg.setChecked(False)
        self._refresh_table()
        self.lbl_proj_info.setText("Dự án: <b style='color:#38BDF8;'>Bản tin mới</b>")
        notification_hub.notify_info.emit("Dự Án Mới", "Đã khởi tạo dự án bản tin mới.")

    def open_project_dialog(self):
        """Mở danh sách các dự án broadcast đã lưu trong data/projects/broadcast/."""
        projs = project_manager.list_projects("broadcast")
        if not projs:
            QMessageBox.information(self, "Chưa có dự án", "Chưa có dự án bản tin nào được lưu trước đó.")
            return

        names = [f"{p['name']} ({p.get('updated_at', '')})" for p in projs]
        chosen, ok = QInputDialog.getItem(self, "Mở dự án bản tin", "Chọn dự án cần mở:", names, 0, False)
        if ok and chosen:
            idx = names.index(chosen)
            pid = projs[idx]["id"]
            self.load_project(pid)

    def save_project(self) -> Optional[str]:
        """Lưu cấu trúc bản tin vào JSON qua ProjectManager."""
        name, ok = QInputDialog.getText(self, "Lưu dự án", "Tên dự án bản tin:", text=self.current_project_name)
        if not ok or not name.strip():
            return None

        self.current_project_name = name.strip()
        proj_dict = self.build_project_dict(self.current_project_name)
        if self.current_project_id:
            proj_dict["id"] = self.current_project_id

        pid = project_manager.save_project("broadcast", proj_dict)
        self.current_project_id = pid
        self.lbl_proj_info.setText(f"Dự án: <b style='color:#38BDF8;'>{self.current_project_name}</b>")
        notification_hub.notify_success.emit("Lưu Dự Án", f"Đã lưu dự án '{self.current_project_name}' thành công.")
        return pid

    def load_project(self, project_id: str) -> bool:
        """Nạp dự án bản tin từ JSON và khôi phục timeline."""
        proj = project_manager.load_project("broadcast", project_id)
        if not proj:
            QMessageBox.critical(self, "Lỗi dự án", "Không tìm thấy tệp dự án.")
            return False

        ok = self.restore_from_project_dict(proj)
        if ok:
            self.current_project_id = project_id
            self.current_project_name = proj.get("name", "Bản tin phát thanh")
            self.lbl_proj_info.setText(f"Dự án: <b style='color:#38BDF8;'>{self.current_project_name}</b>")
            notification_hub.notify_success.emit("Mở Dự Án", f"Đã mở dự án '{self.current_project_name}'.")
        return ok

    def build_project_dict(self, name: str = "") -> Dict[str, Any]:
        """Tạo dictionary dự án chuẩn hóa (không chứa nhị phân audio)."""
        pct = self.bg_vol_slider.value()
        bg_db = -35.0 + (pct / 50.0) * 25.0
        return {
            "name": name or self.current_project_name,
            "type": "broadcast",
            "title": self.title_edit.text().strip(),
            "default_pause_sec": self.spin_default_pause.value(),
            "out_format": "mp3" if self.radio_mp3.isChecked() else "wav",
            "bg_music_enabled": self.chk_enable_bg.isChecked(),
            "bg_music_path": self.bg_path_edit.text().strip(),
            "bg_music_vol_pct": pct,
            "bg_music_vol_db": bg_db,
            "bg_music_loop": self.chk_loop_bg.isChecked(),
            "bg_music_ducking": self.chk_ducking.isChecked(),
            "intro_music_path": self.edit_intro_music.text().strip(),
            "outro_music_path": self.edit_outro_music.text().strip(),
            "segments": [dict(s) for s in self.segments],
        }

    def restore_from_project_dict(self, proj: Dict[str, Any], prompt_relink: bool = False) -> bool:
        """Khôi phục trạng thái bản tin từ dictionary, có cơ chế Relink an toàn."""
        data = proj.get("data") if "data" in proj and isinstance(proj["data"], dict) and "segments" in proj["data"] else proj
        self.segments = []

        self.title_edit.setText(data.get("title", "Ban_tin_phat_thanh"))
        self.spin_default_pause.setValue(float(data.get("default_pause_sec", 1.0)))
        if data.get("out_format") == "mp3":
            self.radio_mp3.setChecked(True)
        else:
            self.radio_wav.setChecked(True)

        # Nhạc nền & Jingle
        bg_enabled = data.get("bg_music_enabled", False)
        self.chk_enable_bg.setChecked(bg_enabled)
        bg_p = data.get("bg_music_path", "")
        self.bg_path_edit.setText(bg_p)
        self.chk_loop_bg.setChecked(data.get("bg_music_loop", True))
        self.chk_ducking.setChecked(data.get("bg_music_ducking", True))
        self.bg_vol_slider.setValue(int(data.get("bg_music_vol_pct", 15)))

        self.edit_intro_music.setText(data.get("intro_music_path", ""))
        self.edit_outro_music.setText(data.get("outro_music_path", ""))

        # Khôi phục các phân đoạn
        missing_files = []
        for s in data.get("segments", []):
            seg_copy = dict(s)
            fpath = seg_copy.get("file_path")
            if fpath and not Path(fpath).is_file():
                missing_files.append((seg_copy, fpath))
                seg_copy["status"] = "pending"
            self.segments.append(seg_copy)

        self._refresh_table()

        if missing_files and prompt_relink:
            msg = (
                f"Phát hiện {len(missing_files)} tệp âm thanh nguồn bị thiếu hoặc đã di chuyển.\n"
                "Bạn có muốn chỉ định lại đường dẫn (Relink) ngay bây giờ không?"
            )
            ans = QMessageBox.warning(self, "Thiếu Tệp Nguồn", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if ans == QMessageBox.Yes:
                for seg_item, old_p in missing_files:
                    new_f, _ = QFileDialog.getOpenFileName(
                        self, f"Chỉ định lại tệp cho: {seg_item.get('title', 'Phân đoạn')}",
                        "", "Audio Files (*.wav *.mp3 *.flac *.ogg *.m4a)"
                    )
                    if new_f and Path(new_f).is_file():
                        seg_item["file_path"] = new_f
                        seg_item["duration_sec"] = get_audio_duration_safe(Path(new_f))
                        seg_item["status"] = "ready"
                self._refresh_table()

        return True

    # =========================================================================
    # MULTI-SEGMENT TIMELINE VÀ THAO TÁC BIÊN TẬP
    # =========================================================================
    def _quick_add_segment(self, seg_type: str):
        """Thêm nhanh phân đoạn theo loại."""
        sid = f"seg_{int(time.time())}_{uuid.uuid4().hex[:4]}"
        type_name, _ = SEGMENT_TYPES.get(seg_type, ("Phân đoạn", "#FFF"))
        default_seg = {
            "id": sid,
            "type": seg_type,
            "title": f"{type_name} {len(self.segments)+1}",
            "text": "" if seg_type in ("lead_in", "news", "announcement", "speech") else "",
            "voice_id": "hn_nam_quan_doi",
            "speed": 1.0,
            "file_path": None,
            "duration_sec": 1.0 if seg_type == "silence" else 0.0,
            "pause_after": self.spin_default_pause.value(),
            "gain_db": 0.0,
            "fade_in_ms": 0,
            "fade_out_ms": 0,
            "status": "ready" if seg_type == "silence" else "pending",
            "is_modified": True,
        }

        # Nếu là nhạc hiệu, mở chọn file ngay
        if seg_type in ("intro_music", "outro_music", "jingle"):
            f, _ = QFileDialog.getOpenFileName(self, f"Chọn tệp cho {type_name}", "", "Audio Files (*.wav *.mp3 *.flac *.ogg *.m4a)")
            if not f:
                return
            default_seg["file_path"] = f
            default_seg["title"] = Path(f).stem.replace("_", " ")
            default_seg["duration_sec"] = get_audio_duration_safe(Path(f))
            default_seg["status"] = "ready"
            default_seg["is_modified"] = False
            self.segments.append(default_seg)
            self._refresh_table()
            return

        # Mở hộp thoại nhập kịch bản
        dlg = SegmentEditorDialog(default_seg, self)
        if dlg.exec() == QDialog.Accepted:
            self.segments.append(dlg.get_segment_data())
            self._refresh_table()

    def edit_segment(self, idx: int):
        """Mở hộp thoại biên tập cho phân đoạn thứ idx."""
        if not (0 <= idx < len(self.segments)):
            return
        dlg = SegmentEditorDialog(self.segments[idx], self)
        if dlg.exec() == QDialog.Accepted:
            self.segments[idx] = dlg.get_segment_data()
            self._refresh_table()

    def duplicate_segment(self, idx: int):
        """Nhân bản phân đoạn tại vị trí idx."""
        if not (0 <= idx < len(self.segments)):
            return
        clone = dict(self.segments[idx])
        clone["id"] = f"seg_{int(time.time())}_{uuid.uuid4().hex[:4]}"
        clone["title"] = f"{clone.get('title', 'Đoạn')} (Bản sao)"
        self.segments.insert(idx + 1, clone)
        self._refresh_table()
        self.table.selectRow(idx + 1)

    def delete_segment(self, idx: int):
        """Xóa phân đoạn tại vị trí idx."""
        if 0 <= idx < len(self.segments):
            self.segments.pop(idx)
            self._refresh_table()

    def clear_all_segments(self, confirm: bool = True):
        """Xóa toàn bộ phân đoạn."""
        if not self.segments:
            return
        if confirm:
            ret = QMessageBox.question(
                self, "Xác nhận xóa", "Bạn có chắc muốn xóa toàn bộ phân đoạn trong bản tin?",
                QMessageBox.Yes | QMessageBox.No
            )
            if ret != QMessageBox.Yes:
                return
        self.segments.clear()
        self._refresh_table()

    def _move_up(self):
        row = self.table.currentRow()
        if row > 0:
            self.segments[row - 1], self.segments[row] = self.segments[row], self.segments[row - 1]
            self._refresh_table()
            self.table.selectRow(row - 1)

    def _move_down(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.segments) - 1:
            self.segments[row + 1], self.segments[row] = self.segments[row], self.segments[row + 1]
            self._refresh_table()
            self.table.selectRow(row + 1)

    def _add_audio_files(self):
        """Nhập các file âm thanh bên ngoài vào danh sách."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Chọn các tệp âm thanh nhập vào bản tin", "",
            "Âm thanh (*.wav *.mp3 *.flac *.ogg *.m4a);;Tất cả (*.*)"
        )
        if not files:
            return
        for f in files:
            p = Path(f)
            self.segments.append({
                "id": f"seg_{int(time.time())}_{uuid.uuid4().hex[:4]}",
                "type": "speech",
                "title": p.stem.replace("_", " "),
                "file_path": str(p),
                "duration_sec": get_audio_duration_safe(p),
                "pause_after": self.spin_default_pause.value(),
                "gain_db": 0.0,
                "fade_in_ms": 0,
                "fade_out_ms": 0,
                "status": "ready",
                "is_modified": False,
            })
        self._refresh_table()

    def add_batch_items(self, batch_results: List[Dict[str, Any]]):
        """Tiếp nhận danh sách các đoạn âm thanh từ trang Xử Lý Hàng Loạt."""
        added_count = 0
        for item in batch_results:
            if not item.get("success"):
                continue
            fpath = item.get("main_file") or item.get("file_path")
            if not fpath or not Path(fpath).is_file():
                continue

            orig = item.get("original_item") or {}
            txt = orig.get("text") or item.get("text") or Path(fpath).stem
            title = txt[:60] + ("..." if len(txt) > 60 else "")
            dur = float(item.get("duration_sec") or 0.0)

            self.segments.append({
                "id": f"seg_{int(time.time())}_{uuid.uuid4().hex[:4]}",
                "type": "speech",
                "title": title,
                "text": txt,
                "file_path": str(fpath),
                "duration_sec": dur,
                "pause_after": self.spin_default_pause.value(),
                "gain_db": 0.0,
                "fade_in_ms": 0,
                "fade_out_ms": 0,
                "status": "ready",
                "is_modified": False,
            })
            added_count += 1

        self._refresh_table()
        if added_count > 0:
            self.lbl_list_status.setText(f"🎉 Đã tiếp nhận {added_count} đoạn đọc từ Xử Lý Hàng Loạt!")
            self.lbl_list_status.setStyleSheet("color: #22C55E; font-weight: bold;")

    # =========================================================================
    # TỔNG HỢP GIỌNG ĐỌC VIENEU-TTS CHO TỪNG PHÂN ĐOẠN (REGENERATION ENGINE)
    # =========================================================================
    def generate_segment_speech(self, idx: int):
        """Tạo giọng đọc riêng cho MỘT phân đoạn bằng TTSService (không làm mất các đoạn khác)."""
        if not (0 <= idx < len(self.segments)):
            return

        seg = self.segments[idx]
        text = seg.get("text", "").strip()
        if not text:
            QMessageBox.information(self, "Thiếu văn bản", "Phân đoạn này chưa có nội dung văn bản để đọc.")
            return

        seg["status"] = "generating"
        self._refresh_table()

        voice_id = seg.get("voice_id", "hn_nam_quan_doi")
        speed = float(seg.get("speed", 1.0))
        seg_id = seg["id"]

        def _worker_fn():
            res = tts_service.synthesize_text(
                text=text,
                voice_id=voice_id,
                speed=speed,
                out_format="wav",
                filename_prefix=f"broadcast_seg_{seg_id}",
            )
            return res

        worker = FunctionTaskWorker(_worker_fn)

        def _on_done(res):
            if res.get("success") and res.get("file_path"):
                seg["file_path"] = res["file_path"]
                seg["duration_sec"] = float(res.get("duration_sec", 0.0))
                seg["status"] = "ready"
                seg["is_modified"] = False
                notification_hub.notify_success.emit("Tạo Giọng Thành Công", f"Đoạn '{seg.get('title')}' đã sẵn sàng ({seg['duration_sec']}s).")
            else:
                seg["status"] = "error"
                seg["error_msg"] = res.get("error", "Lỗi tạo giọng")
                notification_hub.notify_error.emit("Lỗi Tạo Giọng", seg["error_msg"])
            self._refresh_table()

        worker.finished_task.connect(_on_done)
        self.active_workers[seg_id] = worker
        worker.start()

    def generate_all_pending_speech(self):
        """Tạo giọng đọc cho tất cả các phân đoạn chưa có audio hoặc bị chỉnh sửa."""
        pending_indices = [
            i for i, s in enumerate(self.segments)
            if s.get("type") in ("lead_in", "news", "announcement", "speech")
            and (s.get("is_modified") or not s.get("file_path") or not Path(str(s.get("file_path"))).is_file())
        ]
        if not pending_indices:
            QMessageBox.information(self, "Đã sẵn sàng", "Tất cả các phân đoạn đã có file giọng đọc sẵn sàng.")
            return

        for idx in pending_indices:
            self.generate_segment_speech(idx)

    # =========================================================================
    # BẢNG HIỂN THỊ VÀ GIAO DIỆN PHÂN ĐOẠN
    # =========================================================================
    def _refresh_table(self):
        self.table.setRowCount(len(self.segments))
        for idx, seg in enumerate(self.segments):
            self.table.setRowHeight(idx, 46)

            # Cột 0: STT
            item_stt = QTableWidgetItem(str(idx + 1))
            item_stt.setTextAlignment(Qt.AlignCenter)
            item_stt.setForeground(QColor("#FFD700"))
            self.table.setItem(idx, 0, item_stt)

            # Cột 1: Loại phân đoạn
            stype = seg.get("type", "news")
            type_label, color_hex = SEGMENT_TYPES.get(stype, ("Phân đoạn", "#FFF"))
            item_type = QTableWidgetItem(type_label)
            item_type.setTextAlignment(Qt.AlignCenter)
            item_type.setForeground(QColor(color_hex))
            self.table.setItem(idx, 1, item_type)

            # Cột 2: Nội dung / Tệp
            content_desc = seg.get("text", "") or seg.get("title", "")
            if seg.get("file_path") and not content_desc:
                content_desc = Path(seg["file_path"]).name
            item_content = QTableWidgetItem(content_desc[:70] + ("..." if len(content_desc) > 70 else ""))
            self.table.setItem(idx, 2, item_content)

            # Cột 3: Giọng đọc & Tốc độ
            if stype in ("lead_in", "news", "announcement", "speech"):
                vid = seg.get("voice_id", "hn_nam_quan_doi")
                spd = seg.get("speed", 1.0)
                item_voice = QTableWidgetItem(f"{vid} (x{spd:.2f})")
            elif stype == "silence":
                item_voice = QTableWidgetItem("Khoảng lặng")
            else:
                item_voice = QTableWidgetItem("Tệp âm thanh ngoài")
            item_voice.setTextAlignment(Qt.AlignCenter)
            item_voice.setForeground(QColor("#CBD5E1"))
            self.table.setItem(idx, 3, item_voice)

            # Cột 4: Thời lượng
            dur = seg.get("duration_sec", 0.0)
            m = int(dur // 60)
            s = int(dur % 60)
            item_dur = QTableWidgetItem(f"{m:02d}:{s:02d}")
            item_dur.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(idx, 4, item_dur)

            # Cột 5: Trạng thái
            status = seg.get("status", "pending")
            if status == "ready":
                st_text = "🟢 Sẵn sàng"
                st_color = "#4ADE80"
            elif status == "generating":
                st_text = "⏳ Đang tạo..."
                st_color = "#38BDF8"
            elif status == "error":
                st_text = "🔴 Lỗi"
                st_color = "#EF4444"
            else:
                st_text = "🟡 Chờ tạo giọng"
                st_color = "#FACC15"
            item_st = QTableWidgetItem(st_text)
            item_st.setTextAlignment(Qt.AlignCenter)
            item_st.setForeground(QColor(st_color))
            self.table.setItem(idx, 5, item_st)

            # Cột 6: Thao tác
            act_widget = QWidget()
            act_layout = QHBoxLayout(act_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(6)

            # Nút tạo giọng (chỉ cho đoạn speech)
            if stype in ("lead_in", "news", "announcement", "speech"):
                btn_gen = QPushButton("🎙️")
                btn_gen.setToolTip("Tạo giọng đọc VieNeu-TTS cho riêng đoạn này")
                btn_gen.setProperty("class", "SecondaryBtn")
                btn_gen.setFixedSize(30, 28)
                btn_gen.clicked.connect(lambda _, i=idx: self.generate_segment_speech(i))
                act_layout.addWidget(btn_gen)

            # Nút sửa
            btn_edit = QPushButton("✏️")
            btn_edit.setToolTip("Chỉnh sửa nội dung phân đoạn")
            btn_edit.setProperty("class", "SecondaryBtn")
            btn_edit.setFixedSize(30, 28)
            btn_edit.clicked.connect(lambda _, i=idx: self.edit_segment(i))
            act_layout.addWidget(btn_edit)

            # Nút nhân bản
            btn_dup = QPushButton("📋")
            btn_dup.setToolTip("Nhân bản phân đoạn")
            btn_dup.setProperty("class", "SecondaryBtn")
            btn_dup.setFixedSize(30, 28)
            btn_dup.clicked.connect(lambda _, i=idx: self.duplicate_segment(i))
            act_layout.addWidget(btn_dup)

            # Nút nghe thử
            btn_p = QPushButton("▶")
            btn_p.setToolTip("Nghe thử phân đoạn")
            btn_p.setProperty("class", "SecondaryBtn")
            btn_p.setFixedSize(30, 28)
            btn_p.setEnabled(bool(seg.get("file_path") and Path(str(seg.get("file_path"))).is_file()))
            btn_p.clicked.connect(lambda _, p=seg.get("file_path"): self.play_segment_audio(p))
            act_layout.addWidget(btn_p)

            # Nút xóa
            btn_del = QPushButton("🗑️")
            btn_del.setToolTip("Xóa phân đoạn")
            btn_del.setProperty("class", "DangerBtn")
            btn_del.setFixedSize(30, 28)
            btn_del.clicked.connect(lambda _, i=idx: self.delete_segment(i))
            act_layout.addWidget(btn_del)

            self.table.setCellWidget(idx, 6, act_widget)

        # Cập nhật tổng thời lượng
        total_dur = sum(s.get("duration_sec", 0.0) + s.get("pause_after", 1.0) for s in self.segments)
        m_tot = int(total_dur // 60)
        s_tot = int(total_dur % 60)
        ready_count = sum(1 for s in self.segments if s.get("status") == "ready")
        self.lbl_list_status.setText(
            f"Tổng số phân đoạn: <b>{len(self.segments)}</b> (Đã sẵn sàng: <b>{ready_count}/{len(self.segments)}</b>) | "
            f"Ước tính tổng thời lượng chương trình: <b style='color:#22D3EE;'>{m_tot:02d}:{s_tot:02d}</b>"
        )

    def play_segment_audio(self, fpath: Optional[str]):
        """Phát âm thanh riêng của một phân đoạn."""
        if not fpath or not Path(fpath).is_file():
            return
        if audio_player.is_playing():
            audio_player.stop()
        audio_player.play(str(fpath))

    # =========================================================================
    # NHẠC NỀN & AUTO-DUCKING
    # =========================================================================
    def _on_bg_toggle(self, checked: bool):
        self.bg_ctrl_frame.setEnabled(checked)

    def _on_bg_vol_changed(self, v: int):
        self.lbl_vol_val.setText(f"{v}% (vừa phải, không át tiếng nói)")

    def _browse_bg_music(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self, "Chọn tệp bài hát / nhạc nền", "",
            "Âm thanh (*.mp3 *.wav *.flac *.ogg *.m4a);;Tất cả (*.*)"
        )
        if fpath:
            self.bg_path_edit.setText(fpath)
            self.chk_enable_bg.setChecked(True)
            self.bg_ctrl_frame.setEnabled(True)

    def _browse_intro_music(self):
        f, _ = QFileDialog.getOpenFileName(self, "Chọn nhạc mở đầu (Intro)", "", "Audio Files (*.mp3 *.wav *.flac *.ogg)")
        if f:
            self.edit_intro_music.setText(f)

    def _browse_outro_music(self):
        f, _ = QFileDialog.getOpenFileName(self, "Chọn nhạc kết thúc (Outro)", "", "Audio Files (*.mp3 *.wav *.flac *.ogg)")
        if f:
            self.edit_outro_music.setText(f)

    def _preview_bg_music(self):
        bg_p = self.bg_path_edit.text().strip()
        if not bg_p or not Path(bg_p).is_file():
            QMessageBox.information(self, "Chưa chọn nhạc", "Vui lòng chọn tệp nhạc nền trước khi nghe thử.")
            return
        self.play_segment_audio(bg_p)

    def _smart_broadcast_mix_dialog(self):
        """Phân tích cân bằng thông minh giữa giọng đọc và nhạc nền (Sprint 5 - 9.5)."""
        bg_path_str = self.bg_path_edit.text().strip()
        if not bg_path_str or not Path(bg_path_str).is_file():
            QMessageBox.warning(
                self,
                "Chưa Chọn Nhạc Nền",
                "Vui lòng chọn tệp nhạc nền trước khi thực hiện cân bằng âm thanh thông minh.",
            )
            return

        # Tìm phân đoạn giọng đọc đầu tiên có tệp âm thanh hợp lệ
        voice_path = None
        for s in self.segments:
            fp = s.get("file_path")
            if fp and Path(fp).is_file():
                voice_path = fp
                break

        if not voice_path:
            QMessageBox.warning(
                self,
                "Chưa Có Giọng Đọc",
                "Cần ít nhất một phân đoạn đã tạo âm thanh giọng đọc để phân tích cân bằng âm lượng.",
            )
            return

        try:
            from backend.intelligent_audio import smart_broadcast_mixer
            res = smart_broadcast_mixer.analyze_mix_balance(voice_path, bg_path_str)
            if not res.get("success"):
                QMessageBox.critical(self, "Lỗi Phân Tích", f"Không thể phân tích: {res.get('error')}")
                return

            s_db = res["suggested_bgm_volume_db"]
            # Chuyển đổi dB sang thang slider 5-50%
            pct = int(round((s_db + 35.0) * 2.0))
            pct = max(5, min(50, pct))

            msg = (
                f"📊 <b>KẾT QUẢ PHÂN TÍCH CÂN BẰNG PHÁT THANH:</b><br><br>"
                f"• Mức năng lượng giọng đọc: <b>{res['voice_rms_dbfs']:.1f} dBFS</b> (LUFS: {res['voice_lufs']:.1f})<br>"
                f"• Mức năng lượng nhạc nền: <b>{res['bgm_rms_dbfs']:.1f} dBFS</b><br>"
                f"• Khuyến nghị âm lượng BGM: <b>{s_db:+.1f} dB</b> (khoảng <b>{pct}%</b> slider)<br>"
                f"• Auto-Ducking khuyến nghị: <b>{res['ducking_attenuation_db']:.0f} dB</b> (Attack: {res['ducking_attack_ms']}ms, Release: {res['ducking_release_ms']}ms)<br><br>"
                f"<i>{res['explanation']}</i><br><br>"
                f"Bạn có muốn áp dụng mức âm lượng {pct}% và kích hoạt Auto-Ducking cho chương trình không?"
            )
            reply = QMessageBox.question(
                self,
                "🧠 Cân Bằng Thông Minh (Smart Broadcast Mixing)",
                msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self.bg_vol_slider.setValue(pct)
                self.chk_ducking.setChecked(True)
                self.chk_enable_bg.setChecked(True)
                notification_hub.notify_success.emit(
                    "Cân Bằng Thông Minh",
                    f"Đã thiết lập âm lượng nhạc nền {pct}% và kích hoạt Auto-Ducking."
                )
        except Exception as ex:
            QMessageBox.critical(self, "Lỗi Phân Tích", f"Đã xảy ra lỗi: {ex}")

    # =========================================================================
    # NGHE THỬ TOÀN BỘ CHƯƠNG TRÌNH (PREVIEW FULL PROGRAM)
    # =========================================================================
    def preview_full_program(self):
        """Trộn nhanh toàn bộ chương trình và phát xem trước (Non-blocking)."""
        if not self.segments and not self.edit_intro_music.text() and not self.edit_outro_music.text():
            QMessageBox.warning(self, "Kịch bản rỗng", "Vui lòng thêm ít nhất một phân đoạn vào kịch bản.")
            return

        # Kiểm tra xem có đoạn nào chưa có file audio không
        missing = [s["title"] for s in self.segments if s.get("type") != "silence" and (not s.get("file_path") or not Path(str(s["file_path"])).is_file())]
        if missing:
            ans = QMessageBox.question(
                self, "Chưa tạo giọng",
                f"Có {len(missing)} phân đoạn chưa được tạo giọng đọc. Bạn có muốn tự động tạo giọng ngay bây giờ không?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if ans == QMessageBox.Yes:
                self.generate_all_pending_speech()
                return

        self.status_lbl.setText("⏳ Đang chuẩn bị bản nghe thử toàn chương trình...")
        self.status_lbl.setStyleSheet("color: #38BDF8;")
        self.progress_bar.setVisible(True)

        temp_preview = Path(os.environ.get("TEMP", ".")) / "ttts_broadcast_preview.wav"
        bg_path = self.bg_path_edit.text().strip() if self.chk_enable_bg.isChecked() else None
        pct = self.bg_vol_slider.value()
        bg_db = -35.0 + (pct / 50.0) * 25.0

        def _stitch_fn():
            res = stitch_broadcast_project(
                segments=self.segments,
                output_path=temp_preview,
                out_format="wav",
                default_pause_sec=self.spin_default_pause.value(),
                bg_music_path=bg_path,
                bg_music_volume_db=bg_db,
                bg_music_loop=self.chk_loop_bg.isChecked(),
                bg_music_ducking=self.chk_ducking.isChecked(),
                intro_music_path=self.edit_intro_music.text().strip() or None,
                outro_music_path=self.edit_outro_music.text().strip() or None,
            )
            return res

        worker = FunctionTaskWorker(_stitch_fn)

        def _on_preview_ready(res):
            self.progress_bar.setVisible(False)
            if res.get("success"):
                self.status_lbl.setText(f"🎧 Đang phát bản nghe thử ({res.get('duration_sec', 0)}s)")
                self.status_lbl.setStyleSheet("color: #22C55E;")
                self.current_output_file = temp_preview
                self.player_card.setVisible(True)
                self.lbl_playing_title.setText(f"📻 NGHE THỬ: {self.title_edit.text().strip()}")
                self._start_playback(temp_preview)
            else:
                self.status_lbl.setText("❌ Không thể tạo bản nghe thử")
                self.status_lbl.setStyleSheet("color: #EF4444;")

        worker.finished_task.connect(_on_preview_ready)
        worker.start()

    # =========================================================================
    # XUẤT BẢN TIN PHÁT THANH HOÀN CHỈNH (PROGRAM EXPORT)
    # =========================================================================
    def export_broadcast_program(self):
        """Xuất bản tin ra đĩa cứng theo định dạng WAV hoặc MP3."""
        if not self.segments and not self.edit_intro_music.text() and not self.edit_outro_music.text():
            QMessageBox.warning(self, "Kịch bản rỗng", "Vui lòng thêm ít nhất một phân đoạn vào kịch bản.")
            return

        out_fmt = "mp3" if self.radio_mp3.isChecked() else "wav"
        title = self.title_edit.text().strip() or "Ban_tin_phat_thanh"

        bg_path = None
        pct = self.bg_vol_slider.value()
        bg_db = -35.0 + (pct / 50.0) * 25.0
        if self.chk_enable_bg.isChecked():
            p_str = self.bg_path_edit.text().strip()
            if not p_str or not Path(p_str).is_file():
                QMessageBox.warning(
                    self, "Chưa chọn bài nhạc nền",
                    "Bạn đã tích chọn 'Lồng bài hát / Nhạc nền' nhưng chưa chọn tệp âm thanh nào.\n"
                    "Vui lòng nhấn nút '📁 Chọn bài nhạc...' hoặc bỏ tích chọn."
                )
                return
            bg_path = p_str

        self.btn_export.setEnabled(False)
        self.btn_export.setText("⏳ Đang xuất bản tin...")
        self.progress_bar.setVisible(True)
        self.status_lbl.setText("Đang ghép nối đa tầng, hòa âm và xuất bản tin...")
        self.status_lbl.setStyleSheet("color: #38BDF8;")

        def _export_fn():
            res = tts_service.stitch_broadcast(
                segments=self.segments,
                title=title,
                out_format=out_fmt,
                default_pause_sec=self.spin_default_pause.value(),
                bg_music_path=bg_path,
                bg_music_volume_db=bg_db,
                bg_music_loop=self.chk_loop_bg.isChecked(),
                bg_music_ducking=self.chk_ducking.isChecked(),
                intro_music_path=self.edit_intro_music.text().strip() or None,
                outro_music_path=self.edit_outro_music.text().strip() or None,
            )
            # Nếu người dùng bật Nâng cấp DSP Mastering, áp dụng bộ lọc EBU R128 + Lọc nhiễu
            if res.get("success") and self.chk_dsp_mastering.isChecked():
                raw_fp = Path(res.get("file_path", ""))
                if raw_fp.is_file():
                    from backend.audio_enhancement import audio_enhancement_engine, PRESETS
                    dsp_out = raw_fp.parent / f"{raw_fp.stem}_mastered{raw_fp.suffix}"
                    pkey = self.combo_dsp_preset.currentData() if hasattr(self, "combo_dsp_preset") else "military_narration"
                    cfg = PRESETS.get(pkey, PRESETS.get("broadcast_military"))
                    dsp_res = audio_enhancement_engine.enhance_audio(
                        raw_fp, dsp_out, config=cfg
                    )
                    if dsp_res.get("success"):
                        res["file_path"] = str(dsp_out)
                        res["duration_sec"] = get_audio_duration_safe(dsp_out)
            return res

        worker = FunctionTaskWorker(_export_fn)

        def _on_export_done(res):
            self.btn_export.setEnabled(True)
            self.btn_export.setText("📻 XUẤT BẢN TIN PHÁT THANH HOÀN CHỈNH")
            self.progress_bar.setVisible(False)

            if not res.get("success"):
                err = res.get("error", "Lỗi xuất bản tin không xác định.")
                self.status_lbl.setText(f"❌ {err}")
                self.status_lbl.setStyleSheet("color: #EF4444;")
                QMessageBox.critical(self, "Lỗi xuất bản tin", err)
                return

            fpath = Path(res.get("file_path", ""))
            self.current_output_file = fpath
            dur = float(res.get("duration_sec", 0.0))
            m = int(dur // 60)
            s = int(dur % 60)

            self.status_lbl.setText(f"✅ Xuất bản tin thành công! Tệp: {fpath.name} ({m:02d}:{s:02d})")
            self.status_lbl.setStyleSheet("color: #22C55E; font-weight: bold;")
            notification_hub.notify_success.emit("Xuất Bản Tin Thành Công", f"Đã xuất bản tin: '{fpath.name}' ({m:02d}:{s:02d})")

            # Mở trình phát
            self.player_card.setVisible(True)
            self.lbl_playing_title.setText(f"📻 BẢN TIN ĐÃ XUẤT: {fpath.name}")
            self.lbl_time_display.setText(f"00:00 / {m:02d}:{s:02d}")
            self.timeline_slider.setValue(0)
            self.btn_play_pause.setText("▶ Phát Bản Tin")

            QMessageBox.information(
                self, "Xuất Bản Tin Thành Công",
                f"🎉 Bản tin phát thanh đã được tạo thành công!\n\n"
                f"• Tên tệp: {fpath.name}\n"
                f"• Thời lượng: {m:02d}:{s:02d}\n"
                f"• Định dạng: {out_fmt.upper()}\n"
                f"• Phân đoạn: {res.get('segments_count', len(self.segments))}\n\n"
                f"Bạn có thể nghe thử, sao chép file hoặc mở thư mục chứa ngay bên dưới."
            )

        worker.finished_task.connect(_on_export_done)
        worker.start()

    # =========================================================================
    # TRÌNH PHÁT BẢN TIN TÍCH HỢP (PLAYBACK CONTROLS)
    # =========================================================================
    def _start_playback(self, file_path: Path):
        self.stop_playback()
        ok = audio_player.play(str(file_path))
        if ok:
            self.play_timer.start()
            self.btn_play_pause.setText("⏸ Tạm dừng")

    def _toggle_playback(self):
        if not self.current_output_file or not self.current_output_file.is_file():
            return

        if audio_player.is_playing():
            audio_player.pause()
            self.play_timer.stop()
            self.btn_play_pause.setText("▶ Tiếp tục")
        elif audio_player.is_paused():
            audio_player.resume()
            self.play_timer.start()
            self.btn_play_pause.setText("⏸ Tạm dừng")
        else:
            self._start_playback(self.current_output_file)

    def stop_playback(self):
        if audio_player.is_playing() or audio_player.is_paused():
            audio_player.stop()
        self.play_timer.stop()
        self.btn_play_pause.setText("▶ Phát Bản Tin")
        self.timeline_slider.setValue(0)

    def _update_player_progress(self):
        if not audio_player.is_playing():
            self.play_timer.stop()
            self.btn_play_pause.setText("▶ Phát Bản Tin")
            self.timeline_slider.setValue(0)
            return

        pos_ms = audio_player.get_position_ms()
        dur_ms = audio_player.get_duration_ms()

        if dur_ms > 0:
            frac = pos_ms / float(dur_ms)
            self.timeline_slider.setValue(int(frac * 1000))

            cur_s = int(pos_ms / 1000)
            tot_s = int(dur_ms / 1000)
            self.lbl_time_display.setText(f"{cur_s//60:02d}:{cur_s%60:02d} / {tot_s//60:02d}:{tot_s%60:02d}")

    def _on_seek_moved(self, val: int):
        dur_ms = audio_player.get_duration_ms()
        if dur_ms > 0:
            target_ms = int((val / 1000.0) * dur_ms)
            audio_player.seek_ms(target_ms)

    def _copy_output_to_clipboard(self):
        if not self.current_output_file or not self.current_output_file.is_file():
            return
        clipboard = QApplication.clipboard()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.current_output_file))])
        clipboard.setMimeData(mime)
        notification_hub.notify_success.emit("Đã Chép File", f"Đã chép '{self.current_output_file.name}' vào bộ nhớ tạm.")

    def _save_output_as(self):
        if not self.current_output_file or not self.current_output_file.is_file():
            return
        ext = self.current_output_file.suffix
        fpath, _ = QFileDialog.getSaveFileName(
            self, "Lưu bản tin phát thanh thành...", self.current_output_file.name,
            f"Âm thanh (*{ext});;Tất cả tệp (*.*)"
        )
        if fpath:
            shutil.copy2(str(self.current_output_file), fpath)
            QMessageBox.information(self, "Đã lưu", f"Đã lưu tệp bản tin tại:\n{fpath}")

    def _open_output_file_folder(self):
        if self.current_output_file and self.current_output_file.is_file():
            tts_service.open_file_in_explorer(self.current_output_file)
        else:
            tts_service.open_output_folder()

    # =========================================================================
    # PROGRAMMATIC & TESTABLE API (BROADCAST STUDIO 2.0)
    # =========================================================================
    def add_segment(self, segment_dict: Dict[str, Any]) -> str:
        """Thêm một phân đoạn có cấu trúc vào bản tin (trả về segment_id)."""
        seg = dict(segment_dict)
        if "id" not in seg or not seg["id"]:
            seg["id"] = f"seg_{int(time.time())}_{uuid.uuid4().hex[:4]}"
        if "type" not in seg:
            seg["type"] = "news"
        if "title" not in seg:
            type_name, _ = SEGMENT_TYPES.get(seg["type"], ("Phân đoạn", "#FFF"))
            seg["title"] = f"{type_name} {len(self.segments)+1}"
        if "duration_sec" not in seg:
            fpath = seg.get("file_path")
            if fpath and Path(fpath).is_file():
                seg["duration_sec"] = get_audio_duration_safe(Path(fpath))
            else:
                seg["duration_sec"] = 0.0
        if "pause_after" not in seg:
            seg["pause_after"] = self.spin_default_pause.value()
        if "status" not in seg:
            seg["status"] = "ready" if seg.get("file_path") and Path(str(seg.get("file_path"))).is_file() else "pending"
        self.segments.append(seg)
        self._refresh_table()
        return seg["id"]

    def update_segment(self, idx: int, **kwargs):
        """Cập nhật thuộc tính của phân đoạn thứ idx."""
        if 0 <= idx < len(self.segments):
            seg = self.segments[idx]
            for k, v in kwargs.items():
                if k in ("text", "voice_id", "speed") and seg.get(k) != v:
                    seg["is_modified"] = True
                    seg["status"] = "pending"
                seg[k] = v
            self._refresh_table()

    def reorder_segments(self, from_idx: int, to_idx: int):
        """Thay đổi thứ tự phân đoạn từ from_idx sang to_idx."""
        if 0 <= from_idx < len(self.segments) and 0 <= to_idx < len(self.segments):
            item = self.segments.pop(from_idx)
            self.segments.insert(to_idx, item)
            self._refresh_table()

    def generate_segment_speech_sync(self, idx: int) -> bool:
        """Tạo giọng đọc đồng bộ cho riêng 1 phân đoạn (cho kiểm thử tự động)."""
        if not (0 <= idx < len(self.segments)):
            return False
        seg = self.segments[idx]
        text = seg.get("text", "").strip()
        if not text:
            return False
        voice_id = seg.get("voice_id", "hn_nam_quan_doi")
        speed = float(seg.get("speed", 1.0))
        seg_id = seg["id"]
        res = tts_service.synthesize_text(
            text=text,
            voice_id=voice_id,
            speed=speed,
            out_format="wav",
            filename_prefix=f"broadcast_seg_{seg_id}",
        )
        if res.get("success") and res.get("file_path"):
            seg["file_path"] = res["file_path"]
            seg["duration_sec"] = float(res.get("duration_sec", 0.0))
            seg["status"] = "ready"
            seg["is_modified"] = False
            self._refresh_table()
            return True
        else:
            seg["status"] = "error"
            seg["error_msg"] = res.get("error", "Lỗi tạo giọng")
            self._refresh_table()
            return False

    def get_total_duration(self) -> float:
        """Tính toán tổng thời lượng ước tính của toàn bộ chương trình."""
        return sum(s.get("duration_sec", 0.0) + s.get("pause_after", 1.0) for s in self.segments)

    def set_bg_music(self, path: str, vol_pct: int = 15, loop: bool = True, ducking: bool = True):
        """Thiết lập nhạc nền chương trình."""
        self.bg_path_edit.setText(path)
        self.chk_enable_bg.setChecked(bool(path))
        self.bg_vol_slider.setValue(vol_pct)
        self.chk_loop_bg.setChecked(loop)
        self.chk_ducking.setChecked(ducking)

    def set_intro_music(self, path: str):
        """Thiết lập nhạc mở đầu."""
        self.edit_intro_music.setText(path)

    def set_outro_music(self, path: str):
        """Thiết lập nhạc kết thúc."""
        self.edit_outro_music.setText(path)

    def export_program_direct(self, output_path: Union[str, Path], out_format: str = "wav") -> Dict[str, Any]:
        """Xuất bản tin trực tiếp ra file đích (không mở popup)."""
        out_p = Path(output_path).resolve()
        bg_path = self.bg_path_edit.text().strip() if self.chk_enable_bg.isChecked() else None
        pct = self.bg_vol_slider.value()
        bg_db = -35.0 + (pct / 50.0) * 25.0

        res = stitch_broadcast_project(
            segments=self.segments,
            output_path=out_p,
            out_format=out_format,
            default_pause_sec=self.spin_default_pause.value(),
            bg_music_path=bg_path,
            bg_music_volume_db=bg_db,
            bg_music_loop=self.chk_loop_bg.isChecked(),
            bg_music_ducking=self.chk_ducking.isChecked(),
            intro_music_path=self.edit_intro_music.text().strip() or None,
            outro_music_path=self.edit_outro_music.text().strip() or None,
        )
        if res.get("success"):
            self.current_output_file = out_p
        return res
