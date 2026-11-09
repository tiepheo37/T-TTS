"""gui/pages/page_podcast.py — TAB: KỊCH BẢN PODCAST & HỘI THOẠI (PODCAST STUDIO)
================================================================================
Khôi phục và nâng cấp tính năng tạo kịch bản Podcast / Hội thoại nhiều nhân vật:
- Từng câu thoại có thể chỉ định nhân vật, giọng đọc (trong 25+ giọng hoặc giọng nhân bản),
  tốc độ đọc riêng biệt và thời gian ngắt nghỉ sau câu thoại.
- Nút nghe thử từng câu thoại riêng lẻ trước khi ghép.
- Nạp kịch bản mẫu sẵn để thử nghiệm nhanh chóng.
- Xử lý nền bằng QThread ghép nối thành một tệp WAV/MP3 hoàn chỉnh.
- Tích hợp trình phát âm thanh, sao chép file vào Clipboard và lưu ra máy tính.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QMimeData
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QSlider,
    QRadioButton,
    QButtonGroup,
    QFileDialog,
    QMessageBox,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QProgressBar,
    QScrollArea,
    QApplication,
)

from backend.service import tts_service
from backend.audio_player import audio_player


class LinePreviewWorker(QThread):
    """Tiểu trình đọc thử 1 dòng câu thoại."""

    finished = Signal(str)
    error = Signal(str)

    def __init__(self, text: str, voice_id: str, speed: float):
        super().__init__()
        self.text = text
        self.voice_id = voice_id
        self.speed = speed

    def run(self):
        try:
            res = tts_service.synthesize_text(
                text=self.text,
                voice_id=self.voice_id,
                speed=self.speed,
                out_format="wav",
                filename_prefix="_preview_line",
                custom_out_dir=tts_service.upload_dir,
            )
            if res.get("success"):
                self.finished.emit(res["main_file"])
            else:
                self.error.emit(res.get("error", "Lỗi tổng hợp câu thoại."))
        except Exception as e:
            self.error.emit(str(e))


class PodcastWorker(QThread):
    """Tiểu trình tổng hợp toàn bộ kịch bản Podcast trong nền."""

    progress = Signal(int, int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        lines: List[Dict[str, Any]],
        title: str,
        out_format: str,
        custom_out_dir: Optional[Path] = None,
    ):
        super().__init__()
        self.lines = lines
        self.title = title
        self.out_format = out_format
        self.custom_out_dir = custom_out_dir
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        def _prog(cur, tot, msg):
            self.progress.emit(cur, tot, msg)

        def _cancel():
            return self._cancel_requested

        try:
            res = tts_service.synthesize_podcast(
                lines=self.lines,
                title=self.title,
                out_format=self.out_format,
                custom_out_dir=self.custom_out_dir,
                on_progress=_prog,
                should_cancel=_cancel,
            )
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class PagePodcast(QWidget):
    """Trang Soạn Kịch Bản và Ghép Podcast Đa Nhân Vật."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.worker: Optional[PodcastWorker] = None
        self.preview_worker: Optional[LinePreviewWorker] = None
        self.current_output_file: Optional[Path] = None

        self.play_timer = QTimer(self)
        self.play_timer.setInterval(200)
        self.play_timer.timeout.connect(self._update_player_progress)

        self._build_ui()
        self._load_sample_script()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        # 1. TIÊU ĐỀ
        header_card = QFrame()
        header_card.setProperty("class", "CardFrame")
        hc_layout = QVBoxLayout(header_card)
        hc_layout.setContentsMargins(14, 12, 14, 12)

        h_title = QLabel("🎙️ KỊCH BẢN HỘI THOẠI & PODCAST ĐA NHÂN VẬT")
        h_title.setProperty("class", "CardTitle")
        hc_layout.addWidget(h_title)

        h_sub = QLabel(
            "Tạo cuộc trò chuyện nhiều nhân vật với các giọng đọc khác nhau ghép thành một bản thu âm hoàn chỉnh.<br>"
            "Mỗi nhân vật có thể chọn một giọng riêng (Bắc, Trung, Nam, Quân đội hoặc giọng nhân bản) và tốc độ riêng."
        )
        h_sub.setWordWrap(True)
        h_sub.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.4;")
        hc_layout.addWidget(h_sub)
        layout.addWidget(header_card)

        # 2. KHUNG KỊCH BẢN
        script_card = QFrame()
        script_card.setProperty("class", "CardFrame")
        sc_layout = QVBoxLayout(script_card)
        sc_layout.setContentsMargins(14, 12, 14, 12)
        sc_layout.setSpacing(10)

        # Thanh nút thao tác
        tb_row = QHBoxLayout()
        lbl_sc_title = QLabel("DANH SÁCH CÁC CÂU THOẠI TRONG KỊCH BẢN")
        lbl_sc_title.setStyleSheet("color: #FFD700; font-size: 13px; font-weight: bold;")
        tb_row.addWidget(lbl_sc_title)
        tb_row.addStretch()

        self.btn_add_line = QPushButton("➕ Thêm câu thoại")
        self.btn_add_line.setProperty("class", "PrimaryBtn")
        self.btn_add_line.setCursor(Qt.PointingHandCursor)
        self.btn_add_line.clicked.connect(self._add_empty_line)
        tb_row.addWidget(self.btn_add_line)

        self.btn_sample_script = QPushButton("📑 Kịch bản mẫu")
        self.btn_sample_script.setProperty("class", "SecondaryBtn")
        self.btn_sample_script.setCursor(Qt.PointingHandCursor)
        self.btn_sample_script.clicked.connect(self._load_sample_script)
        tb_row.addWidget(self.btn_sample_script)

        self.btn_clear_script = QPushButton("🧹 Xóa hết")
        self.btn_clear_script.setProperty("class", "SecondaryBtn")
        self.btn_clear_script.setCursor(Qt.PointingHandCursor)
        self.btn_clear_script.clicked.connect(self._clear_all_lines)
        tb_row.addWidget(self.btn_clear_script)

        sc_layout.addLayout(tb_row)

        # Bảng câu thoại
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "STT", "Nhân Vật", "Giọng Đọc", "Tốc Độ", "Nghỉ Sau", "Nội Dung Câu Thoại", "Thao Tác"
        ])
        
        # Đặt kích thước cột rộng rãi, ngăn hiện tượng co rúm widget
        self.table.setColumnWidth(0, 48)   # STT
        self.table.setColumnWidth(1, 130)  # Nhân vật
        self.table.setColumnWidth(2, 230)  # Giọng đọc
        self.table.setColumnWidth(3, 85)   # Tốc độ
        self.table.setColumnWidth(4, 85)   # Nghỉ sau
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch) # Nội dung câu thoại
        self.table.setColumnWidth(6, 110)  # Thao tác
        
        # Thiết lập chiều cao mặc định cho mỗi hàng (66px) để text edit và input hiển thị thoáng đẹp
        self.table.verticalHeader().setDefaultSectionSize(66)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(320)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #162E1A;
                gridline-color: #2D5A32;
                border: 1px solid #3F7545;
                border-radius: 6px;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #1E3A21;
                color: #FFD700;
                font-weight: bold;
                font-size: 12px;
                padding: 6px;
                border: 1px solid #2D5A32;
            }
        """)
        sc_layout.addWidget(self.table)

        layout.addWidget(script_card)

        # 3. KHUNG XUẤT AUDIO PODCAST
        export_card = QFrame()
        export_card.setProperty("class", "CardFrame")
        ec_layout = QVBoxLayout(export_card)
        ec_layout.setContentsMargins(14, 12, 14, 12)
        ec_layout.setSpacing(10)

        cfg_row = QHBoxLayout()
        lbl_pc_title = QLabel("Tên Podcast / Hội thoại:")
        lbl_pc_title.setStyleSheet("color: #FFFFFF; font-weight: bold;")
        cfg_row.addWidget(lbl_pc_title)

        self.title_edit = QLineEdit()
        self.title_edit.setText("Hoi_thoai_podcast")
        self.title_edit.setPlaceholderText("Nhập tên tệp...")
        cfg_row.addWidget(self.title_edit)

        self.radio_wav = QRadioButton("WAV (Chuẩn Studio)")
        self.radio_wav.setChecked(True)
        self.radio_mp3 = QRadioButton("MP3 (Gọn nhẹ)")
        self.fmt_group = QButtonGroup(self)
        self.fmt_group.addButton(self.radio_wav)
        self.fmt_group.addButton(self.radio_mp3)
        cfg_row.addWidget(self.radio_wav)
        cfg_row.addWidget(self.radio_mp3)

        ec_layout.addLayout(cfg_row)

        ctrl_row = QHBoxLayout()
        self.btn_start_podcast = QPushButton("🎙️  GHÉP THÀNH AUDIO HỘI THOẠI / PODCAST")
        self.btn_start_podcast.setProperty("class", "PrimaryBtn")
        self.btn_start_podcast.setFixedHeight(46)
        self.btn_start_podcast.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.btn_start_podcast.setCursor(Qt.PointingHandCursor)
        self.btn_start_podcast.clicked.connect(self._start_podcast_synthesis)
        ctrl_row.addWidget(self.btn_start_podcast, 3)

        self.btn_cancel_podcast = QPushButton("⏹ Dừng lại")
        self.btn_cancel_podcast.setProperty("class", "DangerBtn")
        self.btn_cancel_podcast.setFixedHeight(46)
        self.btn_cancel_podcast.setEnabled(False)
        self.btn_cancel_podcast.setCursor(Qt.PointingHandCursor)
        self.btn_cancel_podcast.clicked.connect(self._cancel_podcast_synthesis)
        ctrl_row.addWidget(self.btn_cancel_podcast, 1)

        ec_layout.addLayout(ctrl_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setVisible(False)
        ec_layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setStyleSheet("font-size: 13px; font-weight: 500;")
        ec_layout.addWidget(self.status_lbl)

        layout.addWidget(export_card)

        # 4. TRÌNH PHÁT KẾT QUẢ PODCAST
        self.player_card = QFrame()
        self.player_card.setProperty("class", "CardFrame")
        self.player_card.setVisible(False)
        pc_layout = QVBoxLayout(self.player_card)
        pc_layout.setContentsMargins(14, 12, 14, 12)
        pc_layout.setSpacing(10)

        p_header = QHBoxLayout()
        self.lbl_playing_title = QLabel("🎙️ PODCAST ĐÃ TẠO:")
        self.lbl_playing_title.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 13px;")
        p_header.addWidget(self.lbl_playing_title)
        p_header.addStretch()

        self.btn_copy_file = QPushButton("📋 Sao chép file")
        self.btn_copy_file.setProperty("class", "SecondaryBtn")
        self.btn_copy_file.setCursor(Qt.PointingHandCursor)
        self.btn_copy_file.setToolTip("Sao chép file vào Clipboard để dán (Ctrl+V) vào Zalo hoặc thư mục bất kỳ")
        self.btn_copy_file.clicked.connect(self._copy_output_to_clipboard)
        p_header.addWidget(self.btn_copy_file)

        self.btn_save_as = QPushButton("💾 Lưu thành...")
        self.btn_save_as.setProperty("class", "SecondaryBtn")
        self.btn_save_as.setCursor(Qt.PointingHandCursor)
        self.btn_save_as.clicked.connect(self._save_output_as)
        p_header.addWidget(self.btn_save_as)

        self.btn_open_folder = QPushButton("📂 Xem file")
        self.btn_open_folder.setProperty("class", "SecondaryBtn")
        self.btn_open_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_folder.clicked.connect(self._open_output_file_folder)
        p_header.addWidget(self.btn_open_folder)
        pc_layout.addLayout(p_header)

        # Thanh phát
        play_ctrl_row = QHBoxLayout()
        self.btn_play_pause = QPushButton("▶ Phát Podcast")
        self.btn_play_pause.setProperty("class", "PrimaryBtn")
        self.btn_play_pause.setFixedWidth(140)
        self.btn_play_pause.setFixedHeight(36)
        self.btn_play_pause.setCursor(Qt.PointingHandCursor)
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

    # -----------------------------------------------------------------
    # QUẢN LÝ DÒNG THOẠI TRONG BẢNG
    # -----------------------------------------------------------------
    def _add_line_row(self, speaker: str, voice_id: str, speed: float, pause_after: float, text: str):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 66)

        # 0: STT
        stt_item = QTableWidgetItem(f"{row+1}")
        stt_item.setTextAlignment(Qt.AlignCenter)
        stt_item.setForeground(QColor("#FFD700"))
        stt_item.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.table.setItem(row, 0, stt_item)

        # 1: Nhân vật
        spk_edit = QLineEdit(speaker)
        spk_edit.setPlaceholderText("Tên nhân vật...")
        spk_edit.setFixedHeight(36)
        spk_edit.setFont(QFont("Segoe UI", 11, QFont.Bold))
        spk_edit.setStyleSheet(
            "background-color: #1E3A21; color: #FFD700; font-weight: bold; "
            "border: 1px solid #3F7545; border-radius: 4px; padding: 4px 8px;"
        )
        self.table.setCellWidget(row, 1, spk_edit)

        # 2: Giọng đọc
        cb_voice = QComboBox()
        cb_voice.setFixedHeight(36)
        cb_voice.setStyleSheet(
            "background-color: #1E3A21; color: #FFFFFF; font-size: 12px; "
            "border: 1px solid #3F7545; border-radius: 4px; padding: 2px 6px;"
        )
        voices = tts_service.list_voices()
        v_idx = 0
        for idx, v in enumerate(voices):
            cb_voice.addItem(v.get("label", v["id"]), v["id"])
            if v["id"] == voice_id:
                v_idx = idx
        if cb_voice.count() > 0:
            cb_voice.setCurrentIndex(v_idx)
        self.table.setCellWidget(row, 2, cb_voice)

        # 3: Tốc độ
        spin_spd = QDoubleSpinBox()
        spin_spd.setFixedHeight(36)
        spin_spd.setRange(0.75, 1.50)
        spin_spd.setSingleStep(0.05)
        spin_spd.setValue(speed)
        spin_spd.setSuffix("x")
        spin_spd.setStyleSheet("background-color: #1E3A21; color: #FFFFFF; border: 1px solid #3F7545; border-radius: 4px; padding: 2px;")
        self.table.setCellWidget(row, 3, spin_spd)

        # 4: Nghỉ sau
        spin_pause = QDoubleSpinBox()
        spin_pause.setFixedHeight(36)
        spin_pause.setRange(0.0, 5.0)
        spin_pause.setSingleStep(0.2)
        spin_pause.setValue(pause_after)
        spin_pause.setSuffix("s")
        spin_pause.setStyleSheet("background-color: #1E3A21; color: #FFFFFF; border: 1px solid #3F7545; border-radius: 4px; padding: 2px;")
        self.table.setCellWidget(row, 4, spin_pause)

        # 5: Nội dung
        txt_edit = QTextEdit(text)
        txt_edit.setFixedHeight(54)
        txt_edit.setFont(QFont("Segoe UI", 11))
        txt_edit.setStyleSheet(
            "background-color: #1E3A21; color: #FFFFFF; border: 1px solid #3F7545; "
            "border-radius: 4px; padding: 4px; line-height: 1.3;"
        )
        txt_edit.setPlaceholderText("Nhập câu thoại của nhân vật tại đây...")
        self.table.setCellWidget(row, 5, txt_edit)

        # 6: Thao tác (Nghe thử + Xóa)
        act_widget = QWidget()
        act_layout = QHBoxLayout(act_widget)
        act_layout.setContentsMargins(4, 4, 4, 4)
        act_layout.setSpacing(6)

        btn_preview = QPushButton("▶")
        btn_preview.setProperty("class", "SecondaryBtn")
        btn_preview.setToolTip("Nghe thử câu thoại này")
        btn_preview.setCursor(Qt.PointingHandCursor)
        btn_preview.setFixedSize(42, 34)
        btn_preview.clicked.connect(lambda _, r=row: self._preview_single_line(r))
        act_layout.addWidget(btn_preview)

        btn_del = QPushButton("🗑️")
        btn_del.setProperty("class", "DangerBtn")
        btn_del.setToolTip("Xóa dòng câu thoại này")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setFixedSize(38, 34)
        btn_del.clicked.connect(lambda _, r=row: self._delete_line(r))
        act_layout.addWidget(btn_del)

        self.table.setCellWidget(row, 6, act_widget)

    def _add_empty_line(self):
        row_count = self.table.rowCount()
        spk = f"Nhân vật {row_count + 1}"
        voices = tts_service.list_voices()
        v_id = voices[row_count % len(voices)]["id"] if voices else "Hải Đăng"
        self._add_line_row(spk, v_id, 1.0, 0.5, "")

    def _load_sample_script(self):
        self.table.setRowCount(0)
        sample = [
            ("Chỉ huy", "Hải Đăng", 1.0, 0.6, "Báo cáo đồng chí, tình hình huấn luyện của đơn vị hôm nay thế nào?"),
            ("Chiến sĩ", "Quốc Tuấn", 1.0, 0.6, "Báo cáo chỉ huy, toàn đơn vị đã hoàn thành tốt các nội dung huấn luyện theo đúng kế hoạch và duy trì nghiêm chế độ trực ban."),
            ("Chỉ huy", "Hải Đăng", 1.0, 0.5, "Rất tốt. Đề nghị các đồng chí tiếp tục phát huy tinh thần trách nhiệm, sẵn sàng nhận và hoàn thành xuất sắc mọi nhiệm vụ được giao!"),
        ]
        for spk, vid, spd, pause, txt in sample:
            self._add_line_row(spk, vid, spd, pause, txt)

    def _clear_all_lines(self):
        ret = QMessageBox.question(
            self,
            "Xác nhận xóa",
            "Bạn có chắc muốn xóa toàn bộ kịch bản hiện tại?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self.table.setRowCount(0)

    def _delete_line(self, row_idx: int):
        if 0 <= row_idx < self.table.rowCount():
            self.table.removeRow(row_idx)
            # Cập nhật lại số thứ tự
            for r in range(self.table.rowCount()):
                self.table.setItem(r, 0, QTableWidgetItem(f"{r+1}"))

    def _preview_single_line(self, row_idx: int):
        if row_idx >= self.table.rowCount():
            return
        txt_w = self.table.cellWidget(row_idx, 5)
        text = txt_w.toPlainText().strip() if isinstance(txt_w, QTextEdit) else ""
        if not text:
            QMessageBox.warning(self, "Chưa có nội dung", "Vui lòng nhập nội dung câu thoại trước khi nghe thử.")
            return

        cb_w = self.table.cellWidget(row_idx, 2)
        v_id = cb_w.currentData() if isinstance(cb_w, QComboBox) else "Hải Đăng"

        spd_w = self.table.cellWidget(row_idx, 3)
        spd = spd_w.value() if isinstance(spd_w, QDoubleSpinBox) else 1.0

        if audio_player.is_playing():
            audio_player.stop()

        self.preview_worker = LinePreviewWorker(text=text, voice_id=v_id, speed=spd)
        self.preview_worker.finished.connect(lambda p: audio_player.play(p))
        self.preview_worker.error.connect(lambda e: QMessageBox.warning(self, "Lỗi đọc thử", e))
        self.preview_worker.start()

    # -----------------------------------------------------------------
    # TỔNG HỢP TOÀN BỘ KỊCH BẢN
    # -----------------------------------------------------------------
    def _extract_script_lines(self) -> List[Dict[str, Any]]:
        lines = []
        for r in range(self.table.rowCount()):
            spk_w = self.table.cellWidget(r, 1)
            speaker = spk_w.text().strip() if isinstance(spk_w, QLineEdit) else f"Nhân vật {r+1}"

            cb_w = self.table.cellWidget(r, 2)
            voice_id = cb_w.currentData() if isinstance(cb_w, QComboBox) else "Hải Đăng"

            spd_w = self.table.cellWidget(r, 3)
            speed = spd_w.value() if isinstance(spd_w, QDoubleSpinBox) else 1.0

            p_w = self.table.cellWidget(r, 4)
            pause_after = p_w.value() if isinstance(p_w, QDoubleSpinBox) else 0.5

            txt_w = self.table.cellWidget(r, 5)
            text = txt_w.toPlainText().strip() if isinstance(txt_w, QTextEdit) else ""

            if text:
                lines.append({
                    "speaker": speaker,
                    "voice_id": voice_id,
                    "speed": speed,
                    "pause_after": pause_after,
                    "text": text,
                })
        return lines

    def _start_podcast_synthesis(self):
        lic = tts_service.get_license_info()
        if not lic["is_active"]:
            QMessageBox.critical(
                self,
                "Bản quyền không hợp lệ",
                f"Chức năng tạo podcast bị khóa:\n\n{lic['status_message']}\n\n"
                "Vui lòng vào tab 'Bản quyền & Giấy phép' để kích hoạt key mới.",
            )
            return

        lines = self._extract_script_lines()
        if not lines:
            QMessageBox.warning(self, "Kịch bản rỗng", "Vui lòng nhập ít nhất một câu thoại có nội dung.")
            return

        title = self.title_edit.text().strip() or "Hoi_thoai_podcast"
        out_fmt = "mp3" if self.radio_mp3.isChecked() else "wav"

        if audio_player.is_playing():
            audio_player.stop()

        self.btn_start_podcast.setEnabled(False)
        self.btn_cancel_podcast.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_lbl.setText(f"Đang chuẩn bị tổng hợp {len(lines)} câu thoại...")
        self.status_lbl.setStyleSheet("color: #22D3EE;")

        self.worker = PodcastWorker(
            lines=lines,
            title=title,
            out_format=out_fmt,
        )
        self.worker.progress.connect(self._on_podcast_progress)
        self.worker.finished.connect(self._on_podcast_finished)
        self.worker.error.connect(self._on_podcast_error)
        self.worker.start()

    def _cancel_podcast_synthesis(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            self.status_lbl.setText("Đang yêu cầu dừng tiến trình...")

    def _on_podcast_progress(self, cur: int, tot: int, msg: str):
        pct = int((cur / float(tot)) * 100) if tot > 0 else 0
        self.progress_bar.setValue(pct)
        self.status_lbl.setText(f"Đang xử lý {cur}/{tot}: {msg} ({pct}%)")

    def _on_podcast_finished(self, res: dict):
        self.btn_start_podcast.setEnabled(True)
        self.btn_cancel_podcast.setEnabled(False)
        self.progress_bar.setVisible(False)

        if not res.get("success"):
            err = res.get("error", "Lỗi không xác định.")
            self.status_lbl.setText(f"❌ {err}")
            self.status_lbl.setStyleSheet("color: #EF4444;")
            QMessageBox.critical(self, "Lỗi tạo Podcast", err)
            return

        fpath = Path(res.get("file_path", ""))
        self.current_output_file = fpath
        dur = float(res.get("duration_sec", 0.0))
        m = int(dur // 60)
        s = int(dur % 60)

        self.status_lbl.setText(f"🎉 Hoàn thành Podcast! Tệp: {fpath.name} ({m:02d}:{s:02d})")
        self.status_lbl.setStyleSheet("color: #22C55E; font-weight: bold;")

        # Hiển thị trình phát
        self.player_card.setVisible(True)
        self.lbl_playing_title.setText(f"🎙️ PODCAST ĐÃ TẠO: {fpath.name}")
        self.lbl_time_display.setText(f"00:00 / {m:02d}:{s:02d}")
        self.timeline_slider.setValue(0)
        self.btn_play_pause.setText("▶ Phát Podcast")

        QMessageBox.information(
            self,
            "Tạo Podcast Thành Công",
            f"🎉 Đã tổng hợp thành công toàn bộ kịch bản đối thoại Podcast!\n\n"
            f"• Tên tệp: {fpath.name}\n"
            f"• Thời lượng: {m:02d}:{s:02d}\n"
            f"• Số câu thoại: {res.get('segments_count', len(self.table.rowCount()))}\n\n"
            f"Bạn có thể nghe thử, sao chép file hoặc xem thư mục chứa ngay bên dưới.",
        )

    def _on_podcast_error(self, err: str):
        self.btn_start_podcast.setEnabled(True)
        self.btn_cancel_podcast.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_lbl.setText(f"❌ {err}")
        self.status_lbl.setStyleSheet("color: #EF4444;")
        QMessageBox.critical(self, "Lỗi", f"Quá trình tạo Podcast gặp lỗi:\n\n{err}")

    # -----------------------------------------------------------------
    # TRÌNH PHÁT KẾT QUẢ TÍCH HỢP
    # -----------------------------------------------------------------
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
            ok = audio_player.play(str(self.current_output_file))
            if ok:
                self.play_timer.start()
                self.btn_play_pause.setText("⏸ Tạm dừng")
            else:
                QMessageBox.warning(self, "Không thể phát", "Không thể phát tệp âm thanh này.")

    def _update_player_progress(self):
        if not audio_player.is_playing():
            self.play_timer.stop()
            self.btn_play_pause.setText("▶ Phát Podcast")
            self.timeline_slider.setValue(0)
            return

        pos_ms = audio_player.get_position_ms()
        dur_ms = audio_player.get_duration_ms()

        if dur_ms > 0:
            frac = pos_ms / float(dur_ms)
            self.timeline_slider.setValue(int(frac * 1000))
            cur_s = int(pos_ms / 1000)
            tot_s = int(dur_ms / 1000)
            self.lbl_time_display.setText(
                f"{cur_s//60:02d}:{cur_s%60:02d} / {tot_s//60:02d}:{tot_s%60:02d}"
            )

    def _on_seek_moved(self, val: int):
        dur_ms = audio_player.get_duration_ms()
        if dur_ms > 0:
            target_ms = int((val / 1000.0) * dur_ms)
            audio_player.seek(target_ms)

    def _copy_output_to_clipboard(self):
        if not self.current_output_file or not self.current_output_file.is_file():
            return
        clipboard = QApplication.clipboard()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.current_output_file))])
        clipboard.setMimeData(mime)
        self.btn_copy_file.setText("✅ Đã chép file!")
        QTimer.singleShot(2500, lambda: self.btn_copy_file.setText("📋 Sao chép file"))

    def _save_output_as(self):
        if not self.current_output_file or not self.current_output_file.is_file():
            return
        ext = self.current_output_file.suffix
        fpath, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu Podcast thành...",
            self.current_output_file.name,
            f"Âm thanh (*{ext});;Tất cả tệp (*.*)",
        )
        if fpath:
            shutil.copy2(str(self.current_output_file), fpath)
            QMessageBox.information(self, "Đã lưu", f"Đã lưu tệp Podcast tại:\n{fpath}")

    def _open_output_file_folder(self):
        if self.current_output_file and self.current_output_file.is_file():
            tts_service.open_file_in_explorer(self.current_output_file)
        else:
            tts_service.open_output_folder()
