"""gui/dialog_update.py — HỘP THOẠI CẬP NHẬT PHẦN MỀM T-TTS (DARK NAVY BLUE)
=============================================================================
Thiết kế chuyên nghiệp theo phong cách Dark Navy Blue & Blue Accent:
- Nền xanh thẫm hiện đại (#0B192C / #0F172A).
- Điểm nhấn xanh dương công nghệ (#2563EB / #3B82F6).
- Thông tin phiên bản rõ ràng, hiển thị mục 'CÓ GÌ MỚI?' (Release Notes).
- Thanh tiến trình tải thời gian thực (phần trăm, dung lượng đã tải, tốc độ MB/s).
- Nút Hủy tải, Thử lại, và tự động khởi động lại sau khi cài đặt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
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


DARK_NAVY_UPDATE_QSS = """
QDialog#UpdateDialog {
    background-color: #0B192C;
    border: 1.5px solid #1E3A8A;
    border-radius: 12px;
}

QLabel {
    color: #F8FAFC;
    font-family: "Segoe UI", Arial, sans-serif;
    border: none;
    background: transparent;
}

QFrame.UpdateCard {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 8px;
}

QTextEdit {
    background-color: #0F172A;
    color: #E2E8F0;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 10px;
    font-size: 13px;
    line-height: 1.5;
}

QProgressBar {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    color: #FFFFFF;
    font-weight: bold;
    font-size: 12px;
    min-height: 20px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563EB, stop:1 #38BDF8);
    border-radius: 5px;
}

QPushButton.BluePrimaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1D4ED8, stop:1 #2563EB);
    color: #FFFFFF;
    font-weight: bold;
    font-size: 13px;
    border: 1px solid #60A5FA;
    border-radius: 6px;
    padding: 9px 20px;
    min-height: 18px;
}

QPushButton.BluePrimaryBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563EB, stop:1 #3B82F6);
    border-color: #93C5FD;
}

QPushButton.BlueSecondaryBtn {
    background-color: #1E293B;
    color: #E2E8F0;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    font-size: 13px;
    min-height: 18px;
}

QPushButton.BlueSecondaryBtn:hover {
    background-color: #334155;
    border-color: #94A3B8;
    color: #FFFFFF;
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


class UpdateDialog(QDialog):
    """Cửa sổ thông báo và cài đặt bản cập nhật T-TTS mới."""

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
        self.setFixedSize(580, 480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(DARK_NAVY_UPDATE_QSS)

        self._build_ui()
        self._set_state_ready()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        # 1. HEADER BAR
        header_row = QHBoxLayout()
        header_icon = QLabel("🚀")
        header_icon.setFont(QFont("Segoe UI Emoji", 26))
        header_row.addWidget(header_icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        self.title_lbl = QLabel("Đã có phiên bản T-TTS mới")
        self.title_lbl.setStyleSheet("font-size: 17px; font-weight: 800; color: #60A5FA;")
        title_box.addWidget(self.title_lbl)

        self.subtitle_lbl = QLabel(
            f"Bạn đang sử dụng phiên bản <b>{self.update_info.current_version}</b>.<br>"
            f"Đã có phiên bản <b>{self.update_info.latest_version}</b> mới. Cập nhật để sử dụng những cải tiến mới nhất."
        )
        self.subtitle_lbl.setStyleSheet("font-size: 12.5px; color: #CBD5E1; line-height: 1.4;")
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
        notes_title = QLabel("📌 CÓ GÌ MỚI TRONG BẢN NÀY?")
        notes_title.setStyleSheet("font-size: 12px; font-weight: 800; color: #93C5FD; letter-spacing: 0.5px;")
        notes_title_row.addWidget(notes_title)

        if self.update_info.published_at:
            pub_date = str(self.update_info.published_at).split("T")[0]
            date_badge = QLabel(f"📅 Ngày phát hành: {pub_date}")
            date_badge.setStyleSheet("color: #94A3B8; font-size: 11px;")
            notes_title_row.addWidget(date_badge)

        if self.update_info.asset_size > 0:
            sz_mb = self.update_info.asset_size / (1024 * 1024)
            size_badge = QLabel(f"📦 Dung lượng: ~{sz_mb:.1f} MB")
            size_badge.setStyleSheet("color: #94A3B8; font-size: 11px;")
            notes_title_row.addWidget(size_badge)

        notes_title_row.addStretch()
        nc_layout.addLayout(notes_title_row)

        self.notes_text = QTextEdit()
        self.notes_text.setReadOnly(True)
        self.notes_text.setPlainText(self.update_info.release_notes or "Cải tiến hiệu năng và sửa lỗi.")
        nc_layout.addWidget(self.notes_text)
        layout.addWidget(self.notes_card)

        # 3. KHU VỰC TIẾN TRÌNH TẢI & CÀI ĐẶT
        self.progress_frame = QFrame()
        self.progress_frame.setVisible(False)
        pf_layout = QVBoxLayout(self.progress_frame)
        pf_layout.setContentsMargins(0, 0, 0, 0)
        pf_layout.setSpacing(6)

        self.status_lbl = QLabel("Đang tải bản cập nhật...")
        self.status_lbl.setStyleSheet("color: #38BDF8; font-size: 12.5px; font-weight: 600;")
        pf_layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        pf_layout.addWidget(self.progress_bar)

        self.detail_lbl = QLabel("Đang chuẩn bị...")
        self.detail_lbl.setStyleSheet("color: #94A3B8; font-size: 11.5px;")
        pf_layout.addWidget(self.detail_lbl)

        layout.addWidget(self.progress_frame)

        # 4. THANH NÚT ĐIỀU KHIỂN (ACTION BUTTONS)
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(10)

        self.btn_later = QPushButton("⏰ Để sau")
        self.btn_later.setProperty("class", "BlueSecondaryBtn")
        self.btn_later.setCursor(Qt.PointingHandCursor)
        self.btn_later.clicked.connect(self.reject)
        self.btn_layout.addWidget(self.btn_later)

        self.btn_layout.addStretch()

        self.btn_cancel = QPushButton("🛑 Hủy tải")
        self.btn_cancel.setProperty("class", "CancelBtn")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._on_cancel_download)
        self.btn_layout.addWidget(self.btn_cancel)

        self.btn_update = QPushButton("🚀 Cập nhật ngay")
        self.btn_update.setProperty("class", "BluePrimaryBtn")
        self.btn_update.setCursor(Qt.PointingHandCursor)
        self.btn_update.clicked.connect(self._start_download)
        self.btn_layout.addWidget(self.btn_update)

        layout.addLayout(self.btn_layout)

    def _set_state_ready(self):
        self.notes_card.setVisible(True)
        self.progress_frame.setVisible(False)
        self.btn_later.setVisible(True)
        self.btn_cancel.setVisible(False)
        self.btn_update.setVisible(True)
        self.btn_update.setText("🚀 Cập nhật ngay")
        self.btn_update.setEnabled(True)

    def _set_state_downloading(self):
        self.notes_card.setVisible(False)
        self.progress_frame.setVisible(True)
        self.btn_later.setVisible(False)
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
        # Gọi cài đặt sau 1.2s để giao diện hiển thị thông báo mượt mà
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1200, self._perform_install)

    def _perform_install(self):
        try:
            self.updater.install_and_restart(self.update_info, self.downloaded_file)
        except Exception as e:
            self._set_state_error(f"Lỗi khởi chạy bộ cài đặt: {e}")
