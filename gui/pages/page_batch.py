"""gui/pages/page_batch.py — TAB 3: XỬ LÝ HÀNG LOẠT (BATCH TTS PROCESSING)
========================================================================
Tính năng:
- Nạp nhiều tệp Word (.docx) và tệp văn bản (.txt) cùng lúc.
- Hoặc nhập danh sách nhiều dòng văn bản từ ô soạn thảo.
- TÙY CHỈNH GIỌNG ĐỌC & TỐC ĐỘ RIÊNG CHO TỪNG TỆP WORD/TXT:
  Mỗi hàng trong bảng có một ô chọn giọng riêng biệt (trong 25+ giọng hoặc giọng nhân bản).
- Nút "Áp dụng giọng cho tất cả" giúp đổi nhanh toàn bộ danh sách khi cần.
- Bảng quản lý tiến độ từng tác vụ (STT, Tệp/Nội dung, Giọng đọc riêng, Tốc độ, Trạng thái, Tệp xuất, Thao tác).
- Khả năng tạm dừng / hủy tiến trình an toàn.
- Đóng gói toàn bộ file kết quả thành tệp nén .ZIP tải về máy.
- Chuyển toàn bộ danh sách file kết quả sang tab "Bản Tin Phát Thanh".
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QComboBox,
    QSlider,
    QDoubleSpinBox,
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


def extract_text_from_file(file_path: Path) -> tuple[str, str]:
    """Trích xuất nội dung văn bản từ tệp .docx hoặc .txt."""
    ext = file_path.suffix.lower()
    title = file_path.stem.replace("_", " ")

    if ext == ".docx":
        try:
            import docx
            doc = docx.Document(str(file_path))
            paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            content = "\n".join(paras)
            return title, content
        except Exception as e:
            raise ValueError(f"Không thể đọc tệp Word '{file_path.name}': {e}")
    else:
        # Tệp txt hoặc các định dạng text khác
        for enc in ["utf-8", "utf-8-sig", "cp1258", "latin-1"]:
            try:
                content = file_path.read_text(encoding=enc).strip()
                return title, content
            except Exception:
                continue
        raise ValueError(f"Không thể giải mã tệp văn bản '{file_path.name}'.")


class BatchWorker(QThread):
    """Tiểu trình xử lý danh sách hàng loạt trong nền."""

    item_finished = Signal(int, int, dict)
    batch_finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        items: List[Dict[str, Any]],
        default_voice_id: str,
        default_speed: float,
        out_fmt: str,
        custom_out_dir: Optional[Path] = None,
    ):
        super().__init__()
        self.items = items
        self.default_voice_id = default_voice_id
        self.default_speed = default_speed
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
                common_voice=self.default_voice_id,
                common_speed=self.default_speed,
                out_format=self.out_fmt,
                custom_out_dir=self.custom_out_dir,
                on_progress=_on_prog,
                should_cancel=_check_cancel,
            )
            self.batch_finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class PageBatch(QWidget):
    """Trang Xử Lý Hàng Loạt với hỗ trợ Word/Txt & Giọng đọc riêng từng tệp."""

    transfer_to_broadcast = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.selected_out_dir: Optional[Path] = None
        self.worker: Optional[BatchWorker] = None
        self.batch_data: List[Dict[str, Any]] = []  # Dữ liệu của các dòng trong bảng
        self.completed_batch_results: List[Dict[str, Any]] = []

        self._build_ui()
        self.refresh_voices()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # -------------------------------------------------------------
        # 1. KHUNG NẠP TỆP VÀ NHẬP VĂN BẢN
        # -------------------------------------------------------------
        input_card = QFrame()
        input_card.setProperty("class", "CardFrame")
        ic_layout = QVBoxLayout(input_card)
        ic_layout.setContentsMargins(14, 12, 14, 12)
        ic_layout.setSpacing(10)

        ih_layout = QHBoxLayout()
        i_title = QLabel("⚡ XỬ LÝ HÀNG LOẠT (TÙY CHỈNH GIỌNG RIÊNG CHO TỪNG TỆP WORD / TXT)")
        i_title.setProperty("class", "CardTitle")
        ih_layout.addWidget(i_title)
        ih_layout.addStretch()

        btn_import_files = QPushButton("📄 Nạp tệp Word (.docx) & Txt...")
        btn_import_files.setProperty("class", "PrimaryBtn")
        btn_import_files.setCursor(Qt.PointingHandCursor)
        btn_import_files.setToolTip("Chọn một hoặc nhiều tệp Word (.docx) hoặc tệp Text (.txt)")
        btn_import_files.clicked.connect(self._import_files)
        ih_layout.addWidget(btn_import_files)

        btn_add_lines = QPushButton("📝 Thêm từ ô soạn thảo")
        btn_add_lines.setProperty("class", "SecondaryBtn")
        btn_add_lines.setCursor(Qt.PointingHandCursor)
        btn_add_lines.setToolTip("Đưa các dòng văn bản bên dưới vào danh sách xử lý")
        btn_add_lines.clicked.connect(self._add_from_text_edit)
        ih_layout.addWidget(btn_add_lines)

        btn_clear_input = QPushButton("🗑️ Xóa danh sách")
        btn_clear_input.setProperty("class", "SecondaryBtn")
        btn_clear_input.setCursor(Qt.PointingHandCursor)
        btn_clear_input.clicked.connect(self._clear_input)
        ih_layout.addWidget(btn_clear_input)
        ic_layout.addLayout(ih_layout)

        self.text_batch_edit = QTextEdit()
        self.text_batch_edit.setPlaceholderText(
            "Hoặc dán danh sách các câu / đoạn văn bản vào đây rồi bấm '📝 Thêm từ ô soạn thảo'...\n"
            "Ví dụ:\n"
            "Báo cáo tình hình công tác trực ban và quân số đơn vị.\n"
            "Thông báo kế hoạch diễn tập phòng thủ tác chiến quý 4.\n"
            "Chương trình thời sự phát thanh Quân đội nhân dân Việt Nam."
        )
        self.text_batch_edit.setFixedHeight(75)
        self.text_batch_edit.setFont(QFont("Segoe UI", 10))
        ic_layout.addWidget(self.text_batch_edit)

        # Cấu hình giọng đọc mặc định & tốc độ
        cfg_layout = QHBoxLayout()
        lbl_v = QLabel("Giọng mặc định:")
        lbl_v.setStyleSheet("color: #FFD700; font-weight: bold;")
        cfg_layout.addWidget(lbl_v)

        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(220)
        cfg_layout.addWidget(self.voice_combo)

        btn_apply_all_voices = QPushButton("🔄 Đặt giọng này cho tất cả các dòng")
        btn_apply_all_voices.setProperty("class", "SecondaryBtn")
        btn_apply_all_voices.setCursor(Qt.PointingHandCursor)
        btn_apply_all_voices.setToolTip("Áp dụng nhanh giọng đọc này cho toàn bộ các file trong danh sách bên dưới")
        btn_apply_all_voices.clicked.connect(self._apply_voice_to_all_rows)
        cfg_layout.addWidget(btn_apply_all_voices)

        lbl_s = QLabel("Tốc độ:")
        lbl_s.setStyleSheet("color: #FFFFFF; font-weight: bold; margin-left: 10px;")
        cfg_layout.addWidget(lbl_s)

        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(75, 150)
        self.speed_slider.setValue(100)
        self.speed_slider.setMaximumWidth(100)
        self.speed_slider.valueChanged.connect(lambda v: self.speed_val_lbl.setText(f"{v/100:.2f}x"))
        cfg_layout.addWidget(self.speed_slider)

        self.speed_val_lbl = QLabel("1.00x")
        self.speed_val_lbl.setStyleSheet("color: #22D3EE; font-weight: bold; min-width: 36px;")
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

        # -------------------------------------------------------------
        # 2. HÀNG ĐIỀU KHIỂN & TIẾN ĐỘ
        # -------------------------------------------------------------
        ctrl_layout = QHBoxLayout()
        self.btn_start_batch = QPushButton("▶  BẮT ĐẦU XỬ LÝ HÀNG LOẠT")
        self.btn_start_batch.setProperty("class", "PrimaryBtn")
        self.btn_start_batch.setFixedHeight(40)
        self.btn_start_batch.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_start_batch.setCursor(Qt.PointingHandCursor)
        self.btn_start_batch.clicked.connect(self._start_batch)
        ctrl_layout.addWidget(self.btn_start_batch)

        self.btn_cancel_batch = QPushButton("⏹ Dừng lại")
        self.btn_cancel_batch.setProperty("class", "DangerBtn")
        self.btn_cancel_batch.setFixedHeight(40)
        self.btn_cancel_batch.setEnabled(False)
        self.btn_cancel_batch.setCursor(Qt.PointingHandCursor)
        self.btn_cancel_batch.clicked.connect(self._cancel_batch)
        ctrl_layout.addWidget(self.btn_cancel_batch)

        ctrl_layout.addStretch()

        self.btn_transfer_broadcast = QPushButton("📻 Chuyển vào Bản Tin")
        self.btn_transfer_broadcast.setProperty("class", "PrimaryBtn")
        self.btn_transfer_broadcast.setFixedHeight(40)
        self.btn_transfer_broadcast.setEnabled(False)
        self.btn_transfer_broadcast.setCursor(Qt.PointingHandCursor)
        self.btn_transfer_broadcast.setToolTip("Chuyển toàn bộ các tệp âm thanh vừa tạo vào trang Tạo Bản Tin Phát Thanh")
        self.btn_transfer_broadcast.clicked.connect(self._transfer_to_broadcast)
        ctrl_layout.addWidget(self.btn_transfer_broadcast)

        self.btn_download_zip = QPushButton("💾 Tải tệp nén .ZIP")
        self.btn_download_zip.setProperty("class", "SecondaryBtn")
        self.btn_download_zip.setFixedHeight(40)
        self.btn_download_zip.setEnabled(False)
        self.btn_download_zip.setCursor(Qt.PointingHandCursor)
        self.btn_download_zip.setToolTip("Đóng gói toàn bộ các tệp âm thanh vừa tạo thành 1 tệp ZIP để tải về máy")
        self.btn_download_zip.clicked.connect(self._download_as_zip)
        ctrl_layout.addWidget(self.btn_download_zip)

        btn_open_folder = QPushButton("📂 Mở thư mục đầu ra")
        btn_open_folder.setProperty("class", "SecondaryBtn")
        btn_open_folder.setFixedHeight(40)
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

        self.stats_lbl = QLabel("Sẵn sàng. Chưa có tác vụ nào trong danh sách.")
        self.stats_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
        layout.addWidget(self.stats_lbl)

        # -------------------------------------------------------------
        # 3. BẢNG TIẾN ĐỘ TÁC VỤ (HỖ TRỢ GIỌNG ĐỌC RIÊNG TỪNG HÀNG)
        # -------------------------------------------------------------
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "STT", "Tệp / Nội Dung Văn Bản", "Giọng Đọc (Tùy chọn riêng)", "Tốc Độ", "Trạng Thái", "Tệp Âm Thanh", "Thao Tác"
        ])
        self.table.setColumnWidth(0, 48)   # STT
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch) # Nội dung
        self.table.setColumnWidth(2, 230)  # Giọng đọc riêng
        self.table.setColumnWidth(3, 85)   # Tốc độ
        self.table.setColumnWidth(4, 120)  # Trạng thái
        self.table.setColumnWidth(5, 140)  # Tệp âm thanh
        self.table.setColumnWidth(6, 105)  # Thao tác
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
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
        tts_service.open_output_folder(self.selected_out_dir)

    def _clear_input(self):
        self.text_batch_edit.clear()
        self.table.setRowCount(0)
        self.batch_data.clear()
        self.completed_batch_results.clear()
        self.progress_bar.setValue(0)
        self.btn_transfer_broadcast.setEnabled(False)
        self.btn_download_zip.setEnabled(False)
        self.stats_lbl.setText("Đã xóa danh sách.")

    # -----------------------------------------------------------------
    # NẠP TỆP WORD (.DOCX) VÀ TXT
    # -----------------------------------------------------------------
    def _import_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn các tệp Word (.docx) hoặc Văn bản (.txt)",
            "",
            "Tài liệu Word & Văn bản (*.docx *.txt *.doc);;Word Document (*.docx);;Văn bản Text (*.txt);;Tất cả (*.*)",
        )
        if not files:
            return

        def_voice = self.voice_combo.currentData() or "Hải Đăng"
        def_speed = self.speed_slider.value() / 100.0
        success_count = 0

        for f in files:
            p = Path(f)
            try:
                title, content = extract_text_from_file(p)
                if not content:
                    continue

                words = len(content.split())
                self._add_row_item(
                    title=f"{p.name} ({words} từ)",
                    text=content,
                    tag=p.stem,
                    voice_id=def_voice,
                    speed=def_speed,
                )
                success_count += 1
            except Exception as e:
                QMessageBox.warning(self, "Lỗi đọc tệp", str(e))

        if success_count > 0:
            self.stats_lbl.setText(f"Đã nạp {success_count} tệp vào danh sách. Bạn có thể tùy chỉnh giọng đọc từng tệp bên dưới.")
            self.stats_lbl.setStyleSheet("color: #22D3EE; font-weight: bold;")

    def _add_from_text_edit(self):
        raw_text = self.text_batch_edit.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "Chưa có nội dung", "Vui lòng nhập văn bản vào ô soạn thảo trước.")
            return

        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not lines:
            return

        def_voice = self.voice_combo.currentData() or "Hải Đăng"
        def_speed = self.speed_slider.value() / 100.0

        for idx, line in enumerate(lines):
            words = len(line.split())
            title = line[:50] + ("..." if len(line) > 50 else "")
            self._add_row_item(
                title=f"{title} ({words} từ)",
                text=line,
                tag=f"doan_{len(self.batch_data)+1:03d}",
                voice_id=def_voice,
                speed=def_speed,
            )

        self.text_batch_edit.clear()
        self.stats_lbl.setText(f"Đã thêm {len(lines)} đoạn văn bản vào danh sách.")
        self.stats_lbl.setStyleSheet("color: #22D3EE; font-weight: bold;")

    def _add_row_item(self, title: str, text: str, tag: str, voice_id: str, speed: float):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 48)

        self.batch_data.append({
            "title": title,
            "text": text,
            "tag": tag,
            "default_voice": voice_id,
            "default_speed": speed,
        })

        # 0: STT
        stt_item = QTableWidgetItem(f"{row+1}")
        stt_item.setTextAlignment(Qt.AlignCenter)
        stt_item.setForeground(QColor("#FFD700"))
        stt_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.table.setItem(row, 0, stt_item)

        # 1: Tệp / Nội dung tóm tắt
        title_item = QTableWidgetItem(title)
        title_item.setToolTip(text[:500] + ("..." if len(text) > 500 else ""))
        self.table.setItem(row, 1, title_item)

        # 2: Giọng đọc riêng
        cb_voice = QComboBox()
        cb_voice.setFixedHeight(34)
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
        spin_spd.setFixedHeight(34)
        spin_spd.setRange(0.75, 1.50)
        spin_spd.setSingleStep(0.05)
        spin_spd.setValue(speed)
        spin_spd.setSuffix("x")
        spin_spd.setStyleSheet("background-color: #1E3A21; color: #FFFFFF; border: 1px solid #3F7545; border-radius: 4px;")
        self.table.setCellWidget(row, 3, spin_spd)

        # 4: Trạng thái
        status_item = QTableWidgetItem("⏳ Chờ...")
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setForeground(QColor("#94A3B8"))
        self.table.setItem(row, 4, status_item)

        # 5: Tệp âm thanh
        file_item = QTableWidgetItem("-")
        self.table.setItem(row, 5, file_item)

        # 6: Thao tác (Xóa dòng)
        act_widget = QWidget()
        act_layout = QHBoxLayout(act_widget)
        act_layout.setContentsMargins(4, 2, 4, 2)
        act_layout.setSpacing(4)

        btn_del = QPushButton("🗑️")
        btn_del.setProperty("class", "DangerBtn")
        btn_del.setFixedSize(36, 30)
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.clicked.connect(lambda _, r=row: self._delete_row(r))
        act_layout.addWidget(btn_del)

        self.table.setCellWidget(row, 6, act_widget)

    def _delete_row(self, row_idx: int):
        if 0 <= row_idx < self.table.rowCount():
            self.table.removeRow(row_idx)
            if row_idx < len(self.batch_data):
                self.batch_data.pop(row_idx)
            # Đánh số lại STT
            for r in range(self.table.rowCount()):
                stt_item = QTableWidgetItem(f"{r+1}")
                stt_item.setTextAlignment(Qt.AlignCenter)
                stt_item.setForeground(QColor("#FFD700"))
                self.table.setItem(r, 0, stt_item)

    def _apply_voice_to_all_rows(self):
        target_voice = self.voice_combo.currentData()
        if not target_voice:
            return

        row_count = self.table.rowCount()
        if row_count == 0:
            QMessageBox.information(self, "Thông báo", "Danh sách đang trống, chưa có tệp nào để áp dụng.")
            return

        for r in range(row_count):
            cb_w = self.table.cellWidget(r, 2)
            if isinstance(cb_w, QComboBox):
                for idx in range(cb_w.count()):
                    if cb_w.itemData(idx) == target_voice:
                        cb_w.setCurrentIndex(idx)
                        break

        self.stats_lbl.setText(f"Đã đặt giọng '{self.voice_combo.currentText()}' cho toàn bộ {row_count} dòng.")
        self.stats_lbl.setStyleSheet("color: #22C55E;")

    # -----------------------------------------------------------------
    # BẮT ĐẦU XỬ LÝ HÀNG LOẠT
    # -----------------------------------------------------------------
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

        row_count = self.table.rowCount()
        if row_count == 0:
            QMessageBox.warning(self, "Danh sách rỗng", "Vui lòng nạp ít nhất một tệp Word/Txt hoặc câu văn bản.")
            return

        # Thu thập các dòng với giọng đọc và tốc độ riêng của từng dòng
        batch_items = []
        for r in range(row_count):
            row_data = self.batch_data[r] if r < len(self.batch_data) else {}
            text = row_data.get("text", "")

            # Lấy giọng đọc được chọn riêng cho dòng này
            cb_w = self.table.cellWidget(r, 2)
            v_id = cb_w.currentData() if isinstance(cb_w, QComboBox) else self.voice_combo.currentData()

            # Lấy tốc độ được chọn riêng cho dòng này
            spd_w = self.table.cellWidget(r, 3)
            spd = spd_w.value() if isinstance(spd_w, QDoubleSpinBox) else 1.0

            tag = row_data.get("tag", f"batch_{r+1:03d}")

            batch_items.append({
                "text": text,
                "voice": v_id,
                "speed": spd,
                "tag": tag,
            })

            # Đặt lại trạng thái trong bảng
            status_item = QTableWidgetItem("⏳ Đang chờ...")
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(QColor("#94A3B8"))
            self.table.setItem(r, 4, status_item)

        out_fmt = "mp3" if self.radio_mp3.isChecked() else "wav"

        self.btn_start_batch.setEnabled(False)
        self.btn_cancel_batch.setEnabled(True)
        self.completed_batch_results.clear()
        self.btn_transfer_broadcast.setEnabled(False)
        self.btn_download_zip.setEnabled(False)
        self.progress_bar.setValue(0)
        self.stats_lbl.setText(f"Đang xử lý 0/{row_count} tác vụ...")
        self.stats_lbl.setStyleSheet("color: #22D3EE;")

        self.worker = BatchWorker(
            items=batch_items,
            default_voice_id=self.voice_combo.currentData() or "Hải Đăng",
            default_speed=self.speed_slider.value() / 100.0,
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
                status_item = QTableWidgetItem("✅ Xong")
                status_item.setTextAlignment(Qt.AlignCenter)
                status_item.setForeground(QColor("#22C55E"))
                self.table.setItem(idx, 4, status_item)

                main_f = res.get("main_file", "")
                self.table.setItem(idx, 5, QTableWidgetItem(Path(main_f).name))

                # Lưu vào kết quả thành công
                self.completed_batch_results.append(res)
                self.btn_transfer_broadcast.setEnabled(True)
                self.btn_download_zip.setEnabled(True)

                # Nút nghe và xóa
                act_w = QWidget()
                act_l = QHBoxLayout(act_w)
                act_l.setContentsMargins(4, 2, 4, 2)
                act_l.setSpacing(4)

                btn_play = QPushButton("▶")
                btn_play.setProperty("class", "SecondaryBtn")
                btn_play.setFixedSize(36, 30)
                btn_play.setToolTip("Nghe tệp âm thanh này")
                btn_play.setCursor(Qt.PointingHandCursor)
                btn_play.clicked.connect(lambda _, p=main_f: self._play_item_audio(p))
                act_l.addWidget(btn_play)

                btn_del = QPushButton("🗑️")
                btn_del.setProperty("class", "DangerBtn")
                btn_del.setFixedSize(32, 30)
                btn_del.setCursor(Qt.PointingHandCursor)
                btn_del.clicked.connect(lambda _, r=idx: self._delete_row(r))
                act_l.addWidget(btn_del)

                self.table.setCellWidget(idx, 6, act_w)
            else:
                status_item = QTableWidgetItem("❌ Lỗi")
                status_item.setTextAlignment(Qt.AlignCenter)
                status_item.setForeground(QColor("#EF4444"))
                status_item.setToolTip(res.get("error", "Lỗi"))
                self.table.setItem(idx, 4, status_item)

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
            f"🎉 Hoàn tất xử lý hàng loạt! Tổng: {total} | Thành công: {completed} | Thất bại: {failed}"
        )
        self.stats_lbl.setStyleSheet("color: #22C55E; font-weight: bold;")
        QMessageBox.information(
            self,
            "Hoàn tất xử lý hàng loạt",
            f"Đã hoàn thành toàn bộ tác vụ xử lý hàng loạt!\n\n"
            f"• Tổng số tệp/đoạn: {total}\n"
            f"• Thành công: {completed}\n"
            f"• Lỗi: {failed}\n\n"
            "Bạn có thể bấm '💾 Tải tệp nén .ZIP' để tải về hoặc '📻 Chuyển vào Bản Tin' để ghép thành bản phát thanh hoàn chỉnh.",
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

    def _transfer_to_broadcast(self):
        if not self.completed_batch_results:
            QMessageBox.warning(self, "Chưa có kết quả", "Chưa có tệp âm thanh hoàn thành nào để chuyển.")
            return
        self.transfer_to_broadcast.emit(self.completed_batch_results)

    def _download_as_zip(self):
        if not self.completed_batch_results:
            QMessageBox.warning(self, "Chưa có kết quả", "Chưa có tệp âm thanh hoàn thành nào để tải về.")
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu tệp nén ZIP hàng loạt",
            "T-TTS_HangLoat.zip",
            "Tệp nén ZIP (*.zip);;Tất cả (*.*)",
        )
        if not save_path:
            return
        try:
            with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for idx, r in enumerate(self.completed_batch_results):
                    mf = r.get("main_file")
                    if mf and Path(mf).is_file():
                        p = Path(mf)
                        zf.write(str(p), arcname=p.name)
            QMessageBox.information(
                self,
                "Tải về thành công",
                f"🎉 Đã đóng gói và lưu thành công {len(self.completed_batch_results)} tệp âm thanh vào:\n{save_path}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Lỗi đóng gói ZIP", f"Không thể tạo file ZIP: {e}")
