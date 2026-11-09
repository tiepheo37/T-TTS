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
import time
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
from backend.version import APP_VERSION, APP_NAME, APP_DISPLAY_NAME, APP_AUTHOR, DEFAULT_GITHUB_REPO


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

        # BANNER NỔI BẬT: TÊN PHẦN MỀM · TÁC GIẢ · CÔNG NGHỆ
        banner_card = QFrame()
        banner_card.setProperty("class", "CardFrame")
        banner_card.setStyleSheet(
            "#SettingsBanner { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1E2D22, stop:1 #152219); border: 1px solid #3B533E; border-radius: 8px; }"
        )
        banner_card.setObjectName("SettingsBanner")
        bn_layout = QVBoxLayout(banner_card)
        bn_layout.setContentsMargins(18, 14, 18, 14)
        bn_layout.setSpacing(6)

        lbl_app_name = QLabel(f"🇻🇳 {APP_NAME} v{APP_VERSION} — HỆ THỐNG TRỢ LÝ GIỌNG NÓI QUÂN ĐỘI")
        lbl_app_name.setStyleSheet("color: #FFD700; font-size: 16px; font-weight: 800; letter-spacing: 0.5px; border: none;")
        bn_layout.addWidget(lbl_app_name)

        lbl_author_info = QLabel("<b>TÁC GIẢ:</b> <span style='color: #FFFFFF; font-size: 15px; font-weight: 800;'>Nguyễn Văn Tiệp</span>")
        lbl_author_info.setStyleSheet("color: #E2E8F0; font-size: 13px; border: none;")
        bn_layout.addWidget(lbl_author_info)

        lbl_tech_info = QLabel(
            "<b>CÔNG NGHỆ CỐT LÕI:</b> "
            "<span style='color: #22D3EE;'>VieNeu-TTS v3 Turbo ONNX Lite CPU</span> · "
            "<span style='color: #86EFAC;'>Quantized INT8</span> · "
            "<span style='color: #FCD34D;'>Âm thanh phát thanh 48,000 Hz</span> · "
            "<span style='color: #93C5FD;'>100% Native Desktop (0% Localhost, 0% Trình duyệt)</span>"
        )
        lbl_tech_info.setStyleSheet("color: #CBD5E1; font-size: 12px; border: none; line-height: 1.4;")
        bn_layout.addWidget(lbl_tech_info)

        layout.addWidget(banner_card)

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

        # 4. CẬP NHẬT PHẦN MỀM TỰ ĐỘNG (AUTO UPDATE)
        update_card = QFrame()
        update_card.setProperty("class", "CardFrame")
        uc_layout = QVBoxLayout(update_card)
        uc_layout.setContentsMargins(16, 14, 16, 14)
        uc_layout.setSpacing(10)

        uc_title = QLabel("🔄 CẬP NHẬT PHẦN MỀM TỰ ĐỘNG (AUTO UPDATE)")
        uc_title.setProperty("class", "CardTitle")
        uc_layout.addWidget(uc_title)

        uc_desc = QLabel(
            "Hệ thống tự động kiểm tra và nâng cấp phiên bản mới nhất từ GitHub Releases qua VelopPack & HTTPS an toàn."
        )
        uc_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        uc_layout.addWidget(uc_desc)

        from backend.updater import UpdateManager
        self.update_manager = UpdateManager(tts_service.data_dir)
        cfg = self.update_manager.config

        ver_info_row = QHBoxLayout()
        lbl_cur_ver = QLabel(f"• Phiên bản hiện tại: <b style='color: #FFD700;'>v{APP_VERSION}</b>")
        lbl_cur_ver.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        ver_info_row.addWidget(lbl_cur_ver)

        lbl_chan = QLabel(f"• Kênh phát hành: <b style='color: #22D3EE;'>{cfg.get('channel', 'stable').capitalize()}</b>")
        lbl_chan.setStyleSheet("color: #CBD5E1; font-size: 13px;")
        ver_info_row.addWidget(lbl_chan)

        ver_info_row.addStretch()
        uc_layout.addLayout(ver_info_row)

        repo_row = QHBoxLayout()
        repo_lbl = QLabel("• Nguồn máy chủ cập nhật (GitHub Releases):")
        repo_lbl.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        repo_row.addWidget(repo_lbl)

        self.repo_edit = QLineEdit(cfg.get("github_repo", DEFAULT_GITHUB_REPO))
        self.repo_edit.setPlaceholderText("VD: tiepheo37/T-TTS")
        self.repo_edit.setMaximumWidth(260)
        repo_row.addWidget(self.repo_edit)

        btn_save_repo = QPushButton("💾 Lưu kho")
        btn_save_repo.setProperty("class", "SecondaryBtn")
        btn_save_repo.setCursor(Qt.PointingHandCursor)
        btn_save_repo.clicked.connect(self._save_repo_config)
        repo_row.addWidget(btn_save_repo)

        repo_row.addStretch()
        uc_layout.addLayout(repo_row)

        from PySide6.QtWidgets import QCheckBox
        self.chk_auto_update = QCheckBox("Tự động kiểm tra bản cập nhật mới khi khởi động T-TTS")
        self.chk_auto_update.setChecked(cfg.get("auto_check_on_startup", True))
        self.chk_auto_update.toggled.connect(self._on_toggle_auto_update)
        uc_layout.addWidget(self.chk_auto_update)

        last_time = cfg.get("last_checked_time") or "Chưa kiểm tra"
        self.lbl_last_check = QLabel(f"Thời gian kiểm tra gần nhất: {last_time}")
        self.lbl_last_check.setStyleSheet("color: #64748B; font-size: 11.5px;")
        uc_layout.addWidget(self.lbl_last_check)

        btn_row = QHBoxLayout()
        self.btn_check_update = QPushButton("🔍 Kiểm tra cập nhật ngay")
        self.btn_check_update.setProperty("class", "GoldBtn")
        self.btn_check_update.setCursor(Qt.PointingHandCursor)
        self.btn_check_update.clicked.connect(self._check_update_now)
        btn_row.addWidget(self.btn_check_update)
        btn_row.addStretch()
        uc_layout.addLayout(btn_row)

        layout.addWidget(update_card)

        # 5. THÔNG TIN PHIÊN BẢN
        ver_card = QFrame()
        ver_card.setProperty("class", "CardFrame")
        vc_layout = QVBoxLayout(ver_card)
        vc_layout.setContentsMargins(16, 14, 16, 14)
        vc_layout.setSpacing(6)

        ver_title = QLabel(f"{APP_NAME} v{APP_VERSION} — HỆ THỐNG TRỢ LÝ GIỌNG NÓI QUÂN ĐỘI")
        ver_title.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 14px; border: none;")
        vc_layout.addWidget(ver_title)

        ver_text = QLabel(
            "• <b>Tác giả:</b> <span style='color: #FFFFFF; font-weight: bold;'>Nguyễn Văn Tiệp</span><br>"
            "• <b>Công nghệ tổng hợp:</b> VieNeu-TTS v3 Turbo ONNX Runtime Lite CPU (Quantized int8)<br>"
            "• <b>Kiến trúc phần mềm:</b> Native Desktop Windows (PySide6) — 100% Offline, không phụ thuộc localhost/trình duyệt<br>"
            "• <b>Chất lượng âm thanh:</b> Chuẩn phát thanh Studio 48,000 Hz 16-bit Mono / MP3 192kbps<br>"
            "• <b>Hệ thống bản quyền:</b> Mật mã bất đối xứng Ed25519 offline 6 gói thời hạn (1D, 7D, 30D, 6M, 1Y, Lifetime)"
        )
        ver_text.setWordWrap(True)
        ver_text.setStyleSheet("color: #CBD5E1; font-size: 12px; line-height: 1.6; border: none;")
        vc_layout.addWidget(ver_text)
        layout.addWidget(ver_card)

        layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _on_toggle_auto_update(self, checked: bool):
        from backend.version import save_update_config
        self.update_manager.config["auto_check_on_startup"] = checked
        save_update_config(tts_service.data_dir, self.update_manager.config)

    def _save_repo_config(self):
        new_repo = self.repo_edit.text().strip()
        if not new_repo or "/" not in new_repo:
            QMessageBox.warning(
                self,
                "Sai định dạng",
                "Vui lòng nhập đúng định dạng tài khoản/kho GitHub.\nVí dụ: 'TenTaiKhoan/T-TTS'",
            )
            return
        from backend.version import save_update_config
        self.update_manager.config["github_repo"] = new_repo
        self.update_manager.repo = new_repo
        save_update_config(tts_service.data_dir, self.update_manager.config)
        QMessageBox.information(
            self,
            "Đã cập nhật kho",
            f"Đã lưu kho cập nhật GitHub thành công:\n{new_repo}",
        )

    def _check_update_now(self):
        from backend.updater import CheckUpdateWorker
        self.btn_check_update.setEnabled(False)
        self.btn_check_update.setText("⏳ Đang kiểm tra cập nhật...")

        self.check_worker = CheckUpdateWorker(tts_service.data_dir)
        self.check_worker.check_finished.connect(self._on_manual_check_finished)
        self.check_worker.check_error.connect(self._on_manual_check_error)
        self.check_worker.start()

    def _on_manual_check_finished(self, info):
        self.btn_check_update.setEnabled(True)
        self.btn_check_update.setText("🔍 Kiểm tra cập nhật ngay")
        last_time = time.strftime("%Y-%m-%d %H:%M:%S")
        self.lbl_last_check.setText(f"Thời gian kiểm tra gần nhất: {last_time}")

        if info and getattr(info, "available", False):
            from gui.dialog_update import UpdateDialog
            dlg = UpdateDialog(self.update_manager, info, self)
            dlg.exec()
        elif info and getattr(info, "error_msg", ""):
            QMessageBox.warning(
                self,
                "Không Thể Kiểm Tra Cập Nhật",
                f"Đã xảy ra lỗi khi kết nối tới máy chủ cập nhật:\n\n{info.error_msg}\n\n"
                "Vui lòng kiểm tra lại kết nối mạng Internet.",
            )
        else:
            QMessageBox.information(
                self,
                "T-TTS Đã Ở Bản Mới Nhất",
                f"🎉 Bạn đang sử dụng phiên bản T-TTS mới nhất (v{APP_VERSION})!\n\n"
                "Hiện chưa có bản cập nhật nào mới hơn trên kênh phát hành.",
            )

    def _on_manual_check_error(self, err: str):
        self.btn_check_update.setEnabled(True)
        self.btn_check_update.setText("🔍 Kiểm tra cập nhật ngay")
        QMessageBox.warning(
            self,
            "Lỗi Kết Nối",
            f"Không thể kiểm tra bản cập nhật mới:\n\n{err}",
        )

    def _change_default_dir(self):
        new_dir = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu mặc định mới", str(tts_service.default_out_dir))
        if new_dir:
            tts_service.set_default_out_dir(new_dir)
            self.out_dir_edit.setText(str(tts_service.default_out_dir))
            QMessageBox.information(self, "Đã cập nhật", f"Đã lưu vĩnh viễn thư mục lưu mặc định thành:\n{new_dir}")

    def _open_output_dir(self):
        self._open_folder(tts_service.default_out_dir)

    def _open_folder(self, folder_path: Path):
        p = Path(folder_path)
        p.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(p))
        else:
            subprocess.Popen(["xdg-open", str(p)])
