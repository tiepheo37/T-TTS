"""gui/pages/page_synthesize.py — TAB 1: TẠO GIỌNG NÓI TIẾNG VIỆT
==============================================================
Màn hình chính của T-TTS:
- Nhập văn bản tiếng Việt lớn, đếm ký tự, dán nhanh, nhập từ tệp.
- Chọn giọng đọc (25 giọng preset allowlist VieNeu v3 Turbo + giọng custom).
- Điều chỉnh tốc độ đọc thực tế (0.75x - 1.50x).
- Tùy chọn định dạng xuất (WAV gốc / MP3), chọn thư mục lưu file.
- Nút bấm tạo giọng nổi bật, chạy ngầm bằng QThread không gây đơ giao diện.
- Trình phát nghe thử native trực tiếp sau khi hoàn thành.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
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
    QRadioButton,
    QButtonGroup,
    QFileDialog,
    QMessageBox,
    QFrame,
    QApplication,
    QProgressBar,
    QScrollArea,
)

from backend.service import tts_service
from backend.audio_player import audio_player


class SynthesisWorker(QThread):
    """Tiểu trình chạy ngầm xử lý tổng hợp giọng nói để giữ giao diện luôn mượt mà."""

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


class PageSynthesize(QWidget):
    """Trang Tạo Giọng Nói Chính."""

    audio_generated = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.selected_out_dir: Optional[Path] = None
        self.last_result: Optional[dict] = None
        self.worker: Optional[SynthesisWorker] = None

        self._build_ui()
        self.refresh_voices()

        # Timer theo dõi vị trí phát audio
        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(200)
        self.playback_timer.timeout.connect(self._update_playback_progress)

    def _build_ui(self):
        # Cho phép cuộn khi cửa sổ có kích thước nhỏ
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        # -------------------------------------------------------------
        # 1. KHU VỰC NHẬP VĂN BẢN
        # -------------------------------------------------------------
        text_card = QFrame()
        text_card.setProperty("class", "CardFrame")
        tc_layout = QVBoxLayout(text_card)
        tc_layout.setContentsMargins(14, 12, 14, 12)
        tc_layout.setSpacing(8)

        # Header hàng nút thao tác văn bản
        th_layout = QHBoxLayout()
        t_title = QLabel("1. VĂN BẢN TIẾNG VIỆT CẦN ĐỌC")
        t_title.setProperty("class", "CardTitle")
        th_layout.addWidget(t_title)
        th_layout.addStretch()

        self.char_count_lbl = QLabel("0 ký tự  |  0 từ")
        self.char_count_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
        th_layout.addWidget(self.char_count_lbl)

        btn_paste = QPushButton("📋 Dán")
        btn_paste.setProperty("class", "SecondaryBtn")
        btn_paste.setCursor(Qt.PointingHandCursor)
        btn_paste.clicked.connect(self._paste_clipboard)
        th_layout.addWidget(btn_paste)

        btn_import_file = QPushButton("📁 Nhập tệp...")
        btn_import_file.setProperty("class", "SecondaryBtn")
        btn_import_file.setCursor(Qt.PointingHandCursor)
        btn_import_file.clicked.connect(self._import_text_file)
        th_layout.addWidget(btn_import_file)

        btn_clear = QPushButton("🗑️ Xóa")
        btn_clear.setProperty("class", "SecondaryBtn")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self._clear_text)
        th_layout.addWidget(btn_clear)
        tc_layout.addLayout(th_layout)

        # Ô nhập văn bản lớn
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            "Nhập hoặc dán văn bản tiếng Việt vào đây...\n\n"
            "Mẹo: Bạn có thể chèn thẻ ngắt nghỉ ví dụ: [pause:0.5s] hoặc [pause:1.0s] để giọng đọc tự nhiên hơn."
        )
        self.text_edit.setMinimumHeight(170)
        self.text_edit.setFont(QFont("Segoe UI", 11))
        self.text_edit.textChanged.connect(self._on_text_changed)
        tc_layout.addWidget(self.text_edit)
        layout.addWidget(text_card)

        # -------------------------------------------------------------
        # 2. KHU VỰC CHỌN GIỌNG & ĐIỀU CHỈNH THAM SỐ
        # -------------------------------------------------------------
        settings_card = QFrame()
        settings_card.setProperty("class", "CardFrame")
        sc_layout = QGridLayout(settings_card)
        sc_layout.setContentsMargins(14, 12, 14, 12)
        sc_layout.setSpacing(12)

        # Cột 1: Chọn giọng đọc
        lbl_v = QLabel("2. CHỌN GIỌNG ĐỌC:")
        lbl_v.setProperty("class", "CardTitle")
        sc_layout.addWidget(lbl_v, 0, 0, 1, 2)

        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(280)
        self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        sc_layout.addWidget(self.voice_combo, 1, 0)

        self.voice_desc_lbl = QLabel("")
        self.voice_desc_lbl.setStyleSheet("color: #22D3EE; font-size: 11px;")
        sc_layout.addWidget(self.voice_desc_lbl, 2, 0)

        # Cột 2: Tốc độ đọc
        lbl_s = QLabel("3. TỐC ĐỘ ĐỌC (0.75x - 1.50x):")
        lbl_s.setProperty("class", "CardTitle")
        sc_layout.addWidget(lbl_s, 0, 1)

        speed_box = QHBoxLayout()
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(75, 150)
        self.speed_slider.setValue(100)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_box.addWidget(self.speed_slider)

        self.speed_val_lbl = QLabel("1.00x")
        self.speed_val_lbl.setStyleSheet("color: #22D3EE; font-weight: bold; min-width: 45px;")
        speed_box.addWidget(self.speed_val_lbl)

        btn_reset_speed = QPushButton("Đặt lại")
        btn_reset_speed.setProperty("class", "SecondaryBtn")
        btn_reset_speed.setCursor(Qt.PointingHandCursor)
        btn_reset_speed.clicked.connect(lambda: self.speed_slider.setValue(100))
        speed_box.addWidget(btn_reset_speed)
        sc_layout.addLayout(speed_box, 1, 1)

        layout.addWidget(settings_card)

        # -------------------------------------------------------------
        # 3. KHU VỰC XUẤT TỆP & THƯ MỤC LƯU
        # -------------------------------------------------------------
        export_card = QFrame()
        export_card.setProperty("class", "CardFrame")
        ec_layout = QHBoxLayout(export_card)
        ec_layout.setContentsMargins(14, 12, 14, 12)
        ec_layout.setSpacing(16)

        # Định dạng xuất
        fmt_layout = QVBoxLayout()
        fmt_lbl = QLabel("Định dạng âm thanh:")
        fmt_lbl.setStyleSheet("color: #F1F5F9; font-weight: bold; font-size: 12px;")
        fmt_layout.addWidget(fmt_lbl)

        radio_layout = QHBoxLayout()
        self.radio_wav = QRadioButton("WAV (48kHz gốc)")
        self.radio_wav.setChecked(True)
        self.radio_wav.setCursor(Qt.PointingHandCursor)
        self.radio_mp3 = QRadioButton("MP3 (192kbps)")
        self.radio_mp3.setCursor(Qt.PointingHandCursor)

        self.fmt_group = QButtonGroup(self)
        self.fmt_group.addButton(self.radio_wav)
        self.fmt_group.addButton(self.radio_mp3)
        radio_layout.addWidget(self.radio_wav)
        radio_layout.addWidget(self.radio_mp3)
        fmt_layout.addLayout(radio_layout)
        ec_layout.addLayout(fmt_layout)

        # Tiền tố tên file
        prefix_layout = QVBoxLayout()
        prefix_lbl = QLabel("Tên tệp (tùy chọn):")
        prefix_lbl.setStyleSheet("color: #F1F5F9; font-weight: bold; font-size: 12px;")
        prefix_layout.addWidget(prefix_lbl)
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("Để trống sẽ tự động đặt theo nội dung...")
        prefix_layout.addWidget(self.prefix_edit)
        ec_layout.addLayout(prefix_layout)

        # Thư mục lưu
        dir_layout = QVBoxLayout()
        dir_lbl = QLabel("Thư mục lưu âm thanh:")
        dir_lbl.setStyleSheet("color: #F1F5F9; font-weight: bold; font-size: 12px;")
        dir_layout.addWidget(dir_lbl)

        dir_btns = QHBoxLayout()
        self.btn_select_dir = QPushButton("📁 Chọn thư mục...")
        self.btn_select_dir.setProperty("class", "SecondaryBtn")
        self.btn_select_dir.setCursor(Qt.PointingHandCursor)
        self.btn_select_dir.clicked.connect(self._select_output_dir)
        dir_btns.addWidget(self.btn_select_dir)

        self.btn_open_out_dir = QPushButton("📂 Mở thư mục")
        self.btn_open_out_dir.setProperty("class", "SecondaryBtn")
        self.btn_open_out_dir.setCursor(Qt.PointingHandCursor)
        self.btn_open_out_dir.clicked.connect(self._open_output_folder)
        dir_btns.addWidget(self.btn_open_out_dir)
        dir_layout.addLayout(dir_btns)
        ec_layout.addLayout(dir_layout)

        layout.addWidget(export_card)

        # -------------------------------------------------------------
        # 4. NÚT TẠO GIỌNG NÓI CHÍNH (PROMINENT ACTION BUTTON)
        # -------------------------------------------------------------
        action_layout = QHBoxLayout()
        self.btn_generate = QPushButton("▶  TẠO GIỌNG NÓI")
        self.btn_generate.setProperty("class", "PrimaryBtn")
        self.btn_generate.setFixedHeight(48)
        self.btn_generate.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.btn_generate.setCursor(Qt.PointingHandCursor)
        self.btn_generate.clicked.connect(self._start_synthesize)
        action_layout.addWidget(self.btn_generate)
        layout.addLayout(action_layout)

        # Thanh tiến trình xử lý
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate animation
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_msg_lbl = QLabel("")
        self.status_msg_lbl.setStyleSheet("font-size: 12px; font-weight: 500;")
        self.status_msg_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_msg_lbl)

        # -------------------------------------------------------------
        # 5. KHU VỰC PHÁT ÂM THANH KẾT QUẢ (AUDIO PLAYER CARD)
        # -------------------------------------------------------------
        self.player_card = QFrame()
        self.player_card.setProperty("class", "CardFrame")
        self.player_card.setStyleSheet("background-color: #172235; border: 1px solid #1687FF; border-radius: 8px;")
        self.player_card.setVisible(False)

        pc_layout = QVBoxLayout(self.player_card)
        pc_layout.setContentsMargins(16, 12, 16, 12)
        pc_layout.setSpacing(10)

        # Thông tin file vừa tạo
        info_row = QHBoxLayout()
        self.res_title_lbl = QLabel("🎉 TẠO ÂM THANH THÀNH CÔNG!")
        self.res_title_lbl.setStyleSheet("color: #22C55E; font-weight: bold; font-size: 13px;")
        info_row.addWidget(self.res_title_lbl)
        info_row.addStretch()

        self.res_details_lbl = QLabel("")
        self.res_details_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        info_row.addWidget(self.res_details_lbl)
        pc_layout.addLayout(info_row)

        self.res_path_lbl = QLabel("")
        self.res_path_lbl.setStyleSheet("color: #F1F5F9; font-family: Consolas; font-size: 11px;")
        self.res_path_lbl.setWordWrap(True)
        pc_layout.addWidget(self.res_path_lbl)

        # Hàng thanh trượt thời gian phát
        seek_row = QHBoxLayout()
        self.playback_time_lbl = QLabel("0:00 / 0:00")
        self.playback_time_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; min-width: 75px;")
        seek_row.addWidget(self.playback_time_lbl)

        self.player_slider = QSlider(Qt.Horizontal)
        self.player_slider.setRange(0, 1000)
        self.player_slider.setValue(0)
        self.player_slider.sliderMoved.connect(self._on_seek_slider_moved)
        seek_row.addWidget(self.player_slider)
        pc_layout.addLayout(seek_row)

        # Hàng nút điều khiển phát
        ctrl_row = QHBoxLayout()
        self.btn_play_pause = QPushButton("▶ Nghe Thử")
        self.btn_play_pause.setProperty("class", "PrimaryBtn")
        self.btn_play_pause.setCursor(Qt.PointingHandCursor)
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        ctrl_row.addWidget(self.btn_play_pause)

        self.btn_stop = QPushButton("⏹ Dừng")
        self.btn_stop.setProperty("class", "SecondaryBtn")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.clicked.connect(self._stop_playback)
        ctrl_row.addWidget(self.btn_stop)

        ctrl_row.addStretch()

        btn_open_file_loc = QPushButton("📂 Mở tệp trong Explorer")
        btn_open_file_loc.setProperty("class", "SecondaryBtn")
        btn_open_file_loc.setCursor(Qt.PointingHandCursor)
        btn_open_file_loc.clicked.connect(self._open_file_location)
        ctrl_row.addWidget(btn_open_file_loc)

        btn_copy_path = QPushButton("📋 Sao chép đường dẫn")
        btn_copy_path.setProperty("class", "SecondaryBtn")
        btn_copy_path.setCursor(Qt.PointingHandCursor)
        btn_copy_path.clicked.connect(self._copy_audio_path)
        ctrl_row.addWidget(btn_copy_path)

        pc_layout.addLayout(ctrl_row)
        layout.addWidget(self.player_card)

        layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    # =========================================================================
    # CÁC HÀM XỬ LÝ SỰ KIỆN
    # =========================================================================
    def refresh_voices(self):
        """Cập nhật danh sách giọng đọc từ engine."""
        curr_id = self.voice_combo.currentData()
        self.voice_combo.clear()

        voices = tts_service.list_voices()
        default_idx = 0

        for idx, v in enumerate(voices):
            vid = v["id"]
            label = v.get("label", vid)
            self.voice_combo.addItem(label, vid)
            if vid == curr_id or vid == "Hải Đăng":
                default_idx = idx

        if self.voice_combo.count() > 0:
            self.voice_combo.setCurrentIndex(default_idx)
            self._on_voice_changed(default_idx)

    def _on_voice_changed(self, index: int):
        vid = self.voice_combo.currentData()
        if not vid:
            return
        voices = tts_service.list_voices()
        for v in voices:
            if v["id"] == vid:
                gender = v.get("gender", "")
                region = v.get("region", "")
                style = v.get("style", "")
                desc = v.get("description", "")
                self.voice_desc_lbl.setText(f"🏷️ {gender} · {region} · {style} — {desc}")
                break

    def _on_text_changed(self):
        txt = self.text_edit.toPlainText().strip()
        chars = len(txt)
        words = len(txt.split()) if txt else 0
        self.char_count_lbl.setText(f"{chars:,} ký tự  |  {words:,} từ")

    def _on_speed_changed(self, val: int):
        speed_float = val / 100.0
        self.speed_val_lbl.setText(f"{speed_float:.2f}x")

    def _paste_clipboard(self):
        clip = QApplication.clipboard()
        self.text_edit.insertPlainText(clip.text())

    def _clear_text(self):
        self.text_edit.clear()

    def _import_text_file(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn tệp văn bản",
            "",
            "Văn bản (*.txt *.docx *.pdf);;Tất cả tệp (*.*)",
        )
        if not fpath:
            return
        p = Path(fpath)
        try:
            if p.suffix.lower() == ".txt":
                content = p.read_text(encoding="utf-8", errors="replace")
            elif p.suffix.lower() == ".docx":
                import docx
                doc = docx.Document(str(p))
                content = "\n".join([para.text for para in doc.paragraphs])
            elif p.suffix.lower() == ".pdf":
                import pypdf
                reader = pypdf.PdfReader(str(p))
                content = "\n".join([page.extract_text() or "" for page in reader.pages])
            else:
                content = p.read_text(encoding="utf-8", errors="replace")
            self.text_edit.setPlainText(content)
        except Exception as e:
            QMessageBox.critical(self, "Lỗi đọc tệp", f"Không thể đọc tệp văn bản: {e}")

    def _select_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu file âm thanh")
        if dir_path:
            self.selected_out_dir = Path(dir_path)
            self.btn_select_dir.setText(f"📁 .../{self.selected_out_dir.name}")
            self.btn_select_dir.setToolTip(str(self.selected_out_dir))

    def _open_output_folder(self):
        folder = self.selected_out_dir or tts_service.default_out_dir
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(folder))
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _start_synthesize(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Chưa nhập văn bản", "Vui lòng nhập văn bản tiếng Việt cần đọc.")
            return

        # Kiểm tra bản quyền trước khi bắt đầu
        lic_info = tts_service.get_license_info()
        if not lic_info["is_active"]:
            QMessageBox.critical(
                self,
                "Bản quyền không hợp lệ",
                f"Chức năng tạo giọng nói bị khóa:\n\n{lic_info['status_message']}\n\n"
                "Vui lòng vào tab 'Bản quyền & Giấy phép' để kích hoạt key mới.",
            )
            return

        voice_id = self.voice_combo.currentData() or "Hải Đăng"
        speed = self.speed_slider.value() / 100.0
        out_fmt = "mp3" if self.radio_mp3.isChecked() else "wav"
        prefix = self.prefix_edit.text().strip()

        # Dừng phát âm thanh cũ nếu đang phát
        audio_player.stop()
        self.playback_timer.stop()

        # Cập nhật trạng thái UI
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("⏳ Đang tổng hợp giọng nói...")
        self.progress_bar.setVisible(True)
        self.status_msg_lbl.setText("Đang chạy mô hình VieNeu-TTS v3 Turbo ONNX CPU...")
        self.status_msg_lbl.setStyleSheet("color: #22D3EE;")
        self.player_card.setVisible(False)

        # Khởi chạy Worker Thread
        self.worker = SynthesisWorker(
            text=text,
            voice_id=voice_id,
            speed=speed,
            out_format=out_fmt,
            filename_prefix=prefix,
            custom_out_dir=self.selected_out_dir,
        )
        self.worker.finished.connect(self._on_synthesis_finished)
        self.worker.error.connect(self._on_synthesis_error)
        self.worker.start()

    def _on_synthesis_finished(self, res: dict):
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("▶  TẠO GIỌNG NÓI")
        self.progress_bar.setVisible(False)

        if not res.get("success"):
            err_msg = res.get("error", "Lỗi tổng hợp âm thanh.")
            self.status_msg_lbl.setText(f"❌ {err_msg}")
            self.status_msg_lbl.setStyleSheet("color: #EF4444;")
            QMessageBox.critical(self, "Lỗi tạo giọng", err_msg)
            return

        self.last_result = res
        self.status_msg_lbl.setText("✅ Tổng hợp âm thanh hoàn tất!")
        self.status_msg_lbl.setStyleSheet("color: #22C55E;")

        # Hiển thị kết quả trong Player Card
        main_file = Path(res["main_file"])
        size_mb = res["size_bytes"] / (1024 * 1024)
        self.res_details_lbl.setText(
            f"Thời lượng: {res['duration']}s  ·  Dung lượng: {size_mb:.2f} MB  ·  Giọng: {res['voice']}  ·  Tốc độ: {res['speed']}x"
        )
        self.res_path_lbl.setText(f"📍 Tệp: {main_file.name}\n({str(main_file)})")

        self.player_card.setVisible(True)
        self.btn_play_pause.setText("▶ Nghe Thử")
        self.player_slider.setValue(0)
        self.playback_time_lbl.setText(f"0:00 / {self._format_seconds(res['duration'])}")

        self.audio_generated.emit(res)

    def _on_synthesis_error(self, err: str):
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("▶  TẠO GIỌNG NÓI")
        self.progress_bar.setVisible(False)
        self.status_msg_lbl.setText(f"❌ Lỗi: {err}")
        self.status_msg_lbl.setStyleSheet("color: #EF4444;")
        QMessageBox.critical(self, "Lỗi", f"Quá trình xử lý gặp lỗi:\n\n{err}")

    # =========================================================================
    # ĐIỀU KHIỂN PHÁT ÂM THANH
    # =========================================================================
    def _toggle_play_pause(self):
        if not self.last_result or not self.last_result.get("main_file"):
            return

        main_file = self.last_result["main_file"]

        if audio_player.is_playing():
            audio_player.pause()
            self.btn_play_pause.setText("▶ Tiếp tục")
            self.playback_timer.stop()
        elif audio_player.is_paused():
            audio_player.resume()
            self.btn_play_pause.setText("⏸ Tạm dừng")
            self.playback_timer.start()
        else:
            # Phát từ đầu
            ok = audio_player.play(main_file)
            if ok:
                self.btn_play_pause.setText("⏸ Tạm dừng")
                self.playback_timer.start()
            else:
                QMessageBox.warning(self, "Không thể phát", f"Không thể phát tệp âm thanh: {main_file}")

    def _stop_playback(self):
        audio_player.stop()
        self.playback_timer.stop()
        self.btn_play_pause.setText("▶ Nghe Thử")
        self.player_slider.setValue(0)

    def _update_playback_progress(self):
        if not audio_player.is_playing() and not audio_player.is_paused():
            self.btn_play_pause.setText("▶ Nghe Thử")
            self.playback_timer.stop()
            self.player_slider.setValue(0)
            return

        pos_ms = audio_player.get_position_ms()
        dur_ms = audio_player.get_duration_ms()
        if dur_ms > 0:
            val = int((pos_ms / float(dur_ms)) * 1000)
            self.player_slider.blockSignals(True)
            self.player_slider.setValue(val)
            self.player_slider.blockSignals(False)
            self.playback_time_lbl.setText(
                f"{self._format_seconds(pos_ms / 1000.0)} / {self._format_seconds(dur_ms / 1000.0)}"
            )

    def _on_seek_slider_moved(self, val: int):
        dur_ms = audio_player.get_duration_ms()
        if dur_ms > 0:
            target_ms = int((val / 1000.0) * dur_ms)
            audio_player.seek_ms(target_ms)

    def _open_file_location(self):
        if not self.last_result or not self.last_result.get("main_file"):
            return
        f = Path(self.last_result["main_file"])
        if f.exists() and sys.platform == "win32":
            subprocess.run(f'explorer /select,"{str(f)}"', shell=True)
        elif f.parent.exists():
            os.startfile(str(f.parent))

    def _copy_audio_path(self):
        if self.last_result and self.last_result.get("main_file"):
            clip = QApplication.clipboard()
            clip.setText(self.last_result["main_file"])
            QMessageBox.information(self, "Đã sao chép", "Đã sao chép đường dẫn tệp âm thanh vào bộ nhớ đệm.")

    def _format_seconds(self, s: float) -> str:
        s = int(s)
        mins = s // 60
        secs = s % 60
        return f"{mins}:{secs:02d}"
