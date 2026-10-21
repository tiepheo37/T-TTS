"""gui/main_window.py — CỬA SỔ CHÍNH DESKTOP WINDOWS NATIVE T-TTS v1.0.1
========================================================================
- Giao diện Modern Dark: Xanh đen (#0B1120), thanh bên (#101827), điểm nhấn Cyan/Blue.
- Thanh điều hướng 8 mục bên trái, khu vực làm việc QStackedWidget bên phải.
- Header hiển thị trạng thái mô hình thực tế (Đang nạp / Đã sẵn sàng / Lỗi) và trạng thái Bản quyền.
- Loại bỏ hoàn toàn /docs, localhost, 127.0.0.1, Flask server và Chrome App Mode.
- Tự động nạp trước mô hình VieNeu-TTS v3 Turbo ONNX CPU trong nền khi khởi động.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QFont, QColor
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QFrame,
    QApplication,
    QMessageBox,
)

from .styles import MODERN_DARK_QSS
from .dialogs.license_dialog import LicenseActivationDialog
from .pages.page_synthesize import PageSynthesize
from .pages.page_clone import PageClone
from .pages.page_batch import PageBatch
from .pages.page_voices import PageVoices
from .pages.page_history import PageHistory
from .pages.page_settings import PageSettings
from .pages.page_about import PageAbout
from .pages.page_guide import PageGuide

from backend.service import tts_service
from backend.audio_player import audio_player


class ModelLoaderThread(QThread):
    """Tiểu trình chạy ngầm khởi tạo mô hình VieNeu-TTS khi mở ứng dụng."""

    status_changed = Signal(str)
    finished_loading = Signal(bool, str)

    def run(self):
        def _prog(msg):
            self.status_changed.emit(msg)

        ok = tts_service.initialize_model(on_progress=_prog)
        st = tts_service.get_model_status()
        self.finished_loading.emit(ok, st.get("error", ""))


class MainWindow(QMainWindow):
    """Cửa sổ ứng dụng desktop chính của T-TTS v1.0.1."""

    def __init__(self):
        super().__init__()
        self.setObjectName("MainRoot")
        self.setWindowTitle("T-TTS v1.0.1 — Chuyển Văn Bản Thành Giọng Nói Tiếng Việt")
        self.setMinimumSize(1024, 680)
        self.resize(1280, 820)
        self.setStyleSheet(MODERN_DARK_QSS)

        # Đặt biểu tượng ứng dụng nếu có
        icon_path = self._find_app_icon()
        if icon_path:
            self.setWindowIcon(QIcon(str(icon_path)))

        self.nav_buttons: list[QPushButton] = []
        self._build_ui()

        # Tiểu trình nạp trước mô hình trong nền
        self.loader_thread: Optional[ModelLoaderThread] = None
        self._start_background_model_loader()

        # Kiểm tra trạng thái bản quyền
        self._update_license_badge()

        # Nếu chưa kích hoạt bản quyền, mở hộp thoại kích hoạt sau khi giao diện đã hiển thị
        QTimer.singleShot(600, self._check_initial_license)

    def _find_app_icon(self) -> Optional[Path]:
        candidates = [
            Path(__file__).resolve().parent.parent / "app_icon.ico",
            Path(sys.executable).resolve().parent / "app_icon.ico",
            Path.cwd() / "app_icon.ico",
        ]
        for c in candidates:
            if c.is_file():
                return c
        return None

    def _build_ui(self):
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # -------------------------------------------------------------
        # 1. HEADER TRẠNG THÁI (TOP BANNER)
        # -------------------------------------------------------------
        header = QFrame()
        header.setObjectName("HeaderFrame")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 10, 18, 10)
        h_layout.setSpacing(14)

        # Logo / Title
        logo_layout = QVBoxLayout()
        logo_layout.setSpacing(2)
        title_lbl = QLabel("T-TTS v1.0.1")
        title_lbl.setObjectName("AppTitle")
        sub_lbl = QLabel("Chuyển Văn Bản Thành Giọng Nói Tiếng Việt · VieNeu-TTS v3 Turbo ONNX CPU")
        sub_lbl.setObjectName("AppSubtitle")
        logo_layout.addWidget(title_lbl)
        logo_layout.addWidget(sub_lbl)
        h_layout.addLayout(logo_layout)

        h_layout.addStretch()

        # Badge trạng thái mô hình
        self.model_status_badge = QLabel("🔄 Đang khởi tạo mô hình...")
        self.model_status_badge.setObjectName("BadgeModelLoading")
        self.model_status_badge.setAlignment(Qt.AlignCenter)
        h_layout.addWidget(self.model_status_badge)

        # Badge trạng thái bản quyền (Click vào để mở hộp thoại kích hoạt)
        self.license_badge = QPushButton("🛡️ Kiểm tra bản quyền...")
        self.license_badge.setObjectName("BadgeLicenseActive")
        self.license_badge.setCursor(Qt.PointingHandCursor)
        self.license_badge.clicked.connect(self._open_activation_dialog)
        h_layout.addWidget(self.license_badge)

        central_layout.addWidget(header)

        # -------------------------------------------------------------
        # 2. KHU VỰC THÂN CHÍNH (SIDEBAR TRÁI + WORKSPACE PHẢI)
        # -------------------------------------------------------------
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar điều hướng bên trái
        sidebar = QFrame()
        sidebar.setObjectName("NavSidebar")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 12, 0, 12)
        sb_layout.setSpacing(2)

        # 8 mục điều hướng chính thức
        nav_items = [
            ("🎙️  Tạo Giọng Nói", 0),
            ("🧬  Nhân Bản Giọng", 1),
            ("⚡  Xử Lý Hàng Loạt", 2),
            ("👥  Quản Lý Giọng", 3),
            ("📜  Lịch Sử", 4),
            ("⚙️  Cài Đặt", 5),
            ("🛡️  Bản Quyền & Giấy Phép", 6),
            ("📖  Hướng Dẫn Sử Dụng", 7),
        ]

        for text, idx in nav_items:
            btn = QPushButton(text)
            btn.setProperty("class", "NavBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, index=idx: self._switch_tab(index))
            sb_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sb_layout.addStretch()

        # Chân trang sidebar hiển thị thông tin tác giả ngắn gọn
        footer_lbl = QLabel("Phát triển bởi\nĐại úy Nguyễn Văn Tiệp")
        footer_lbl.setAlignment(Qt.AlignCenter)
        footer_lbl.setStyleSheet("color: #64748B; font-size: 11px; padding: 10px; border-top: 1px solid #1E2D44;")
        sb_layout.addWidget(footer_lbl)

        body_layout.addWidget(sidebar)

        # Workspace bên phải (QStackedWidget)
        self.stack = QStackedWidget()

        # Tạo các trang chức năng
        self.page_synth = PageSynthesize()
        self.page_clone = PageClone()
        self.page_batch = PageBatch()
        self.page_voices = PageVoices()
        self.page_history = PageHistory()
        self.page_settings = PageSettings()
        self.page_about = PageAbout()
        self.page_guide = PageGuide()

        # Kết nối các tín hiệu giữa các trang
        self.page_synth.audio_generated.connect(self._on_audio_generated)
        self.page_clone.voice_cloned.connect(self._on_voice_cloned)
        self.page_voices.voices_updated.connect(self._on_voices_updated)
        self.page_about.request_open_activation.connect(self._open_activation_dialog)

        self.stack.addWidget(self.page_synth)      # Index 0
        self.stack.addWidget(self.page_clone)      # Index 1
        self.stack.addWidget(self.page_batch)      # Index 2
        self.stack.addWidget(self.page_voices)     # Index 3
        self.stack.addWidget(self.page_history)    # Index 4
        self.stack.addWidget(self.page_settings)   # Index 5
        self.stack.addWidget(self.page_about)      # Index 6
        self.stack.addWidget(self.page_guide)      # Index 7

        body_layout.addWidget(self.stack)
        central_layout.addWidget(body_widget)

        self.setCentralWidget(central)

        # Mặc định chọn tab đầu tiên
        self._switch_tab(0)

    def _switch_tab(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

        # Khi chuyển sang tab Lịch sử hoặc Quản lý giọng, làm mới dữ liệu
        if index == 3:
            self.page_voices.reload_voices()
        elif index == 4:
            self.page_history.reload_history()
        elif index == 6:
            self.page_about.reload_license_info()

    def _start_background_model_loader(self):
        self.model_status_badge.setText("🔄 Đang khởi tạo mô hình VieNeu-TTS...")
        self.model_status_badge.setObjectName("BadgeModelLoading")
        self.model_status_badge.setStyleSheet(
            "background-color: rgba(245, 158, 11, 0.15); color: #F59E0B; "
            "border: 1px solid #F59E0B; border-radius: 12px; padding: 4px 10px; font-weight: bold; font-size: 11px;"
        )

        self.loader_thread = ModelLoaderThread()
        self.loader_thread.finished_loading.connect(self._on_model_loaded)
        self.loader_thread.start()

    def _on_model_loaded(self, success: bool, error: str):
        if success:
            self.model_status_badge.setText("● Mô hình đã sẵn sàng (ONNX CPU)")
            self.model_status_badge.setObjectName("BadgeModelReady")
            self.model_status_badge.setStyleSheet(
                "background-color: rgba(34, 197, 94, 0.15); color: #22C55E; "
                "border: 1px solid #22C55E; border-radius: 12px; padding: 4px 10px; font-weight: bold; font-size: 11px;"
            )
            # Làm mới danh sách giọng ở các trang
            self.page_synth.refresh_voices()
            self.page_batch.refresh_voices()
            self.page_voices.reload_voices()
        else:
            self.model_status_badge.setText("✕ Khởi tạo mô hình thất bại")
            self.model_status_badge.setObjectName("BadgeModelError")
            self.model_status_badge.setStyleSheet(
                "background-color: rgba(239, 68, 68, 0.15); color: #EF4444; "
                "border: 1px solid #EF4444; border-radius: 12px; padding: 4px 10px; font-weight: bold; font-size: 11px;"
            )
            QMessageBox.critical(
                self,
                "Lỗi Khởi Tạo Mô Hình",
                f"Không thể nạp mô hình giọng nói VieNeu-TTS v3 Turbo:\n\n{error}\n\n"
                "Vui lòng kiểm tra lại tài nguyên thư mục models.",
            )

    def _update_license_badge(self):
        info = tts_service.get_license_info()
        is_active = info.get("is_active", False)
        plan = info.get("plan") or ""
        rem = info.get("remaining_formatted") or ""

        if is_active:
            if plan == "KEY-PERM":
                txt = "● Bản quyền: Vĩnh viễn"
            else:
                txt = f"● Bản quyền: {plan} ({rem})"
            self.license_badge.setText(txt)
            self.license_badge.setStyleSheet(
                "background-color: rgba(22, 135, 255, 0.15); color: #22D3EE; "
                "border: 1px solid #1687FF; border-radius: 12px; padding: 4px 10px; font-weight: bold; font-size: 11px;"
            )
        else:
            status = info.get("status")
            if status == "expired":
                self.license_badge.setText("✕ Bản quyền đã hết hạn")
            else:
                self.license_badge.setText("⚠️ Chưa kích hoạt bản quyền")
            self.license_badge.setStyleSheet(
                "background-color: rgba(239, 68, 68, 0.15); color: #EF4444; "
                "border: 1px solid #EF4444; border-radius: 12px; padding: 4px 10px; font-weight: bold; font-size: 11px;"
            )

    def _check_initial_license(self):
        info = tts_service.get_license_info()
        if not info.get("is_active"):
            self._open_activation_dialog()

    def _open_activation_dialog(self):
        dlg = LicenseActivationDialog(self)
        dlg.license_activated.connect(self._on_license_activated)
        dlg.exec()

    def _on_license_activated(self, info: dict):
        self._update_license_badge()
        self.page_about.reload_license_info()

    def _on_audio_generated(self, res: dict):
        self.page_history.reload_history()

    def _on_voice_cloned(self, vname: str):
        self.page_synth.refresh_voices()
        self.page_batch.refresh_voices()
        self.page_voices.reload_voices()

    def _on_voices_updated(self):
        self.page_synth.refresh_voices()
        self.page_batch.refresh_voices()

    def closeEvent(self, event):
        """Dọn dẹp sạch tài nguyên và dừng bộ phát âm thanh khi đóng cửa sổ."""
        try:
            audio_player.stop()
        except Exception:
            pass
        event.accept()
