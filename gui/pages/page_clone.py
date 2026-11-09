"""gui/pages/page_clone.py — TAB 2: NHÂN BẢN GIỌNG NÓI (VOICE CLONING)
=====================================================================
Chức năng nhân bản giọng nói hỗ trợ 2 chế độ:
1. 🎙️ Thu âm trực tiếp qua Micro trên máy tính.
2. 📁 Tải lên tệp âm thanh có sẵn (WAV / MP3 / M4A / FLAC / OGG).
- Nghe thử tệp âm thanh mẫu trước khi nhân bản.
- Đặt tên định danh cho giọng nhân bản.
- Xử lý nền bằng QThread qua engine VieNeu-TTS denoise & embedding.
- Tự động lưu vào custom_voices.json và cập nhật ngay lập tức vào danh sách giọng đọc.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QFrame,
    QProgressBar,
    QScrollArea,
    QButtonGroup,
)

from backend.service import tts_service
from backend.audio_player import audio_player
from backend.recorder import MicRecorderThread, get_available_mics


class CloneWorker(QThread):
    """Tiểu trình xử lý nén mẫu giọng và trích xuất embedding."""

    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, voice_name: str, ref_audio_path: str, description: str):
        super().__init__()
        self.voice_name = voice_name
        self.ref_audio_path = ref_audio_path
        self.description = description

    def run(self):
        try:
            res = tts_service.clone_voice(
                voice_name=self.voice_name,
                ref_audio_path=self.ref_audio_path,
                description=self.description,
            )
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class PageClone(QWidget):
    """Trang Nhân Bản Giọng Nói hỗ trợ Thu âm trực tiếp & Nạp tệp có sẵn."""

    voice_cloned = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.selected_ref_file: Optional[Path] = None
        self.worker: Optional[CloneWorker] = None
        self.rec_thread: Optional[MicRecorderThread] = None
        self.is_recording = False
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(16)

        # 1. KHUNG HƯỚNG DẪN NHÂN BẢN
        info_card = QFrame()
        info_card.setProperty("class", "CardFrame")
        ic_layout = QVBoxLayout(info_card)
        ic_layout.setContentsMargins(14, 12, 14, 12)

        info_title = QLabel("🧬 NHÂN BẢN GIỌNG NÓI CÁ NHÂN (VOICE CLONING)")
        info_title.setProperty("class", "CardTitle")
        ic_layout.addWidget(info_title)

        info_text = QLabel(
            "Hệ thống cho phép bạn nhân bản giọng nói từ mẫu âm thanh để đọc bất kỳ văn bản nào.<br>"
            "<b>Yêu cầu âm thanh mẫu đạt chuẩn:</b><br>"
            "• Thời lượng khuyến nghị: từ <b>5 đến 15 giây</b> (nói tự nhiên, không ngắt quãng quá dài).<br>"
            "• VieNeu-TTS v3 Turbo sẽ tự động khử nhiễu và trích xuất vector đặc trưng giọng nói."
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.5;")
        ic_layout.addWidget(info_text)
        layout.addWidget(info_card)

        # 2. KHUNG CHỌN NGUỒN ÂM THANH (CHUYỂN ĐỔI: MICRO HOẶC FILE CÓ SẴN)
        source_card = QFrame()
        source_card.setProperty("class", "CardFrame")
        sc_layout = QVBoxLayout(source_card)
        sc_layout.setContentsMargins(14, 12, 14, 12)
        sc_layout.setSpacing(12)

        s_title = QLabel("1. CHỌN NGUỒN ÂM THANH MẪU (REFERENCE AUDIO)")
        s_title.setProperty("class", "CardTitle")
        sc_layout.addWidget(s_title)

        # Thanh chọn chế độ: Thu âm Micro vs Tải tệp có sẵn
        mode_row = QHBoxLayout()
        self.btn_mode_mic = QPushButton("🎙️ Thu Âm Trực Tiếp Qua Micro")
        self.btn_mode_mic.setProperty("class", "SecondaryBtn")
        self.btn_mode_mic.setCheckable(True)
        self.btn_mode_mic.setChecked(True)
        self.btn_mode_mic.setCursor(Qt.PointingHandCursor)
        self.btn_mode_mic.clicked.connect(self._select_mic_mode)
        mode_row.addWidget(self.btn_mode_mic)

        self.btn_mode_file = QPushButton("📁 Tải Lên Tệp Âm Thanh Có Sẵn")
        self.btn_mode_file.setProperty("class", "SecondaryBtn")
        self.btn_mode_file.setCheckable(True)
        self.btn_mode_file.setCursor(Qt.PointingHandCursor)
        self.btn_mode_file.clicked.connect(self._select_file_mode)
        mode_row.addWidget(self.btn_mode_file)
        mode_row.addStretch()
        sc_layout.addLayout(mode_row)

        # -------------------------------------------------------------
        # PANEL A: THU ÂM TRỰC TIẾP QUA MICRO
        # -------------------------------------------------------------
        self.panel_mic = QFrame()
        pm_layout = QVBoxLayout(self.panel_mic)
        pm_layout.setContentsMargins(8, 8, 8, 8)
        pm_layout.setSpacing(10)

        sample_box = QFrame()
        sample_box.setStyleSheet("background-color: rgba(30, 58, 33, 0.6); border: 1px dashed #22C55E; border-radius: 6px; padding: 10px;")
        sb_layout = QVBoxLayout(sample_box)
        sb_layout.setContentsMargins(8, 6, 8, 6)
        lbl_sample_title = QLabel("📝 <i>Đọc to rõ ràng câu mẫu sau khi bấm nút bắt đầu thu âm:</i>")
        lbl_sample_title.setStyleSheet("color: #FFD700; font-size: 12px; font-weight: bold;")
        sb_layout.addWidget(lbl_sample_title)
        self.lbl_sample_quote = QLabel(
            "\"Tôi là [Họ và tên], tôi xác nhận đây là mẫu âm thanh giọng nói của chính tôi để phục vụ công tác và nghiên cứu.\""
        )
        self.lbl_sample_quote.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 600; font-style: italic;")
        self.lbl_sample_quote.setWordWrap(True)
        sb_layout.addWidget(self.lbl_sample_quote)
        pm_layout.addWidget(sample_box)

        rec_ctrl_row = QHBoxLayout()
        self.btn_record_toggle = QPushButton("🔴 Bắt đầu thu âm")
        self.btn_record_toggle.setProperty("class", "PrimaryBtn")
        self.btn_record_toggle.setFixedHeight(40)
        self.btn_record_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_record_toggle.clicked.connect(self._toggle_recording)
        rec_ctrl_row.addWidget(self.btn_record_toggle)

        self.btn_preview_mic = QPushButton("▶ Nghe lại bản ghi")
        self.btn_preview_mic.setProperty("class", "SecondaryBtn")
        self.btn_preview_mic.setFixedHeight(40)
        self.btn_preview_mic.setEnabled(False)
        self.btn_preview_mic.setCursor(Qt.PointingHandCursor)
        self.btn_preview_mic.clicked.connect(self._preview_mic_audio)
        rec_ctrl_row.addWidget(self.btn_preview_mic)

        self.lbl_rec_timer = QLabel("⏱️ 00:00 (Khuyến nghị: 5 - 15 giây)")
        self.lbl_rec_timer.setStyleSheet("color: #22D3EE; font-size: 13px; font-weight: bold; margin-left: 10px;")
        rec_ctrl_row.addWidget(self.lbl_rec_timer)
        rec_ctrl_row.addStretch()
        pm_layout.addLayout(rec_ctrl_row)

        self.lbl_mic_status = QLabel("")
        self.lbl_mic_status.setStyleSheet("color: #94A3B8; font-size: 12px;")
        pm_layout.addWidget(self.lbl_mic_status)

        sc_layout.addWidget(self.panel_mic)

        # -------------------------------------------------------------
        # PANEL B: CHỌN TỆP ÂM THANH CÓ SẴN (WAV/MP3)
        # -------------------------------------------------------------
        self.panel_file = QFrame()
        self.panel_file.setVisible(False)
        pf_layout = QVBoxLayout(self.panel_file)
        pf_layout.setContentsMargins(8, 8, 8, 8)
        pf_layout.setSpacing(10)

        file_row = QHBoxLayout()
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setPlaceholderText("Chưa chọn tệp âm thanh mẫu...")
        file_row.addWidget(self.file_path_edit)

        self.btn_browse = QPushButton("📁 Chọn tệp WAV/MP3...")
        self.btn_browse.setProperty("class", "SecondaryBtn")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.clicked.connect(self._browse_audio)
        file_row.addWidget(self.btn_browse)

        self.btn_preview_file = QPushButton("▶ Nghe thử")
        self.btn_preview_file.setProperty("class", "SecondaryBtn")
        self.btn_preview_file.setEnabled(False)
        self.btn_preview_file.setCursor(Qt.PointingHandCursor)
        self.btn_preview_file.clicked.connect(self._preview_file_audio)
        file_row.addWidget(self.btn_preview_file)
        pf_layout.addLayout(file_row)

        self.ref_info_lbl = QLabel("")
        self.ref_info_lbl.setStyleSheet("color: #22D3EE; font-size: 12px;")
        pf_layout.addWidget(self.ref_info_lbl)

        sc_layout.addWidget(self.panel_file)
        layout.addWidget(source_card)

        # 3. KHUNG ĐẶT TÊN VÀ THÔNG TIN GIỌNG
        name_card = QFrame()
        name_card.setProperty("class", "CardFrame")
        nc_layout = QVBoxLayout(name_card)
        nc_layout.setContentsMargins(14, 12, 14, 12)
        nc_layout.setSpacing(10)

        n_title = QLabel("2. ĐẶT TÊN GIỌNG NHÂN BẢN")
        n_title.setProperty("class", "CardTitle")
        nc_layout.addWidget(n_title)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ví dụ: Giọng Bác Ba, MC Thùy Linh, Giọng Cá Nhân...")
        nc_layout.addWidget(self.name_edit)

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Mô tả bổ sung (tùy chọn, ví dụ: Giọng ấm, truyền cảm, nói rõ)...")
        nc_layout.addWidget(self.desc_edit)
        layout.addWidget(name_card)

        # 4. NÚT THỰC HIỆN NHÂN BẢN
        self.btn_clone = QPushButton("🧬  BẮT ĐẦU NHÂN BẢN GIỌNG NÓI")
        self.btn_clone.setProperty("class", "PrimaryBtn")
        self.btn_clone.setFixedHeight(46)
        self.btn_clone.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.btn_clone.setCursor(Qt.PointingHandCursor)
        self.btn_clone.clicked.connect(self._start_cloning)
        layout.addWidget(self.btn_clone)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setStyleSheet("font-size: 13px; font-weight: 500;")
        layout.addWidget(self.status_lbl)

        layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _select_mic_mode(self):
        self.btn_mode_mic.setChecked(True)
        self.btn_mode_file.setChecked(False)
        self.panel_mic.setVisible(True)
        self.panel_file.setVisible(False)

    def _select_file_mode(self):
        self.btn_mode_mic.setChecked(False)
        self.btn_mode_file.setChecked(True)
        self.panel_mic.setVisible(False)
        self.panel_file.setVisible(True)

    # -----------------------------------------------------------------
    # MICROPHONE RECORDING LOGIC
    # -----------------------------------------------------------------
    def _toggle_recording(self):
        if not self.is_recording:
            # Bắt đầu thu âm
            mics = get_available_mics()
            if not mics:
                QMessageBox.warning(
                    self,
                    "Không tìm thấy Micro",
                    "⚠️ Hệ thống không phát hiện thấy thiết bị Microphone nào đang kết nối.\n\n"
                    "• Vui lòng cắm Micro / Tai nghe vào máy tính.\n"
                    "• Hoặc chuyển sang tab 'Tải lên tệp âm thanh có sẵn' để sử dụng file ghi âm từ điện thoại.",
                )
                return

            # Dừng phát nếu đang phát
            if audio_player.is_playing():
                audio_player.stop()

            stamp = int(time.time() * 1000)
            rec_save_path = tts_service.upload_dir / f"mic_clone_{stamp}.wav"

            self.rec_thread = MicRecorderThread(save_path=rec_save_path)
            self.rec_thread.tick.connect(self._on_rec_tick)
            self.rec_thread.finished.connect(self._on_rec_finished)
            self.rec_thread.error.connect(self._on_rec_error)

            self.is_recording = True
            self.btn_record_toggle.setText("⏹ Dừng thu âm")
            self.btn_record_toggle.setProperty("class", "DangerBtn")
            self.btn_record_toggle.style().unpolish(self.btn_record_toggle)
            self.btn_record_toggle.style().polish(self.btn_record_toggle)

            self.btn_preview_mic.setEnabled(False)
            self.lbl_rec_timer.setText("🔴 Đang thu âm: 00:00...")
            self.lbl_mic_status.setText("🔴 Đang ghi âm từ Micro... Hãy đọc to câu mẫu ở trên.")
            self.lbl_mic_status.setStyleSheet("color: #EF4444; font-weight: bold;")

            self.rec_thread.start()
        else:
            # Dừng thu âm
            if self.rec_thread and self.rec_thread.isRunning():
                self.btn_record_toggle.setEnabled(False)
                self.lbl_mic_status.setText("⏳ Đang lưu tệp thu âm...")
                self.rec_thread.request_stop()

    def _on_rec_tick(self, elapsed: float):
        m = int(elapsed // 60)
        s = int(elapsed % 60)
        self.lbl_rec_timer.setText(f"🔴 Đang thu âm: {m:02d}:{s:02d} ({elapsed:.1f}s)")

    def _on_rec_finished(self, wav_path_str: str, duration: float):
        self.is_recording = False
        self.btn_record_toggle.setEnabled(True)
        self.btn_record_toggle.setText("🔴 Bắt đầu thu âm lại")
        self.btn_record_toggle.setProperty("class", "PrimaryBtn")
        self.btn_record_toggle.style().unpolish(self.btn_record_toggle)
        self.btn_record_toggle.style().polish(self.btn_record_toggle)

        p = Path(wav_path_str)
        self.selected_ref_file = p
        self.btn_preview_mic.setEnabled(True)

        self.lbl_rec_timer.setText(f"✅ Đã thu âm: {duration:.1f} giây")
        self.lbl_mic_status.setText(f"📁 Tệp mẫu: {p.name} ({duration:.1f}s) — Đã sẵn sàng nhân bản.")
        self.lbl_mic_status.setStyleSheet("color: #22C55E; font-weight: bold;")

        if not self.name_edit.text().strip():
            self.name_edit.setText("Giọng Thu Âm Cá Nhân")

    def _on_rec_error(self, err: str):
        self.is_recording = False
        self.btn_record_toggle.setEnabled(True)
        self.btn_record_toggle.setText("🔴 Bắt đầu thu âm")
        self.btn_record_toggle.setProperty("class", "PrimaryBtn")
        self.btn_record_toggle.style().unpolish(self.btn_record_toggle)
        self.btn_record_toggle.style().polish(self.btn_record_toggle)

        self.lbl_mic_status.setText(f"❌ {err}")
        self.lbl_mic_status.setStyleSheet("color: #EF4444;")
        QMessageBox.warning(self, "Lỗi thu âm", err)

    def _preview_mic_audio(self):
        if not self.selected_ref_file or not self.selected_ref_file.is_file():
            return
        if audio_player.is_playing():
            audio_player.stop()
            self.btn_preview_mic.setText("▶ Nghe lại bản ghi")
        else:
            ok = audio_player.play(str(self.selected_ref_file))
            if ok:
                self.btn_preview_mic.setText("⏹ Dừng")
            else:
                QMessageBox.warning(self, "Không thể phát", f"Không thể phát tệp: {self.selected_ref_file.name}")

    # -----------------------------------------------------------------
    # FILE BROWSER LOGIC
    # -----------------------------------------------------------------
    def _browse_audio(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn tệp âm thanh mẫu để nhân bản",
            "",
            "Âm thanh (*.wav *.mp3 *.m4a *.flac *.ogg);;Tất cả tệp (*.*)",
        )
        if not fpath:
            return
        p = Path(fpath)
        self.selected_ref_file = p
        self.file_path_edit.setText(str(p))
        self.btn_preview_file.setEnabled(True)

        size_kb = p.stat().st_size / 1024
        self.ref_info_lbl.setText(f"📁 Tệp: {p.name} ({size_kb:.1f} KB)")

        # Gợi ý tên nếu ô tên đang trống
        if not self.name_edit.text().strip():
            suggest = p.stem.replace("_", " ").title()
            self.name_edit.setText(f"Giọng {suggest}")

    def _preview_file_audio(self):
        if not self.selected_ref_file or not self.selected_ref_file.is_file():
            return
        if audio_player.is_playing():
            audio_player.stop()
            self.btn_preview_file.setText("▶ Nghe thử")
        else:
            ok = audio_player.play(str(self.selected_ref_file))
            if ok:
                self.btn_preview_file.setText("⏹ Dừng")
            else:
                QMessageBox.warning(self, "Không thể phát", f"Không thể phát tệp: {self.selected_ref_file.name}")

    # -----------------------------------------------------------------
    # CLONING LOGIC
    # -----------------------------------------------------------------
    def _start_cloning(self):
        lic = tts_service.get_license_info()
        if not lic["is_active"]:
            QMessageBox.critical(
                self,
                "Bản quyền không hợp lệ",
                f"Chức năng nhân bản giọng bị khóa:\n\n{lic['status_message']}\n\n"
                "Vui lòng vào tab 'Bản quyền & Giấy phép' để kích hoạt key mới.",
            )
            return

        if not self.selected_ref_file or not self.selected_ref_file.is_file():
            QMessageBox.warning(
                self,
                "Chưa có tệp âm thanh",
                "Vui lòng thu âm từ Micro hoặc chọn một tệp âm thanh mẫu (WAV hoặc MP3).",
            )
            return

        voice_name = self.name_edit.text().strip()
        if not voice_name:
            QMessageBox.warning(self, "Chưa đặt tên", "Vui lòng đặt tên cho giọng nhân bản.")
            return

        # Dừng phát âm thanh
        audio_player.stop()
        self.btn_preview_mic.setText("▶ Nghe lại bản ghi")
        self.btn_preview_file.setText("▶ Nghe thử")

        self.btn_clone.setEnabled(False)
        self.btn_clone.setText("⏳ Đang phân tích và nhân bản giọng...")
        self.progress_bar.setVisible(True)
        self.status_lbl.setText("Đang trích xuất đặc trưng âm sắc VieNeu-TTS v3 Turbo...")
        self.status_lbl.setStyleSheet("color: #22D3EE;")

        self.worker = CloneWorker(
            voice_name=voice_name,
            ref_audio_path=str(self.selected_ref_file),
            description=self.desc_edit.text().strip(),
        )
        self.worker.finished.connect(self._on_clone_finished)
        self.worker.error.connect(self._on_clone_error)
        self.worker.start()

    def _on_clone_finished(self, res: dict):
        self.btn_clone.setEnabled(True)
        self.btn_clone.setText("🧬  BẮT ĐẦU NHÂN BẢN GIỌNG NÓI")
        self.progress_bar.setVisible(False)

        if not res.get("success"):
            err = res.get("error", "Lỗi không xác định.")
            self.status_lbl.setText(f"❌ {err}")
            self.status_lbl.setStyleSheet("color: #EF4444;")
            QMessageBox.critical(self, "Lỗi nhân bản", err)
            return

        vname = res.get("voice_name", "")
        self.status_lbl.setText(f"✅ Nhân bản thành công giọng '{vname}'!")
        self.status_lbl.setStyleSheet("color: #22C55E;")

        QMessageBox.information(
            self,
            "Nhân Bản Thành Công",
            f"🎉 Giọng '{vname}' đã được nhân bản thành công và lưu trữ an toàn!\n\n"
            "Bây giờ bạn có thể quay lại màn hình 'Tạo Giọng Nói' để sử dụng giọng này.",
        )

        self.voice_cloned.emit(vname)

    def _on_clone_error(self, err: str):
        self.btn_clone.setEnabled(True)
        self.btn_clone.setText("🧬  BẮT ĐẦU NHÂN BẢN GIỌNG NÓI")
        self.progress_bar.setVisible(False)
        self.status_lbl.setText(f"❌ Lỗi: {err}")
        self.status_lbl.setStyleSheet("color: #EF4444;")
        QMessageBox.critical(self, "Lỗi", f"Quá trình nhân bản gặp lỗi:\n\n{err}")
