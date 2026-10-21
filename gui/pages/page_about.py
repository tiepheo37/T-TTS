"""gui/pages/page_about.py — TAB 7: BẢN QUYỀN & GIẤY PHÉP (ABOUT & LICENSE)
========================================================================
Thiết kế trang trọng, làm nổi bật tác giả theo yêu cầu Phần IX:
- THÔNG TIN BẮT BUỘC:
  * T-TTS v1.0.1
  * PHÁT TRIỂN: Đại úy Nguyễn Văn Tiệp (Điểm nhấn chính, chữ lớn, phân cấp thị giác rõ ràng).
  * Mô tả: "Phần mềm chuyển văn bản thành giọng nói tiếng Việt, tích hợp mô hình VieNeu-TTS v3 Turbo sử dụng ONNX Runtime CPU."
  * Thông tin mô hình: "Mô hình VieNeu-TTS do Phạm Nguyễn Ngọc Bảo phát triển."
- Phân biệt rõ tác giả phần mềm T-TTS với tác giả mô hình giọng nói VieNeu-TTS.
- Hiển thị tình trạng bản quyền hiện tại của máy tính, Machine ID và nút mở cửa sổ kích hoạt key mới.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
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
        # 1. THẺ TÁC GIẢ PHÁT TRIỂN (AUTHOR HIGHLIGHT CARD)
        # -------------------------------------------------------------
        author_card = QFrame()
        author_card.setProperty("class", "CardFrame")
        author_card.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #101827, stop:1 #172554);"
            "border: 2px solid #1687FF; border-radius: 10px; padding: 18px;"
        )
        ac_layout = QVBoxLayout(author_card)
        ac_layout.setContentsMargins(18, 16, 18, 16)
        ac_layout.setSpacing(8)

        # Header Huy hiệu & Tên Ứng dụng
        badge_row = QHBoxLayout()
        app_tag = QLabel("T-TTS v1.0.1")
        app_tag.setStyleSheet(
            "background-color: #1687FF; color: #FFFFFF; font-weight: bold; "
            "padding: 4px 12px; border-radius: 4px; font-size: 13px;"
        )
        badge_row.addWidget(app_tag)

        offline_tag = QLabel("OFFLINE DESKTOP")
        offline_tag.setStyleSheet(
            "background-color: rgba(34, 211, 238, 0.15); color: #22D3EE; "
            "border: 1px solid #22D3EE; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;"
        )
        badge_row.addWidget(offline_tag)
        badge_row.addStretch()
        ac_layout.addLayout(badge_row)

        lbl_intro = QLabel("PHẦN MỀM CHUYỂN VĂN BẢN THÀNH GIỌNG NÓI TIẾNG VIỆT")
        lbl_intro.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 600; letter-spacing: 0.5px;")
        ac_layout.addWidget(lbl_intro)

        # ĐIỂM NHẤN CHÍNH: TÁC GIẢ PHÁT TRIỂN
        author_title_lbl = QLabel("PHÁT TRIỂN BỞI")
        author_title_lbl.setStyleSheet("color: #F59E0B; font-size: 12px; font-weight: bold; letter-spacing: 1px; margin-top: 6px;")
        ac_layout.addWidget(author_title_lbl)

        author_name_lbl = QLabel("Đại úy Nguyễn Văn Tiệp")
        author_name_lbl.setStyleSheet(
            "color: #FFFFFF; font-size: 26px; font-weight: bold; "
            "font-family: 'Segoe UI', Arial, sans-serif; letter-spacing: 0.5px;"
        )
        ac_layout.addWidget(author_name_lbl)

        # Mô tả chính thức
        desc_lbl = QLabel(
            "Phần mềm chuyển văn bản thành giọng nói tiếng Việt, tích hợp mô hình VieNeu-TTS v3 Turbo sử dụng ONNX Runtime CPU."
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #E2E8F0; font-size: 13px; line-height: 1.5; margin-top: 4px;")
        ac_layout.addWidget(desc_lbl)

        # Dải phân cách nhẹ
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #28364A; margin-top: 8px; margin-bottom: 8px;")
        ac_layout.addWidget(sep)

        # Ghi nhận bản quyền mô hình VieNeu-TTS (Phân biệt rõ ràng)
        model_credit_lbl = QLabel(
            "<b>Thông tin mô hình:</b> Mô hình VieNeu-TTS do <b>Phạm Nguyễn Ngọc Bảo</b> phát triển.<br>"
            "<i>(T-TTS sử dụng bộ suy luận VieNeu ONNX Runtime CPU chính thức theo giấy phép mã nguồn mở).</i>"
        )
        model_credit_lbl.setWordWrap(True)
        model_credit_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.4;")
        ac_layout.addWidget(model_credit_lbl)

        layout.addWidget(author_card)

        # -------------------------------------------------------------
        # 2. KHUNG TRẠNG THÁI BẢN QUYỀN MÁY TÍNH
        # -------------------------------------------------------------
        lic_card = QFrame()
        lic_card.setProperty("class", "CardFrame")
        lc_layout = QVBoxLayout(lic_card)
        lc_layout.setContentsMargins(16, 14, 16, 14)
        lc_layout.setSpacing(10)

        lc_title = QLabel("🛡️ TRẠNG THÁI BẢN QUYỀN TRÊN THIẾT BỊ NÀY")
        lc_title.setProperty("class", "CardTitle")
        lc_layout.addWidget(lc_title)

        # Hàng Machine ID
        mid_layout = QHBoxLayout()
        mid_title = QLabel("Mã Máy Tính (Machine ID):")
        mid_title.setStyleSheet("color: #F1F5F9; font-weight: bold;")
        mid_layout.addWidget(mid_title)

        self.mid_lbl = QLabel("")
        self.mid_lbl.setStyleSheet("color: #22D3EE; font-family: Consolas; font-weight: bold; font-size: 13px;")
        mid_layout.addWidget(self.mid_lbl)

        btn_copy_mid = QPushButton("📋 Sao chép")
        btn_copy_mid.setProperty("class", "SecondaryBtn")
        btn_copy_mid.setCursor(Qt.PointingHandCursor)
        btn_copy_mid.clicked.connect(self._copy_mid)
        mid_layout.addWidget(btn_copy_mid)

        mid_layout.addStretch()
        lc_layout.addLayout(mid_layout)

        # Chi tiết bản quyền
        self.lic_status_lbl = QLabel("")
        self.lic_status_lbl.setStyleSheet("font-size: 13px; font-weight: 500;")
        lc_layout.addWidget(self.lic_status_lbl)

        self.lic_details_lbl = QLabel("")
        self.lic_details_lbl.setWordWrap(True)
        self.lic_details_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.6;")
        lc_layout.addWidget(self.lic_details_lbl)

        # Hàng nút kích hoạt
        btn_row = QHBoxLayout()
        self.btn_open_act = QPushButton("🔑  KÍCH HOẠT / NHẬP KEY MỚI")
        self.btn_open_act.setProperty("class", "PrimaryBtn")
        self.btn_open_act.setCursor(Qt.PointingHandCursor)
        self.btn_open_act.clicked.connect(lambda: self.request_open_activation.emit())
        btn_row.addWidget(self.btn_open_act)

        btn_refresh_lic = QPushButton("🔄 Kiểm tra lại")
        btn_refresh_lic.setProperty("class", "SecondaryBtn")
        btn_refresh_lic.setCursor(Qt.PointingHandCursor)
        btn_refresh_lic.clicked.connect(self.reload_license_info)
        btn_row.addWidget(btn_refresh_lic)

        btn_row.addStretch()
        lc_layout.addLayout(btn_row)

        layout.addWidget(lic_card)

        # -------------------------------------------------------------
        # 3. CHÍNH SÁCH BẢN QUYỀN VÀ BẢO HÀNH
        # -------------------------------------------------------------
        policy_card = QFrame()
        policy_card.setProperty("class", "CardFrame")
        pc_layout = QVBoxLayout(policy_card)
        pc_layout.setContentsMargins(16, 14, 16, 14)
        pc_layout.setSpacing(6)

        pol_title = QLabel("📜 ĐIỀU KHOẢN SỬ DỤNG & BẢO ĐẢM DỮ LIỆU")
        pol_title.setProperty("class", "CardTitle")
        pc_layout.addWidget(pol_title)

        pol_text = QLabel(
            "• Bản quyền phần mềm gắn liền với chữ ký số Ed25519 và mã phần cứng của máy tính.<br>"
            "• Hỗ trợ đầy đủ 5 thời hạn bản quyền: <b>1 Ngày, 7 Ngày, 30 Ngày, 6 Tháng và Vĩnh Viễn</b>.<br>"
            "• Khi giấy phép hết hạn, toàn bộ lịch sử, các file âm thanh đã xuất và các giọng đã nhân bản "
            "<b>hoàn toàn được giữ nguyên</b> và không bao giờ bị xóa.<br>"
            "• Hoạt động 100% offline, không gửi bất kỳ dữ liệu âm thanh hoặc văn bản nào của người dùng ra Internet."
        )
        pol_text.setWordWrap(True)
        pol_text.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.6;")
        pc_layout.addWidget(pol_text)
        layout.addWidget(policy_card)

        layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def reload_license_info(self):
        mid = tts_service.get_machine_id()
        self.mid_lbl.setText(mid)

        info = tts_service.get_license_info()
        is_active = info.get("is_active", False)
        status = info.get("status", "unactivated")
        plan = info.get("plan") or "Chưa có"
        rem_str = info.get("remaining_formatted", "")
        exp_str = info.get("expires_readable", "Chưa có")
        first_act = info.get("first_activated_readable", "Chưa kích hoạt")

        if is_active:
            self.lic_status_lbl.setText("● BẢN QUYỀN HỢP LỆ — ĐANG HOẠT ĐỘNG BÌNH THƯỜNG")
            self.lic_status_lbl.setStyleSheet("color: #22C55E; font-weight: bold; font-size: 13px;")
            self.lic_details_lbl.setText(
                f"• Gói bản quyền: <b>{plan}</b><br>"
                f"• Thời hạn còn lại: <b>{rem_str}</b><br>"
                f"• Kích hoạt lần đầu: {first_act}<br>"
                f"• Hạn sử dụng: {exp_str}"
            )
        else:
            self.lic_status_lbl.setText("✕ CHƯA KÍCH HOẠT HOẶC ĐÃ HẾT HẠN SỬ DỤNG")
            self.lic_status_lbl.setStyleSheet("color: #EF4444; font-weight: bold; font-size: 13px;")
            self.lic_details_lbl.setText(
                f"• Trạng thái: {info.get('status_message')}<br>"
                f"• Gói gần nhất: {plan}<br>"
                f"• Hãy bấm nút <b>'KÍCH HOẠT / NHẬP KEY MỚI'</b> bên dưới để tiếp tục sử dụng."
            )

    def _copy_mid(self):
        mid = self.mid_lbl.text().strip()
        if mid:
            QApplication.clipboard().setText(mid)
            QMessageBox.information(self, "Đã sao chép", f"Đã sao chép Mã Máy:\n\n{mid}")
