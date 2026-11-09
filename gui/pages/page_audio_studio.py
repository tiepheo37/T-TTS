"""gui/pages/page_audio_studio.py — PHÂN HỆ BIÊN TẬP ÂM THANH CHUYÊN NGHIỆP (AUDIO STUDIO)
=============================================================================
Trang biên tập âm thanh tích hợp:
- Dạng sóng waveform thời gian thực, timeline trực quan, zoom in/out/fit.
- Cắt (Cut), Sao chép (Copy), Dán (Paste), Xóa (Delete), Trim, Tách (Split).
- Chèn khoảng lặng (Insert Silence), Ghép file (Join Audio).
- Điều chỉnh âm lượng (Gain dB), Mờ đầu (Fade In), Mờ cuối (Fade Out), Chuẩn hóa (Normalize).
- Lồng nhạc nền (Background Music) với âm lượng tùy chỉnh và lặp lại tự động.
- Quản lý dự án âm thanh (New, Open, Save, Relink Source) độc lập qua project_manager.
- Phát âm thanh native, điều khiển âm lượng, tốc độ và tua thời gian thực.
"""

from __future__ import annotations

import os
import sys
import tempfile
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.ffmpeg_bootstrap import initialize_ffmpeg
initialize_ffmpeg()

from pydub import AudioSegment
from pydub.effects import normalize as pydub_normalize

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QCursor, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QSlider,
    QComboBox,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QFrame,
    QScrollArea,
    QProgressBar,
    QDialog,
    QLineEdit,
    QScrollBar,
)

from backend.audio_utils import (
    load_audio_segment_safe,
    save_wav,
    wav_to_mp3,
    slice_audio,
    apply_audio_gain_and_fade,
    get_audio_duration_safe,
)
from backend.audio_player import audio_player
from backend.project_manager import project_manager
from backend.service import tts_service
from gui.waveform_widget import WaveformWidget, format_ms_to_time
from gui.notification_hub import notification_hub


class BGMConfigDialog(QDialog):
    """Hộp thoại cấu hình lồng nhạc nền (Background Music)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Cấu Hình Lồng Nhạc Nền (Background Music)")
        self.setFixedSize(520, 280)
        self.setStyleSheet("""
            QDialog { background-color: #162E1A; color: #FFFFFF; }
            QLabel { color: #CBD5E1; font-size: 13px; }
            QLineEdit { background-color: #0F1E11; color: #FFFFFF; border: 1px solid #3B533E; padding: 6px; border-radius: 4px; }
            QPushButton { background-color: #2D5A27; color: #FFFFFF; border: 1px solid #4ADE80; padding: 6px 14px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #386E31; }
        """)

        self.selected_file: Optional[Path] = None
        self.volume_db: float = -18.0
        self.auto_loop: bool = True

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 18, 20, 18)

        layout.addWidget(QLabel("<b>Chọn tệp nhạc nền (MP3, WAV, FLAC, OGG):</b>"))
        f_row = QHBoxLayout()
        self.txt_path = QLineEdit()
        self.txt_path.setReadOnly(True)
        self.txt_path.setPlaceholderText("Chưa chọn tệp nhạc...")
        f_row.addWidget(self.txt_path)

        btn_browse = QPushButton("Chọn File...")
        btn_browse.clicked.connect(self._browse_file)
        f_row.addWidget(btn_browse)
        layout.addLayout(f_row)

        layout.addWidget(QLabel("<b>Âm lượng nhạc nền so với giọng đọc:</b>"))
        v_row = QHBoxLayout()
        self.slider_vol = QSlider(Qt.Horizontal)
        self.slider_vol.setRange(-36, 0)
        self.slider_vol.setValue(int(self.volume_db))
        self.lbl_vol = QLabel(f"{int(self.volume_db)} dB (nhỏ hơn giọng đọc)")
        self.slider_vol.valueChanged.connect(lambda v: self.lbl_vol.setText(f"{v} dB (nhỏ hơn giọng đọc)"))
        v_row.addWidget(self.slider_vol, 1)
        v_row.addWidget(self.lbl_vol)
        layout.addLayout(v_row)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_ok = QPushButton("Áp Dụng Lồng Nhạc")
        btn_ok.setStyleSheet("background-color: #D4AF37; color: #000000; border: none;")
        btn_ok.clicked.connect(self._on_apply)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def _browse_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Chọn bài hát / nhạc nền", "", "Audio Files (*.mp3 *.wav *.flac *.ogg);;All Files (*.*)")
        if f:
            self.selected_file = Path(f)
            self.txt_path.setText(f)

    def _on_apply(self):
        if not self.selected_file or not self.selected_file.is_file():
            QMessageBox.warning(self, "Chưa chọn tệp", "Vui lòng chọn tệp nhạc nền hợp lệ.")
            return
        self.volume_db = float(self.slider_vol.value())
        self.accept()


class AudioStudioExportDialog(QDialog):
    """Hộp thoại cấu hình xuất bản âm thanh nâng cao (WAV/MP3 + Chuẩn hóa LUFS / Peak)."""

    def __init__(self, default_name: str, default_dir: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Xuất Bản Âm Thanh (Audio Export Master)")
        self.setFixedSize(560, 360)
        self.setStyleSheet("""
            QDialog { background-color: #122215; color: #FFFFFF; }
            QLabel { color: #CBD5E1; font-size: 13px; }
            QLineEdit { background-color: #0F1E11; color: #FFFFFF; border: 1px solid #3B533E; padding: 6px; border-radius: 4px; }
            QComboBox { background-color: #0F1E11; color: #FFFFFF; border: 1px solid #3B533E; padding: 6px; border-radius: 4px; }
            QPushButton { background-color: #2D5A27; color: #FFFFFF; border: 1px solid #4ADE80; padding: 6px 14px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #386E31; }
        """)

        self.default_dir = default_dir
        self.export_path: Optional[Path] = None
        self.format_type: str = "wav"
        self.mastering_mode: str = "lufs_voice"
        self.target_lufs: float = -16.0
        self.bitrate_kbps: int = 192

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 18, 20, 18)

        # 1. Đường dẫn xuất
        layout.addWidget(QLabel("<b>Đường dẫn tệp xuất ra:</b>"))
        p_row = QHBoxLayout()
        self.txt_path = QLineEdit()
        init_file = default_dir / f"{default_name}.wav"
        self.txt_path.setText(str(init_file))
        p_row.addWidget(self.txt_path, 1)

        btn_browse = QPushButton("Chọn...")
        btn_browse.clicked.connect(self._browse_save_path)
        p_row.addWidget(btn_browse)
        layout.addLayout(p_row)

        # 2. Định dạng & Bitrate
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Định dạng:"))
        self.combo_fmt = QComboBox()
        self.combo_fmt.addItem("WAV (Không nén PCM 16-bit 48kHz)", "wav")
        self.combo_fmt.addItem("MP3 (Nén âm thanh tiêu chuẩn)", "mp3")
        self.combo_fmt.currentIndexChanged.connect(self._on_fmt_changed)
        fmt_row.addWidget(self.combo_fmt, 1)

        self.lbl_bitrate = QLabel("Bitrate:")
        self.combo_bitrate = QComboBox()
        self.combo_bitrate.addItem("128 kbps", 128)
        self.combo_bitrate.addItem("192 kbps (Chuẩn)", 192)
        self.combo_bitrate.addItem("256 kbps", 256)
        self.combo_bitrate.addItem("320 kbps (Cao nhất)", 320)
        self.combo_bitrate.setCurrentIndex(1)
        self.lbl_bitrate.setVisible(False)
        self.combo_bitrate.setVisible(False)
        fmt_row.addWidget(self.lbl_bitrate)
        fmt_row.addWidget(self.combo_bitrate)
        layout.addLayout(fmt_row)

        # 3. Chuẩn hóa âm lượng (Mastering Normalization)
        layout.addWidget(QLabel("<b>Chuẩn hóa âm lượng đầu ra (Loudness Mastering):</b>"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("✨ EBU R128: -16.0 LUFS (Chuẩn Giọng đọc / Podcast)", "lufs_voice")
        self.combo_mode.addItem("📻 EBU R128: -23.0 LUFS (Chuẩn Phát thanh Châu Âu / Quốc tế)", "lufs_broadcast")
        self.combo_mode.addItem("📺 EBU R128: -24.0 LUFS (Chuẩn Truyền hình ATSC A/85)", "lufs_tv")
        self.combo_mode.addItem("📊 Peak Normalization (-0.1 dBFS)", "peak")
        self.combo_mode.addItem("🔘 Giữ nguyên âm lượng gốc (Không can thiệp)", "none")
        layout.addWidget(self.combo_mode)

        layout.addStretch()

        # Nút hành động
        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Hủy Bỏ")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_box.addStretch()

        btn_ok = QPushButton("🚀 Xuất Bản Tệp Âm Thanh")
        btn_ok.setProperty("class", "PrimaryBtn")
        btn_ok.clicked.connect(self._on_export)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def _on_fmt_changed(self):
        is_mp3 = self.combo_fmt.currentData() == "mp3"
        self.lbl_bitrate.setVisible(is_mp3)
        self.combo_bitrate.setVisible(is_mp3)
        curr = Path(self.txt_path.text())
        new_ext = ".mp3" if is_mp3 else ".wav"
        self.txt_path.setText(str(curr.with_suffix(new_ext)))

    def _browse_save_path(self):
        is_mp3 = self.combo_fmt.currentData() == "mp3"
        filter_str = "MP3 Audio (*.mp3);;All Files (*.*)" if is_mp3 else "WAV Audio (*.wav);;All Files (*.*)"
        f, _ = QFileDialog.getSaveFileName(self, "Chọn nơi lưu tệp xuất", self.txt_path.text(), filter_str)
        if f:
            self.txt_path.setText(f)

    def _on_export(self):
        p_str = self.txt_path.text().strip()
        if not p_str:
            QMessageBox.warning(self, "Lỗi đường dẫn", "Vui lòng nhập đường dẫn tệp xuất.")
            return
        self.export_path = Path(p_str)
        self.format_type = self.combo_fmt.currentData()
        self.mastering_mode = self.combo_mode.currentData()
        self.bitrate_kbps = self.combo_bitrate.currentData() if self.format_type == "mp3" else 192

        if self.mastering_mode == "lufs_voice":
            self.target_lufs = -16.0
        elif self.mastering_mode == "lufs_broadcast":
            self.target_lufs = -23.0
        elif self.mastering_mode == "lufs_tv":
            self.target_lufs = -24.0

        self.accept()


class PageAudioStudio(QWidget):
    """Trang Phân Hệ Biên Tập Âm Thanh Chuyên Nghiệp (Audio Studio)."""

    send_to_broadcast = Signal(dict)
    send_to_schedule = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # Trạng thái dự án âm thanh
        self.current_project_id: Optional[str] = None
        self.current_project_name: str = "Dự án mới"
        self.current_file_path: Optional[Path] = None

        # Đối tượng AudioSegment đang chỉnh sửa & Stack Undo/Redo
        self.current_audio: Optional[AudioSegment] = None
        self.clipboard_audio: Optional[AudioSegment] = None
        self.undo_stack: List[AudioSegment] = []
        self.redo_stack: List[AudioSegment] = []
        self._max_history = 15

        # Tệp tạm preview phát âm thanh
        self._temp_preview_wav = Path(tempfile.gettempdir()) / "ttts_audio_studio_preview.wav"
        self._syncing_scrollbar: bool = False

        # Timer cập nhật vị trí Playhead khi phát
        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(40)  # ~25 FPS
        self._playback_timer.timeout.connect(self._on_playback_tick)

        self._build_ui()
        self._update_ui_state()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        # 1. THANH CÔNG CỤ (TOOLBAR)
        tb_card = QFrame()
        tb_card.setProperty("class", "CardFrame")
        tb_card.setStyleSheet("background-color: #122215; border: 1px solid #27472A; border-radius: 6px;")
        tb_layout = QHBoxLayout(tb_card)
        tb_layout.setContentsMargins(10, 8, 10, 8)
        tb_layout.setSpacing(6)

        self.btn_new = QPushButton("📄 Dự Án Mới")
        self.btn_new.setProperty("class", "SecondaryBtn")
        self.btn_new.clicked.connect(self.new_project)
        tb_layout.addWidget(self.btn_new)

        self.btn_open_proj = QPushButton("📂 Mở Dự Án")
        self.btn_open_proj.setProperty("class", "SecondaryBtn")
        self.btn_open_proj.clicked.connect(self.open_project_dialog)
        tb_layout.addWidget(self.btn_open_proj)

        self.btn_save_proj = QPushButton("💾 Lưu Dự Án")
        self.btn_save_proj.setProperty("class", "SecondaryBtn")
        self.btn_save_proj.clicked.connect(self.save_project)
        tb_layout.addWidget(self.btn_save_proj)

        # Separator line
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("color: #27472A;")
        tb_layout.addWidget(sep1)

        self.btn_import = QPushButton("📥 Nhập Âm Thanh")
        self.btn_import.setProperty("class", "PrimaryBtn")
        self.btn_import.clicked.connect(self.import_audio_dialog)
        tb_layout.addWidget(self.btn_import)

        self.btn_export = QPushButton("📤 Xuất Âm Thanh")
        self.btn_export.setProperty("class", "PrimaryBtn")
        self.btn_export.clicked.connect(self.export_audio_dialog)
        tb_layout.addWidget(self.btn_export)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color: #27472A;")
        tb_layout.addWidget(sep2)

        self.btn_undo = QPushButton("↩ Hoàn Tác")
        self.btn_undo.setProperty("class", "SecondaryBtn")
        self.btn_undo.clicked.connect(self.undo)
        tb_layout.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("↪ Làm Lại")
        self.btn_redo.setProperty("class", "SecondaryBtn")
        self.btn_redo.clicked.connect(self.redo)
        tb_layout.addWidget(self.btn_redo)

        sep2b = QFrame()
        sep2b.setFrameShape(QFrame.VLine)
        sep2b.setStyleSheet("color: #27472A;")
        tb_layout.addWidget(sep2b)

        self.btn_send_broadcast = QPushButton("📻 Gửi sang Bản Tin")
        self.btn_send_broadcast.setProperty("class", "SecondaryBtn")
        self.btn_send_broadcast.setToolTip("Gửi âm thanh hiện tại sang Bản Tin Phát Thanh")
        self.btn_send_broadcast.clicked.connect(self._on_send_to_broadcast)
        tb_layout.addWidget(self.btn_send_broadcast)

        self.btn_send_schedule = QPushButton("📅 Lập Lịch Phát")
        self.btn_send_schedule.setProperty("class", "SecondaryBtn")
        self.btn_send_schedule.setToolTip("Lập lịch phát thanh tự động cho tệp âm thanh này")
        self.btn_send_schedule.clicked.connect(self._on_send_to_schedule)
        tb_layout.addWidget(self.btn_send_schedule)

        tb_layout.addStretch()

        self.lbl_project_title = QLabel(f"Dự án: <b style='color: #FFD700;'>{self.current_project_name}</b>")
        self.lbl_project_title.setStyleSheet("color: #CBD5E1; font-size: 13px; border: none;")
        tb_layout.addWidget(self.lbl_project_title)

        main_layout.addWidget(tb_card)

        # 2. KHU VỰC DẠNG SÓNG WAVEFORM & ZOOM
        wave_box = QFrame()
        wave_box.setStyleSheet("background-color: #071308; border: 1px solid #27472A; border-radius: 6px;")
        wb_layout = QVBoxLayout(wave_box)
        wb_layout.setContentsMargins(6, 6, 6, 6)
        wb_layout.setSpacing(4)

        # Header waveform: Thời lượng & nút zoom
        w_header = QHBoxLayout()
        self.lbl_time_status = QLabel("Vị trí: 00:00.0 / 00:00.0")
        self.lbl_time_status.setStyleSheet("color: #22D3EE; font-weight: bold; font-size: 13px; border: none;")
        w_header.addWidget(self.lbl_time_status)

        self.lbl_selection_status = QLabel("Vùng chọn: Chưa chọn")
        self.lbl_selection_status.setStyleSheet("color: #94A3B8; font-size: 12px; border: none;")
        w_header.addWidget(self.lbl_selection_status)
        w_header.addStretch()

        btn_zoom_in = QPushButton("🔍+")
        btn_zoom_in.setFixedSize(32, 26)
        btn_zoom_in.setProperty("class", "SecondaryBtn")
        btn_zoom_in.setToolTip("Phóng to dạng sóng (hoặc cuộn chuột lên)")
        btn_zoom_in.clicked.connect(lambda: self.waveform.zoom_in())
        w_header.addWidget(btn_zoom_in)

        btn_zoom_out = QPushButton("🔍-")
        btn_zoom_out.setFixedSize(32, 26)
        btn_zoom_out.setProperty("class", "SecondaryBtn")
        btn_zoom_out.setToolTip("Thu nhỏ dạng sóng (hoặc cuộn chuột xuống)")
        btn_zoom_out.clicked.connect(lambda: self.waveform.zoom_out())
        w_header.addWidget(btn_zoom_out)

        btn_zoom_fit = QPushButton("↔ Fit")
        btn_zoom_fit.setFixedSize(45, 26)
        btn_zoom_fit.setProperty("class", "SecondaryBtn")
        btn_zoom_fit.setToolTip("Vừa khung toàn bộ âm thanh")
        btn_zoom_fit.clicked.connect(lambda: self.waveform.zoom_fit())
        w_header.addWidget(btn_zoom_fit)

        btn_zoom_reset = QPushButton("🔄 Reset")
        btn_zoom_reset.setFixedSize(60, 26)
        btn_zoom_reset.setProperty("class", "SecondaryBtn")
        btn_zoom_reset.setToolTip("Đặt lại toàn bộ phóng to / thu nhỏ")
        btn_zoom_reset.clicked.connect(lambda: self.waveform.reset_zoom())
        w_header.addWidget(btn_zoom_reset)

        wb_layout.addLayout(w_header)

        # Widget Waveform Canvas
        self.waveform = WaveformWidget(self)
        self.waveform.playhead_moved.connect(self._on_playhead_moved)
        self.waveform.selection_changed.connect(self._on_selection_changed)
        wb_layout.addWidget(self.waveform, 1)

        # Thanh cuộn ngang khi zoom (Horizontal Scrollbar)
        self.wave_scrollbar = QScrollBar(Qt.Horizontal)
        self.wave_scrollbar.setFixedHeight(12)
        self.wave_scrollbar.setStyleSheet("""
            QScrollBar:horizontal {
                background: #0B190D;
                height: 12px;
                margin: 0px;
                border: 1px solid #1E3A22;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #2D5A27;
                min-width: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #4ADE80;
            }
        """)
        self.wave_scrollbar.valueChanged.connect(self._on_wave_scrollbar_changed)
        self.waveform.view_range_changed.connect(self._on_view_range_changed)
        wb_layout.addWidget(self.wave_scrollbar)

        main_layout.addWidget(wave_box, 1)

        # 3. KHU VỰC ĐIỀU KHIỂN PHÁT (PLAYBACK CONTROLS)
        ctrl_card = QFrame()
        ctrl_card.setStyleSheet("background-color: #122215; border: 1px solid #27472A; border-radius: 6px; padding: 6px;")
        cb_layout = QHBoxLayout(ctrl_card)
        cb_layout.setSpacing(10)

        self.btn_play = QPushButton("▶ Phát")
        self.btn_play.setProperty("class", "PrimaryBtn")
        self.btn_play.setMinimumWidth(80)
        self.btn_play.clicked.connect(self.play_audio)
        cb_layout.addWidget(self.btn_play)

        self.btn_pause = QPushButton("⏸ Tạm Dừng")
        self.btn_pause.setProperty("class", "SecondaryBtn")
        self.btn_pause.clicked.connect(self.pause_audio)
        cb_layout.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("⏹ Dừng")
        self.btn_stop.setProperty("class", "SecondaryBtn")
        self.btn_stop.clicked.connect(self.stop_audio)
        cb_layout.addWidget(self.btn_stop)

        # Thanh trượt tua thời gian (Seeker Slider)
        self.slider_seek = QSlider(Qt.Horizontal)
        self.slider_seek.setRange(0, 1000)
        self.slider_seek.sliderMoved.connect(self._on_slider_seek_moved)
        cb_layout.addWidget(self.slider_seek, 1)

        # Âm lượng
        cb_layout.addWidget(QLabel("Âm lượng:"))
        self.slider_vol = QSlider(Qt.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(100)
        self.slider_vol.setFixedWidth(90)
        self.slider_vol.valueChanged.connect(self._on_volume_changed)
        cb_layout.addWidget(self.slider_vol)

        main_layout.addWidget(ctrl_card)

        # 4. THANH CÔNG CỤ BIÊN TẬP (EDITING TOOLS)
        tools_card = QFrame()
        tools_card.setStyleSheet("background-color: #162E1A; border: 1px solid #3B533E; border-radius: 6px; padding: 6px;")
        t_layout = QHBoxLayout(tools_card)
        t_layout.setSpacing(6)

        self.btn_cut = QPushButton("✂ Cắt")
        self.btn_cut.setProperty("class", "SecondaryBtn")
        self.btn_cut.clicked.connect(self.cut_selection)
        t_layout.addWidget(self.btn_cut)

        self.btn_copy = QPushButton("📋 Sao Chép")
        self.btn_copy.setProperty("class", "SecondaryBtn")
        self.btn_copy.clicked.connect(self.copy_selection)
        t_layout.addWidget(self.btn_copy)

        self.btn_paste = QPushButton("📥 Dán")
        self.btn_paste.setProperty("class", "SecondaryBtn")
        self.btn_paste.clicked.connect(self.paste_audio)
        t_layout.addWidget(self.btn_paste)

        self.btn_del = QPushButton("🗑 Xóa Vùng")
        self.btn_del.setProperty("class", "SecondaryBtn")
        self.btn_del.clicked.connect(self.delete_selection)
        t_layout.addWidget(self.btn_del)

        self.btn_trim = QPushButton("✂ Giữ Vùng Chọn")
        self.btn_trim.setProperty("class", "SecondaryBtn")
        self.btn_trim.clicked.connect(self.trim_selection)
        t_layout.addWidget(self.btn_trim)

        self.btn_split = QPushButton("⚡ Tách Đoạn")
        self.btn_split.setProperty("class", "SecondaryBtn")
        self.btn_split.clicked.connect(self.split_at_playhead)
        t_layout.addWidget(self.btn_split)

        self.btn_silence = QPushButton("🔇 Chèn Nghỉ")
        self.btn_silence.setProperty("class", "SecondaryBtn")
        self.btn_silence.clicked.connect(self.insert_silence_dialog)
        t_layout.addWidget(self.btn_silence)

        self.btn_join = QPushButton("➕ Ghép Thêm")
        self.btn_join.setProperty("class", "SecondaryBtn")
        self.btn_join.clicked.connect(self.join_audio_dialog)
        t_layout.addWidget(self.btn_join)

        # Hiệu ứng âm thanh
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.VLine)
        sep3.setStyleSheet("color: #27472A;")
        t_layout.addWidget(sep3)

        self.btn_gain = QPushButton("🔊 Âm Lượng (dB)")
        self.btn_gain.setProperty("class", "SecondaryBtn")
        self.btn_gain.clicked.connect(self.adjust_gain_dialog)
        t_layout.addWidget(self.btn_gain)

        self.btn_fade_in = QPushButton("📈 Mờ Đầu")
        self.btn_fade_in.setProperty("class", "SecondaryBtn")
        self.btn_fade_in.clicked.connect(lambda: self.apply_fade(True))
        t_layout.addWidget(self.btn_fade_in)

        self.btn_fade_out = QPushButton("📉 Mờ Cuối")
        self.btn_fade_out.setProperty("class", "SecondaryBtn")
        self.btn_fade_out.clicked.connect(lambda: self.apply_fade(False))
        t_layout.addWidget(self.btn_fade_out)

        self.btn_normalize = QPushButton("🎚 Chuẩn Hóa Peak")
        self.btn_normalize.setProperty("class", "SecondaryBtn")
        self.btn_normalize.setToolTip("Chuẩn hóa âm lượng đỉnh Peak (-0.1 dBFS)")
        self.btn_normalize.clicked.connect(self.normalize_audio)
        t_layout.addWidget(self.btn_normalize)

        self.btn_bgm = QPushButton("🎵 Nhạc Nền")
        self.btn_bgm.setProperty("class", "SecondaryBtn")
        self.btn_bgm.clicked.connect(self.mix_bgm_dialog)
        t_layout.addWidget(self.btn_bgm)

        self.btn_dsp = QPushButton("✨ Nâng Cấp DSP & LUFS")
        self.btn_dsp.setProperty("class", "SecondaryBtn")
        self.btn_dsp.setToolTip("Giảm nhiễu, Voice EQ 6 dải, De-Esser, Compressor và chuẩn hóa EBU R128 LUFS")
        self.btn_dsp.clicked.connect(self.enhance_audio_dialog)
        t_layout.addWidget(self.btn_dsp)

        self.btn_analyze = QPushButton("🔍 Phân Tích Âm Thanh")
        self.btn_analyze.setProperty("class", "SecondaryBtn")
        self.btn_analyze.setToolTip("Đo đạc 8 thông số âm học LUFS, Clipping, Noise, Silence và gợi ý tối ưu")
        self.btn_analyze.clicked.connect(self.analyze_audio_dialog)
        t_layout.addWidget(self.btn_analyze)

        t_layout.addStretch()
        main_layout.addWidget(tools_card)

        # 5. KHU VỰC THÔNG TIN TỆP (AUDIO METADATA BAR)
        info_card = QFrame()
        info_card.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 4px; padding: 4px;")
        ib_layout = QHBoxLayout(info_card)
        ib_layout.setContentsMargins(8, 4, 8, 4)
        ib_layout.setSpacing(18)

        self.lbl_info_filename = QLabel("Tệp: Chưa nạp")
        self.lbl_info_sr = QLabel("Tần số: —")
        self.lbl_info_channels = QLabel("Số kênh: —")
        self.lbl_info_dur = QLabel("Thời lượng: —")
        self.lbl_info_size = QLabel("Dung lượng: —")

        for lbl in (self.lbl_info_filename, self.lbl_info_sr, self.lbl_info_channels, self.lbl_info_dur, self.lbl_info_size):
            lbl.setStyleSheet("color: #94A3B8; font-size: 11px; border: none;")
            ib_layout.addWidget(lbl)
        ib_layout.addStretch()
        main_layout.addWidget(info_card)

    def _push_undo_state(self):
        """Lưu trạng thái hiện tại vào ngăn xếp Hoàn Tác (Undo) có kiểm soát giới hạn RAM."""
        if self.current_audio is not None:
            dur_ms = len(self.current_audio)
            if dur_ms > 15 * 60 * 1000:
                limit = 5
            elif dur_ms > 5 * 60 * 1000:
                limit = 8
            else:
                limit = self._max_history
            self.undo_stack.append(self.current_audio)
            while len(self.undo_stack) > limit:
                self.undo_stack.pop(0)
            self.redo_stack.clear()
            self._update_ui_state()

    def _update_ui_state(self):
        has_audio = self.current_audio is not None
        self.btn_export.setEnabled(has_audio)
        self.btn_send_broadcast.setEnabled(has_audio)
        self.btn_send_schedule.setEnabled(has_audio)
        self.btn_save_proj.setEnabled(has_audio)
        self.btn_play.setEnabled(has_audio)
        self.btn_pause.setEnabled(has_audio)
        self.btn_stop.setEnabled(has_audio)
        self.slider_seek.setEnabled(has_audio)

        for btn in (
            self.btn_cut, self.btn_copy, self.btn_del, self.btn_trim,
            self.btn_split, self.btn_silence, self.btn_join,
            self.btn_gain, self.btn_fade_in, self.btn_fade_out,
            self.btn_normalize, self.btn_bgm, self.btn_dsp, self.btn_analyze
        ):
            btn.setEnabled(has_audio)

        self.btn_paste.setEnabled(has_audio and self.clipboard_audio is not None)
        self.btn_undo.setEnabled(len(self.undo_stack) > 0)
        self.btn_redo.setEnabled(len(self.redo_stack) > 0)
        self.lbl_project_title.setText(f"Dự án: <b style='color: #FFD700;'>{self.current_project_name}</b>")

    def _refresh_audio_view(self, update_preview: bool = True):
        """Đồng bộ AudioSegment với Waveform widget và nhãn thông tin."""
        if self.current_audio is None:
            self.waveform.set_audio_data(None)
            self.lbl_info_filename.setText("Tệp: Chưa nạp")
            self.lbl_info_sr.setText("Tần số: —")
            self.lbl_info_channels.setText("Số kênh: —")
            self.lbl_info_dur.setText("Thời lượng: —")
            self.lbl_info_size.setText("Dung lượng: —")
            self.lbl_time_status.setText("Vị trí: 00:00.0 / 00:00.0")
            self._update_ui_state()
            return

        # Trích xuất mảng numpy
        raw_samples = self.current_audio.get_array_of_samples()
        np_arr = np.array(raw_samples, dtype=np.float32)
        sr = self.current_audio.frame_rate
        channels = self.current_audio.channels

        if channels > 1:
            np_arr = np_arr.reshape(-1, channels).mean(axis=1)

        self.waveform.set_audio_data(np_arr, sample_rate=sr)

        # Cập nhật thông tin tệp
        dur_ms = len(self.current_audio)
        fname = self.current_file_path.name if self.current_file_path else "Untitled"
        self.lbl_info_filename.setText(f"Tệp: <b>{fname}</b>")
        self.lbl_info_sr.setText(f"Tần số: <b>{sr:,} Hz</b>")
        self.lbl_info_channels.setText(f"Kênh: <b>{'Stereo (2.0)' if channels == 2 else 'Mono (1.0)'}</b>")
        self.lbl_info_dur.setText(f"Thời lượng: <b>{format_ms_to_time(dur_ms)}</b>")

        est_size_mb = (dur_ms * sr * 2) / (1000 * 1024 * 1024)
        self.lbl_info_size.setText(f"Dung lượng ước tính: <b>~{est_size_mb:.2f} MB</b>")
        self.lbl_time_status.setText(f"Vị trí: {format_ms_to_time(self.waveform.playhead_ms)} / {format_ms_to_time(dur_ms)}")

        # Lưu file tạm để sẵn sàng phát preview
        if update_preview:
            try:
                self.current_audio.export(str(self._temp_preview_wav), format="wav")
            except Exception as e:
                print(f"Lỗi xuất preview: {e}")

        self._update_ui_state()

    # =========================================================================
    # QUẢN LÝ DỰ ÁN & NHẬP / XUẤT TỆP
    # =========================================================================
    def new_project(self):
        """Tạo dự án mới sạch sẽ."""
        if self.current_audio is not None:
            ans = QMessageBox.question(
                self, "Tạo dự án mới", "Bạn có chắc muốn tạo dự án mới? Các thay đổi chưa lưu sẽ bị xóa.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ans != QMessageBox.Yes:
                return

        self.stop_audio()
        self.current_project_id = None
        self.current_project_name = "Dự án mới"
        self.current_file_path = None
        self.current_audio = None
        self.clipboard_audio = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        import gc
        gc.collect()
        self._refresh_audio_view()
        notification_hub.notify_info.emit("Dự Án Mới", "Đã khởi tạo dự án âm thanh mới.")

    def import_audio_dialog(self):
        """Mở hộp thoại chọn file âm thanh để nạp vào Studio."""
        f, _ = QFileDialog.getOpenFileName(
            self, "Nhập tệp âm thanh vào Audio Studio", "",
            "Tệp Âm Thanh (*.wav *.mp3 *.flac *.ogg);;Tất cả tệp (*.*)"
        )
        if f:
            self.load_audio_file(Path(f))

    def load_audio_file(self, file_path: Any) -> bool:
        """Nạp một file âm thanh và khởi tạo dự án."""
        file_path = Path(file_path)
        if not file_path.is_file():
            return False
        try:
            audio = load_audio_segment_safe(file_path)
            self._push_undo_state()
            self.current_file_path = file_path
            self.current_audio = audio
            self.current_project_name = file_path.stem
            self._refresh_audio_view()
            notification_hub.notify_success.emit("Nhập Tệp Thành Công", f"Đã nạp tệp: '{file_path.name}' ({format_ms_to_time(len(audio))})")
            return True
        except Exception as e:
            print(f"Lỗi nạp âm thanh: {e}")
            return False

    def save_project(self):
        """Lưu dự án hiện tại vào data/projects/audio/."""
        if self.current_audio is None:
            QMessageBox.information(self, "Chưa có âm thanh", "Vui lòng nhập tệp âm thanh trước khi lưu dự án.")
            return

        name, ok = QInputDialog.getText(self, "Lưu dự án", "Tên dự án âm thanh:", text=self.current_project_name)
        if not ok or not name.strip():
            return

        self.current_project_name = name.strip()
        proj_data = {
            "name": self.current_project_name,
            "type": "audio",
            "source_file": str(self.current_file_path) if self.current_file_path else "",
            "duration_ms": len(self.current_audio),
            "sample_rate": self.current_audio.frame_rate,
            "channels": self.current_audio.channels,
            "playhead_ms": self.waveform.playhead_ms,
            "sel_start_ms": self.waveform.sel_start_ms,
            "sel_end_ms": self.waveform.sel_end_ms,
        }
        pid = project_manager.save_project("audio", proj_data)
        self.current_project_id = pid
        self._update_ui_state()
        notification_hub.notify_success.emit("Lưu Dự Án", f"Đã lưu dự án '{self.current_project_name}' thành công.")

    def open_project_dialog(self):
        """Mở danh sách các dự án audio đã lưu."""
        projects = project_manager.list_projects("audio")
        if not projects:
            QMessageBox.information(self, "Chưa có dự án", "Chưa có dự án âm thanh nào được lưu trước đó.")
            return

        names = [f"{p['name']} ({p.get('updated_at', '')})" for p in projects]
        chosen, ok = QInputDialog.getItem(self, "Mở dự án âm thanh", "Chọn dự án cần mở:", names, 0, False)
        if ok and chosen:
            idx = names.index(chosen)
            p_id = projects[idx]["id"]
            self.load_project(p_id)

    def load_project(self, project_id: str):
        """Khôi phục dự án từ tệp JSON."""
        proj = project_manager.load_project("audio", project_id)
        if not proj:
            QMessageBox.critical(self, "Lỗi dự án", "Không tìm thấy tệp dự án tương ứng.")
            return

        src = proj.get("source_file")
        if src and Path(src).is_file():
            self.load_audio_file(Path(src))
        else:
            # File nguồn bị thiếu -> Cho phép người dùng liên kết lại (Relink)
            ans = QMessageBox.warning(
                self, "Tệp nguồn bị thiếu",
                f"Tệp âm thanh nguồn gốc không còn ở đường dẫn:\n{src}\n\nBạn có muốn chỉ định tệp thay thế không?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if ans == QMessageBox.Yes:
                new_f, _ = QFileDialog.getOpenFileName(self, "Chỉ định tệp âm thanh thay thế", "", "Audio Files (*.mp3 *.wav *.flac *.ogg)")
                if new_f:
                    self.load_audio_file(Path(new_f))
                else:
                    return
            else:
                return

        self.current_project_id = project_id
        self.current_project_name = proj.get("name", "Dự án âm thanh")
        self._update_ui_state()

    def export_audio_dialog(self):
        """Mở hộp thoại xuất bản âm thanh tích hợp chuẩn hóa LUFS hoặc Peak."""
        if self.current_audio is None:
            return

        default_dir = Path(tts_service.default_out_dir)
        default_name = f"{self.current_project_name}_exported"
        dlg = AudioStudioExportDialog(default_name=default_name, default_dir=default_dir, parent=self)
        if dlg.exec() != QDialog.Accepted or not dlg.export_path:
            return

        out_p = dlg.export_path
        fmt = dlg.format_type
        mode = dlg.mastering_mode

        try:
            temp_raw = Path(tempfile.gettempdir()) / f"studio_export_raw_{os.getpid()}.wav"
            self.current_audio.export(str(temp_raw), format="wav")

            if mode == "peak":
                norm_audio = pydub_normalize(self.current_audio)
                if fmt == "mp3":
                    norm_audio.export(str(out_p), format="mp3", bitrate=f"{dlg.bitrate_kbps}k")
                else:
                    norm_audio.export(str(out_p), format="wav")
            elif mode.startswith("lufs"):
                from backend.audio_enhancement import audio_enhancement_engine, AudioEnhancementConfig
                cfg = AudioEnhancementConfig(
                    enable_loudnorm=True,
                    target_lufs=dlg.target_lufs,
                    loudness_range=7.0,
                    true_peak=-1.5,
                    enable_noise_reduction=False,
                    enable_eq=False,
                    enable_compressor=False,
                )
                res = audio_enhancement_engine.enhance_audio(
                    input_file=temp_raw,
                    output_file=out_p,
                    config=cfg,
                )
                if not res.get("success"):
                    raise RuntimeError(res.get("error") or "Lỗi chuẩn hóa LUFS")
            else:
                if fmt == "mp3":
                    self.current_audio.export(str(out_p), format="mp3", bitrate=f"{dlg.bitrate_kbps}k")
                else:
                    self.current_audio.export(str(out_p), format="wav")

            try:
                if temp_raw.is_file():
                    temp_raw.unlink()
            except Exception:
                pass

            notification_hub.notify_success.emit("Xuất Âm Thanh Thành Công", f"Đã xuất tệp:\n{out_p.name}")
            QMessageBox.information(
                self, "Xuất thành công",
                f"Đã xuất tệp âm thanh thành công:\n\n{out_p}\n\nĐịnh dạng: {fmt.upper()} | Chế độ: {dlg.combo_mode.currentText()}\nThời lượng: {format_ms_to_time(len(self.current_audio))}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Lỗi xuất file", f"Không thể xuất file âm thanh:\n\n{e}")

    def _on_send_to_broadcast(self):
        """Chuyển âm thanh đang biên tập sang phân đoạn Bản Tin Phát Thanh."""
        if self.current_audio is None:
            return
        tmp = Path(tempfile.gettempdir()) / f"studio_broadcast_{int(time.time())}.wav"
        save_wav(self.current_audio, tmp)
        dur = len(self.current_audio) / 1000.0
        seg = {
            "title": f"Biên tập: {self.current_project_name}",
            "file_path": str(tmp),
            "text": f"Dự án Audio Studio: {self.current_project_name}",
            "duration_sec": dur,
            "type": "news",
        }
        self.send_to_broadcast.emit(seg)

    def _on_send_to_schedule(self):
        """Chuyển âm thanh đang biên tập sang Lịch Phát Thanh."""
        if self.current_audio is None:
            return
        tmp = Path(tts_service.default_out_dir) / f"{self.current_project_name}_schedule.wav"
        save_wav(self.current_audio, tmp)
        dur = len(self.current_audio) / 1000.0
        item = {
            "title": self.current_project_name,
            "file_path": str(tmp),
            "duration_sec": dur,
        }
        self.send_to_schedule.emit(item)

    # =========================================================================
    # CÁC THAO TÁC BIÊN TẬP ÂM THANH (EDIT OPERATIONS)
    # =========================================================================
    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self.current_audio)
        self.current_audio = self.undo_stack.pop()
        self._refresh_audio_view()
        notification_hub.notify_info.emit("Hoàn Tác", "Đã hoàn tác thao tác trước đó.")

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.current_audio)
        self.current_audio = self.redo_stack.pop()
        self._refresh_audio_view()
        notification_hub.notify_info.emit("Làm Lại", "Đã làm lại thao tác.")

    def cut_selection(self):
        if self.current_audio is None:
            return
        s = self.waveform.sel_start_ms
        e = self.waveform.sel_end_ms
        if s == e:
            QMessageBox.information(self, "Chưa chọn vùng", "Vui lòng kéo chuột trên dạng sóng để chọn vùng cần cắt.")
            return

        self._push_undo_state()
        self.clipboard_audio = self.current_audio[s:e]
        self.current_audio = self.current_audio[:s] + self.current_audio[e:]
        self.waveform.clear_selection()
        self.waveform.set_playhead_ms(s)
        self._refresh_audio_view()
        notification_hub.notify_info.emit("Đã Cắt Vùng Chọn", f"Đã cắt {format_ms_to_time(e - s)} vào bộ nhớ tạm.")

    def copy_selection(self):
        if self.current_audio is None:
            return
        s = self.waveform.sel_start_ms
        e = self.waveform.sel_end_ms
        if s == e:
            QMessageBox.information(self, "Chưa chọn vùng", "Vui lòng kéo chuột trên dạng sóng để chọn vùng cần sao chép.")
            return
        self.clipboard_audio = self.current_audio[s:e]
        self._update_ui_state()
        notification_hub.notify_info.emit("Đã Sao Chép", f"Đã sao chép {format_ms_to_time(e - s)} vào bộ nhớ tạm.")

    def paste_audio(self):
        if self.current_audio is None or self.clipboard_audio is None:
            return
        pos = self.waveform.playhead_ms
        self._push_undo_state()

        # Đồng bộ frame rate và channels nếu cần
        clip = self.clipboard_audio
        if clip.frame_rate != self.current_audio.frame_rate:
            clip = clip.set_frame_rate(self.current_audio.frame_rate)
        if clip.channels != self.current_audio.channels:
            clip = clip.set_channels(self.current_audio.channels)

        self.current_audio = self.current_audio[:pos] + clip + self.current_audio[pos:]
        self.waveform.set_playhead_ms(pos + len(clip))
        self._refresh_audio_view()
        notification_hub.notify_info.emit("Đã Dán Âm Thanh", f"Đã dán đoạn âm thanh vào vị trí {format_ms_to_time(pos)}.")

    def delete_selection(self):
        if self.current_audio is None:
            return
        s = self.waveform.sel_start_ms
        e = self.waveform.sel_end_ms
        if s == e:
            QMessageBox.information(self, "Chưa chọn vùng", "Vui lòng chọn vùng cần xóa.")
            return
        self._push_undo_state()
        self.current_audio = self.current_audio[:s] + self.current_audio[e:]
        self.waveform.clear_selection()
        self.waveform.set_playhead_ms(s)
        self._refresh_audio_view()
        notification_hub.notify_info.emit("Đã Xóa", f"Đã xóa phân đoạn {format_ms_to_time(e - s)}.")

    def trim_selection(self):
        if self.current_audio is None:
            return
        s = self.waveform.sel_start_ms
        e = self.waveform.sel_end_ms
        if s == e:
            QMessageBox.information(self, "Chưa chọn vùng", "Vui lòng chọn vùng muốn giữ lại (Trim).")
            return
        self._push_undo_state()
        self.current_audio = self.current_audio[s:e]
        self.waveform.clear_selection()
        self.waveform.set_playhead_ms(0)
        self._refresh_audio_view()
        notification_hub.notify_info.emit("Đã Trim", f"Giữ lại phân đoạn: {format_ms_to_time(e - s)}.")

    def split_at_playhead(self):
        """Tách đoạn tại vị trí Playhead (thêm 200ms im lặng phân định)."""
        if self.current_audio is None:
            return
        pos = self.waveform.playhead_ms
        if pos <= 0 or pos >= len(self.current_audio):
            return
        self._push_undo_state()
        silence = AudioSegment.silent(duration=200, frame_rate=self.current_audio.frame_rate)
        if self.current_audio.channels > 1:
            silence = silence.set_channels(self.current_audio.channels)
        self.current_audio = self.current_audio[:pos] + silence + self.current_audio[pos:]
        self._refresh_audio_view()
        notification_hub.notify_info.emit("Đã Tách Đoạn", f"Đã tách đoạn tại {format_ms_to_time(pos)}.")

    def insert_silence_dialog(self):
        """Chèn một khoảng lặng (silence) vào vị trí playhead."""
        if self.current_audio is None:
            return
        sec, ok = QInputDialog.getDouble(self, "Chèn khoảng lặng", "Thời gian khoảng lặng (giây):", 1.0, 0.1, 30.0, 1)
        if not ok or sec <= 0:
            return
        pos = self.waveform.playhead_ms
        self._push_undo_state()
        silence_clip = AudioSegment.silent(duration=int(sec * 1000), frame_rate=self.current_audio.frame_rate)
        if self.current_audio.channels > 1:
            silence_clip = silence_clip.set_channels(self.current_audio.channels)
        self.current_audio = self.current_audio[:pos] + silence_clip + self.current_audio[pos:]
        self.waveform.set_playhead_ms(pos + int(sec * 1000))
        self._refresh_audio_view()
        notification_hub.notify_info.emit("Chèn Khoảng Lặng", f"Đã chèn {sec}s khoảng lặng tại {format_ms_to_time(pos)}.")

    def join_audio_dialog(self):
        """Ghép nối thêm một tệp âm thanh vào cuối hoặc vị trí con trỏ."""
        if self.current_audio is None:
            return
        f, _ = QFileDialog.getOpenFileName(self, "Chọn file âm thanh để ghép", "", "Audio Files (*.mp3 *.wav *.flac *.ogg)")
        if not f:
            return
        try:
            append_clip = load_audio_segment_safe(f)
            if append_clip.frame_rate != self.current_audio.frame_rate:
                append_clip = append_clip.set_frame_rate(self.current_audio.frame_rate)
            if append_clip.channels != self.current_audio.channels:
                append_clip = append_clip.set_channels(self.current_audio.channels)

            self._push_undo_state()
            pos = self.waveform.playhead_ms
            # Ghép vào vị trí playhead
            self.current_audio = self.current_audio[:pos] + append_clip + self.current_audio[pos:]
            self.waveform.set_playhead_ms(pos + len(append_clip))
            self._refresh_audio_view()
            notification_hub.notify_success.emit("Ghép File Thành Công", f"Đã ghép tệp: '{Path(f).name}'")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi ghép âm thanh", f"Không thể ghép tệp:\n\n{e}")

    def adjust_gain_dialog(self):
        """Tăng hoặc giảm âm lượng theo đơn vị dB."""
        if self.current_audio is None:
            return
        gain_val, ok = QInputDialog.getDouble(self, "Điều chỉnh âm lượng", "Tăng/giảm dB (-20.0 đến +20.0):", 2.0, -20.0, 20.0, 1)
        if not ok or abs(gain_val) < 0.01:
            return
        self._push_undo_state()
        s = self.waveform.sel_start_ms
        e = self.waveform.sel_end_ms

        if s < e:
            # Chỉ áp dụng cho vùng chọn
            sub = self.current_audio[s:e] + gain_val
            self.current_audio = self.current_audio[:s] + sub + self.current_audio[e:]
        else:
            # Áp dụng cho toàn bộ âm thanh
            self.current_audio = self.current_audio + gain_val

        self._refresh_audio_view()
        notification_hub.notify_info.emit("Điều Chỉnh Gain", f"Đã áp dụng độ lợi: {gain_val:+.1f} dB.")

    def apply_fade(self, is_in: bool = True):
        """Làm mờ dần đầu (Fade In) hoặc cuối (Fade Out)."""
        if self.current_audio is None:
            return
        dur_default = min(1500, len(self.current_audio) // 3)
        ms, ok = QInputDialog.getInt(self, "Hiệu ứng Fade", "Thời gian Fade (ms):", dur_default, 100, 10000, 100)
        if not ok or ms <= 0:
            return
        self._push_undo_state()
        if is_in:
            self.current_audio = self.current_audio.fade_in(ms)
            msg = f"Đã áp dụng Fade In ({ms}ms)."
        else:
            self.current_audio = self.current_audio.fade_out(ms)
            msg = f"Đã áp dụng Fade Out ({ms}ms)."
        self._refresh_audio_view()
        notification_hub.notify_info.emit("Áp Dụng Fade", msg)

    def normalize_audio(self):
        """Chuẩn hóa âm lượng (Normalize peak -0.1 dBFS)."""
        if self.current_audio is None:
            return
        self._push_undo_state()
        try:
            self.current_audio = pydub_normalize(self.current_audio)
            self._refresh_audio_view()
            notification_hub.notify_success.emit("Chuẩn Hóa Âm Lượng", "Đã chuẩn hóa âm lượng theo chuẩn Peak an toàn.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi chuẩn hóa", f"Không thể chuẩn hóa âm lượng:\n\n{e}")

    def mix_bgm_dialog(self):
        """Lồng nhạc nền vào đoạn âm thanh chính."""
        if self.current_audio is None:
            return
        dlg = BGMConfigDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.selected_file:
            return

        try:
            bgm = load_audio_segment_safe(dlg.selected_file)
            if bgm.frame_rate != self.current_audio.frame_rate:
                bgm = bgm.set_frame_rate(self.current_audio.frame_rate)
            if bgm.channels != self.current_audio.channels:
                bgm = bgm.set_channels(self.current_audio.channels)

            bgm = bgm + dlg.volume_db

            # Lặp lại nếu nhạc ngắn hơn giọng đọc
            if len(bgm) < len(self.current_audio):
                loops = int(len(self.current_audio) / len(bgm)) + 1
                bgm = bgm * loops
            bgm = bgm[:len(self.current_audio)]

            # Thêm fade in / fade out nhẹ cho nhạc nền
            bgm = bgm.fade_in(1000).fade_out(1500)

            self._push_undo_state()
            self.current_audio = self.current_audio.overlay(bgm)
            self._refresh_audio_view()
            notification_hub.notify_success.emit("Lồng Nhạc Nền Thành Công", f"Đã lồng nhạc: '{dlg.selected_file.name}' ({dlg.volume_db} dB).")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi lồng nhạc", f"Không thể lồng nhạc nền:\n\n{e}")

    def enhance_audio_dialog(self):
        """Mở hộp thoại nâng cấp chất lượng âm thanh DSP."""
        if self.current_audio is None or len(self.current_audio) == 0:
            QMessageBox.warning(self, "Chưa Có Âm Thanh", "Vui lòng nhập hoặc nạp tệp âm thanh trước khi áp dụng DSP!")
            return

        # Lưu audio hiện tại ra file tạm để đưa vào dialog
        temp_input = Path(tempfile.gettempdir()) / f"studio_dsp_in_{os.getpid()}.wav"
        self.current_audio.export(str(temp_input), format="wav")

        has_sel = self.waveform.has_selection()
        sel_start = self.waveform.sel_start_ms if has_sel else None
        sel_end = self.waveform.sel_end_ms if has_sel else None

        from gui.dialog_audio_enhancement import AudioEnhancementDialog
        dlg = AudioEnhancementDialog(input_wav_path=temp_input, start_ms=sel_start, end_ms=sel_end, parent=self)
        if dlg.exec() == QDialog.Accepted:
            enhanced_path = getattr(dlg, "final_enhanced_path", None)
            if enhanced_path and Path(enhanced_path).is_file():
                self._push_undo_state()
                self.current_audio = load_audio_segment_safe(enhanced_path)
                self._refresh_audio_view()
                notification_hub.notify_success.emit("Nâng Cấp Âm Thanh Thành Công", "Đã áp dụng chuỗi bộ lọc DSP cho âm thanh dự án.")

    def analyze_audio_dialog(self):
        """Mở hộp thoại phân tích chất lượng âm thanh 8 chỉ số âm học và gợi ý thông minh."""
        if self.current_audio is None or len(self.current_audio) == 0:
            QMessageBox.warning(self, "Chưa Có Âm Thanh", "Vui lòng nhập hoặc nạp tệp âm thanh trước khi phân tích!")
            return

        temp_input = Path(tempfile.gettempdir()) / f"studio_analyze_in_{os.getpid()}.wav"
        self.current_audio.export(str(temp_input), format="wav")

        from gui.dialog_voice_analyzer import VoiceQualityAnalyzerDialog
        dlg = VoiceQualityAnalyzerDialog(input_wav_path=temp_input, parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.should_open_dsp:
            from gui.dialog_audio_enhancement import AudioEnhancementDialog
            has_sel = self.waveform.has_selection()
            sel_start = self.waveform.sel_start_ms if has_sel else None
            sel_end = self.waveform.sel_end_ms if has_sel else None
            dsp_dlg = AudioEnhancementDialog(
                input_wav_path=temp_input,
                start_ms=sel_start,
                end_ms=sel_end,
                initial_config=dlg.applied_suggested_config,
                parent=self,
            )
            if dsp_dlg.exec() == QDialog.Accepted:
                enhanced_path = getattr(dsp_dlg, "final_enhanced_path", None)
                if enhanced_path and Path(enhanced_path).is_file():
                    self._push_undo_state()
                    self.current_audio = load_audio_segment_safe(enhanced_path)
                    self._refresh_audio_view()
                    notification_hub.notify_success.emit("Nâng Cấp Âm Thanh Thành Công", "Đã áp dụng cấu hình đề xuất thông minh.")

    # =========================================================================
    # ĐIỀU KHIỂN PHÁT ÂM THANH NATIVE (PLAYBACK)
    # =========================================================================
    def play_audio(self):
        if self.current_audio is None:
            return
        if not self._temp_preview_wav.exists():
            self.current_audio.export(str(self._temp_preview_wav), format="wav")

        pos = self.waveform.playhead_ms
        if audio_player.is_paused():
            audio_player.resume()
        else:
            ok = audio_player.play(self._temp_preview_wav)
            if ok and pos > 0:
                audio_player.seek_ms(pos)

        self._playback_timer.start()

    def pause_audio(self):
        audio_player.pause()
        self._playback_timer.stop()

    def stop_audio(self):
        audio_player.stop()
        self._playback_timer.stop()
        self.waveform.set_playhead_ms(0)
        if self.current_audio:
            self.lbl_time_status.setText(f"Vị trí: 00:00.0 / {format_ms_to_time(len(self.current_audio))}")
            self.slider_seek.setValue(0)

    def _on_playhead_moved(self, pos_ms: int):
        if self.current_audio:
            dur = len(self.current_audio)
            self.lbl_time_status.setText(f"Vị trí: {format_ms_to_time(pos_ms)} / {format_ms_to_time(dur)}")
            if dur > 0:
                self.slider_seek.blockSignals(True)
                self.slider_seek.setValue(int(pos_ms * 1000 / dur))
                self.slider_seek.blockSignals(False)

        if audio_player.is_playing() or audio_player.is_paused():
            audio_player.seek_ms(pos_ms)

    def _on_selection_changed(self, s: int, e: int):
        if s == e:
            self.lbl_selection_status.setText("Vùng chọn: Chưa chọn")
        else:
            dur = e - s
            self.lbl_selection_status.setText(f"Vùng chọn: {format_ms_to_time(s)} -> {format_ms_to_time(e)} ({dur/1000.0:.2f}s)")

    def _on_wave_scrollbar_changed(self, val: int):
        if not self._syncing_scrollbar:
            self.waveform.scroll_to_ms(val)

    def _on_view_range_changed(self, view_start_ms: int, view_end_ms: int, total_dur: int):
        self._syncing_scrollbar = True
        try:
            span = view_end_ms - view_start_ms
            if total_dur <= span or total_dur <= 0:
                self.wave_scrollbar.setEnabled(False)
                self.wave_scrollbar.setRange(0, 0)
            else:
                self.wave_scrollbar.setEnabled(True)
                self.wave_scrollbar.setRange(0, total_dur - span)
                self.wave_scrollbar.setPageStep(span)
                self.wave_scrollbar.setValue(view_start_ms)
        finally:
            self._syncing_scrollbar = False

    def _on_slider_seek_moved(self, val: int):
        if self.current_audio:
            dur = len(self.current_audio)
            pos_ms = int(val * dur / 1000.0)
            self.waveform.set_playhead_ms(pos_ms)
            if audio_player.is_playing() or audio_player.is_paused():
                audio_player.seek_ms(pos_ms)

    def _on_volume_changed(self, val: int):
        # Scale 0-100 -> 0-1000 cho MCI
        audio_player._send_cmd(f"setaudio {audio_player._alias} volume to {int(val * 10)}")

    def _on_playback_tick(self):
        if audio_player.is_playing():
            pos_ms = audio_player.get_position_ms()
            self.waveform.set_playhead_ms(pos_ms)
            if self.current_audio:
                dur = len(self.current_audio)
                if pos_ms >= dur - 100:
                    self.stop_audio()
                else:
                    self.lbl_time_status.setText(f"Vị trí: {format_ms_to_time(pos_ms)} / {format_ms_to_time(dur)}")
                    self.slider_seek.blockSignals(True)
                    self.slider_seek.setValue(int(pos_ms * 1000 / dur))
                    self.slider_seek.blockSignals(False)
        else:
            self._playback_timer.stop()

    # =========================================================================
    # PROGRAMMATIC / TESTABLE METHODS
    # =========================================================================
    def apply_gain(self, gain_val: float):
        """Áp dụng tăng/giảm âm lượng dB (không hiện popup)."""
        if self.current_audio is None:
            return
        self._push_undo_state()
        s = self.waveform.sel_start_ms
        e = self.waveform.sel_end_ms
        if s < e:
            sub = self.current_audio[s:e] + gain_val
            self.current_audio = self.current_audio[:s] + sub + self.current_audio[e:]
        else:
            self.current_audio = self.current_audio + gain_val
        self._refresh_audio_view()

    def apply_fade_effect(self, is_in: bool = True, ms: int = 1000):
        """Áp dụng hiệu ứng fade in / out (không hiện popup)."""
        if self.current_audio is None:
            return
        self._push_undo_state()
        if is_in:
            self.current_audio = self.current_audio.fade_in(ms)
        else:
            self.current_audio = self.current_audio.fade_out(ms)
        self._refresh_audio_view()

    def insert_silence(self, duration_ms: int):
        """Chèn khoảng lặng (không hiện popup)."""
        if self.current_audio is None:
            return
        pos = self.waveform.playhead_ms
        self._push_undo_state()
        silence_clip = AudioSegment.silent(duration=duration_ms, frame_rate=self.current_audio.frame_rate)
        if self.current_audio.channels > 1:
            silence_clip = silence_clip.set_channels(self.current_audio.channels)
        self.current_audio = self.current_audio[:pos] + silence_clip + self.current_audio[pos:]
        self.waveform.set_playhead_ms(pos + duration_ms)
        self._refresh_audio_view()

    def append_audio_segment(self, segment: AudioSegment):
        """Nối thêm audio segment (không hiện popup)."""
        if self.current_audio is None:
            self._push_undo_state()
            self.current_audio = segment
            self._refresh_audio_view()
            return
        if segment.frame_rate != self.current_audio.frame_rate:
            segment = segment.set_frame_rate(self.current_audio.frame_rate)
        if segment.channels != self.current_audio.channels:
            segment = segment.set_channels(self.current_audio.channels)
        self._push_undo_state()
        self.current_audio = self.current_audio + segment
        self._refresh_audio_view()

    def mix_bgm_file(self, bgm_path: str, volume_pct: int = 15, loop: bool = True):
        """Lồng nhạc nền trực tiếp (không hiện popup)."""
        if self.current_audio is None:
            return
        bgm = load_audio_segment_safe(Path(bgm_path))
        if bgm.frame_rate != self.current_audio.frame_rate:
            bgm = bgm.set_frame_rate(self.current_audio.frame_rate)
        if bgm.channels != self.current_audio.channels:
            bgm = bgm.set_channels(self.current_audio.channels)
        vol_ratio = max(0.01, min(1.0, volume_pct / 100.0))
        vol_db = 20.0 * np.log10(vol_ratio)
        bgm = bgm + vol_db
        if loop and len(bgm) < len(self.current_audio):
            loops = int(len(self.current_audio) / len(bgm)) + 1
            bgm = bgm * loops
        bgm = bgm[:len(self.current_audio)]
        bgm = bgm.fade_in(1000).fade_out(1500)
        self._push_undo_state()
        self.current_audio = self.current_audio.overlay(bgm)
        self._refresh_audio_view()

    def export_to_file(self, file_path: str, format_type: str = "wav") -> bool:
        """Xuất file âm thanh ra đĩa (không hiện popup)."""
        if self.current_audio is None:
            return False
        out_p = Path(file_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fmt = format_type.lower()
        if fmt == "mp3":
            self.current_audio.export(str(out_p), format="mp3", bitrate="192k")
        else:
            self.current_audio.export(str(out_p), format="wav")
        return out_p.is_file()

    def build_project_dict(self, name: str = "") -> dict:
        """Tạo dictionary dự án để lưu vào JSON."""
        pname = name or self.current_project_name
        return {
            "name": pname,
            "type": "audio",
            "source_file": str(self.current_file_path) if self.current_file_path else "",
            "duration_ms": len(self.current_audio) if self.current_audio else 0,
            "sample_rate": self.current_audio.frame_rate if self.current_audio else 44100,
            "channels": self.current_audio.channels if self.current_audio else 1,
            "playhead_ms": self.waveform.playhead_ms,
            "sel_start_ms": self.waveform.sel_start_ms,
            "sel_end_ms": self.waveform.sel_end_ms,
        }

    def restore_from_project_dict(self, proj_data: dict) -> bool:
        """Khôi phục trạng thái từ dictionary dự án."""
        src = proj_data.get("source_file") or proj_data.get("source_path")
        if not src or not Path(src).is_file():
            return False
        ok = self.load_audio_file(Path(src))
        if not ok:
            return False
        self.current_project_name = proj_data.get("name", "Dự án âm thanh")
        if "playhead_ms" in proj_data:
            self.waveform.set_playhead_ms(proj_data["playhead_ms"])
        if "sel_start_ms" in proj_data and "sel_end_ms" in proj_data:
            self.waveform.set_selection_range(proj_data["sel_start_ms"], proj_data["sel_end_ms"])
        self._update_ui_state()
        return True
