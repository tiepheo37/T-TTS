"""gui/pages/page_batch.py — TAB 3: XỬ LÝ HÀNG LOẠT (BATCH TTS PROCESSING)
========================================================================
Tính năng:
- Nhập danh sách nhiều dòng văn bản (mỗi dòng tạo 1 tệp âm thanh độc lập).
- Hoặc chọn nhiều tệp .txt trong máy.
- Bảng quản lý tiến độ từng tác vụ (STT, Nội dung tóm tắt, Trạng thái, Tệp xuất, Thao tác).
- Khả năng tạm dừng / hủy tiến trình an toàn.
- Cơ chế cách ly lỗi: Một tác vụ lỗi không làm dừng hoặc mất kết quả của các tác vụ khác.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor
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
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QProgressBar,
    QApplication,
)

from backend.service import tts_service
from backend.audio_player import audio_player


class BatchWorker(QThread):
    """Tiểu trình xử lý danh sách hàng loạt trong nền."""

    item_finished = Signal(int, int, dict)
    batch_finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        items: List[Dict[str, Any]],
        voice_id: str,
        speed: float,
        out_fmt: str,
        custom_out_dir: Optional[Path] = None,
    ):
        super().__init__()
        self.items = items
        self.voice_id = voice_id
        self.speed = speed
        self.out_fmt = out_fmt
        self.custom_out_dir = custom_out_dir
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        def _check_cancel():
            return self._cancel_requested

        def _on_prog(curr, total, res):
            self.item_finished.emit(curr, total, res)

        try:
            res = tts_service.process_batch(
                items=self.items,
                common_voice=self.voice_id,
                common_speed=self.speed,
                out_format=self.out_fmt,
                custom_out_dir=self.custom_out_dir,
                on_progress=_on_prog,
                should_cancel=_check_cancel,
            )
            self.batch_finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class PageBatch(QWidget):
    """Trang Xử Lý Hàng Loạt."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.selected_out_dir: Optional[Path] = None
        self.worker: Optional[BatchWorker] = None
        self.batch_items: List[Dict[str, Any]] = []

        self._build_ui()
        self.refresh_voices()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # 1. KHUNG NHẬP DANH SÁCH VĂN BẢN
        input_card = QFrame()
        input_card.setProperty("class", "CardFrame")
        ic_layout = QVBoxLayout(input_card)
        ic_layout.setContentsMargins(14, 12, 14, 12)
        ic_layout.setSpacing(8)

        ih_layout = QHBoxLayout()
        i_title = QLabel("⚡ XỬ LÝ HÀNG LOẠT (MỖI DÒNG LÀ 1 TỆP ÂM THANH)")
        i_title.setProperty("class", "CardTitle")
        ih_layout.addWidget(i_title)
        ih_layout.addStretch()

        btn_import_txts = QPushButton("📁 Nạp nhiều file .txt...")
        btn_import_txts.setProperty("class", "SecondaryBtn")
        btn_import_txts.setCursor(Qt.PointingHandCursor)
        btn_import_txts.clicked.connect(self._import_multiple_files)
        ih_layout.addWidget(btn_import_txts)

        btn_clear_input = QPushButton("🗑️ Xóa danh sách")
        btn_clear_input.setProperty("class", "SecondaryBtn")
        btn_clear_input.setCursor(Qt.PointingHandCursor)
        btn_clear_input.clicked.connect(self._clear_input)
        ih_layout.addWidget(btn_clear_input)
        ic_layout.addLayout(ih_layout)

        self.text_batch_edit = QTextEdit()
        self.text_batch_edit.setPlaceholderText(
            "Dán danh sách các câu / đoạn văn bản vào đây, mỗi dòng sẽ xuất thành một tệp âm thanh riêng biệt...\n\n"
            "Ví dụ:\n"
            "Xin chào quý vị khán giả đã đến với chương trình.\n"
            "Hôm nay chúng ta sẽ tìm hiểu về mô hình giọng nói tiếng Việt VieNeu-TTS v3 Turbo.\n"
            "Phần mềm được phát triển bởi Đại úy Nguyễn Văn Tiệp."
        )
        self.text_batch_edit.setFixedHeight(120)
        self.text_batch_edit.setFont(QFont("Segoe UI", 10))
        ic_layout.addWidget(self.text_batch_edit)

        # Cấu hình giọng đọc & tốc độ chung
        cfg_layout = QHBoxLayout()
        lbl_v = QLabel("Giọng đọc:")
        lbl_v.setStyleSheet("color: #F1F5F9; font-weight: bold;")
        cfg_layout.addWidget(lbl_v)

        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(220)
        cfg_layout.addWidget(self.voice_combo)

        lbl_s = QLabel("Tốc độ:")
        lbl_s.setStyleSheet("color: #F1F5F9; font-weight: bold; margin-left: 10px;")
        cfg_layout.addWidget(lbl_s)

        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(75, 150)
        self.speed_slider.setValue(100)
        self.speed_slider.setMaximumWidth(120)
        self.speed_slider.valueChanged.connect(lambda v: self.speed_val_lbl.setText(f"{v/100:.2f}x"))
        cfg_layout.addWidget(self.speed_slider)

        self.speed_val_lbl = QLabel("1.00x")
        self.speed_val_lbl.setStyleSheet("color: #22D3EE; font-weight: bold; min-width: 40px;")
        cfg_layout.addWidget(self.speed_val_lbl)

        # Định dạng
        self.radio_wav = QRadioButton("WAV")
        self.radio_wav.setChecked(True)
        self.radio_mp3 = QRadioButton("MP3")
        self.fmt_group = QButtonGroup(self)
        self.fmt_group.addButton(self.radio_wav)
        self.fmt_group.addButton(self.radio_mp3)
        cfg_layout.addWidget(self.radio_wav)
        cfg_layout.addWidget(self.radio_mp3)

        cfg_layout.addStretch()

        self.btn_select_dir = QPushButton("📁 Thư mục lưu...")
        self.btn_select_dir.setProperty("class", "SecondaryBtn")
        self.btn_select_dir.setCursor(Qt.PointingHandCursor)
        self.btn_select_dir.clicked.connect(self._select_output_dir)
        cfg_layout.addWidget(self.btn_select_dir)

        ic_layout.addLayout(cfg_layout)
        layout.addWidget(input_card)

        # 2. HÀNG ĐIỀU KHIỂN & TIẾN ĐỘ
        ctrl_layout = QHBoxLayout()
        self.btn_start_batch = QPushButton("▶  BẮT ĐẦU XỬ LÝ HÀNG LOẠT")
        self.btn_start_batch.setProperty("class", "PrimaryBtn")
        self.btn_start_batch.setFixedHeight(38)
        self.btn_start_batch.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_start_batch.setCursor(Qt.PointingHandCursor)
        self.btn_start_batch.clicked.connect(self._start_batch)
        ctrl_layout.addWidget(self.btn_start_batch)

        self.btn_cancel_batch = QPushButton("⏹ Dừng lại")
        self.btn_cancel_batch.setProperty("class", "DangerBtn")
        self.btn_cancel_batch.setEnabled(False)
        self.btn_cancel_batch.setCursor(Qt.PointingHandCursor)
        self.btn_cancel_batch.clicked.connect(self._cancel_batch)
        ctrl_layout.addWidget(self.btn_cancel_batch)

        ctrl_layout.addStretch()

        btn_open_folder = QPushButton("📂 Mở thư mục đầu ra")
        btn_open_folder.setProperty("class", "SecondaryBtn")
        btn_open_folder.setCursor(Qt.PointingHandCursor)
        btn_open_folder.clicked.connect(self._open_output_folder)
        ctrl_layout.addWidget(btn_open_folder)
        layout.addLayout(ctrl_layout)

        # Thanh tiến trình tổng thể
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(12)
        layout.addWidget(self.progress_bar)

        self.stats_lbl = QLabel("Sẵn sàng. Chưa có tác vụ nào đang chạy.")
        self.stats_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
        layout.addWidget(self.stats_lbl)

        # 3. BẢNG TIẾN ĐỘ TÁC VỤ
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["STT", "Nội Dung Tóm Tắt", "Trạng Thái", "Tệp Âm Thanh", "Thao Tác"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

    def refresh_voices(self):
        self.voice_combo.clear()
        voices = tts_service.list_voices()
        default_idx = 0
        for idx, v in enumerate(voices):
            self.voice_combo.addItem(v.get("label", v["id"]), v["id"])
            if v["id"] == "Hải Đăng":
                default_idx = idx
        if self.voice_combo.count() > 0:
            self.voice_combo.setCurrentIndex(default_idx)

    def _select_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu tệp hàng loạt")
        if d:
            self.selected_out_dir = Path(d)
            self.btn_select_dir.setText(f"📁 .../{self.selected_out_dir.name}")
            self.btn_select_dir.setToolTip(str(self.selected_out_dir))

    def _open_output_folder(self):
        f = self.selected_out_dir or tts_service.default_out_dir
        f.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(f))
        else:
            subprocess.Popen(["xdg-open", str(f)])

    def _clear_input(self):
        self.text_batch_edit.clear()
        self.table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.stats_lbl.setText("Đã xóa danh sách.")

    def _import_multiple_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn nhiều tệp văn bản .txt",
            "",
            "Văn bản (*.txt);;Tất cả (*.*)",
        )
        if not files:
            return
        lines = []
        for f in files:
            try:
                content = Path(f).read_text(encoding="utf-8", errors="replace").strip()
                if content:
                    lines.append(content.replace("\n", " "))
            except Exception:
                pass
        if lines:
            existing = self.text_batch_edit.toPlainText().strip()
            if existing:
                self.text_batch_edit.setPlainText(existing + "\n" + "\n".join(lines))
            else:
                self.text_batch_edit.setPlainText("\n".join(lines))

    def _start_batch(self):
        lic = tts_service.get_license_info()
        if not lic["is_active"]:
            QMessageBox.critical(
                self,
                "Bản quyền không hợp lệ",
                f"Chức năng xử lý hàng loạt bị khóa:\n\n{lic['status_message']}\n\n"
                "Vui lòng vào tab 'Bản quyền & Giấy phép' để kích hoạt key mới.",
            )
            return

        raw_text = self.text_batch_edit.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "Chưa nhập dữ liệu", "Vui lòng nhập các dòng văn bản cần xử lý.")
            return

        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not lines:
            QMessageBox.warning(self, "Dữ liệu rỗng", "Không tìm thấy dòng văn bản hợp lệ nào.")
            return

        voice_id = self.voice_combo.currentData() or "Hải Đăng"
        speed = self.speed_slider.value() / 100.0
        out_fmt = "mp3" if self.radio_mp3.isChecked() else "wav"

        # Thiết lập bảng tác vụ
        self.batch_items = []
        self.table.setRowCount(len(lines))

        for idx, line in enumerate(lines):
            self.batch_items.append({
                "text": line,
                "voice": voice_id,
                "speed": speed,
                "tag": f"batch_{idx+1:03d}",
            })
            # Cột 0: STT
            self.table.setItem(idx, 0, QTableWidgetItem(f"{idx+1}"))
            # Cột 1: Text
            self.table.setItem(idx, 1, QTableWidgetItem(line[:80] + ("..." if len(line) > 80 else "")))
            # Cột 2: Status
            status_item = QTableWidgetItem("⏳ Đang chờ...")
            status_item.setForeground(QColor("#94A3B8"))
            self.table.setItem(idx, 2, status_item)
            # Cột 3: Tệp xuất
            self.table.setItem(idx, 3, QTableWidgetItem("-"))
            # Cột 4: Thao tác
            self.table.setItem(idx, 4, QTableWidgetItem("-"))

        self.btn_start_batch.setEnabled(False)
        self.btn_cancel_batch.setEnabled(True)
        self.progress_bar.setValue(0)
        self.stats_lbl.setText(f"Đang xử lý 0/{len(lines)} tác vụ...")

        self.worker = BatchWorker(
            items=self.batch_items,
            voice_id=voice_id,
            speed=speed,
            out_fmt=out_fmt,
            custom_out_dir=self.selected_out_dir,
        )
        self.worker.item_finished.connect(self._on_item_finished)
        self.worker.batch_finished.connect(self._on_batch_finished)
        self.worker.error.connect(self._on_batch_error)
        self.worker.start()

    def _cancel_batch(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            self.stats_lbl.setText("Đang yêu cầu dừng tiến trình...")

    def _on_item_finished(self, current: int, total: int, res: dict):
        idx = res.get("index", current - 1)
        if 0 <= idx < self.table.rowCount():
            if res.get("success"):
                status_item = QTableWidgetItem("✅ Hoàn thành")
                status_item.setForeground(QColor("#22C55E"))
                self.table.setItem(idx, 2, status_item)

                main_f = res.get("main_file", "")
                self.table.setItem(idx, 3, QTableWidgetItem(Path(main_f).name))

                # Nút nghe
                btn_play = QPushButton("▶ Nghe")
                btn_play.setProperty("class", "SecondaryBtn")
                btn_play.setCursor(Qt.PointingHandCursor)
                btn_play.clicked.connect(lambda _, p=main_f: self._play_item_audio(p))
                self.table.setCellWidget(idx, 4, btn_play)
            else:
                status_item = QTableWidgetItem(f"❌ Lỗi: {res.get('error', 'Lỗi')}")
                status_item.setForeground(QColor("#EF4444"))
                self.table.setItem(idx, 2, status_item)

        pct = int((current / float(total)) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.stats_lbl.setText(f"Đã xử lý: {current}/{total} tác vụ ({pct}%)")

    def _on_batch_finished(self, res: dict):
        self.btn_start_batch.setEnabled(True)
        self.btn_cancel_batch.setEnabled(False)
        total = res.get("total", 0)
        completed = res.get("completed", 0)
        failed = res.get("failed", 0)
        self.stats_lbl.setText(
            f"🎉 Xử lý hàng loạt hoàn tất! Tổng: {total} | Thành công: {completed} | Thất bại: {failed}"
        )
        self.stats_lbl.setStyleSheet("color: #22C55E; font-weight: bold;")
        QMessageBox.information(
            self,
            "Hoàn tất xử lý hàng loạt",
            f"Đã hoàn thành toàn bộ tác vụ xử lý hàng loạt!\n\n"
            f"• Tổng số: {total}\n"
            f"• Thành công: {completed}\n"
            f"• Lỗi: {failed}",
        )

    def _on_batch_error(self, err: str):
        self.btn_start_batch.setEnabled(True)
        self.btn_cancel_batch.setEnabled(False)
        self.stats_lbl.setText(f"❌ Quá trình xử lý bị dừng do lỗi: {err}")
        self.stats_lbl.setStyleSheet("color: #EF4444;")
        QMessageBox.critical(self, "Lỗi xử lý hàng loạt", err)

    def _play_item_audio(self, fpath: str):
        if audio_player.is_playing():
            audio_player.stop()
        audio_player.play(fpath)
