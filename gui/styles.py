"""gui/styles.py — GIAO DIỆN QUÂN ĐỘI NHÂN DÂN VIỆT NAM (RẰN RI K20 SÁNG RÕ)
=============================================================================
Thiết kế theo chuẩn màu Quân đội nhân dân Việt Nam (rằn ri K20):
- Tông xanh quân sự K20 sáng rõ, dịu mắt, dễ nhìn (#1E3A21 / #254829).
- Bỏ chế độ sáng/tối rườm rà, tập trung 1 giao diện chuẩn chỉ, ổn định.
- Chữ vàng quân hàm #FFD700, đỏ quân hiệu #C92A2A, chữ trắng #FFFFFF sắc nét.
- Triệt tiêu hoàn toàn viền thừa trên tất cả QLabel (tránh lỗi ô vuông quanh chữ).
- Định dạng nút bấm hộp thoại kích hoạt bản quyền sáng rõ, không bị mất nút.
"""

MILITARY_K20_THEME_QSS = """
/* =========================================================================
   GIAO DIỆN QUÂN ĐỘI K20 CHUẨN — T-TTS v1.0.1
   ========================================================================= */

QMainWindow, QWidget#MainRoot {
    background-color: #1E3A21;
    color: #FFFFFF;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #FFFFFF;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

/* TRIỆT TIÊU TOÀN BỘ VIỀN THỪA TRÊN MỌI LABEL */
QLabel {
    border: none;
    background-color: transparent;
    color: #FFFFFF;
}

/* Header Bar */
#HeaderFrame {
    background-color: #162E1A;
    border-bottom: 2px solid #C92A2A;
    padding: 8px 16px;
}

#AppTitle {
    font-size: 17px;
    font-weight: 800;
    color: #FFD700;
    letter-spacing: 0.5px;
    border: none;
    background: transparent;
}

#AppSubtitle {
    font-size: 11px;
    color: #C8DEC6;
    border: none;
    background: transparent;
}

#BadgeModelReady {
    background-color: #166534;
    color: #4ADE80;
    border: 1px solid #22C55E;
    border-radius: 12px;
    padding: 4px 12px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeModelLoading {
    background-color: #854D0E;
    color: #FEF08A;
    border: 1px solid #EAB308;
    border-radius: 12px;
    padding: 4px 12px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeModelError {
    background-color: #991B1B;
    color: #FECACA;
    border: 1px solid #EF4444;
    border-radius: 12px;
    padding: 4px 12px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeLicenseActive {
    background-color: #274D2B;
    color: #FFD700;
    border: 1px solid #FFD700;
    border-radius: 12px;
    padding: 4px 12px;
    font-weight: bold;
    font-size: 11px;
}

/* Sidebar Navigation */
#NavFrame {
    background-color: #162E1A;
    border-right: 1px solid #2D5831;
    min-width: 240px;
    max-width: 250px;
}

.NavGroupLabel {
    color: #FFD700;
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 10px 14px 4px 14px;
    border: none;
    background: transparent;
}

QPushButton.NavBtn {
    background-color: transparent;
    color: #E8F5E7;
    border: none;
    border-radius: 6px;
    padding: 10px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}

QPushButton.NavBtn:hover {
    background-color: #2A522E;
    color: #FFD700;
}

QPushButton.NavBtn[active="true"] {
    background-color: #315F36;
    color: #FFD700;
    font-weight: bold;
    border-left: 4px solid #FFD700;
}

/* Sidebar Author Badge */
#SidebarAuthorCard {
    background-color: #142817;
    border: 1px solid #3F7545;
    border-radius: 8px;
    padding: 8px;
    margin: 8px;
}

/* Cards & Frames */
QFrame.CardFrame, #CardFrame {
    background-color: #254829;
    border: 1px solid #386B3E;
    border-radius: 8px;
}

QLabel.CardTitle, #CardTitle {
    font-size: 14px;
    font-weight: bold;
    color: #FFD700;
    padding-bottom: 2px;
    border: none;
    background: transparent;
}

/* Inputs & TextEdit */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #18331C;
    color: #FFFFFF;
    border: 1px solid #3E7345;
    border-radius: 6px;
    padding: 8px 10px;
    selection-background-color: #3B7542;
    selection-color: #FFD700;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #FFD700;
    background-color: #1C3B20;
}

/* Buttons */
QPushButton.PrimaryBtn, #BtnGenerate, #BtnPrimary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #C92A2A, stop:1 #A81C1C);
    color: #FFFFFF;
    font-weight: bold;
    font-size: 13px;
    border: 1px solid #FFD700;
    border-radius: 6px;
    padding: 9px 18px;
}

QPushButton.PrimaryBtn:hover, #BtnGenerate:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #DC2626, stop:1 #B91C1C);
    border: 1px solid #FFF066;
}

QPushButton.PrimaryBtn:disabled, #BtnGenerate:disabled {
    background-color: #334F36;
    color: #8CA990;
    border: 1px solid #436347;
}

QPushButton.GoldBtn, #BtnGold {
    background-color: #EAB308;
    color: #0F1E11;
    font-weight: bold;
    border: 1px solid #CA8A04;
    border-radius: 6px;
    padding: 8px 16px;
}

QPushButton.GoldBtn:hover {
    background-color: #FACC15;
}

QPushButton.SecondaryBtn, #BtnSecondary {
    background-color: #2D5632;
    color: #FFFFFF;
    border: 1px solid #447B4B;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 500;
}

QPushButton.SecondaryBtn:hover {
    background-color: #386A3E;
    border-color: #5BA164;
    color: #FFD700;
}

/* Quick Tag Pill Buttons */
QPushButton.TagPill {
    background-color: #1E3D22;
    color: #E8F5E7;
    border: 1px solid #3E7345;
    border-radius: 14px;
    padding: 4px 11px;
    font-size: 12px;
}

QPushButton.TagPill:hover {
    background-color: #315F36;
    border-color: #FFD700;
    color: #FFD700;
}

/* Voice Card in Selector */
QFrame.VoiceCard {
    background-color: #1E3D22;
    border: 1px solid #386B3E;
    border-radius: 8px;
    padding: 6px;
}

QFrame.VoiceCard:hover {
    background-color: #2B5430;
    border: 1px solid #5BA164;
}

QFrame.VoiceCard[selected="true"] {
    background-color: #336338;
    border: 2px solid #FFD700;
}

/* ComboBox */
QComboBox {
    background-color: #18331C;
    color: #FFFFFF;
    border: 1px solid #3E7345;
    border-radius: 6px;
    padding: 6px 12px;
    min-height: 24px;
}

QComboBox:hover {
    border: 1px solid #5BA164;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #1C3B20;
    color: #FFFFFF;
    border: 1px solid #447B4B;
    selection-background-color: #336338;
    selection-color: #FFD700;
    padding: 4px;
}

/* Slider */
QSlider::groove:horizontal {
    height: 6px;
    background: #18331C;
    border: 1px solid #3E7345;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #FFD700;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #FFD700;
    border: 1px solid #B45309;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}

/* Table Widget */
QTableWidget {
    background-color: #18331C;
    color: #FFFFFF;
    gridline-color: #2D5831;
    border: 1px solid #3E7345;
    border-radius: 6px;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background-color: #336338;
    color: #FFD700;
}

QHeaderView::section {
    background-color: #244829;
    color: #FFD700;
    font-weight: bold;
    padding: 6px;
    border: none;
    border-right: 1px solid #2D5831;
    border-bottom: 1px solid #3E7345;
}

/* ScrollBar */
QScrollBar:vertical {
    border: none;
    background-color: #142817;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #3A6D40;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background-color: #5BA164;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

FRIENDLY_LIGHT_QSS = """
QDialog#ActivationDialog, QDialog {
    background-color: #FFFFFF;
    color: #0F172A;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

QDialog QLabel {
    color: #0F172A;
    background: transparent;
    border: none;
}

QDialog QLineEdit {
    background-color: #F1F5F9;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 8px 10px;
}

QDialog QTextEdit {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 8px;
}

/* NÚT BẤM TRONG HỘP THOẠI KÍCH HOẠT: HIỂN THỊ RÕ RÀNG 100% */
QDialog QPushButton {
    background-color: #E2E8F0;
    color: #0F172A;
    font-weight: 600;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 8px 16px;
}

QDialog QPushButton:hover {
    background-color: #CBD5E1;
}

QDialog QPushButton.LightPrimaryBtn, QDialog #BtnActivate {
    background-color: #C92A2A;
    color: #FFFFFF;
    font-weight: bold;
    font-size: 13px;
    border: 1px solid #B91C1C;
    border-radius: 6px;
    padding: 10px 20px;
}

QDialog QPushButton.LightPrimaryBtn:hover, QDialog #BtnActivate:hover {
    background-color: #DC2626;
}

QDialog QPushButton.LightSecondaryBtn, QDialog #BtnClose {
    background-color: #E2E8F0;
    color: #0F172A;
    font-weight: bold;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 8px 16px;
}

QDialog QPushButton.LightSecondaryBtn:hover, QDialog #BtnClose:hover {
    background-color: #CBD5E1;
    color: #000000;
}
"""

LIGHT_ACTIVATION_QSS = FRIENDLY_LIGHT_QSS
MODERN_DARK_QSS = MILITARY_K20_THEME_QSS


def get_theme_qss(theme: str = "k20_dark") -> str:
    """Trả về CSS chuẩn Quân đội K20."""
    return MILITARY_K20_THEME_QSS
