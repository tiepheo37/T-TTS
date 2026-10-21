"""gui/styles.py — HỆ THỐNG GIAO DIỆN & BẢNG MÀU CHO T-TTS v1.0.1
===================================================================
1. MODERN DARK: Dành cho toàn bộ ứng dụng chính (Xanh đen #0B1120, slate #101827,
   card #172235, viền #28364A, điểm nhấn Xanh dương #1687FF và Cyan #22D3EE).
2. FRIENDLY LIGHT: Dành riêng cho Hộp thoại kích hoạt bản quyền (Nền trắng #FFFFFF / #F8FAFC,
   chữ tối, điểm nhấn xanh dương #1687FF).
"""

DARK_PALETTE = {
    "bg_main": "#0B1120",        # Nền tổng thể
    "bg_nav": "#101827",         # Thanh điều hướng trái
    "bg_card": "#172235",        # Thẻ chức năng
    "bg_card_elevated": "#1E2D44", # Thẻ nổi bật / hover
    "bg_input": "#0F172A",       # Ô nhập liệu
    "border": "#28364A",         # Đường viền
    "border_focus": "#1687FF",   # Đường viền khi focus
    "accent_blue": "#1687FF",    # Xanh dương chính
    "accent_cyan": "#22D3EE",    # Cyan điểm nhấn
    "text_main": "#F1F5F9",      # Chữ chính
    "text_muted": "#94A3B8",     # Chữ phụ
    "success": "#22C55E",        # Thành công
    "warning": "#F59E0B",        # Cảnh báo
    "error": "#EF4444",          # Lỗi
}

MODERN_DARK_QSS = """
/* =========================================================================
   MODERN DARK THEME — T-TTS v1.0.1
   ========================================================================= */

QMainWindow, QWidget#MainRoot {
    background-color: #0B1120;
    color: #F1F5F9;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #F1F5F9;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

/* Header Banner */
#HeaderFrame {
    background-color: #101827;
    border-bottom: 1px solid #28364A;
    padding: 8px 16px;
}

#AppTitle {
    font-size: 18px;
    font-weight: bold;
    color: #22D3EE;
    letter-spacing: 0.5px;
}

#AppSubtitle {
    font-size: 11px;
    color: #94A3B8;
}

#BadgeModelReady {
    background-color: rgba(34, 197, 94, 0.15);
    color: #22C55E;
    border: 1px solid #22C55E;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeModelLoading {
    background-color: rgba(245, 158, 11, 0.15);
    color: #F59E0B;
    border: 1px solid #F59E0B;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeModelError {
    background-color: rgba(239, 68, 68, 0.15);
    color: #EF4444;
    border: 1px solid #EF4444;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeLicenseActive {
    background-color: rgba(22, 135, 255, 0.15);
    color: #22D3EE;
    border: 1px solid #1687FF;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

#BadgeLicenseLocked {
    background-color: rgba(239, 68, 68, 0.15);
    color: #EF4444;
    border: 1px solid #EF4444;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 11px;
}

/* Left Navigation Sidebar */
#NavSidebar {
    background-color: #101827;
    border-right: 1px solid #28364A;
    min-width: 220px;
    max-width: 240px;
}

QPushButton.NavBtn {
    background-color: transparent;
    color: #94A3B8;
    text-align: left;
    padding: 12px 18px;
    border: none;
    border-left: 3px solid transparent;
    font-size: 13px;
    font-weight: 500;
    border-radius: 0px;
}

QPushButton.NavBtn:hover {
    background-color: #172235;
    color: #F1F5F9;
}

QPushButton.NavBtn:checked, QPushButton.NavBtn.active {
    background-color: #172235;
    color: #22D3EE;
    border-left: 3px solid #22D3EE;
    font-weight: bold;
}

/* Card Containers */
QFrame.CardFrame {
    background-color: #172235;
    border: 1px solid #28364A;
    border-radius: 8px;
    padding: 14px;
}

QLabel.CardTitle {
    color: #F1F5F9;
    font-size: 14px;
    font-weight: bold;
    margin-bottom: 6px;
}

QLabel.CardSubtitle {
    color: #94A3B8;
    font-size: 12px;
}

/* Input Controls */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #0F172A;
    border: 1px solid #28364A;
    border-radius: 6px;
    color: #F1F5F9;
    padding: 8px 10px;
    selection-background-color: #1687FF;
    selection-color: #FFFFFF;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #1687FF;
}

QComboBox {
    background-color: #0F172A;
    border: 1px solid #28364A;
    border-radius: 6px;
    color: #F1F5F9;
    padding: 7px 12px;
    min-height: 24px;
}

QComboBox:focus, QComboBox:hover {
    border: 1px solid #1687FF;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #101827;
    border: 1px solid #28364A;
    selection-background-color: #1687FF;
    selection-color: #FFFFFF;
    color: #F1F5F9;
    padding: 4px;
}

/* Sliders */
QSlider::groove:horizontal {
    height: 6px;
    background: #28364A;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #1687FF;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #22D3EE;
    border: 2px solid #0B1120;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background: #FFFFFF;
}

/* Buttons */
QPushButton.PrimaryBtn {
    background-color: #1687FF;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: bold;
}

QPushButton.PrimaryBtn:hover {
    background-color: #0070E0;
}

QPushButton.PrimaryBtn:pressed {
    background-color: #0056B3;
}

QPushButton.PrimaryBtn:disabled {
    background-color: #28364A;
    color: #64748B;
}

QPushButton.AccentBtn {
    background-color: #0E7490;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}

QPushButton.AccentBtn:hover {
    background-color: #0891B2;
}

QPushButton.SecondaryBtn {
    background-color: #1E2D44;
    color: #F1F5F9;
    border: 1px solid #28364A;
    border-radius: 6px;
    padding: 7px 14px;
    font-size: 12px;
}

QPushButton.SecondaryBtn:hover {
    background-color: #28364A;
    border-color: #384C66;
}

QPushButton.DangerBtn {
    background-color: rgba(239, 68, 68, 0.2);
    color: #EF4444;
    border: 1px solid #EF4444;
    border-radius: 6px;
    padding: 7px 14px;
    font-size: 12px;
}

QPushButton.DangerBtn:hover {
    background-color: #EF4444;
    color: #FFFFFF;
}

/* Table Widget */
QTableWidget {
    background-color: #0F172A;
    border: 1px solid #28364A;
    gridline-color: #1E2D44;
    color: #F1F5F9;
    border-radius: 6px;
    selection-background-color: rgba(22, 135, 255, 0.3);
    selection-color: #FFFFFF;
}

QTableWidget QHeaderView::section {
    background-color: #101827;
    color: #94A3B8;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #28364A;
    font-weight: bold;
    font-size: 12px;
}

QTableWidget::item {
    padding: 6px;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #0B1120;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #28364A;
    border-radius: 4px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #384C66;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #0B1120;
    height: 8px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #28364A;
    border-radius: 4px;
    min-width: 20px;
}

/* Progress Bar */
QProgressBar {
    border: 1px solid #28364A;
    border-radius: 4px;
    background-color: #0F172A;
    text-align: center;
    color: #F1F5F9;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: #1687FF;
    border-radius: 3px;
}

/* TabWidget */
QTabWidget::pane {
    border: 1px solid #28364A;
    background: #172235;
    border-radius: 6px;
}

QTabBar::tab {
    background: #101827;
    color: #94A3B8;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background: #172235;
    color: #22D3EE;
    font-weight: bold;
    border-top: 2px solid #22D3EE;
}
"""

# Theme Sáng dành riêng cho Màn hình kích hoạt bản quyền
LIGHT_ACTIVATION_QSS = """
QDialog#ActivationDialog {
    background-color: #F8FAFC;
    color: #1E293B;
    font-family: "Segoe UI", Arial, sans-serif;
}

QFrame.LightCard {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 20px;
}

QLabel#DialogTitle {
    font-size: 20px;
    font-weight: bold;
    color: #0F172A;
}

QLabel#DialogSubtitle {
    font-size: 13px;
    color: #64748B;
}

QLineEdit.LightInput, QTextEdit.LightInput {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    color: #0F172A;
    padding: 10px 12px;
    font-size: 13px;
}

QLineEdit.LightInput:focus, QTextEdit.LightInput:focus {
    border: 1px solid #1687FF;
}

QPushButton.LightPrimaryBtn {
    background-color: #1687FF;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 11px 24px;
    font-size: 14px;
    font-weight: bold;
}

QPushButton.LightPrimaryBtn:hover {
    background-color: #0070E0;
}

QPushButton.LightSecondaryBtn {
    background-color: #F1F5F9;
    color: #334155;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton.LightSecondaryBtn:hover {
    background-color: #E2E8F0;
}
"""
