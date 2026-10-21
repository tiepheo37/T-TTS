"""gui/pages/page_about.py — TAB 7: BẢN QUYỀN & THÔNG TIN TÁC GIẢ QUÂN ĐỘI
========================================================================
Thiết kế trang trọng, làm nổi bật tác giả Đại úy Nguyễn Văn Tiệp:
- Phù hiệu chính thức của QUÂN ĐỘI NHÂN DÂN VIỆT NAM.
- Phân định rõ ràng:
  * Tác giả phát triển phần mềm T-TTS: Đại úy Nguyễn Văn Tiệp
  * Tác giả mô hình lõi VieNeu-TTS v3 Turbo: Phạm Nguyễn Ngọc Bảo
- Trạng thái bản quyền hiện tại, Machine ID và nút mở cửa sổ kích hoạt key.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QApplication,
    QMessageBox,
    QScrollArea,
)

from backend.service import tts_service


class PageAbout(QWidget):
    """Trang Bản Quyền, Giấy Phép & Thông Tin Tác Giả."""

    request_open_activation = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._build_ui()
        self.reload_license_info()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(16)

        # -------------------------------------------------------------
        # 1. THẺ TÔN VINH TÁC GIẢ VỚI LOGO QUÂN ĐỘI NHÂN DÂN VIỆT NAM
        # -------------------------------------------------------------
        author_card = QFrame()
        author_card.setProperty("class", "CardFrame")
        author_card.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #122415, stop:1 #1C3A20); "
            "border: 2px solid #FFD700; border-radius: 10px; }"
        )
        ac_main_layout = QHBoxLayout(author_card)
        ac_main_layout.setContentsMargins(20, 18, 20, 18)
        ac_main_layout.setSpacing(20)

        # Phù hiệu Quân đội Nhân dân Việt Nam bên trái
        lbl_logo = QLabel()
        lbl_logo.setAlignment(Qt.AlignCenter)
        logo_path = Path(__file__).resolve().parent.parent / "assets" / "logo_quan_doi.png"
        if not logo_path.exists():
            logo_path = Path.cwd() / "gui" / "assets" / "logo_quan_doi.png"
        if logo_path.exists():
            pm = QPixmap(str(logo_path)).scaled(85, 115, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_logo.setPixmap(pm)
        else:
            lbl_logo.setText("⭐")
            lbl_logo.setStyleSheet("font-size: 54px; color: #FFD700;")
        ac_main_layout.addWidget(lbl_logo)

        # Khối nội dung thông tin tác giả
        ac_layout = QVBoxLayout()
        ac_layout.setSpacing(6)

        # Header Huy hiệu
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)

        app_tag = QLabel("T-TTS v1.0.1")
        app_tag.setStyleSheet(
            "background-color: #C92A2A; color: #FFD700; font-weight: 800; "
            "padding: 4px 12px; border-radius: 4px; font-size: 13px; border: 1px solid #FFD700;"
        )
        badge_row.addWidget(app_tag)

        army_tag = QLabel("QUÂN ĐỘI NHÂN DÂN VIỆT NAM")
        army_tag.setStyleSheet(
            "background-color: rgba(234, 179, 8, 0.15); color: #FFD700; "
            "border: 1px solid #EAB308; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;"
        )
        badge_row.addWidget(army_tag)

        offline_tag = QLabel("OFFLINE DESKTOP")
        offline_tag.setStyleSheet(
            "background-color: rgba(34, 197, 94, 0.15); color: #4ADE80; "
            "border: 1px solid #22C55E; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;"
        )
        badge_row.addWidget(offline_tag)
        badge_row.addStretch()
        ac_layout.addLayout(badge_row)

        lbl_intro = QLabel("PHẦN MỀM CHUYỂN VĂN BẢN THÀNH GIỌNG NÓI TIẾNG VIỆT CHUYÊN NGHIỆP")
        lbl_intro.setStyleSheet("color: #E2ECE1; font-size: 12px; font-weight: 600; letter-spacing: 0.5px;")
        ac_layout.addWidget(lbl_intro)

        # TÁC GIẢ CHÍNH
        author_title_lbl = QLabel("TÁC GIẢ & KIẾN TRÚC SƯ PHẦN MỀM:")
        author_title_lbl.setStyleSheet("color: #FFD700; font-size: 12px; font-weight: bold; letter-spacing: 1px; margin-top: 4px;")
        ac_layout.addWidget(author_title_lbl)

        author_name_lbl = QLabel("Đại úy Nguyễn Văn Tiệp")
        author_name_lbl.setStyleSheet(
            "color: #FFFFFF; font-size: 26px; font-weight: 800; "
            "letter-spacing: 0.5px; padding-bottom: 2px;"
        )
        ac_layout.addWidget(author_name_lbl)

        lbl_rank = QLabel("Quân hàm: Đại úy · Quân đội nhân dân Việt Nam")
        lbl_rank.setStyleSheet("color: #FFD700; font-size: 12px; font-weight: 600;")
        ac_layout.addWidget(lbl_rank)

        lbl_desc = QLabel(
            "Phần mềm được phát triển phục vụ công tác chuyển đổi văn bản thành giọng nói tiếng Việt chất lượng cao, "
            "hoạt động 100% offline, tích hợp công nghệ suy luận ONNX Runtime CPU tối ưu cho máy tính cá nhân."
        )
        lbl_desc.setStyleSheet("color: #A3BCA0; font-size: 12px; line-height: 1.4;")
        lbl_desc.setWordWrap(True)
        ac_layout.addWidget(lbl_desc)

        ac_main_layout.addLayout(ac_layout, 1)
        layout.addWidget(author_card)

        # -------------------------------------------------------------
        # 2. GHI NHẬN TÁC GIẢ MÔ HÌNH VIE-NEU TTS
        # -------------------------------------------------------------
        model_card = QFrame()
        model_card.setProperty("class", "CardFrame")
        mc_layout = QVBoxLayout(model_card)
        mc_layout.setContentsMargins(16, 12, 16, 12)
        mc_layout.setSpacing(6)

        mc_title = QLabel("🔬 CÔNG NGHỆ SUY LUẬN & MÔ HÌNH ÂM THANH LÕI")
        mc_title.setProperty("class", "CardTitle")
        mc_layout.addWidget(mc_title)

        lbl_model_credit = QLabel(
            "Mô hình giọng nói: <b>VieNeu-TTS v3 Turbo</b> do tác giả <b>Phạm Nguyễn Ngọc Bảo</b> phát triển.<br>"
            "Kiến trúc suy luận: <i>ONNX Runtime CPU INT8</i> đa luồng (100% Offline, độc lập, không yêu cầu card đồ họa rời GPU)."
        )
        lbl_model_credit.setStyleSheet("color: #E2ECE1; font-size: 12px; line-height: 1.4;")
        lbl_model_credit.setWordWrap(True)
        mc_layout.addWidget(lbl_model_credit)

        layout.addWidget(model_card)

        # -------------------------------------------------------------
        # 3. THẺ TRẠNG THÁI BẢN QUYỀN & MÃ MÁY (MACHINE ID)
        # -------------------------------------------------------------
        lic_card = QFrame()
        lic_card.setProperty("class", "CardFrame")
        lc_layout = QVBoxLayout(lic_card)
        lc_layout.setContentsMargins(16, 14, 16, 14)
        lc_layout.setSpacing(10)

        lc_title_row = QHBoxLayout()
        lc_title = QLabel("🛡️ TRẠNG THÁI BẢN QUYỀN MÁY TÍNH HIỆN TẠI")
        lc_title.setProperty("class", "CardTitle")
        lc_title_row.addWidget(lc_title)
        lc_title_row.addStretch()

        self.btn_open_act = QPushButton("🔑 Kích Hoạt Bản Quyền Mới")
        self.btn_open_act.setProperty("class", "GoldBtn")
        self.btn_open_act.clicked.connect(self._on_activate_clicked)
        lc_title_row.addWidget(self.btn_open_act)
        lc_layout.addLayout(lc_title_row)

        # Machine ID Box
        mid_box = QHBoxLayout()
        lbl_mid_title = QLabel("Mã Định Danh Máy (Machine ID):")
        lbl_mid_title.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 12px;")
        mid_box.addWidget(lbl_mid_title)

        self.lbl_mid_val = QLabel("Đang tải...")
        self.lbl_mid_val.setStyleSheet(
            "background-color: #111F13; color: #4ADE80; font-family: 'Consolas', monospace; "
            "font-size: 13px; font-weight: bold; padding: 6px 12px; border-radius: 6px; border: 1px solid #2F4D32;"
        )
        self.lbl_mid_val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        mid_box.addWidget(self.lbl_mid_val)

        btn_copy_mid = QPushButton("📋 Sao chép")
        btn_copy_mid.setProperty("class", "SecondaryBtn")
        btn_copy_mid.clicked.connect(self._copy_machine_id)
        mid_box.addWidget(btn_copy_mid)

        mid_box.addStretch()
        lc_layout.addLayout(mid_box)

        # Thông tin chi tiết bản quyền
        self.lbl_lic_status = QLabel("Trạng thái: Đang kiểm tra...")
        self.lbl_lic_status.setStyleSheet("color: #E2ECE1; font-size: 13px; font-weight: 500;")
        lc_layout.addWidget(self.lbl_lic_status)

        self.lbl_lic_detail = QLabel("")
        self.lbl_lic_detail.setStyleSheet("color: #9EB39B; font-size: 12px;")
        lc_layout.addWidget(self.lbl_lic_detail)

        layout.addWidget(lic_card)

        # -------------------------------------------------------------
        # 4. CHÍNH SÁCH 5 GÓI BẢN QUYỀN
        # -------------------------------------------------------------
        policy_card = QFrame()
        policy_card.setProperty("class", "CardFrame")
        pc_layout = QVBoxLayout(policy_card)
        pc_layout.setContentsMargins(16, 12, 16, 12)
        pc_layout.setSpacing(6)

        pc_title = QLabel("📜 5 GÓI BẢN QUYỀN CẤP PHÉP HỆ THỐNG")
        pc_title.setProperty("class", "CardTitle")
        pc_layout.addWidget(pc_title)

        plans_text = (
            "• <b>1 Ngày (KEY-1D)</b>: Gói dùng thử nhanh trong 24 giờ kể từ khi kích hoạt.<br>"
            "• <b>7 Ngày (KEY-7D)</b>: Gói trải nghiệm 1 tuần (168 giờ).<br>"
            "• <b>30 Ngày (KEY-30D)</b>: Gói bản quyền 1 tháng tiêu chuẩn.<br>"
            "• <b>6 Tháng (KEY-6M)</b>: Cấp phép nửa năm, tự động tính hạn theo lịch ngày thực tế.<br>"
            "• <b>Vĩnh Viễn (KEY-PERM)</b>: Bản quyền trọn đời, không bao giờ hết hạn."
        )
        lbl_plans = QLabel(plans_text)
        lbl_plans.setStyleSheet("color: #E2ECE1; font-size: 12px; line-height: 1.4;")
        pc_layout.addWidget(lbl_plans)

        layout.addWidget(policy_card)
        layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def reload_license_info(self):
        info = tts_service.get_license_info()
        mid = info.get("machine_id", "KHÔNG XÁC ĐỊNH")
        self.lbl_mid_val.setText(mid)

        status = info.get("status", "unknown")
        plan = info.get("plan", "none").upper()
        days_left = info.get("days_left", 0)
        expires_at = info.get("expires_at")

        if status == "active":
            if plan == "PERMANENT":
                self.lbl_lic_status.setText("Trạng thái: <b style='color:#FFD700;'>ĐÃ KÍCH HOẠT VĨNH VIỄN (TRỌN ĐỜI)</b>")
                self.lbl_lic_detail.setText("Bản quyền trọn đời không giới hạn thời gian sử dụng.")
            else:
                self.lbl_lic_status.setText(
                    f"Trạng thái: <b style='color:#4ADE80;'>ĐANG HOẠT ĐỘNG (Gói {plan})</b> — Còn {days_left} ngày"
                )
                self.lbl_lic_detail.setText(f"Hạn sử dụng đến: {expires_at or 'Không giới hạn'}")
        elif status == "trial":
            self.lbl_lic_status.setText(
                f"Trạng thái: <b style='color:#FDE047;'>DÙNG THỬ (TRIAL)</b> — Còn {days_left} ngày"
            )
            self.lbl_lic_detail.setText(f"Hạn dùng thử: {expires_at or 'N/A'}")
        elif status == "expired":
            self.lbl_lic_status.setText("Trạng thái: <b style='color:#F87171;'>BẢN QUYỀN ĐÃ HẾT HẠN</b>")
            self.lbl_lic_detail.setText("Vui lòng kích hoạt key mới để tiếp tục sử dụng phần mềm.")
        else:
            self.lbl_lic_status.setText("Trạng thái: <b style='color:#F87171;'>CHƯA KÍCH HOẠT</b>")
            self.lbl_lic_detail.setText("Nhấn nút 'Kích Hoạt Bản Quyền Mới' ở trên để nhập key.")

    def _copy_machine_id(self):
        mid = self.lbl_mid_val.text()
        if mid and mid != "Đang tải...":
            QApplication.clipboard().setText(mid)
            QMessageBox.information(self, "Đã Sao Chép", f"Đã sao chép Machine ID vào bộ nhớ tạm:\n{mid}")

    def _on_activate_clicked(self):
        self.request_open_activation.emit()
