"""gui/dialog_update.py — HỘP THOẠI CẬP NHẬT PHẦN MỀM T-TTS (DARK MILITARY K20)
=============================================================================
Thiết kế chuyên nghiệp theo phong cách Dark Military K20 & Gold Accent:
- Nền xanh quân đội sẫm (#0F1E11 / #142817).
- Điểm nhấn vàng sao vàng (#FFD700) và xanh lá K20 (#4ADE80 / #2D5A27).
- Huy hiệu 'NÂNG CẤP TRỰC TIẾP v3.0.0 → v3.1.0' (Bảo toàn 100% dữ liệu, bản quyền và dự án).
- Thông tin phiên bản rõ ràng, hiển thị mục 'CÓ GÌ MỚI?' (Release Notes).
- Hỗ trợ Khôi phục bản sao lưu (Rollback & Restore).
- Thanh tiến trình tải thời gian thực (phần trăm, dung lượng đã tải, tốc độ MB/s).
- Nút Hủy tải, Thử lại, và tự động khởi động lại sau khi cài đặt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QFrame,
    QWidget,
    QMessageBox,
)

from backend.updater import UpdateInfoData, UpdateManager, DownloadUpdateWorker


MILITARY_K20_UPDATE_QSS = """
QDialog#UpdateDialog {
    background-color: #0F1E11;
    border: 1.5px solid #27472A;
    border-radius: 12px;
}

QLabel {
    color: #E8F5E9;
    font-family: "Segoe UI", Arial, sans-serif;
    border: none;
    background: transparent;
}

QFrame.UpdateCard {
    background-color: #142817;
    border: 1px solid #27472A;
    border-radius: 8px;
}

QTextEdit {
    background-color: #0B170D;
    color: #E8F5E9;
    border: 1px solid #27472A;
    border-radius: 6px;
    padding: 10px;
    font-size: 13px;
    line-height: 1.5;
}

QProgressBar {
    background-color: #142817;
    border: 1px solid #27472A;
    border-radius: 6px;
    text-align: center;
    color: #FFFFFF;
    font-weight: bold;
    font-size: 12px;
    min-height: 22px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2D5A27, stop:1 #4ADE80);
    border-radius: 5px;
}

QPushButton.MilitaryPrimaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2D5A27, stop:1 #3B7233);
    color: #FFFFFF;
    font-weight: bold;
    font-size: 13px;
    border: 1px solid #4ADE80;
    border-radius: 6px;
    padding: 9px 20px;
    min-height: 18px;
}

QPushButton.MilitaryPrimaryBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3B7233, stop:1 #4E9B44);
    border-color: #86EFAC;
}

QPushButton.MilitarySecondaryBtn {
    background-color: #142817;
    color: #C8E6C9;
    border: 1px solid #27472A;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    font-size: 13px;
    min-height: 18px;
}

QPushButton.MilitarySecondaryBtn:hover {
    background-color: #1E3A21;
    border-color: #4ADE80;
    color: #FFFFFF;
}

QPushButton.MilitaryGoldBtn {
    background-color: #242410;
    color: #FFD700;
    border: 1px solid #B8860B;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
    font-size: 13px;
    min-height: 18px;
}

QPushButton.MilitaryGoldBtn:hover {
    background-color: #383416;
    border-color: #FFD700;
    color: #FFF9C4;
}

QPushButton.CancelBtn {
    background-color: #7F1D1D;
    color: #FECACA;
    border: 1px solid #DC2626;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
    font-size: 13px;
    min-height: 18px;
}

QPushButton.CancelBtn:hover {
    background-color: #991B1B;
    color: #FFFFFF;
}
"""

DARK_NAVY_UPDATE_QSS = MILITARY_K20_UPDATE_QSS  # Hỗ trợ tương thích ngược


class UpdateDialog(QDialog):
    """Cửa sổ thông báo và cài đặt bản cập nhật T-TTS mới theo phong cách Quân đội K20."""

    update_installed = Signal()

    def __init__(
        self,
        updater: UpdateManager,
        update_info: UpdateInfoData,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.updater = updater
        self.update_info = update_info
        self.download_worker: Optional[DownloadUpdateWorker] = None
        self.downloaded_file: Optional[Path] = None

        self.setObjectName("UpdateDialog")
        self.setWindowTitle("Cập Nhật Phần Mềm T-TTS")
        self.setFixedSize(620, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(MILITARY_K20_UPDATE_QSS)

        self._build_ui()
        self._set_state_ready()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        # 0. DIRECT UPGRADE BADGE
        self.banner = QLabel("★ NÂNG CẤP TRỰC TIẾP v3.0.0 → v3.1.0 (BẢO TOÀN 100% DỮ LIỆU & BẢN QUYỀN) ★")
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setStyleSheet(
            "background-color: #18381C; color: #FFD700; font-size: 11.5px; font-weight: 800; "
            "border: 1px solid #3B7233; border-radius: 6px; padding: 6px;"
        )
        layout.addWidget(self.banner)

        # 1. HEADER BAR
        header_row = QHBoxLayout()
        header_icon = QLabel("🎖️")
        header_icon.setFont(QFont("Segoe UI Emoji", 26))
        header_row.addWidget(header_icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        self.title_lbl = QLabel(f"Đã có phiên bản T-TTS v{self.update_info.latest_version} Mới")
        self.title_lbl.setStyleSheet("font-size: 16.5px; font-weight: 800; color: #FFD700;")
        title_box.addWidget(self.title_lbl)

        self.subtitle_lbl = QLabel(
            f"Phiên bản hiện tại: <b>v{self.update_info.current_version}</b>  ➔  "
            f"Phiên bản mới: <b style='color:#4ADE80;'>v{self.update_info.latest_version}</b>.<br>"
            f"Hệ thống sẽ tự động sao lưu an toàn toàn bộ dữ liệu, bản quyền và dự án trước khi cập nhật."
        )
        self.subtitle_lbl.setStyleSheet("font-size: 12px; color: #C8E6C9; line-height: 1.4;")
        self.subtitle_lbl.setWordWrap(True)
        title_box.addWidget(self.subtitle_lbl)

        header_row.addLayout(title_box)
        header_row.addStretch()
        layout.addLayout(header_row)

        # 2. KHU VỰC CÓ GÌ MỚI? (RELEASE NOTES)
        self.notes_card = QFrame()
        self.notes_card.setProperty("class", "UpdateCard")
        nc_layout = QVBoxLayout(self.notes_card)
        nc_layout.setContentsMargins(12, 10, 12, 10)
        nc_layout.setSpacing(6)

        notes_title_row = QHBoxLayout()
        notes_title = QLabel("📌 CÓ GÌ MỚI TRONG BẢN V3.1.0?")
        notes_title.setStyleSheet("font-size: 12px; font-weight: 800; color: #4ADE80; letter-spacing: 0.5px;")
        notes_title_row.addWidget(notes_title)

        if self.update_info.published_at:
            pub_date = str(self.update_info.published_at).split("T")[0]
            date_badge = QLabel(f"📅 Ngày: {pub_date}")
            date_badge.setStyleSheet("color: #A5D6A7; font-size: 11px;")
            notes_title_row.addWidget(date_badge)

        if self.update_info.asset_size > 0:
            sz_mb = self.update_info.asset_size / (1024 * 1024)
            size_badge = QLabel(f"📦 Dung lượng: ~{sz_mb:.1f} MB")
            size_badge.setStyleSheet("color: #A5D6A7; font-size: 11px;")
            notes_title_row.addWidget(size_badge)

        notes_title_row.addStretch()
        nc_layout.addLayout(notes_title_row)

        self.notes_text = QTextEdit()
        self.notes_text.setReadOnly(True)
        self.notes_text.setPlainText(self.update_info.release_notes or "Cải tiến hiệu năng và cập nhật tính năng mới.")
        nc_layout.addWidget(self.notes_text)
        layout.addWidget(self.notes_card)

        # 3. KHU VỰC TIẾN TRÌNH TẢI & CÀI ĐẶT
        self.progress_frame = QFrame()
        self.progress_frame.setVisible(False)
        pf_layout = QVBoxLayout(self.progress_frame)
        pf_layout.setContentsMargins(0, 0, 0, 0)
        pf_layout.setSpacing(6)

        self.status_lbl = QLabel("Đang tải bản cập nhật...")
        self.status_lbl.setStyleSheet("color: #4ADE80; font-size: 12.5px; font-weight: 600;")
        pf_layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        pf_layout.addWidget(self.progress_bar)

        self.detail_lbl = QLabel("Đang chuẩn bị...")
        self.detail_lbl.setStyleSheet("color: #A5D6A7; font-size: 11.5px;")
        pf_layout.addWidget(self.detail_lbl)

        layout.addWidget(self.progress_frame)

        # 4. THANH NÚT ĐIỀU KHIỂN (ACTION BUTTONS)
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(10)

        self.btn_later = QPushButton("⏰ Để sau")
        self.btn_later.setProperty("class", "MilitarySecondaryBtn")
        self.btn_later.setCursor(Qt.PointingHandCursor)
        self.btn_later.clicked.connect(self.reject)
        self.btn_layout.addWidget(self.btn_later)

        self.btn_rollback = QPushButton("↺ Khôi phục sao lưu")
        self.btn_rollback.setProperty("class", "MilitaryGoldBtn")
        self.btn_rollback.setCursor(Qt.PointingHandCursor)
        self.btn_rollback.setToolTip("Khôi phục cấu hình, license và dự án từ bản sao lưu trước đó")
        self.btn_rollback.clicked.connect(self._on_rollback_clicked)
        self.btn_layout.addWidget(self.btn_rollback)

        self.btn_layout.addStretch()

        self.btn_cancel = QPushButton("🛑 Hủy tải")
        self.btn_cancel.setProperty("class", "CancelBtn")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._on_cancel_download)
        self.btn_layout.addWidget(self.btn_cancel)

        self.btn_update = QPushButton("🚀 Cập nhật ngay")
        self.btn_update.setProperty("class", "MilitaryPrimaryBtn")
        self.btn_update.setCursor(Qt.PointingHandCursor)
        self.btn_update.clicked.connect(self._start_download)
        self.btn_layout.addWidget(self.btn_update)

        layout.addLayout(self.btn_layout)

    def _set_state_ready(self):
        self.notes_card.setVisible(True)
        self.progress_frame.setVisible(False)
        self.btn_later.setVisible(True)
        self.btn_rollback.setVisible(True)
        self.btn_cancel.setVisible(False)
        self.btn_update.setVisible(True)
        self.btn_update.setText("🚀 Cập nhật ngay")
        self.btn_update.setEnabled(True)

    def _set_state_downloading(self):
        self.notes_card.setVisible(False)
        self.progress_frame.setVisible(True)
        self.btn_later.setVisible(False)
        self.btn_rollback.setVisible(False)
        self.btn_cancel.setVisible(True)
        self.btn_cancel.setEnabled(True)
        self.btn_update.setVisible(False)
        self.status_lbl.setText("Đang tải bản cập nhật...")
        self.progress_bar.setValue(0)
        self.detail_lbl.setText("Đang kết nối tới máy chủ GitHub...")

    def _set_state_installing(self):
        self.btn_cancel.setVisible(False)
        self.status_lbl.setText("🎉 Đã tải xong! Đang tiến hành cài đặt...")
        self.status_lbl.setStyleSheet("color: #4ADE80; font-size: 13px; font-weight: bold;")
        self.progress_bar.setValue(100)
        self.detail_lbl.setText("T-TTS sẽ tự động khởi động lại sau giây lát để hoàn tất nâng cấp.")

    def _set_state_error(self, err_msg: str):
        self.notes_card.setVisible(True)
        self.progress_frame.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.btn_later.setVisible(True)
        self.btn_rollback.setVisible(True)
        self.btn_later.setText("✕ Đóng")
        self.btn_update.setVisible(True)
        self.btn_update.setText("🔄 Thử lại")
        self.btn_update.setEnabled(True)
        QMessageBox.warning(
            self,
            "Cập Nhật Thất Bại",
            f"Không thể hoàn thành quá trình cập nhật:\n\n{err_msg}\n\n"
            "Phiên bản hiện tại vẫn đang hoạt động bình thường, không bị ảnh hưởng.",
        )

    def _start_download(self):
        # 1. Kiểm tra readiness
        readiness = self.updater.check_system_readiness(required_free_mb=200)
        if not readiness.get("ready", True):
            issues = "\n".join(f"• {i}" for i in readiness.get("issues", []))
            QMessageBox.critical(
                self,
                "Không Đủ Điều Kiện Cập Nhật",
                f"Hệ thống chưa đủ điều kiện để cài đặt bản cập nhật:\n\n{issues}\n\nVui lòng giải phóng bộ nhớ và thử lại.",
            )
            return

        self._set_state_downloading()
        self.download_worker = DownloadUpdateWorker(self.updater, self.update_info)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.status_changed.connect(lambda s: self.status_lbl.setText(s))
        self.download_worker.download_finished.connect(self._on_download_finished)
        self.download_worker.download_error.connect(self._on_download_error)
        self.download_worker.cancelled.connect(self._on_download_cancelled)
        self.download_worker.start()

    def _on_download_progress(self, pct: int, dl_mb: float, tot_mb: float, speed_mb_s: float):
        self.progress_bar.setValue(pct)
        if tot_mb > 0:
            self.detail_lbl.setText(
                f"Đã tải: <b>{dl_mb:.1f} MB</b> / <b>{tot_mb:.1f} MB</b> ({pct}%) • "
                f"Tốc độ: <b>{speed_mb_s:.2f} MB/s</b>"
            )
        else:
            self.detail_lbl.setText(f"Đã tải: <b>{dl_mb:.1f} MB</b> • Tốc độ: <b>{speed_mb_s:.2f} MB/s</b>")

    def _on_cancel_download(self):
        if self.download_worker:
            self.status_lbl.setText("Đang hủy tải...")
            self.btn_cancel.setEnabled(False)
            self.download_worker.cancel()

    def _on_download_cancelled(self):
        self._set_state_ready()
        self.detail_lbl.setText("Đã hủy tải bản cập nhật.")

    def _on_download_error(self, err: str):
        self._set_state_error(err)

    def _on_download_finished(self, fpath: Path):
        self.downloaded_file = fpath
        self._set_state_installing()
        QTimer.singleShot(1200, self._perform_install)

    def _perform_install(self):
        try:
            self.updater.install_and_restart(self.update_info, self.downloaded_file)
        except Exception as e:
            self._set_state_error(f"Lỗi khởi chạy bộ cài đặt: {e}")

    def _on_rollback_clicked(self):
        """Xử lý khôi phục bản sao lưu dữ liệu."""
        backups = self.updater.list_backups()
        if not backups:
            QMessageBox.information(
                self,
                "Khôi Phục Bản Sao Lưu",
                "Chưa tìm thấy bản sao lưu nào trong hệ thống.\nBản sao lưu sẽ được tự động tạo trước mỗi lần nâng cấp phần mềm.",
            )
            return

        latest_b = backups[0]
        reply = QMessageBox.question(
            self,
            "Xác Nhận Khôi Phục Dữ Liệu",
            f"Bạn có muốn khôi phục dữ liệu từ bản sao lưu gần nhất?\n\n"
            f"• Thời điểm sao lưu: {latest_b.get('timestamp')}\n"
            f"• Phiên bản nguồn: v{latest_b.get('current_version')}\n"
            f"• Số tệp cấu hình: {latest_b.get('file_count')}\n"
            f"• Số dự án đã lưu: {latest_b.get('project_count')}\n\n"
            f"Thao tác này sẽ khôi phục cấu hình, license và các dự án của bạn.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                res = self.updater.restore_backup(latest_b["file_path"])
                QMessageBox.information(
                    self,
                    "Khôi Phục Thành Công",
                    f"Đã khôi phục thành công:\n"
                    f"• {res.get('total_files', 0)} tệp dữ liệu\n"
                    f"• {res.get('total_projects', 0)} dự án\n\n"
                    f"Dữ liệu hệ thống đã trở về trạng thái ổn định.",
                )
            except Exception as e:
                QMessageBox.critical(self, "Lỗi Khôi Phục", f"Không thể khôi phục bản sao lưu:\n{e}")
