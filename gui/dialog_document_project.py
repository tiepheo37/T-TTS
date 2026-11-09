"""gui/dialog_document_project.py — HỘP THOẠI QUẢN LÝ DỰ ÁN TÀI LIỆU (DOCUMENT PROJECT)
====================================================================================
Quản lý vòng đời dự án tài liệu chuyển văn bản thành giọng nói cho T-TTS v3.1.0:
- Liệt kê các dự án gần đây và toàn bộ dự án tài liệu dạng bảng trực quan.
- Mở dự án (Open), Lưu bản mới (Save As), Nhân bản (Duplicate), Đổi tên (Rename), Xóa (Delete).
- Xác nhận an toàn trước khi xóa, bảo toàn các tệp âm thanh đã xuất bản.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QPushButton,
    QInputDialog,
    QMessageBox,
)

from backend.project_manager import project_manager


class DocumentProjectDialog(QDialog):
    """Hộp thoại quản trị danh sách dự án tài liệu văn bản."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.selected_project: Optional[Dict[str, Any]] = None
        self.setWindowTitle("📁 Quản Lý Dự Án Tài Liệu Văn Bản — T-TTS")
        self.setMinimumSize(760, 480)
        self.setStyleSheet("""
            QDialog { background-color: #0F1710; color: #FFFFFF; }
            QLabel { color: #E2E8F0; font-size: 13px; }
            QTableWidget {
                background-color: #122215; color: #FFFFFF; border: 1px solid #27472A;
                gridline-color: #1E3A24; font-size: 12px;
            }
            QHeaderView::section {
                background-color: #1A3520; color: #4ADE80; font-weight: bold;
                border: 1px solid #27472A; padding: 6px;
            }
            QPushButton {
                background-color: #1E3A24; color: #FFFFFF; border: 1px solid #3B6B44;
                border-radius: 4px; padding: 6px 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2D5A34; }
        """)
        self._init_ui()
        self._refresh_list()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("<b>DANH SÁCH DỰ ÁN TÀI LIỆU VĂN BẢN (DOCUMENT PROJECTS):</b>"))
        top_row.addStretch()

        btn_refresh = QPushButton("🔄 Làm Mới")
        btn_refresh.clicked.connect(self._refresh_list)
        top_row.addWidget(btn_refresh)
        layout.addLayout(top_row)

        # Bảng danh sách dự án
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Tên Dự Án", "Cập Nhật Lần Cuối", "Số Đoạn (Chunks)", "Mã ID"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table, 1)

        # Hàng nút điều khiển
        btn_row = QHBoxLayout()
        self.btn_open = QPushButton("📂 Mở Dự Án Đang Chọn")
        self.btn_open.setStyleSheet("background-color: #15803D; color: #FFF;")
        self.btn_open.clicked.connect(self._on_open_clicked)
        btn_row.addWidget(self.btn_open)

        self.btn_duplicate = QPushButton("📋 Nhân Bản")
        self.btn_duplicate.clicked.connect(self._on_duplicate_clicked)
        btn_row.addWidget(self.btn_duplicate)

        self.btn_rename = QPushButton("✏️ Đổi Tên")
        self.btn_rename.clicked.connect(self._on_rename_clicked)
        btn_row.addWidget(self.btn_rename)

        self.btn_delete = QPushButton("🗑️ Xóa Dự Án")
        self.btn_delete.setStyleSheet("background-color: #991B1B; color: #FFF;")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        btn_row.addWidget(self.btn_delete)

        btn_row.addStretch()

        btn_close = QPushButton("Đóng")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _refresh_list(self):
        projects = project_manager.list_document_projects()
        self.table.setRowCount(len(projects))
        self.project_ids = []

        for row, p in enumerate(projects):
            pid = p.get("id", "")
            self.project_ids.append(pid)

            item_name = QTableWidgetItem(p.get("name", "Dự án tài liệu"))
            item_date = QTableWidgetItem(p.get("updated_at", ""))
            item_id = QTableWidgetItem(pid)

            # Đọc chi tiết segments nếu nạp được
            full = project_manager.load_document_project(pid)
            chunks_count = len(full.get("data", {}).get("segments", [])) if full else 0
            item_chunks = QTableWidgetItem(f"{chunks_count} đoạn")
            item_chunks.setTextAlignment(Qt.AlignCenter)

            self.table.setItem(row, 0, item_name)
            self.table.setItem(row, 1, item_date)
            self.table.setItem(row, 2, item_chunks)
            self.table.setItem(row, 3, item_id)

    def _get_selected_pid(self) -> Optional[str]:
        row = self.table.currentRow()
        if 0 <= row < len(self.project_ids):
            return self.project_ids[row]
        return None

    def _on_double_click(self, row: int, col: int):
        self._on_open_clicked()

    def _on_open_clicked(self):
        pid = self._get_selected_pid()
        if not pid:
            QMessageBox.warning(self, "Thông báo", "Vui lòng chọn một dự án trong danh sách!")
            return
        proj = project_manager.load_document_project(pid)
        if proj:
            self.selected_project = proj
            self.accept()
        else:
            QMessageBox.critical(self, "Lỗi", f"Không thể tải dự án '{pid}'.")

    def _on_duplicate_clicked(self):
        pid = self._get_selected_pid()
        if not pid:
            return
        cloned = project_manager.duplicate_document_project(pid)
        if cloned:
            self._refresh_list()
            QMessageBox.information(self, "Thành công", f"Đã nhân bản dự án thành: {cloned.get('name')}")

    def _on_rename_clicked(self):
        pid = self._get_selected_pid()
        if not pid:
            return
        proj = project_manager.load_document_project(pid)
        if not proj:
            return

        old_name = proj.get("name", "")
        new_name, ok = QInputDialog.getText(self, "Đổi tên dự án", "Nhập tên mới:", text=old_name)
        if ok and new_name.strip():
            project_manager.rename_document_project(pid, new_name.strip())
            self._refresh_list()

    def _on_delete_clicked(self):
        pid = self._get_selected_pid()
        if not pid:
            return
        ans = QMessageBox.question(
            self,
            "Xác nhận xóa",
            "Bạn có chắc chắn muốn xóa dự án tài liệu này không?\n\n(Lưu ý: Tệp âm thanh đã xuất sẽ không bị xóa).",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            project_manager.delete_document_project(pid, delete_audio=False)
            self._refresh_list()
