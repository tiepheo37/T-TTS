"""gui/pages/page_clone.py — TAB 2: NHÂN BẢN GIỌNG NÓI (VOICE CLONING)
=====================================================================
Chức năng nhân bản giọng nói từ file âm thanh mẫu:
- Chọn file WAV/MP3 mẫu (khuyên dùng 5-15 giây nói rõ ràng, ít tạp âm).
- Nghe thử tệp âm thanh mẫu trước khi nhân bản.
- Đặt tên định danh cho giọng nhân bản.
- Xử lý nền bằng QThread qua engine VieNeu-TTS denoise & embedding.
- Tự động lưu vào custom_voices.json và cập nhật ngay lập tức vào danh sách giọng đọc.
"""

from __future__ import annotations

import os
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
)

from backend.service import tts_service
from backend.audio_player import audio_player


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
    """Trang Nhân Bản Giọng Nói."""

    voice_cloned = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.selected_ref_file: Optional[Path] = None
        self.worker: Optional[CloneWorker] = None
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

        info_title = QLabel("🧬 NHÂN BẢN GIỌNG NÓI TỪ FILE ÂM THANH MẪU")
        info_title.setProperty("class", "CardTitle")
        ic_layout.addWidget(info_title)

        info_text = QLabel(
            "Tính năng này cho phép bạn nhân bản giọng nói của bản thân hoặc người khác để đọc văn bản.<br>"
            "<b>Yêu cầu âm thanh mẫu đạt chuẩn:</b><br>"
            "• Định dạng: WAV hoặc MP3 rõ tiếng, không lẫn nhạc nền hoặc tạp âm lớn.<br>"
            "• Thời lượng khuyến nghị: từ <b>5 đến 15 giây</b> (nói tự nhiên, ngắt nghỉ rõ ràng).<br>"
            "• VieNeu-TTS v3 Turbo sẽ tự động khử nhiễu và trích xuất vector đặc trưng giọng nói."
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.5;")
        ic_layout.addWidget(info_text)
        layout.addWidget(info_card)

        # 2. KHUNG CHỌN TỆP ÂM THANH MẪU
        file_card = QFrame()
        file_card.setProperty("class", "CardFrame")
        fc_layout = QVBoxLayout(file_card)
        fc_layout.setContentsMargins(14, 12, 14, 12)
        fc_layout.setSpacing(10)

        f_title = QLabel("1. CHỌN TỆP ÂM THANH MẪU (REFERENCE AUDIO)")
        f_title.setProperty("class", "CardTitle")
        fc_layout.addWidget(f_title)

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

        self.btn_preview_ref = QPushButton("▶ Nghe thử")
        self.btn_preview_ref.setProperty("class", "SecondaryBtn")
        self.btn_preview_ref.setEnabled(False)
        self.btn_preview_ref.setCursor(Qt.PointingHandCursor)
        self.btn_preview_ref.clicked.connect(self._preview_ref_audio)
        file_row.addWidget(self.btn_preview_ref)
        fc_layout.addLayout(file_row)

        self.ref_info_lbl = QLabel("")
        self.ref_info_lbl.setStyleSheet("color: #22D3EE; font-size: 12px;")
        fc_layout.addWidget(self.ref_info_lbl)
        layout.addWidget(file_card)

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
        self.desc_edit.setPlaceholderText("Mô tả bổ sung (tùy chọn, ví dụ: Giọng ấm, truyền cảm)...")
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
        self.btn_preview_ref.setEnabled(True)

        size_kb = p.stat().st_size / 1024
        self.ref_info_lbl.setText(f"📁 Tệp: {p.name} ({size_kb:.1f} KB)")

        # Gợi ý tên nếu ô tên đang trống
        if not self.name_edit.text().strip():
            suggest = p.stem.replace("_", " ").title()
            self.name_edit.setText(f"Giọng {suggest}")

    def _preview_ref_audio(self):
        if not self.selected_ref_file or not self.selected_ref_file.is_file():
            return
        if audio_player.is_playing():
            audio_player.stop()
            self.btn_preview_ref.setText("▶ Nghe thử")
        else:
            ok = audio_player.play(str(self.selected_ref_file))
            if ok:
                self.btn_preview_ref.setText("⏹ Dừng")
            else:
                QMessageBox.warning(self, "Không thể phát", f"Không thể phát tệp: {self.selected_ref_file.name}")

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
            QMessageBox.warning(self, "Chưa chọn tệp", "Vui lòng chọn một tệp âm thanh mẫu (WAV hoặc MP3).")
            return

        voice_name = self.name_edit.text().strip()
        if not voice_name:
            QMessageBox.warning(self, "Chưa đặt tên", "Vui lòng đặt tên cho giọng nhân bản.")
            return

        # Dừng phát âm thanh
        audio_player.stop()
        self.btn_preview_ref.setText("▶ Nghe thử")

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
