"""gui/pages/page_schedule.py — GIAO DIỆN SCHEDULE STUDIO (QUẢN LÝ LỊCH PHÁT THANH & NHẮC VIỆC)
=============================================================================
Trang quản lý danh sách lịch trình, tạo lịch mới, chỉnh sửa, bật/tắt, chạy ngay
và xem lịch sử thực thi. Hỗ trợ đầy đủ:
- Quản lý danh sách phát thanh đa nguồn (Audio Playlist Studio).
- Bộ chọn nguồn âm thanh phong phú: Tệp máy tính (WAV/MP3), Lịch sử TTS, Dự án Audio Studio,
  Dự án Broadcast Studio, và Chuyển đổi Văn bản sang TTS (DOCX/TXT).
- Sắp xếp thứ tự phát (Lên/Xuống), khoảng nghỉ (pause_after), kiểm tra tệp mất (Missing) và Relink.
- Điều khiển phát sóng thời gian thực (Dừng, Tạm dừng, Tiếp tục).
- Phong cách Dark Green & Gold quân đội chuẩn T-TTS.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTime, QDate, QTimer
from PySide6.QtGui import QFont, QCursor, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QDialog,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QTimeEdit,
    QDateEdit,
    QCheckBox,
    QSpinBox,
    QFileDialog,
    QFrame,
    QScrollArea,
    QProgressBar,
)

from backend.service import tts_service
from backend.scheduler_engine import scheduler_engine, compute_next_run
from backend.project_manager import project_manager
from backend.audio_utils import get_audio_duration_safe
from backend.audio_player import audio_player
from backend.storage import init_storage
from backend.document_reader import extract_document_text
from gui.notification_hub import notification_hub
from gui.task_worker import FunctionTaskWorker


def format_sec_to_time(sec: float) -> str:
    """Đổi giây sang định dạng MM:SS."""
    s = max(0, int(sec))
    m = s // 60
    rem_s = s % 60
    return f"{m:02d}:{rem_s:02d}"


def extract_text_from_file(file_path: Path) -> tuple[str, str]:
    """Trích xuất nội dung văn bản từ tệp Word (.docx), PDF (.pdf) hoặc Văn bản (.txt)."""
    res = extract_document_text(file_path)
    if not res.get("success"):
        raise ValueError(res.get("error", f"Không thể đọc tệp '{file_path.name}'"))
    title = res.get("title") or file_path.stem.replace("_", " ")
    content = (res.get("raw_text") or res.get("text", "")).strip()
    return title, content


# =============================================================================
# HỘP THOẠI 1: CHUYỂN ĐỔI VĂN BẢN THÀNH TTS TRỰC TIẾP (DOCUMENT-TO-TTS)
# =============================================================================
class DocumentToTTSDialog(QDialog):
    """Hộp thoại trích xuất DOCX/TXT và tổng hợp thành bản tin audio vào Playlist."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Chuyển Đổi Văn Bản Sang Giọng Nói (Document-to-TTS)")
        self.setMinimumSize(660, 560)
        self.setStyleSheet("""
            QDialog { background-color: #142817; color: #FFFFFF; }
            QLabel { color: #CBD5E1; font-size: 13px; font-weight: 500; }
            QLineEdit, QTextEdit, QComboBox {
                background-color: #0B190D;
                color: #FFFFFF;
                border: 1px solid #27472A;
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #FFD700; }
            QPushButton {
                background-color: #2D5A27;
                color: #FFFFFF;
                border: 1px solid #4ADE80;
                padding: 7px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #386E31; }
        """)

        self.generated_audio_path: Optional[Path] = None
        self.result_item: Optional[Dict[str, Any]] = None
        self._worker: Optional[FunctionTaskWorker] = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # 1. Chọn tệp tài liệu
        f_row = QHBoxLayout()
        self.txt_doc_path = QLineEdit()
        self.txt_doc_path.setPlaceholderText("Chọn tệp văn bản Word (.docx) hoặc Text (.txt)...")
        self.txt_doc_path.setReadOnly(True)
        f_row.addWidget(self.txt_doc_path, 1)

        btn_browse = QPushButton("📁 Chọn Tệp")
        btn_browse.clicked.connect(self._browse_file)
        f_row.addWidget(btn_browse)
        layout.addLayout(f_row)

        # 2. Tiêu đề bản tin
        t_row = QHBoxLayout()
        t_row.addWidget(QLabel("Tiêu đề bản tin:"))
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("Ví dụ: Thông báo quân số buổi sáng...")
        t_row.addWidget(self.txt_title, 1)
        layout.addLayout(t_row)

        # 3. Trích xuất & chỉnh sửa văn bản
        layout.addWidget(QLabel("Nội dung văn bản cần đọc (có thể chỉnh sửa trực tiếp):"))
        self.txt_content = QTextEdit()
        self.txt_content.setPlaceholderText("Nội dung văn bản sau khi trích xuất sẽ hiển thị ở đây...")
        layout.addWidget(self.txt_content, 1)

        # 4. Tùy chọn giọng đọc
        cfg_row = QHBoxLayout()
        cfg_row.addWidget(QLabel("Giọng đọc:"))
        self.cbo_voice = QComboBox()
        voices = tts_service.list_voices()
        for v in voices:
            self.cbo_voice.addItem(f"{v.get('name')} ({v.get('gender', '')})", v.get("id"))
        cfg_row.addWidget(self.cbo_voice, 1)
        layout.addLayout(cfg_row)

        # Thanh tiến trình
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #0B190D;
                border: 1px solid #27472A;
                border-radius: 4px;
                text-align: center;
                color: #FFFFFF;
                height: 16px;
            }
            QProgressBar::chunk { background-color: #22C55E; border-radius: 3px; }
        """)
        layout.addWidget(self.progress_bar)

        # 5. Nút tổng hợp & Nghe thử
        act_row = QHBoxLayout()
        self.btn_synth = QPushButton("⚡ Chuyển Đổi Thành Giọng Nói (TTS)")
        self.btn_synth.setStyleSheet("background-color: #D4AF37; color: #000000; border: none; font-weight: 800;")
        self.btn_synth.clicked.connect(self._synthesize_audio)
        act_row.addWidget(self.btn_synth)

        self.btn_preview = QPushButton("▶ Nghe Thử")
        self.btn_preview.setEnabled(False)
        self.btn_preview.clicked.connect(self._toggle_preview)
        act_row.addWidget(self.btn_preview)

        self.btn_stop_preview = QPushButton("⏹ Dừng")
        self.btn_stop_preview.setEnabled(False)
        self.btn_stop_preview.clicked.connect(self._stop_preview)
        act_row.addWidget(self.btn_stop_preview)

        layout.addLayout(act_row)

        # 6. Hàng nút Đóng / Thêm vào Playlist
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Hủy Bỏ")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        self.btn_add_to_playlist = QPushButton("➕ Thêm Vào Playlist")
        self.btn_add_to_playlist.setEnabled(False)
        self.btn_add_to_playlist.setStyleSheet("background-color: #22C55E; color: #000000; border: none; font-weight: 800;")
        self.btn_add_to_playlist.clicked.connect(self._on_add_to_playlist)
        btn_box.addWidget(self.btn_add_to_playlist)

        layout.addLayout(btn_box)

    def _browse_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn tệp tài liệu (Word, PDF, Text)",
            "",
            "Tài liệu (*.docx *.pdf *.txt);;Word Document (*.docx);;Tệp PDF (*.pdf);;Text File (*.txt);;Tất cả (*.*)",
        )
        if not f:
            return
        p = Path(f)
        self.txt_doc_path.setText(str(p))
        try:
            title, text = extract_text_from_file(p)
            self.txt_title.setText(title)
            self.txt_content.setText(text)
        except Exception as e:
            QMessageBox.critical(self, "Lỗi đọc tệp", str(e))

    def _synthesize_audio(self):
        text = self.txt_content.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Thiếu nội dung", "Vui lòng nhập hoặc nạp nội dung văn bản.")
            return

        voice_id = self.cbo_voice.currentData()
        title = self.txt_title.text().strip() or "Ban_Tin_TTS"
        prefix = "".join(c for c in title if c.isalnum() or c in ("_", "-")) or "Doc_TTS"

        self.btn_synth.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        def _do_work(progress_cb=None, cancel_check=None):
            storage = init_storage()
            sched_dir = storage["output_dir"] / "schedule_audio"
            sched_dir.mkdir(parents=True, exist_ok=True)
            return tts_service.synthesize_text(
                text=text,
                voice_id=voice_id,
                speed=1.0,
                out_format="wav",
                filename_prefix=prefix,
                custom_out_dir=sched_dir,
            )

        self._worker = FunctionTaskWorker(_do_work)

        def _on_done(res):
            self.btn_synth.setEnabled(True)
            self.progress_bar.setVisible(False)
            if res.get("success") and res.get("file_path"):
                self.generated_audio_path = Path(res["file_path"])
                self.btn_preview.setEnabled(True)
                self.btn_stop_preview.setEnabled(True)
                self.btn_add_to_playlist.setEnabled(True)
                dur = get_audio_duration_safe(self.generated_audio_path)
                QMessageBox.information(
                    self,
                    "Tạo Thành Công",
                    f"Đã tạo âm thanh thành công!\nThời lượng: {dur:.1f}s\nTệp: {self.generated_audio_path.name}",
                )
            else:
                QMessageBox.critical(self, "Lỗi tạo TTS", res.get("error", "Không xác định"))

        def _on_err(err):
            self.btn_synth.setEnabled(True)
            self.progress_bar.setVisible(False)
            QMessageBox.critical(self, "Lỗi tạo TTS", str(err))

        self._worker.finished_task.connect(_on_done)
        self._worker.error_task.connect(_on_err)
        self._worker.start()

    def _toggle_preview(self):
        if self.generated_audio_path and self.generated_audio_path.is_file():
            audio_player.play(self.generated_audio_path)

    def _stop_preview(self):
        audio_player.stop()

    def _on_add_to_playlist(self):
        if not self.generated_audio_path or not self.generated_audio_path.is_file():
            return
        audio_player.stop()
        dur = get_audio_duration_safe(self.generated_audio_path)
        self.result_item = {
            "id": f"item_{int(time.time()*1000)}",
            "title": self.txt_title.text().strip() or self.generated_audio_path.stem,
            "source_type": "document_tts",
            "file_path": str(self.generated_audio_path),
            "duration_sec": dur,
            "pause_after": 2.0,
            "status": "pending",
        }
        self.accept()


# =============================================================================
# HỘP THOẠI 2: CHỌN ÂM THANH TỪ LỊCH SỬ TTS (AUDIO HISTORY PICKER)
# =============================================================================
class HistoryAudioPickerDialog(QDialog):
    """Hộp thoại chọn file âm thanh từ Lịch sử TTS đã tạo."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Chọn Âm Thanh Từ Lịch Sử TTS")
        self.setMinimumSize(700, 420)
        self.setStyleSheet("""
            QDialog { background-color: #142817; color: #FFFFFF; }
            QTableWidget {
                background-color: #0B190D;
                color: #FFFFFF;
                gridline-color: #27472A;
                border: 1px solid #3B533E;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #1A381F;
                color: #FFD700;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #27472A;
            }
            QPushButton {
                background-color: #2D5A27;
                color: #FFFFFF;
                border: 1px solid #4ADE80;
                padding: 6px 14px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #386E31; }
        """)

        self.selected_item: Optional[Dict[str, Any]] = None
        self._history_items: List[Dict[str, Any]] = []

        self._build_ui()
        self._load_history()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        lbl = QLabel("📜 Danh sách các bản thu âm thanh đã tạo từ VieNeu-TTS:")
        lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #FFD700;")
        layout.addWidget(lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Thời Gian", "Nội Dung Văn Bản", "Giọng Đọc", "Thời Lượng"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_choose)
        layout.addWidget(self.table)

        btn_box = QHBoxLayout()
        btn_preview = QPushButton("▶ Nghe Thử")
        btn_preview.clicked.connect(self._preview_selected)
        btn_box.addWidget(btn_preview)

        btn_stop = QPushButton("⏹ Dừng")
        btn_stop.clicked.connect(lambda: audio_player.stop())
        btn_box.addWidget(btn_stop)

        btn_box.addStretch()

        btn_cancel = QPushButton("Hủy")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_choose = QPushButton("✔ Chọn Bản Thu Này")
        btn_choose.setStyleSheet("background-color: #D4AF37; color: #000000; border: none; font-weight: 800;")
        btn_choose.clicked.connect(self._on_choose)
        btn_box.addWidget(btn_choose)

        layout.addLayout(btn_box)

    def _load_history(self):
        all_hist = tts_service.get_history()
        # Lọc các item có file_path thực tế
        self._history_items = [h for h in all_hist if h.get("file_path") and Path(h["file_path"]).is_file()]
        self.table.setRowCount(len(self._history_items))

        for row, h in enumerate(self._history_items):
            ts = h.get("timestamp", "")
            text = (h.get("text", "") or "").replace("\n", " ")
            if len(text) > 70:
                text = text[:70] + "..."
            voice = h.get("voice_id", "")
            dur_sec = float(h.get("duration") or h.get("duration_sec") or 0.0)
            if dur_sec <= 0:
                dur_sec = get_audio_duration_safe(Path(h["file_path"]))

            self.table.setItem(row, 0, QTableWidgetItem(ts))
            self.table.setItem(row, 1, QTableWidgetItem(text))
            self.table.setItem(row, 2, QTableWidgetItem(voice))
            self.table.setItem(row, 3, QTableWidgetItem(format_sec_to_time(dur_sec)))

    def _preview_selected(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._history_items):
            fp = self._history_items[row].get("file_path")
            if fp and Path(fp).is_file():
                audio_player.play(fp)

    def _on_choose(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._history_items):
            audio_player.stop()
            h = self._history_items[row]
            fp = Path(h["file_path"])
            dur = get_audio_duration_safe(fp)
            self.selected_item = {
                "id": f"item_{int(time.time()*1000)}",
                "title": fp.stem,
                "source_type": "history",
                "file_path": str(fp),
                "duration_sec": dur,
                "pause_after": 2.0,
                "status": "pending",
            }
            self.accept()


# =============================================================================
# HỘP THOẠI 3: CHỌN ÂM THANH TỪ AUDIO / BROADCAST STUDIO
# =============================================================================
class ProjectAudioPickerDialog(QDialog):
    """Hộp thoại chọn file âm thanh từ Dự án Audio Studio hoặc Broadcast Studio."""

    def __init__(self, project_type: str = "audio", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project_type = project_type
        type_title = "Audio Studio" if project_type == "audio" else "Broadcast Studio"
        self.setWindowTitle(f"Chọn Bản Thu Từ Dự Án {type_title}")
        self.setMinimumSize(680, 400)
        self.setStyleSheet("""
            QDialog { background-color: #142817; color: #FFFFFF; }
            QTableWidget {
                background-color: #0B190D;
                color: #FFFFFF;
                gridline-color: #27472A;
                border: 1px solid #3B533E;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #1A381F;
                color: #FFD700;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #27472A;
            }
            QPushButton {
                background-color: #2D5A27;
                color: #FFFFFF;
                border: 1px solid #4ADE80;
                padding: 6px 14px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #386E31; }
        """)

        self.selected_item: Optional[Dict[str, Any]] = None
        self._projects: List[Dict[str, Any]] = []

        self._build_ui()
        self._load_projects()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        lbl = QLabel(f"📁 Danh sách dự án {self.project_type.upper()} có sẵn tệp âm thanh:")
        lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #FFD700;")
        layout.addWidget(lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Tên Dự Án", "Thời Lượng", "Đường Dẫn Tệp"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_choose)
        layout.addWidget(self.table)

        btn_box = QHBoxLayout()
        btn_preview = QPushButton("▶ Nghe Thử")
        btn_preview.clicked.connect(self._preview_selected)
        btn_box.addWidget(btn_preview)

        btn_stop = QPushButton("⏹ Dừng")
        btn_stop.clicked.connect(lambda: audio_player.stop())
        btn_box.addWidget(btn_stop)

        btn_box.addStretch()

        btn_cancel = QPushButton("Hủy")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_choose = QPushButton("✔ Chọn Dự Án Này")
        btn_choose.setStyleSheet("background-color: #D4AF37; color: #000000; border: none; font-weight: 800;")
        btn_choose.clicked.connect(self._on_choose)
        btn_box.addWidget(btn_choose)

        layout.addLayout(btn_box)

    def _load_projects(self):
        projs = project_manager.list_projects(self.project_type)
        valid_items = []
        for p in projs:
            pid = p.get("id")
            full_data = project_manager.load_project(self.project_type, pid) or p
            # Tìm đường dẫn audio
            af = full_data.get("audio_file") or full_data.get("file_path") or full_data.get("exported_audio")
            if af and Path(af).is_file():
                valid_items.append({
                    "id": pid,
                    "name": full_data.get("name", pid),
                    "file_path": str(Path(af)),
                    "duration_sec": get_audio_duration_safe(Path(af)),
                })

        self._projects = valid_items
        self.table.setRowCount(len(self._projects))

        for row, prj in enumerate(self._projects):
            self.table.setItem(row, 0, QTableWidgetItem(prj["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(format_sec_to_time(prj["duration_sec"])))
            self.table.setItem(row, 2, QTableWidgetItem(prj["file_path"]))

    def _preview_selected(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._projects):
            fp = self._projects[row]["file_path"]
            if Path(fp).is_file():
                audio_player.play(fp)

    def _on_choose(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._projects):
            audio_player.stop()
            prj = self._projects[row]
            self.selected_item = {
                "id": f"item_{int(time.time()*1000)}",
                "title": prj["name"],
                "source_type": f"{self.project_type}_project",
                "file_path": prj["file_path"],
                "duration_sec": prj["duration_sec"],
                "pause_after": 2.0,
                "status": "pending",
            }
            self.accept()


# =============================================================================
# HỘP THOẠI 4: LỊCH SỬ THỰC THI (SCHEDULE HISTORY)
# =============================================================================
class ScheduleHistoryDialog(QDialog):
    """Hộp thoại xem lịch sử thực thi của một lịch cụ thể."""

    def __init__(self, schedule_dict: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.schedule_dict = schedule_dict
        self.setWindowTitle(f"Lịch Sử Thực Thi — {schedule_dict.get('name', 'Lịch')}")
        self.setMinimumSize(680, 440)
        self.setStyleSheet("""
            QDialog { background-color: #162E1A; color: #FFFFFF; }
            QLabel { color: #FFFFFF; font-size: 13px; }
            QTableWidget {
                background-color: #0F1E11;
                color: #FFFFFF;
                gridline-color: #27472A;
                border: 1px solid #3B533E;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #1A381F;
                color: #FFD700;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #27472A;
            }
            QPushButton {
                background-color: #2D5A27;
                color: #FFFFFF;
                border: 1px solid #4ADE80;
                padding: 6px 14px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #386E31; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        lbl_title = QLabel(f"📜 Lịch sử thực thi: <b style='color: #FFD700;'>{schedule_dict.get('name')}</b>")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(lbl_title)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Thời Gian", "Trạng Thái", "Chi Tiết Thực Thi"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        self._populate_history()

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_close = QPushButton("Đóng")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

    def _populate_history(self):
        history = self.schedule_dict.get("execution_history", [])
        self.table.setRowCount(len(history))
        for row, entry in enumerate(history):
            ts = entry.get("timestamp", "")
            status = entry.get("status", "")
            msg = entry.get("message", "")
            fp = entry.get("file_path", "")
            detail = f"{msg} | {fp}" if fp else msg

            if status == "success":
                st_text = "🟢 Thành công"
            elif status == "missed":
                st_text = "🟡 Bị lỡ"
            else:
                st_text = "🔴 Thất bại"

            it_ts = QTableWidgetItem(ts)
            it_st = QTableWidgetItem(st_text)
            it_dt = QTableWidgetItem(detail)

            it_ts.setTextAlignment(Qt.AlignCenter)
            it_st.setTextAlignment(Qt.AlignCenter)

            self.table.setItem(row, 0, it_ts)
            self.table.setItem(row, 1, it_st)
            self.table.setItem(row, 2, it_dt)


# =============================================================================
# HỘP THOẠI 5: TRÌNH BIÊN TẬP LỊCH TRÌNH & PLAYLIST (SCHEDULE EDITOR DIALOG)
# =============================================================================
class ScheduleEditorDialog(QDialog):
    """Hộp thoại tạo mới hoặc chỉnh sửa lịch phát thanh & playlist hoàn chỉnh."""

    def __init__(self, schedule_dict: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.schedule_dict = dict(schedule_dict) if schedule_dict else {}
        self.is_edit = bool(schedule_dict)
        self.playlist_items: List[Dict[str, Any]] = []

        title = "Chỉnh Sửa Lịch Phát Thanh & Playlist" if self.is_edit else "Tạo Lịch Phát Thanh & Playlist Mới"
        self.setWindowTitle(title)
        self.setMinimumSize(780, 750)
        self.setStyleSheet("""
            QDialog { background-color: #162E1A; color: #FFFFFF; }
            QLabel { color: #CBD5E1; font-size: 13px; font-weight: 500; }
            QLineEdit, QTextEdit, QComboBox, QTimeEdit, QDateEdit, QSpinBox {
                background-color: #0F1E11;
                color: #FFFFFF;
                border: 1px solid #3B533E;
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #FFD700; }
            QCheckBox { color: #FFFFFF; font-size: 13px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QTableWidget {
                background-color: #0D1C0F;
                color: #FFFFFF;
                gridline-color: #27472A;
                border: 1px solid #3B533E;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #1A381F;
                color: #FFD700;
                font-weight: bold;
                padding: 5px;
                border: 1px solid #27472A;
            }
            QPushButton#SaveBtn {
                background-color: #D4AF37;
                color: #000000;
                font-weight: 800;
                padding: 8px 22px;
                border-radius: 4px;
                border: none;
            }
            QPushButton#SaveBtn:hover { background-color: #FFDF00; }
            QPushButton#CancelBtn {
                background-color: #27472A;
                color: #FFFFFF;
                padding: 8px 18px;
                border-radius: 4px;
                border: 1px solid #3B533E;
            }
            QPushButton#CancelBtn:hover { background-color: #386E31; }
        """)

        self._build_ui()
        self._load_data()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)

        # 1. Tên lịch
        layout.addWidget(QLabel("<b>Tên Lịch Trình Phát Sóng:</b>"))
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Ví dụ: Bản tin chào cờ thứ 2, Phát thanh nội bộ 11:30...")
        layout.addWidget(self.txt_name)

        # 2. Loại tác vụ
        layout.addWidget(QLabel("<b>Loại Tác Vụ:</b>"))
        self.cbo_task_type = QComboBox()
        self.cbo_task_type.addItem("📻 Danh sách phát thanh (Audio Playlist Studio)", "playlist")
        self.cbo_task_type.addItem("🎙️ Tạo giọng nói AI tự động (VieNeu-TTS)", "tts")
        self.cbo_task_type.addItem("🔔 Thông báo nhắc việc", "reminder")
        self.cbo_task_type.currentIndexChanged.connect(self._on_task_type_changed)
        layout.addWidget(self.cbo_task_type)

        # 3. Kiểu lặp & Thời gian
        layout.addWidget(QLabel("<b>Cấu Hình Lịch Trình Thực Thi:</b>"))
        time_grid = QGridLayout()
        time_grid.setSpacing(8)

        self.cbo_repeat = QComboBox()
        self.cbo_repeat.addItem("Chạy một lần duy nhất", "once")
        self.cbo_repeat.addItem("Hàng ngày (Daily)", "daily")
        self.cbo_repeat.addItem("Hàng tuần theo các thứ (Weekly)", "weekly")
        self.cbo_repeat.addItem("Theo chu kỳ khoảng thời gian (Interval)", "interval")
        self.cbo_repeat.currentIndexChanged.connect(self._on_repeat_changed)
        time_grid.addWidget(QLabel("Kiểu lặp:"), 0, 0)
        time_grid.addWidget(self.cbo_repeat, 0, 1)

        self.dt_time = QTimeEdit()
        self.dt_time.setTime(QTime.currentTime().addSecs(300))
        self.dt_time.setDisplayFormat("HH:mm:ss")
        time_grid.addWidget(QLabel("Giờ phát:"), 0, 2)
        time_grid.addWidget(self.dt_time, 0, 3)

        self.box_date = QWidget()
        bd_layout = QHBoxLayout(self.box_date)
        bd_layout.setContentsMargins(0, 0, 0, 0)
        bd_layout.addWidget(QLabel("Ngày chạy:"))
        self.dt_date = QDateEdit()
        self.dt_date.setDate(QDate.currentDate())
        self.dt_date.setCalendarPopup(True)
        bd_layout.addWidget(self.dt_date)
        time_grid.addWidget(self.box_date, 1, 0, 1, 2)

        self.box_interval = QWidget()
        bi_layout = QHBoxLayout(self.box_interval)
        bi_layout.setContentsMargins(0, 0, 0, 0)
        bi_layout.addWidget(QLabel("Chu kỳ (phút):"))
        self.txt_interval = QLineEdit("60")
        bi_layout.addWidget(self.txt_interval)
        time_grid.addWidget(self.box_interval, 1, 2, 1, 2)
        self.box_interval.setVisible(False)

        layout.addLayout(time_grid)

        # Thứ trong tuần
        self.box_weekdays = QWidget()
        bw_layout = QVBoxLayout(self.box_weekdays)
        bw_layout.setContentsMargins(0, 0, 0, 0)
        bw_layout.addWidget(QLabel("Chọn các thứ lặp lại:"))
        days_row = QHBoxLayout()
        self.chk_days = []
        day_names = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
        for idx, d_name in enumerate(day_names):
            chk = QCheckBox(d_name)
            if idx < 5:
                chk.setChecked(True)
            days_row.addWidget(chk)
            self.chk_days.append(chk)
        bw_layout.addLayout(days_row)
        layout.addWidget(self.box_weekdays)
        self.box_weekdays.setVisible(False)

        # Xử lý khi bị lỡ lịch
        m_row = QHBoxLayout()
        m_row.addWidget(QLabel("Khi bị lỡ lịch (do tắt máy):"))
        self.cbo_missed = QComboBox()
        self.cbo_missed.addItem("Hiện thông báo nhắc nhở khi mở lại", "notify")
        self.cbo_missed.addItem("Tự động chạy bù ngay lập tức khi mở lại", "run_immediately")
        self.cbo_missed.addItem("Bỏ qua và đợi đến lần chạy kế tiếp", "ignore")
        m_row.addWidget(self.cbo_missed, 1)
        layout.addLayout(m_row)

        # -------------------------------------------------------------
        # KHUNG 1: AUDIO PLAYLIST STUDIO (DANH SÁCH BẢN TIN PHÁT THANH)
        # -------------------------------------------------------------
        self.card_playlist = QFrame()
        self.card_playlist.setStyleSheet("background-color: #1A381F; border: 1px solid #2E5C35; border-radius: 6px; padding: 10px;")
        cp_layout = QVBoxLayout(self.card_playlist)

        cp_layout.addWidget(QLabel("<b style='color: #FFD700; font-size: 14px;'>📻 Danh Sách Bản Tin Phát Sóng (Audio Playlist):</b>"))

        # Thanh nút chọn nguồn âm thanh phong phú
        src_row = QHBoxLayout()
        src_row.setSpacing(6)

        btn_add_file = QPushButton("📁 Tệp Máy Tính")
        btn_add_file.setToolTip("Thêm tệp âm thanh WAV, MP3 từ máy tính")
        btn_add_file.clicked.connect(self._add_from_file)
        src_row.addWidget(btn_add_file)

        btn_add_hist = QPushButton("📜 Lịch Sử TTS")
        btn_add_hist.setToolTip("Chọn từ các bản âm thanh đã tạo trước đây")
        btn_add_hist.clicked.connect(self._add_from_history)
        src_row.addWidget(btn_add_hist)

        btn_add_audio_prj = QPushButton("🎛️ Dự Án Audio")
        btn_add_audio_prj.setToolTip("Chọn từ các dự án biên tập Audio Studio")
        btn_add_audio_prj.clicked.connect(lambda: self._add_from_project("audio"))
        src_row.addWidget(btn_add_audio_prj)

        btn_add_bcast_prj = QPushButton("📡 Dự Án Broadcast")
        btn_add_bcast_prj.setToolTip("Chọn từ các bản tin Broadcast Studio")
        btn_add_bcast_prj.clicked.connect(lambda: self._add_from_project("broadcast"))
        src_row.addWidget(btn_add_bcast_prj)

        btn_doc_tts = QPushButton("📄 Nhập DOCX/TXT")
        btn_doc_tts.setStyleSheet("background-color: #D4AF37; color: #000000; border: none; font-weight: bold;")
        btn_doc_tts.setToolTip("Nhập văn bản Word/Txt, tự động trích xuất và đọc TTS")
        btn_doc_tts.clicked.connect(self._add_from_doc_tts)
        src_row.addWidget(btn_doc_tts)

        src_row.addStretch()
        cp_layout.addLayout(src_row)

        # Bảng danh sách playlist
        self.table_playlist = QTableWidget()
        self.table_playlist.setColumnCount(7)
        self.table_playlist.setHorizontalHeaderLabels([
            "#",
            "Tên Bản Tin / Tệp Âm Thanh",
            "Nguồn",
            "Thời Lượng",
            "Nghỉ Sau (s)",
            "Trạng Thái",
            "Thao Tác",
        ])
        self.table_playlist.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_playlist.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_playlist.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_playlist.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_playlist.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_playlist.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table_playlist.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table_playlist.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_playlist.setMinimumHeight(200)
        self.table_playlist.verticalHeader().setVisible(False)
        cp_layout.addWidget(self.table_playlist)

        # Thanh tổng kết & Nghe thử
        sum_row = QHBoxLayout()
        self.lbl_playlist_summary = QLabel("📊 Tổng cộng: 0 bản tin | Thời lượng: 00:00")
        self.lbl_playlist_summary.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 13px;")
        sum_row.addWidget(self.lbl_playlist_summary)
        sum_row.addStretch()

        self.btn_preview_playlist = QPushButton("▶ Nghe Thử Toàn Bộ")
        self.btn_preview_playlist.clicked.connect(self._preview_all_playlist)
        sum_row.addWidget(self.btn_preview_playlist)

        self.btn_stop_preview_all = QPushButton("⏹ Dừng Nghe Thử")
        self.btn_stop_preview_all.clicked.connect(self._stop_preview_all)
        sum_row.addWidget(self.btn_stop_preview_all)

        cp_layout.addLayout(sum_row)
        layout.addWidget(self.card_playlist)

        # -------------------------------------------------------------
        # KHUNG 2: TÁC VỤ TTS TRUYỀN THỐNG
        # -------------------------------------------------------------
        self.card_tts = QFrame()
        self.card_tts.setStyleSheet("background-color: #1A381F; border: 1px solid #2E5C35; border-radius: 6px; padding: 10px;")
        ct_layout = QVBoxLayout(self.card_tts)
        ct_layout.addWidget(QLabel("<b style='color: #FFD700;'>Nội dung văn bản phát thanh / đọc tự động:</b>"))
        self.txt_content = QTextEdit()
        self.txt_content.setPlaceholderText("Nhập nội dung văn bản tiếng Việt cần đọc...")
        self.txt_content.setMinimumHeight(100)
        ct_layout.addWidget(self.txt_content)

        v_row = QHBoxLayout()
        v_col1 = QVBoxLayout()
        v_col1.addWidget(QLabel("Giọng đọc:"))
        self.cbo_voice = QComboBox()
        v_col1.addWidget(self.cbo_voice)
        v_row.addLayout(v_col1)

        v_col2 = QVBoxLayout()
        v_col2.addWidget(QLabel("Định dạng xuất:"))
        self.cbo_format = QComboBox()
        self.cbo_format.addItem("WAV (Chuẩn Studio 48kHz)", "wav")
        self.cbo_format.addItem("MP3 (Tiết kiệm dung lượng)", "mp3")
        v_col2.addWidget(self.cbo_format)
        v_row.addLayout(v_col2)
        ct_layout.addLayout(v_row)

        ct_layout.addWidget(QLabel("Tên tệp tiền tố (prefix):"))
        self.txt_prefix = QLineEdit("Lich_Phat_Thanh")
        ct_layout.addWidget(self.txt_prefix)
        layout.addWidget(self.card_tts)
        self.card_tts.setVisible(False)

        # -------------------------------------------------------------
        # KHUNG 3: TÁC VỤ NHẮC VIỆC
        # -------------------------------------------------------------
        self.card_reminder = QFrame()
        self.card_reminder.setStyleSheet("background-color: #1A381F; border: 1px solid #2E5C35; border-radius: 6px; padding: 10px;")
        cr_layout = QVBoxLayout(self.card_reminder)
        cr_layout.addWidget(QLabel("<b style='color: #FFD700;'>Nội dung lời nhắc:</b>"))
        self.txt_reminder = QLineEdit()
        self.txt_reminder.setPlaceholderText("Ví dụ: Đã đến giờ giao ban công tác tuần...")
        cr_layout.addWidget(self.txt_reminder)
        layout.addWidget(self.card_reminder)
        self.card_reminder.setVisible(False)

        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Hủy Bỏ")
        btn_cancel.setObjectName("CancelBtn")
        btn_cancel.clicked.connect(self._on_cancel)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Lưu Lịch Trình")
        btn_save.setObjectName("SaveBtn")
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_save)

        main_layout.addLayout(btn_row)

        self._populate_voices()

    def _populate_voices(self):
        self.cbo_voice.clear()
        voices = tts_service.list_voices()
        for v in voices:
            self.cbo_voice.addItem(f"{v.get('name')} ({v.get('gender', '')})", v.get("id"))

    def _on_task_type_changed(self):
        t = self.cbo_task_type.currentData()
        self.card_playlist.setVisible(t == "playlist")
        self.card_tts.setVisible(t == "tts")
        self.card_reminder.setVisible(t == "reminder")

    def _on_repeat_changed(self):
        rep = self.cbo_repeat.currentData()
        self.box_date.setVisible(rep == "once")
        self.box_weekdays.setVisible(rep == "weekly")
        self.box_interval.setVisible(rep == "interval")

    # -------------------------------------------------------------
    # QUẢN LÝ NGUỒN ÂM THANH & BẢNG PLAYLIST
    # -------------------------------------------------------------
    def _add_from_file(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn tệp âm thanh",
            "",
            "Tệp âm thanh (*.wav *.mp3 *.ogg *.flac *.m4a);;Tất cả (*.*)",
        )
        for f in files:
            p = Path(f)
            dur = get_audio_duration_safe(p)
            item = {
                "id": f"item_{int(time.time()*1000)}_{len(self.playlist_items)}",
                "title": p.stem,
                "source_type": "file",
                "file_path": str(p),
                "duration_sec": dur,
                "pause_after": 2.0,
                "status": "pending",
            }
            self.playlist_items.append(item)
        self._refresh_playlist_table()

    def _add_from_history(self):
        dlg = HistoryAudioPickerDialog(parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_item:
            self.playlist_items.append(dlg.selected_item)
            self._refresh_playlist_table()

    def _add_from_project(self, prj_type: str):
        dlg = ProjectAudioPickerDialog(project_type=prj_type, parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_item:
            self.playlist_items.append(dlg.selected_item)
            self._refresh_playlist_table()

    def _add_from_doc_tts(self):
        dlg = DocumentToTTSDialog(parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.result_item:
            self.playlist_items.append(dlg.result_item)
            self._refresh_playlist_table()

    def _refresh_playlist_table(self):
        self.table_playlist.setRowCount(len(self.playlist_items))
        total_dur = 0.0

        for row, item in enumerate(self.playlist_items):
            fp_str = item.get("file_path", "")
            fp = Path(fp_str) if fp_str else None
            is_exist = fp and fp.is_file()

            dur = float(item.get("duration_sec") or 0.0)
            if dur <= 0 and is_exist:
                dur = get_audio_duration_safe(fp)
                item["duration_sec"] = dur

            pause = float(item.get("pause_after") or 0.0)
            total_dur += dur + pause

            # 0. Số thứ tự
            it_idx = QTableWidgetItem(str(row + 1))
            it_idx.setTextAlignment(Qt.AlignCenter)
            self.table_playlist.setItem(row, 0, it_idx)

            # 1. Tên
            it_title = QTableWidgetItem(item.get("title", "Không tên"))
            self.table_playlist.setItem(row, 1, it_title)

            # 2. Nguồn
            src_map = {
                "file": "Tệp máy",
                "history": "Lịch sử TTS",
                "audio_project": "Audio Studio",
                "broadcast_project": "Broadcast",
                "document_tts": "Doc-to-TTS",
            }
            it_src = QTableWidgetItem(src_map.get(item.get("source_type"), "Khác"))
            it_src.setTextAlignment(Qt.AlignCenter)
            self.table_playlist.setItem(row, 2, it_src)

            # 3. Thời lượng
            it_dur = QTableWidgetItem(format_sec_to_time(dur))
            it_dur.setTextAlignment(Qt.AlignCenter)
            self.table_playlist.setItem(row, 3, it_dur)

            # 4. Khoảng nghỉ (QSpinBox)
            sp_pause = QSpinBox()
            sp_pause.setRange(0, 300)
            sp_pause.setValue(int(pause))
            sp_pause.setSuffix("s")
            sp_pause.setStyleSheet("background-color: #0F1E11; color: #FFFFFF; border: 1px solid #27472A;")
            sp_pause.valueChanged.connect(lambda val, r=row: self._on_pause_changed(r, val))
            self.table_playlist.setCellWidget(row, 4, sp_pause)

            # 5. Trạng thái file
            if is_exist:
                it_st = QTableWidgetItem("🟢 Khả dụng")
                it_st.setForeground(QColor("#4ADE80"))
            else:
                it_st = QTableWidgetItem("⚠️ Mất tệp")
                it_st.setForeground(QColor("#EF4444"))
                it_st.setToolTip(f"Không tìm thấy: {fp_str}")
            it_st.setTextAlignment(Qt.AlignCenter)
            self.table_playlist.setItem(row, 5, it_st)

            # 6. Các nút thao tác
            act_widget = QWidget()
            aw_layout = QHBoxLayout(act_widget)
            aw_layout.setContentsMargins(2, 2, 2, 2)
            aw_layout.setSpacing(4)

            btn_up = QPushButton("▲")
            btn_up.setFixedSize(24, 24)
            btn_up.setToolTip("Di chuyển lên")
            btn_up.clicked.connect(lambda _, r=row: self._move_item(r, -1))
            aw_layout.addWidget(btn_up)

            btn_down = QPushButton("▼")
            btn_down.setFixedSize(24, 24)
            btn_down.setToolTip("Di chuyển xuống")
            btn_down.clicked.connect(lambda _, r=row: self._move_item(r, 1))
            aw_layout.addWidget(btn_down)

            btn_play = QPushButton("▶")
            btn_play.setFixedSize(24, 24)
            btn_play.setToolTip("Nghe thử tệp này")
            btn_play.clicked.connect(lambda _, r=row: self._play_single_item(r))
            aw_layout.addWidget(btn_play)

            if not is_exist:
                btn_relink = QPushButton("🔄")
                btn_relink.setFixedSize(24, 24)
                btn_relink.setStyleSheet("background-color: #EA580C; color: #FFFFFF; font-weight: bold;")
                btn_relink.setToolTip("Chọn lại đường dẫn tệp âm thanh (Relink)")
                btn_relink.clicked.connect(lambda _, r=row: self._relink_item(r))
                aw_layout.addWidget(btn_relink)

            btn_del = QPushButton("🗑")
            btn_del.setFixedSize(24, 24)
            btn_del.setStyleSheet("color: #EF4444;")
            btn_del.setToolTip("Xóa mục này khỏi playlist")
            btn_del.clicked.connect(lambda _, r=row: self._remove_item(r))
            aw_layout.addWidget(btn_del)

            self.table_playlist.setCellWidget(row, 6, act_widget)

        self.lbl_playlist_summary.setText(
            f"📊 Tổng cộng: {len(self.playlist_items)} bản tin | Tổng thời lượng: {format_sec_to_time(total_dur)}"
        )

    def _on_pause_changed(self, row: int, val: int):
        if 0 <= row < len(self.playlist_items):
            self.playlist_items[row]["pause_after"] = float(val)

    def _move_item(self, row: int, direction: int):
        target = row + direction
        if 0 <= target < len(self.playlist_items):
            self.playlist_items[row], self.playlist_items[target] = self.playlist_items[target], self.playlist_items[row]
            self._refresh_playlist_table()

    def _remove_item(self, row: int):
        if 0 <= row < len(self.playlist_items):
            del self.playlist_items[row]
            self._refresh_playlist_table()

    def _relink_item(self, row: int):
        if not (0 <= row < len(self.playlist_items)):
            return
        item = self.playlist_items[row]
        f, _ = QFileDialog.getOpenFileName(
            self,
            f"Chọn lại đường dẫn tệp cho '{item.get('title')}'",
            "",
            "Tệp âm thanh (*.wav *.mp3 *.ogg *.flac *.m4a);;Tất cả (*.*)",
        )
        if f:
            p = Path(f)
            item["file_path"] = str(p)
            item["duration_sec"] = get_audio_duration_safe(p)
            self._refresh_playlist_table()

    def _play_single_item(self, row: int):
        if 0 <= row < len(self.playlist_items):
            fp = self.playlist_items[row].get("file_path")
            if fp and Path(fp).is_file():
                audio_player.play(fp)
            else:
                QMessageBox.warning(self, "Tệp không tồn tại", f"Không tìm thấy tệp:\n{fp}")

    def _preview_all_playlist(self):
        if not self.playlist_items:
            return
        # Bắt đầu phát tệp đầu tiên
        for item in self.playlist_items:
            fp = item.get("file_path")
            if fp and Path(fp).is_file():
                audio_player.play(fp)
                break

    def _stop_preview_all(self):
        audio_player.stop()

    def _on_cancel(self):
        audio_player.stop()
        self.reject()

    # -------------------------------------------------------------
    # NẠP DỮ LIỆU & LƯU
    # -------------------------------------------------------------
    def _load_data(self):
        if not self.schedule_dict:
            return

        self.txt_name.setText(self.schedule_dict.get("name", ""))
        tt = self.schedule_dict.get("task_type", "playlist")
        idx_tt = self.cbo_task_type.findData(tt)
        if idx_tt >= 0:
            self.cbo_task_type.setCurrentIndex(idx_tt)

        rep = self.schedule_dict.get("repeat_type", "once")
        idx_rep = self.cbo_repeat.findData(rep)
        if idx_rep >= 0:
            self.cbo_repeat.setCurrentIndex(idx_rep)

        t_str = self.schedule_dict.get("target_time", "08:00:00")
        self.dt_time.setTime(QTime.fromString(t_str, "HH:mm:ss") or QTime(8, 0))

        d_str = self.schedule_dict.get("target_date")
        if d_str:
            self.dt_date.setDate(QDate.fromString(d_str, "yyyy-MM-dd") or QDate.currentDate())

        days = self.schedule_dict.get("repeat_days", [0, 1, 2, 3, 4])
        for idx, chk in enumerate(self.chk_days):
            chk.setChecked(idx in days)

        self.txt_interval.setText(str(self.schedule_dict.get("interval_minutes", 60)))

        mb = self.schedule_dict.get("missed_behavior", "notify")
        idx_mb = self.cbo_missed.findData(mb)
        if idx_mb >= 0:
            self.cbo_missed.setCurrentIndex(idx_mb)

        cfg = self.schedule_dict.get("task_config", {})
        # Nạp Playlist
        self.playlist_items = list(self.schedule_dict.get("playlist") or cfg.get("playlist") or [])
        self._refresh_playlist_table()

        # Nạp TTS
        self.txt_content.setText(cfg.get("text", ""))
        self.txt_prefix.setText(cfg.get("filename_prefix", "Lich_Phat_Thanh"))
        v_idx = self.cbo_voice.findData(cfg.get("voice_id", "hn_nam_quan_doi"))
        if v_idx >= 0:
            self.cbo_voice.setCurrentIndex(v_idx)
        f_idx = self.cbo_format.findData(cfg.get("out_format", "wav"))
        if f_idx >= 0:
            self.cbo_format.setCurrentIndex(f_idx)

        # Nạp Reminder
        self.txt_reminder.setText(cfg.get("reminder_message", ""))

        self._on_task_type_changed()
        self._on_repeat_changed()

    def _on_save(self):
        audio_player.stop()
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Chưa đặt tên", "Vui lòng nhập tên cho lịch trình.")
            return

        task_type = self.cbo_task_type.currentData()
        repeat_type = self.cbo_repeat.currentData()
        target_time = self.dt_time.time().toString("HH:mm:ss")
        target_date = self.dt_date.date().toString("yyyy-MM-dd") if repeat_type == "once" else None

        repeat_days = [idx for idx, chk in enumerate(self.chk_days) if chk.isChecked()]
        if repeat_type == "weekly" and not repeat_days:
            QMessageBox.warning(self, "Chưa chọn thứ", "Vui lòng chọn ít nhất một ngày trong tuần để lặp lại.")
            return

        try:
            interval_mins = max(1, int(self.txt_interval.text().strip()))
        except ValueError:
            interval_mins = 60

        task_config = {}
        if task_type == "playlist":
            if not self.playlist_items:
                QMessageBox.warning(self, "Playlist rỗng", "Vui lòng thêm ít nhất một bản tin vào Playlist.")
                return
            task_config = {"playlist": self.playlist_items}
            self.schedule_dict["playlist"] = self.playlist_items
        elif task_type == "tts":
            text = self.txt_content.toPlainText().strip()
            if not text:
                QMessageBox.warning(self, "Chưa nhập nội dung", "Vui lòng nhập văn bản cần đọc cho tác vụ TTS.")
                return
            task_config = {
                "text": text,
                "voice_id": self.cbo_voice.currentData(),
                "speed": 1.0,
                "out_format": self.cbo_format.currentData(),
                "filename_prefix": self.txt_prefix.text().strip() or "Lich_Phat_Thanh",
            }
        else:
            reminder_msg = self.txt_reminder.text().strip()
            if not reminder_msg:
                QMessageBox.warning(self, "Chưa nhập lời nhắc", "Vui lòng nhập nội dung lời nhắc việc.")
                return
            task_config = {"reminder_message": reminder_msg}

        self.schedule_dict.update({
            "name": name,
            "task_type": task_type,
            "repeat_type": repeat_type,
            "target_time": target_time,
            "target_date": target_date,
            "repeat_days": repeat_days,
            "interval_minutes": interval_mins,
            "missed_behavior": self.cbo_missed.currentData(),
            "task_config": task_config,
            "is_enabled": self.schedule_dict.get("is_enabled", True),
            "next_run": None,
        })

        self.accept()


# =============================================================================
# TRANG CHÍNH: PAGE SCHEDULE STUDIO
# =============================================================================
class PageSchedule(QWidget):
    """Trang Giao Diện Chính Schedule Studio."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_running_id: Optional[str] = None
        self._build_ui()
        self._connect_signals()
        self.reload_schedules()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # 1. BANNER TIÊU ĐỀ
        banner_card = QFrame()
        banner_card.setProperty("class", "CardFrame")
        banner_card.setStyleSheet(
            "#SchedBanner { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1E2D22, stop:1 #152219); border: 1px solid #3B533E; border-radius: 8px; }"
        )
        banner_card.setObjectName("SchedBanner")
        bn_layout = QVBoxLayout(banner_card)
        bn_layout.setContentsMargins(16, 12, 16, 12)
        bn_layout.setSpacing(4)

        lbl_title = QLabel("⏰  SCHEDULE STUDIO — ĐẶT LỊCH PHÁT THANH & NHẮC VIỆC TỰ ĐỘNG")
        lbl_title.setStyleSheet("color: #FFD700; font-size: 15px; font-weight: 800; border: none;")
        bn_layout.addWidget(lbl_title)

        lbl_sub = QLabel("Tự động phát danh sách âm thanh đa nguồn (Audio Playlist) và tổng hợp giọng nói AI VieNeu-TTS theo lịch định kỳ.")
        lbl_sub.setStyleSheet("color: #C5DFC3; font-size: 12px; border: none;")
        bn_layout.addWidget(lbl_sub)
        main_layout.addWidget(banner_card)

        # 2. KHUNG ĐIỀU KHIỂN PHÁT SÓNG THỜI GIAN THỰC (LIVE BROADCAST PANEL)
        self.live_card = QFrame()
        self.live_card.setStyleSheet("""
            QFrame#LiveCard {
                background-color: #0F2312;
                border: 2px solid #22C55E;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        self.live_card.setObjectName("LiveCard")
        lc_layout = QHBoxLayout(self.live_card)
        lc_layout.setContentsMargins(14, 8, 14, 8)
        lc_layout.setSpacing(12)

        self.lbl_live_status = QLabel("📻 Đang phát sóng: Không có lịch nào đang chạy")
        self.lbl_live_status.setStyleSheet("color: #4ADE80; font-size: 13px; font-weight: bold;")
        lc_layout.addWidget(self.lbl_live_status, 1)

        self.btn_live_pause = QPushButton("⏸ Tạm Dừng")
        self.btn_live_pause.setProperty("class", "SecondaryBtn")
        self.btn_live_pause.clicked.connect(self._on_live_pause)
        lc_layout.addWidget(self.btn_live_pause)

        self.btn_live_resume = QPushButton("▶ Tiếp Tục")
        self.btn_live_resume.setProperty("class", "SecondaryBtn")
        self.btn_live_resume.clicked.connect(self._on_live_resume)
        lc_layout.addWidget(self.btn_live_resume)

        self.btn_live_stop = QPushButton("⏹ Dừng Phát")
        self.btn_live_stop.setStyleSheet("background-color: #EF4444; color: #FFFFFF; font-weight: bold; border-radius: 4px; padding: 6px 14px;")
        self.btn_live_stop.clicked.connect(self._on_live_stop)
        lc_layout.addWidget(self.btn_live_stop)

        self.live_card.setVisible(False)
        main_layout.addWidget(self.live_card)

        # 3. THANH THAO TÁC (ACTION BAR)
        act_row = QHBoxLayout()
        act_row.setSpacing(8)

        self.btn_add = QPushButton("➕  Tạo Lịch Mới")
        self.btn_add.setProperty("class", "PrimaryBtn")
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(self._on_add_schedule)
        act_row.addWidget(self.btn_add)

        self.btn_edit = QPushButton("✏️  Chỉnh Sửa")
        self.btn_edit.setProperty("class", "SecondaryBtn")
        self.btn_edit.setCursor(Qt.PointingHandCursor)
        self.btn_edit.clicked.connect(self._on_edit_schedule)
        act_row.addWidget(self.btn_edit)

        self.btn_toggle = QPushButton("⏯  Bật / Tắt")
        self.btn_toggle.setProperty("class", "SecondaryBtn")
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.clicked.connect(self._on_toggle_schedule)
        act_row.addWidget(self.btn_toggle)

        self.btn_run_now = QPushButton("▶  Chạy Ngay")
        self.btn_run_now.setProperty("class", "SecondaryBtn")
        self.btn_run_now.setCursor(Qt.PointingHandCursor)
        self.btn_run_now.clicked.connect(self._on_run_now)
        act_row.addWidget(self.btn_run_now)

        self.btn_history = QPushButton("📜  Lịch Sử Chạy")
        self.btn_history.setProperty("class", "SecondaryBtn")
        self.btn_history.setCursor(Qt.PointingHandCursor)
        self.btn_history.clicked.connect(self._on_view_history)
        act_row.addWidget(self.btn_history)

        self.btn_delete = QPushButton("🗑  Xóa Lịch")
        self.btn_delete.setProperty("class", "SecondaryBtn")
        self.btn_delete.setStyleSheet("QPushButton { color: #EF4444; border-color: #7F1D1D; } QPushButton:hover { background-color: #450A0A; }")
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.clicked.connect(self._on_delete_schedule)
        act_row.addWidget(self.btn_delete)

        act_row.addStretch()

        self.btn_refresh = QPushButton("🔄  Làm Mới")
        self.btn_refresh.setProperty("class", "SecondaryBtn")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.reload_schedules)
        act_row.addWidget(self.btn_refresh)

        main_layout.addLayout(act_row)

        # 4. BẢNG DANH SÁCH LỊCH TRÌNH
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Tên Lịch Trình",
            "Loại Tác Vụ",
            "Thời Gian",
            "Kiểu Lặp",
            "Trạng Thái",
            "Lần Chạy Tiếp Theo",
            "Lần Chạy Gần Nhất",
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_edit_schedule)

        main_layout.addWidget(self.table, 1)

    def _connect_signals(self):
        scheduler_engine.schedules_updated.connect(self.reload_schedules)
        scheduler_engine.schedule_completed.connect(self._on_engine_completed)
        scheduler_engine.schedule_failed.connect(self._on_engine_failed)
        scheduler_engine.schedule_missed.connect(self._on_engine_missed)
        scheduler_engine.playlist_item_started.connect(self._on_playlist_item_started)
        scheduler_engine.playlist_item_finished.connect(self._on_playlist_item_finished)
        scheduler_engine.playlist_state_changed.connect(self._on_playlist_state_changed)

    def reload_schedules(self):
        """Tải lại danh sách lịch và hiển thị lên bảng."""
        items = scheduler_engine.list_schedules()
        self.table.setRowCount(len(items))

        day_labels = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]

        for row, s in enumerate(items):
            sid = s.get("id")
            name = s.get("name", "Lịch không tên")
            ttype = s.get("task_type", "playlist")
            target_t = s.get("target_time", "")
            rtype = s.get("repeat_type", "once")
            enabled = s.get("is_enabled", True)
            next_run = s.get("next_run") or "—"
            last_run = s.get("last_run") or "Chưa chạy"

            # Tác vụ
            if ttype == "playlist":
                pl = s.get("playlist") or s.get("task_config", {}).get("playlist", [])
                has_missing = any(not (Path(it.get("file_path", "")).is_file()) for it in pl)
                warning_suffix = " ⚠️(Thiếu tệp)" if has_missing else ""
                tt_label = f"📻 Playlist ({len(pl)} tệp){warning_suffix}"
            elif ttype == "tts":
                tt_label = "🎙️ Đọc TTS"
            else:
                tt_label = "🔔 Nhắc việc"

            # Kiểu lặp
            if rtype == "once":
                rep_label = f"1 Lần ({s.get('target_date', '')})"
            elif rtype == "daily":
                rep_label = "Hàng ngày"
            elif rtype == "weekly":
                rdays = s.get("repeat_days", [])
                days_txt = ",".join([day_labels[d] for d in rdays if 0 <= d < 7])
                rep_label = f"Hàng tuần ({days_txt})"
            elif rtype == "interval":
                rep_label = f"Mỗi {s.get('interval_minutes', 60)} phút"
            else:
                rep_label = rtype

            st_badge = "🟢 Đang bật" if enabled else "⚪ Đã tắt"

            it_name = QTableWidgetItem(name)
            it_name.setData(Qt.UserRole, sid)

            it_type = QTableWidgetItem(tt_label)
            if "⚠️" in tt_label:
                it_type.setForeground(QColor("#EF4444"))

            it_time = QTableWidgetItem(target_t)
            it_rep = QTableWidgetItem(rep_label)
            it_st = QTableWidgetItem(st_badge)
            it_next = QTableWidgetItem(next_run)
            it_last = QTableWidgetItem(last_run)

            it_type.setTextAlignment(Qt.AlignCenter)
            it_time.setTextAlignment(Qt.AlignCenter)
            it_st.setTextAlignment(Qt.AlignCenter)
            it_next.setTextAlignment(Qt.AlignCenter)
            it_last.setTextAlignment(Qt.AlignCenter)

            if not enabled:
                it_name.setForeground(QColor("#94A3B8"))
                it_next.setForeground(QColor("#64748B"))

            self.table.setItem(row, 0, it_name)
            self.table.setItem(row, 1, it_type)
            self.table.setItem(row, 2, it_time)
            self.table.setItem(row, 3, it_rep)
            self.table.setItem(row, 4, it_st)
            self.table.setItem(row, 5, it_next)
            self.table.setItem(row, 6, it_last)

    def _get_selected_schedule(self) -> Optional[Dict[str, Any]]:
        row = self.table.currentRow()
        if row < 0:
            return None
        it = self.table.item(row, 0)
        if not it:
            return None
        sid = it.data(Qt.UserRole)
        return scheduler_engine.get_schedule(sid)

    def _on_add_schedule(self):
        dlg = ScheduleEditorDialog(parent=self)
        if dlg.exec() == QDialog.Accepted:
            scheduler_engine.save_schedule(dlg.schedule_dict)
            notification_hub.notify_success.emit("Tạo Lịch Thành Công", f"Đã thêm lịch: '{dlg.schedule_dict.get('name')}'")

    def add_schedule_for_audio(self, audio_path: str | Path, title: str = ""):
        """Thêm và mở hộp thoại tạo lịch phát mới với tệp âm thanh được chuyển từ các module khác."""
        p = Path(audio_path).resolve()
        if not p.is_file():
            return
        sched_data = {
            "name": title or f"Phát {p.stem}",
            "task_type": "playlist",
            "playlist_items": [
                {
                    "title": title or p.stem,
                    "file_path": str(p),
                    "duration_sec": get_audio_duration_safe(p),
                    "source": "file",
                    "pause_after": 2.0,
                }
            ],
            "repeat": "once",
        }
        dlg = ScheduleEditorDialog(schedule_dict=sched_data, parent=self)
        if dlg.exec() == QDialog.Accepted:
            scheduler_engine.save_schedule(dlg.schedule_dict)
            notification_hub.notify_success.emit("Tạo Lịch Thành Công", f"Đã thêm lịch: '{dlg.schedule_dict.get('name')}'")

    def _on_edit_schedule(self):
        sched = self._get_selected_schedule()
        if not sched:
            QMessageBox.information(self, "Chưa chọn", "Vui lòng chọn một lịch từ danh sách để chỉnh sửa.")
            return
        dlg = ScheduleEditorDialog(schedule_dict=sched, parent=self)
        if dlg.exec() == QDialog.Accepted:
            scheduler_engine.save_schedule(dlg.schedule_dict)
            notification_hub.notify_success.emit("Cập Nhật Lịch", f"Đã cập nhật lịch: '{dlg.schedule_dict.get('name')}'")

    def _on_toggle_schedule(self):
        sched = self._get_selected_schedule()
        if not sched:
            QMessageBox.information(self, "Chưa chọn", "Vui lòng chọn một lịch để bật hoặc tắt.")
            return
        new_st = scheduler_engine.toggle_schedule(sched["id"])
        st_text = "được BẬT" if new_st else "được TẮT"
        notification_hub.notify_info.emit("Thay Đổi Trạng Thái Lịch", f"Lịch '{sched.get('name')}' đã {st_text}.")

    def _on_run_now(self):
        sched = self._get_selected_schedule()
        if not sched:
            QMessageBox.information(self, "Chưa chọn", "Vui lòng chọn một lịch để chạy ngay.")
            return
        self._current_running_id = sched["id"]
        scheduler_engine.execute_schedule_task(sched, is_manual_run=True)
        notification_hub.notify_info.emit("Bắt Đầu Chạy Lịch", f"Đang thực thi lịch: '{sched.get('name')}'...")

    def _on_view_history(self):
        sched = self._get_selected_schedule()
        if not sched:
            QMessageBox.information(self, "Chưa chọn", "Vui lòng chọn một lịch để xem lịch sử thực thi.")
            return
        dlg = ScheduleHistoryDialog(sched, parent=self)
        dlg.exec()

    def _on_delete_schedule(self):
        sched = self._get_selected_schedule()
        if not sched:
            QMessageBox.information(self, "Chưa chọn", "Vui lòng chọn một lịch cần xóa.")
            return
        res = QMessageBox.question(
            self,
            "Xác nhận xóa lịch",
            f"Bạn có chắc chắn muốn xóa lịch trình '{sched.get('name')}' không?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if res == QMessageBox.Yes:
            scheduler_engine.delete_schedule(sched["id"])
            notification_hub.notify_info.emit("Đã Xóa Lịch", f"Đã xóa lịch '{sched.get('name')}'.")

    # -------------------------------------------------------------
    # ĐIỀU KHIỂN & THEO DÕI LIVE BROADCAST
    # -------------------------------------------------------------
    def _on_playlist_item_started(self, sched: dict, item: dict, idx: int, total: int):
        self._current_running_id = sched.get("id")
        self.live_card.setVisible(True)
        self.lbl_live_status.setText(
            f"📻 Đang phát: <b style='color:#FFD700;'>{sched.get('name')}</b> — Bản tin [{idx}/{total}]: <i>{item.get('title')}</i>"
        )
        self.btn_live_pause.setEnabled(True)
        self.btn_live_resume.setEnabled(False)

    def _on_playlist_item_finished(self, sched: dict, item: dict, idx: int, total: int):
        self.lbl_live_status.setText(
            f"📻 Đã phát xong [{idx}/{total}]: <i>{item.get('title')}</i>. Chuẩn bị bản tin tiếp theo..."
        )

    def _on_playlist_state_changed(self, sid: str, state: str):
        if state == "stopped":
            self.live_card.setVisible(False)
            self._current_running_id = None
        elif state == "paused":
            self.btn_live_pause.setEnabled(False)
            self.btn_live_resume.setEnabled(True)
            self.lbl_live_status.setText(f"⏸ Tạm dừng phát sóng: <b>{self.lbl_live_status.text()}</b>")
        elif state == "playing":
            self.btn_live_pause.setEnabled(True)
            self.btn_live_resume.setEnabled(False)

    def _on_live_pause(self):
        if self._current_running_id:
            scheduler_engine.pause_schedule_playback(self._current_running_id)

    def _on_live_resume(self):
        if self._current_running_id:
            scheduler_engine.resume_schedule_playback(self._current_running_id)

    def _on_live_stop(self):
        if self._current_running_id:
            scheduler_engine.stop_schedule_playback(self._current_running_id)
            self.live_card.setVisible(False)

    def _on_engine_completed(self, sched: dict, res: dict):
        name = sched.get("name", "Lịch")
        if res.get("is_playlist"):
            notification_hub.notify_success.emit(f"✅ Hoàn Thành Lịch: {name}", res.get("message", "Phát xong danh sách"))
        elif res.get("is_reminder"):
            msg = res.get("message", "Đã đến giờ nhắc việc!")
            notification_hub.notify_info.emit(f"🔔 Nhắc Việc: {name}", msg)
            QMessageBox.information(self, f"🔔 Lời Nhắc: {name}", f"⏰ Đã đến giờ:\n\n{msg}")
        else:
            fp = res.get("file_path", "")
            notification_hub.notify_success.emit(f"✅ Hoàn Thành Lịch: {name}", f"Đã xuất file âm thanh:\n{Path(fp).name}")

    def _on_engine_failed(self, sched: dict, err: str):
        name = sched.get("name", "Lịch")
        notification_hub.notify_error.emit(f"❌ Lỗi Lịch: {name}", f"Quá trình thực thi gặp lỗi:\n{err}")

    def _on_engine_missed(self, sched: dict):
        name = sched.get("name", "Lịch")
        notification_hub.notify_warning.emit(f"⚠️ Lỡ Lịch: {name}", f"Lịch '{name}' bị bỏ lỡ do phần mềm không mở vào thời điểm chạy.")
