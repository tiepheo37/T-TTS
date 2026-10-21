"""gui/styles.py — HỆ THỐNG GIAO DIỆN QUÂN ĐỘI NHÂN DÂN VIỆT NAM (RẰN RI K20)
=============================================================================
Hỗ trợ 2 chế độ:
1. MILITARY K20 DARK (Màu rằn ri K20 chuẩn Quân đội nhân dân Việt Nam - Tối):
   - Nền xanh quân đội sẫm #0D170E, thanh điều hướng #132415, thẻ chức năng #1A2F1C
   - Điểm nhấn Vàng sao quân hàm #FFD700 / #EAB308 và Đỏ quân hiệu #C92A2A
   - Chữ sáng sắc nét #F5FAF4, tương phản cao, tối ưu hiển thị tiếng Việt.
2. MILITARY K20 LIGHT (Chế độ Quân đội - Sáng):
   - Nền đá sáng quân sự #F4F6F0, thanh điều hướng xanh ô-liu sẫm #193617
   - Thẻ trắng #FFFFFF, viền ô-liu #D0DBD0, chữ tối chuẩn mực #152214
   - Đảm bảo độ tương phản tuyệt đối giữa chữ và nền khi chuyển đổi qua lại.
"""

# =========================================================================
# 1. BẢNG MÃ CSS CHẾ ĐỘ QUÂN ĐỘI TỐI (K20 DARK)
# =========================================================================
MILITARY_K20_DARK_QSS = """
QMainWindow, QWidget#MainRoot {
    background-color: #0D170E;
    color: #F5FAF4;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #F5FAF4;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

/* Header Bar */
#HeaderFrame {
    background-color: #122114;
    border-bottom: 2px solid #2D4C2F;
    padding: 8px 16px;
}

#AppTitle {
    font-size: 17px;
    font-weight: 800;
    color: #FFD700;
    letter-spacing: 0.5px;
}

#AppSubtitle {
    font-size: 11px;
    color: #A3BCA0;
}

#BadgeModelReady {
    background-color: rgba(34, 197, 94, 0.2);
    color: #4ADE80;
    border: 1px solid #22C55E;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeModelLoading {
    background-color: rgba(234, 179, 8, 0.2);
    color: #FDE047;
    border: 1px solid #EAB308;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeModelError {
    background-color: rgba(220, 38, 38, 0.2);
    color: #F87171;
    border: 1px solid #DC2626;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeLicenseActive {
    background-color: rgba(255, 215, 0, 0.15);
    color: #FFD700;
    border: 1px solid #EAB308;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

/* Sidebar Navigation */
#NavFrame {
    background-color: #132415;
    border-right: 1px solid #27412A;
    min-width: 240px;
    max-width: 250px;
}

.NavGroupLabel {
    color: #FFD700;
    font-size: 11px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 10px 14px 4px 14px;
}

QPushButton.NavBtn {
    background-color: transparent;
    color: #E2ECE1;
    border: none;
    border-radius: 6px;
    padding: 10px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}

QPushButton.NavBtn:hover {
    background-color: #1F3622;
    color: #FFD700;
}

QPushButton.NavBtn[active="true"] {
    background-color: #26432B;
    color: #FFD700;
    font-weight: bold;
    border-left: 4px solid #FFD700;
}

/* Sidebar Author Badge */
#SidebarAuthorCard {
    background-color: #0E1A10;
    border: 1px solid #365738;
    border-radius: 8px;
    padding: 8px;
    margin: 8px;
}

/* Cards & Frames */
QFrame.CardFrame, #CardFrame {
    background-color: #1A2F1C;
    border: 1px solid #2C482F;
    border-radius: 8px;
}

QLabel.CardTitle, #CardTitle {
    font-size: 14px;
    font-weight: bold;
    color: #FFD700;
    padding-bottom: 2px;
}

/* Inputs & TextEdit */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #111F13;
    color: #F5FAF4;
    border: 1px solid #2F4D32;
    border-radius: 6px;
    padding: 8px 10px;
    selection-background-color: #2F5932;
    selection-color: #FFD700;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #FFD700;
    background-color: #142416;
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
    background-color: #263828;
    color: #6C826A;
    border: 1px solid #3A4E3C;
}

QPushButton.GoldBtn, #BtnGold {
    background-color: #EAB308;
    color: #101E11;
    font-weight: bold;
    border: 1px solid #CA8A04;
    border-radius: 6px;
    padding: 8px 16px;
}

QPushButton.GoldBtn:hover {
    background-color: #FACC15;
}

QPushButton.SecondaryBtn, #BtnSecondary {
    background-color: #1F3622;
    color: #F5FAF4;
    border: 1px solid #365739;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 500;
}

QPushButton.SecondaryBtn:hover {
    background-color: #2A482E;
    border-color: #4D754F;
    color: #FFD700;
}

/* Quick Tag Pill Buttons */
QPushButton.TagPill {
    background-color: #172B19;
    color: #E2ECE1;
    border: 1px solid #315234;
    border-radius: 14px;
    padding: 4px 11px;
    font-size: 12px;
}

QPushButton.TagPill:hover {
    background-color: #244127;
    border-color: #FFD700;
    color: #FFD700;
}

/* Voice Card in Selector */
QFrame.VoiceCard {
    background-color: #162918;
    border: 1px solid #2B472E;
    border-radius: 8px;
    padding: 6px;
}

QFrame.VoiceCard:hover {
    background-color: #1E3721;
    border: 1px solid #4D7A51;
}

QFrame.VoiceCard[selected="true"] {
    background-color: #27472A;
    border: 2px solid #FFD700;
}

/* ComboBox */
QComboBox {
    background-color: #111F13;
    color: #F5FAF4;
    border: 1px solid #2F4D32;
    border-radius: 6px;
    padding: 6px 12px;
    min-height: 24px;
}

QComboBox:hover {
    border: 1px solid #4D7A51;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #142416;
    color: #F5FAF4;
    border: 1px solid #365739;
    selection-background-color: #27472A;
    selection-color: #FFD700;
    padding: 4px;
}

/* Slider */
QSlider::groove:horizontal {
    height: 6px;
    background: #111F13;
    border: 1px solid #2F4D32;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #EAB308;
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
    background-color: #111F13;
    color: #F5FAF4;
    gridline-color: #233925;
    border: 1px solid #2B452D;
    border-radius: 6px;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background-color: #27472A;
    color: #FFD700;
}

QHeaderView::section {
    background-color: #162918;
    color: #FFD700;
    font-weight: bold;
    padding: 6px;
    border: none;
    border-right: 1px solid #233925;
    border-bottom: 1px solid #2B452D;
}

/* ScrollBar */
QScrollBar:vertical {
    border: none;
    background-color: #0E190F;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #2B472E;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background-color: #4D7A51;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

# =========================================================================
# 2. BẢNG MÃ CSS CHẾ ĐỘ QUÂN ĐỘI SÁNG (K20 LIGHT)
# =========================================================================
MILITARY_K20_LIGHT_QSS = """
QMainWindow, QWidget#MainRoot {
    background-color: #F4F6F0;
    color: #152214;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #152214;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

/* Header Bar */
#HeaderFrame {
    background-color: #183317;
    border-bottom: 2px solid #C92A2A;
    padding: 8px 16px;
}

#AppTitle {
    font-size: 17px;
    font-weight: 800;
    color: #FFD700;
    letter-spacing: 0.5px;
}

#AppSubtitle {
    font-size: 11px;
    color: #E2ECE1;
}

#BadgeModelReady {
    background-color: #DCFCE7;
    color: #15803D;
    border: 1px solid #16A34A;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeModelLoading {
    background-color: #FEF9C3;
    color: #A16207;
    border: 1px solid #CA8A04;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeModelError {
    background-color: #FEE2E2;
    color: #B91C1C;
    border: 1px solid #DC2626;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeLicenseActive {
    background-color: #FEF08A;
    color: #854D0E;
    border: 1px solid #CA8A04;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

/* Sidebar Navigation */
#NavFrame {
    background-color: #1B3919;
    border-right: 1px solid #2B5428;
    min-width: 240px;
    max-width: 250px;
}

.NavGroupLabel {
    color: #FFD700;
    font-size: 11px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 10px 14px 4px 14px;
}

QPushButton.NavBtn {
    background-color: transparent;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 10px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}

QPushButton.NavBtn:hover {
    background-color: #275225;
    color: #FFD700;
}

QPushButton.NavBtn[active="true"] {
    background-color: #2F612D;
    color: #FFD700;
    font-weight: bold;
    border-left: 4px solid #FFD700;
}

/* Sidebar Author Badge */
#SidebarAuthorCard {
    background-color: #132A12;
    border: 1px solid #3D733A;
    border-radius: 8px;
    padding: 8px;
    margin: 8px;
}

/* Cards & Frames */
QFrame.CardFrame, #CardFrame {
    background-color: #FFFFFF;
    border: 1px solid #CCD8CB;
    border-radius: 8px;
}

QLabel.CardTitle, #CardTitle {
    font-size: 14px;
    font-weight: bold;
    color: #1A3E18;
    padding-bottom: 2px;
}

/* Inputs & TextEdit */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #FFFFFF;
    color: #152214;
    border: 1px solid #B8C7B5;
    border-radius: 6px;
    padding: 8px 10px;
    selection-background-color: #2D5E2A;
    selection-color: #FFFFFF;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #1E4D1B;
    background-color: #FAFCF9;
}

/* Buttons */
QPushButton.PrimaryBtn, #BtnGenerate, #BtnPrimary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #C92A2A, stop:1 #A81C1C);
    color: #FFFFFF;
    font-weight: bold;
    font-size: 13px;
    border: 1px solid #8B0000;
    border-radius: 6px;
    padding: 9px 18px;
}

QPushButton.PrimaryBtn:hover, #BtnGenerate:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #DC2626, stop:1 #B91C1C);
}

QPushButton.PrimaryBtn:disabled, #BtnGenerate:disabled {
    background-color: #D1D5DB;
    color: #9CA3AF;
    border: 1px solid #D1D5DB;
}

QPushButton.GoldBtn, #BtnGold {
    background-color: #EAB308;
    color: #152214;
    font-weight: bold;
    border: 1px solid #CA8A04;
    border-radius: 6px;
    padding: 8px 16px;
}

QPushButton.GoldBtn:hover {
    background-color: #FACC15;
}

QPushButton.SecondaryBtn, #BtnSecondary {
    background-color: #E8EFE6;
    color: #1E461A;
    border: 1px solid #B8C7B5;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 600;
}

QPushButton.SecondaryBtn:hover {
    background-color: #DCE7D9;
    border-color: #1E461A;
    color: #163613;
}

/* Quick Tag Pill Buttons */
QPushButton.TagPill {
    background-color: #EBF1EA;
    color: #1E461A;
    border: 1px solid #B5C7B3;
    border-radius: 14px;
    padding: 4px 11px;
    font-size: 12px;
}

QPushButton.TagPill:hover {
    background-color: #DCFCE7;
    border-color: #16A34A;
    color: #15803D;
}

/* Voice Card in Selector */
QFrame.VoiceCard {
    background-color: #F9FAF7;
    border: 1px solid #CFDDD0;
    border-radius: 8px;
    padding: 6px;
}

QFrame.VoiceCard:hover {
    background-color: #F0F5EE;
    border: 1px solid #84A982;
}

QFrame.VoiceCard[selected="true"] {
    background-color: #EBF3E8;
    border: 2px solid #C92A2A;
}

/* ComboBox */
QComboBox {
    background-color: #FFFFFF;
    color: #152214;
    border: 1px solid #B8C7B5;
    border-radius: 6px;
    padding: 6px 12px;
    min-height: 24px;
}

QComboBox:hover {
    border: 1px solid #1E461A;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #152214;
    border: 1px solid #B8C7B5;
    selection-background-color: #EBF3E8;
    selection-color: #1A3E18;
    padding: 4px;
}

/* Slider */
QSlider::groove:horizontal {
    height: 6px;
    background: #D9E2D8;
    border: 1px solid #B8C7B5;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #1E461A;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #FFD700;
    border: 1px solid #CA8A04;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}

/* Table Widget */
QTableWidget {
    background-color: #FFFFFF;
    color: #152214;
    gridline-color: #E5EDE4;
    border: 1px solid #CCD8CB;
    border-radius: 6px;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background-color: #EBF3E8;
    color: #163613;
}

QHeaderView::section {
    background-color: #EBF1EA;
    color: #1E461A;
    font-weight: bold;
    padding: 6px;
    border: none;
    border-right: 1px solid #CCD8CB;
    border-bottom: 1px solid #CCD8CB;
}

/* ScrollBar */
QScrollBar:vertical {
    border: none;
    background-color: #F0F4EF;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #B8C9B5;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background-color: #8CA389;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

# Hộp thoại kích hoạt bản quyền (Friendly Light)
FRIENDLY_LIGHT_QSS = """
QDialog {
    background-color: #FFFFFF;
    color: #0F172A;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

QLabel {
    color: #0F172A;
}

QLabel#DialogTitle {
    font-size: 19px;
    font-weight: 800;
    color: #162E10;
}

QLabel#MachineIdBox {
    background-color: #F4F6F0;
    border: 1px dashed #3D5C3A;
    border-radius: 6px;
    padding: 10px 14px;
    font-family: "Consolas", monospace;
    font-size: 14px;
    font-weight: bold;
    color: #162E10;
}

QLineEdit#KeyInput {
    background-color: #FFFFFF;
    border: 2px solid #2B4C1E;
    border-radius: 6px;
    padding: 10px;
    font-size: 13px;
    color: #0F172A;
}

QPushButton#BtnActivate {
    background-color: #C92A2A;
    color: #FFFFFF;
    font-weight: bold;
    font-size: 14px;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
}

QPushButton#BtnActivate:hover {
    background-color: #B71C1C;
}

QPushButton#BtnClose {
    background-color: #E2E8F0;
    color: #334155;
    font-weight: 600;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
}
"""

LIGHT_ACTIVATION_QSS = FRIENDLY_LIGHT_QSS
MODERN_DARK_QSS = MILITARY_K20_DARK_QSS


def get_theme_qss(theme: str = "k20_dark") -> str:
    """Trả về CSS theo tên theme (k20_dark hoặc k20_light)."""
    if theme == "k20_light":
        return MILITARY_K20_LIGHT_QSS
    return MILITARY_K20_DARK_QSS
