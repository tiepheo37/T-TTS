"""gui/dialogs/license_dialog.py — MÀN HÌNH KÍCH HOẠT BẢN QUYỀN (LIGHT STYLE)
=============================================================================
Phong cách thiết kế sáng, thân thiện, chuyên nghiệp theo yêu cầu Phần V.
Hỗ trợ sao chép Machine ID, nạp key từ file .lic/.txt hoặc dán chuỗi key trực tiếp.
Hiển thị rõ 5 gói bản quyền chính thức (1 Ngày, 7 Ngày, 30 Ngày, 6 Tháng, Vĩnh Viễn).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QFont, QColor
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QFrame,
    QApplication,
)

from ..styles import LIGHT_ACTIVATION_QSS
from backend.service import tts_service


class LicenseActivationDialog(QDialog):
    """Hộp thoại kích hoạt bản quyền T-TTS phong cách sáng (Friendly Light)."""

    license_activated = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ActivationDialog")
        self.setWindowTitle("Kích Hoạt Bản Quyền — T-TTS v1.0.1")
        self.setFixedSize(580, 680)
        self.setStyleSheet(LIGHT_ACTIVATION_QSS)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._build_ui()
        self._load_current_info()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        # Card chứa toàn bộ nội dung
        card = QFrame()
        card.setProperty("class", "LightCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)

        # Header: Icon & Tiêu đề
        header_layout = QHBoxLayout()
        header_icon = QLabel("🛡️")
        header_icon.setFont(QFont("Segoe UI Emoji", 28))
        header_layout.addWidget(header_icon)

        title_layout = QVBoxLayout()
        title_lbl = QLabel("KÍCH HOẠT BẢN QUYỀN")
        title_lbl.setObjectName("DialogTitle")
        sub_lbl = QLabel("T-TTS v1.0.1 — Chuyển Văn Bản Thành Giọng Nói Tiếng Việt")
        sub_lbl.setObjectName("DialogSubtitle")
        title_layout.addWidget(title_lbl)
        title_layout.addWidget(sub_lbl)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        card_layout.addLayout(header_layout)

        # Dải phân cách nhẹ
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setStyleSheet("color: #E2E8F0;")
        card_layout.addWidget(line1)

        # Hướng dẫn kích hoạt
        guide_lbl = QLabel(
            "Vui lòng gửi <b>Mã Máy</b> bên dưới cho nhà phát triển "
            "(<b>Đại úy Nguyễn Văn Tiệp</b>) để nhận mã key kích hoạt bản quyền."
        )
        guide_lbl.setWordWrap(True)
        guide_lbl.setStyleSheet("color: #475569; font-size: 13px; line-height: 1.4;")
        card_layout.addWidget(guide_lbl)

        # 1. KHU VỰC MÃ MÁY (MACHINE ID)
        mid_header = QLabel("MÃ MÁY TÍNH CỦA BẠN (MACHINE ID):")
        mid_header.setStyleSheet("color: #0F172A; font-weight: bold; font-size: 11px;")
        card_layout.addWidget(mid_header)

        mid_layout = QHBoxLayout()
        self.mid_edit = QLineEdit()
        self.mid_edit.setProperty("class", "LightInput")
        self.mid_edit.setReadOnly(True)
        self.mid_edit.setFont(QFont("Consolas", 12, QFont.Bold))
        self.mid_edit.setStyleSheet(
            "background-color: #F1F5F9; color: #1E293B; border: 1px solid #CBD5E1; "
            "padding: 8px 12px; border-radius: 6px;"
        )
        mid_layout.addWidget(self.mid_edit)

        self.btn_copy_mid = QPushButton("📋 Sao Chép")
        self.btn_copy_mid.setProperty("class", "LightSecondaryBtn")
        self.btn_copy_mid.setCursor(Qt.PointingHandCursor)
        self.btn_copy_mid.clicked.connect(self._copy_machine_id)
        mid_layout.addWidget(self.btn_copy_mid)
        card_layout.addLayout(mid_layout)

        # Bảng giới thiệu 5 gói bản quyền chính thức
        plans_box = QFrame()
        plans_box.setStyleSheet(
            "background-color: #F8FAFC; border: 1px dashed #CBD5E1; "
            "border-radius: 6px; padding: 10px;"
        )
        plans_layout = QVBoxLayout(plans_box)
        plans_layout.setContentsMargins(6, 6, 6, 6)
        plans_layout.setSpacing(4)

        plans_title = QLabel("CÁC GÓI BẢN QUYỀN HỖ TRỢ:")
        plans_title.setStyleSheet("color: #0F172A; font-weight: bold; font-size: 11px;")
        plans_layout.addWidget(plans_title)

        plans_desc = QLabel(
            "• <b>1 Ngày</b>: Dùng thử nhanh 24h từ lúc kích hoạt<br>"
            "• <b>7 Ngày</b>: Trải nghiệm tiêu chuẩn 168h<br>"
            "• <b>30 Ngày</b>: Dùng thử 1 tháng (720h)<br>"
            "• <b>6 Tháng</b>: Cấp phép nửa năm tính theo ngày lịch<br>"
            "• <b>Vĩnh Viễn</b>: Sử dụng trọn đời không giới hạn thời gian"
        )
        plans_desc.setStyleSheet("color: #475569; font-size: 12px;")
        plans_layout.addWidget(plans_desc)
        card_layout.addWidget(plans_box)

        # 2. KHU VỰC NHẬP KEY
        key_header_layout = QHBoxLayout()
        key_header = QLabel("NHẬP CHUỖI MÃ KEY HOẶC NẠP TỆP GIẤY PHÉP:")
        key_header.setStyleSheet("color: #0F172A; font-weight: bold; font-size: 11px;")
        key_header_layout.addWidget(key_header)
        key_header_layout.addStretch()

        self.btn_browse_lic = QPushButton("📁 Nạp File (.lic / .txt)...")
        self.btn_browse_lic.setProperty("class", "LightSecondaryBtn")
        self.btn_browse_lic.setCursor(Qt.PointingHandCursor)
        self.btn_browse_lic.clicked.connect(self._browse_license_file)
        key_header_layout.addWidget(self.btn_browse_lic)
        card_layout.addLayout(key_header_layout)

        self.key_edit = QTextEdit()
        self.key_edit.setProperty("class", "LightInput")
        self.key_edit.setPlaceholderText("Dán chuỗi mã key (TTTS-LIC1-...) vào đây...")
        self.key_edit.setFont(QFont("Consolas", 10))
        self.key_edit.setFixedHeight(75)
        card_layout.addWidget(self.key_edit)

        # Thông báo trạng thái kết quả
        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 500;")
        card_layout.addWidget(self.status_lbl)

        # 3. NÚT KÍCH HOẠT & ĐÓNG
        btn_layout = QHBoxLayout()
        self.btn_activate = QPushButton("🚀 KÍCH HOẠT BẢN QUYỀN")
        self.btn_activate.setProperty("class", "LightPrimaryBtn")
        self.btn_activate.setCursor(Qt.PointingHandCursor)
        self.btn_activate.clicked.connect(self._do_activate)
        btn_layout.addWidget(self.btn_activate)

        self.btn_close = QPushButton("Đóng")
        self.btn_close.setProperty("class", "LightSecondaryBtn")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_close)

        card_layout.addLayout(btn_layout)
        main_layout.addWidget(card)

    def _load_current_info(self):
        mid = tts_service.get_machine_id()
        self.mid_edit.setText(mid)
        info = tts_service.get_license_info()
        if info["is_active"]:
            self.status_lbl.setText(
                f"✅ Bản quyền hiện tại: <b>{info['plan']}</b> ({info['remaining_formatted']})"
            )
            self.status_lbl.setStyleSheet("color: #16A34A; font-size: 12px;")
        else:
            self.status_lbl.setText(f"ℹ️ {info['status_message']}")
            self.status_lbl.setStyleSheet("color: #DC2626; font-size: 12px;")

    def _copy_machine_id(self):
        mid = self.mid_edit.text().strip()
        if mid:
            clipboard = QApplication.clipboard()
            clipboard.setText(mid)
            QMessageBox.information(
                self,
                "Đã Sao Chép Mã Máy",
                f"Đã sao chép Mã Máy vào bộ nhớ đệm:\n\n{mid}\n\n"
                "Hãy gửi mã này cho nhà phát triển để nhận key kích hoạt.",
            )

    def _browse_license_file(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn tệp giấy phép T-TTS",
            "",
            "Giấy phép T-TTS (*.lic *.txt);;Tất cả tệp (*.*)",
        )
        if fpath:
            try:
                content = Path(fpath).read_text(encoding="utf-8").strip()
                self.key_edit.setPlainText(content)
            except Exception as e:
                QMessageBox.critical(self, "Lỗi đọc tệp", f"Không thể đọc tệp: {e}")

    def _do_activate(self):
        raw_key = self.key_edit.toPlainText().strip()
        if not raw_key:
            QMessageBox.warning(self, "Thiếu mã key", "Vui lòng nhập hoặc dán mã key bản quyền.")
            return

        ok, msg, info = tts_service.activate_license(raw_key)
        if ok:
            self.status_lbl.setText(f"🎉 {msg}")
            self.status_lbl.setStyleSheet("color: #16A34A; font-weight: bold; font-size: 13px;")
            self.license_activated.emit(info)
            QMessageBox.information(
                self,
                "Kích Hoạt Thành Công",
                f"{msg}\n\n"
                f"• Gói: {info.get('plan')}\n"
                f"• Thời hạn còn lại: {info.get('remaining_formatted')}\n"
                f"• Hết hạn vào: {info.get('expires_readable')}",
            )
            self.accept()
        else:
            self.status_lbl.setText(f"❌ {msg}")
            self.status_lbl.setStyleSheet("color: #DC2626; font-weight: bold; font-size: 13px;")
            QMessageBox.critical(self, "Kích Hoạt Thất Bại", msg)
