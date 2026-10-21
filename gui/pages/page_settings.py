"""gui/pages/page_settings.py — TAB 6: CÀI ĐẶT HỆ THỐNG & CẤU HÌNH (SETTINGS)
========================================================================
- Cấu hình thư mục lưu trữ mặc định.
- Quản lý và mở các thư mục hệ thống (Thư mục dữ liệu người dùng, Thư mục cài đặt).
- Thông số kỹ thuật chi tiết: Phiên bản VieNeu-TTS, ONNX Runtime CPU, int8 precision.
- Thông tin kỹ thuật offline (thay thế cho trang /docs và loại bỏ localhost).
"""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
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
    QScrollArea,
)

from backend.service import tts_service


class PageSettings(QWidget):
    """Trang Cài Đặt Hệ Thống."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        # 1. CẤU HÌNH ĐƯỜNG DẪN ĐẦU RA
        dir_card = QFrame()
        dir_card.setProperty("class", "CardFrame")
        dc_layout = QVBoxLayout(dir_card)
        dc_layout.setContentsMargins(16, 14, 16, 14)
        dc_layout.setSpacing(10)

        d_title = QLabel("📁 THƯ MỤC LƯU FILE ÂM THANH MẶC ĐỊNH")
        d_title.setProperty("class", "CardTitle")
        dc_layout.addWidget(d_title)

        d_desc = QLabel(
            "Mọi file âm thanh khi tạo từ văn bản hoặc xử lý hàng loạt sẽ được lưu vào thư mục này."
        )
        d_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        dc_layout.addWidget(d_desc)

        dir_row = QHBoxLayout()
        self.out_dir_edit = QLineEdit(str(tts_service.default_out_dir))
        self.out_dir_edit.setReadOnly(True)
        dir_row.addWidget(self.out_dir_edit)

        btn_browse_dir = QPushButton("📁 Chọn thư mục...")
        btn_browse_dir.setProperty("class", "SecondaryBtn")
        btn_browse_dir.setCursor(Qt.PointingHandCursor)
        btn_browse_dir.clicked.connect(self._change_default_dir)
        dir_row.addWidget(btn_browse_dir)

        btn_open_dir = QPushButton("📂 Mở thư mục")
        btn_open_dir.setProperty("class", "SecondaryBtn")
        btn_open_dir.setCursor(Qt.PointingHandCursor)
        btn_open_dir.clicked.connect(self._open_output_dir)
        dir_row.addWidget(btn_open_dir)
        dc_layout.addLayout(dir_row)
        layout.addWidget(dir_card)

        # 2. THÔNG TIN MÔ HÌNH & PHẦN CỨNG
        spec_card = QFrame()
        spec_card.setProperty("class", "CardFrame")
        sc_layout = QVBoxLayout(spec_card)
        sc_layout.setContentsMargins(16, 14, 16, 14)
        sc_layout.setSpacing(8)

        s_title = QLabel("⚙️ THÔNG SỐ KỸ THUẬT MÔ HÌNH & ENGINE TTS")
        s_title.setProperty("class", "CardTitle")
        sc_layout.addWidget(s_title)

        m_status = tts_service.get_model_status()
        spec_content = (
            f"• <b>Mô hình giọng nói:</b> VieNeu-TTS v3 Turbo (Bản quyền tác giả: Phạm Nguyễn Ngọc Bảo)<br>"
            f"• <b>Engine suy luận:</b> ONNX Runtime Lite CPU (chạy 100% offline nội bộ trên máy tính)<br>"
            f"• <b>Độ chính xác (Precision):</b> int8 quantized (tối ưu hóa tốc độ cao trên CPU Windows)<br>"
            f"• <b>Tần số lấy mẫu (Sample Rate):</b> 48,000 Hz (chuẩn âm thanh phát thanh chất lượng cao)<br>"
            f"• <b>Định dạng hỗ trợ:</b> WAV 16-bit PCM Mono / MP3 192kbps LAME<br>"
            f"• <b>Từ điển phát âm:</b> Tích hợp engine sea_g2p & VieNeu Pronunciation Dictionary<br>"
            f"• <b>Kiến trúc giao diện:</b> Desktop Native Windows (PySide6) — Bỏ hoàn toàn Localhost & Chrome App Mode"
        )
        spec_lbl = QLabel(spec_content)
        spec_lbl.setWordWrap(True)
        spec_lbl.setStyleSheet("color: #CBD5E1; font-size: 12px; line-height: 1.6;")
        sc_layout.addWidget(spec_lbl)
        layout.addWidget(spec_card)

        # 3. QUẢN LÝ DỮ LIỆU & THƯ MỤC ỨNG DỤNG
        data_card = QFrame()
        data_card.setProperty("class", "CardFrame")
        datac_layout = QVBoxLayout(data_card)
        datac_layout.setContentsMargins(16, 14, 16, 14)
        datac_layout.setSpacing(8)

        data_title = QLabel("🗄️ DỮ LIỆU ỨNG DỤNG & TÀI NGUYÊN OFFLINE")
        data_title.setProperty("class", "CardTitle")
        datac_layout.addWidget(data_title)

        data_desc = QLabel(
            "Cấu hình người dùng, danh sách giọng nhân bản và lịch sử được lưu trữ tại:"
        )
        data_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        datac_layout.addWidget(data_desc)

        data_btns = QHBoxLayout()
        btn_open_app_dir = QPushButton("📂 Mở Thư Mục Cài Đặt (App Dir)")
        btn_open_app_dir.setProperty("class", "SecondaryBtn")
        btn_open_app_dir.setCursor(Qt.PointingHandCursor)
        btn_open_app_dir.clicked.connect(lambda: self._open_folder(tts_service.app_dir))
        data_btns.addWidget(btn_open_app_dir)

        btn_open_data_dir = QPushButton("📂 Mở Thư Mục Dữ Liệu (Data Dir)")
        btn_open_data_dir.setProperty("class", "SecondaryBtn")
        btn_open_data_dir.setCursor(Qt.PointingHandCursor)
        btn_open_data_dir.clicked.connect(lambda: self._open_folder(tts_service.data_dir))
        data_btns.addWidget(btn_open_data_dir)

        data_btns.addStretch()
        datac_layout.addLayout(data_btns)
        layout.addWidget(data_card)

        # 4. THÔNG TIN PHIÊN BẢN
        ver_card = QFrame()
        ver_card.setProperty("class", "CardFrame")
        vc_layout = QVBoxLayout(ver_card)
        vc_layout.setContentsMargins(16, 14, 16, 14)
        vc_layout.setSpacing(6)

        ver_title = QLabel("T-TTS v1.0.1 — NATIVE WINDOWS DESKTOP")
        ver_title.setStyleSheet("color: #22D3EE; font-weight: bold; font-size: 14px;")
        vc_layout.addWidget(ver_title)

        ver_text = QLabel(
            "Phần mềm bản quyền offline hoạt động độc lập, không yêu cầu kết nối mạng Internet khi sử dụng.<br>"
            "Phiên bản 1.0.1 nâng cấp toàn diện: Modern Dark UI, loại bỏ localhost và trình duyệt, quản lý bản quyền đa thời hạn."
        )
        ver_text.setWordWrap(True)
        ver_text.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.5;")
        vc_layout.addWidget(ver_text)
        layout.addWidget(ver_card)

        layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _change_default_dir(self):
        new_dir = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu mặc định mới")
        if new_dir:
            tts_service.default_out_dir = Path(new_dir)
            self.out_dir_edit.setText(str(tts_service.default_out_dir))
            QMessageBox.information(self, "Đã cập nhật", f"Đã đổi thư mục lưu mặc định thành:\n{new_dir}")

    def _open_output_dir(self):
        self._open_folder(tts_service.default_out_dir)

    def _open_folder(self, folder_path: Path):
        p = Path(folder_path)
        p.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(p))
        else:
            subprocess.Popen(["xdg-open", str(p)])
