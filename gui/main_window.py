"""gui/main_window.py — CỬA SỔ ỨNG DỤNG DESKTOP CHÍNH (QUÂN ĐỘI NHÂN DÂN VIỆT NAM)
==================================================================================
- Tích hợp Phù hiệu chính thức của QUÂN ĐỘI NHÂN DÂN VIỆT NAM.
- Nổi bật tác giả NGUYỄN VĂN TIỆP ở thanh điều hướng và trang Giới thiệu.
- Hỗ trợ chuyển đổi linh hoạt giữa 2 chế độ màu:
  * 🌙 RẰN RI K20 TỐI (Military K20 Dark)
  * ☀️ QUÂN ĐỘI SÁNG (Military K20 Light)
- Quản lý 8 trang nghiệp vụ chính, luồng nạp mô hình nền mượt mà.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QFrame,
    QMessageBox,
    QApplication,
)

from gui.styles import get_theme_qss, FRIENDLY_LIGHT_QSS
from gui.dialogs.license_dialog import LicenseDialog
from gui.pages.page_synthesize import PageSynthesize
from gui.pages.page_clone import PageClone
from gui.pages.page_batch import PageBatch
from gui.pages.page_broadcast import PageBroadcast
from gui.pages.page_podcast import PagePodcast
from gui.pages.page_voices import PageVoices
from gui.pages.page_history import PageHistory
from gui.pages.page_pron_dict import PagePronDict
from gui.pages.page_schedule import PageSchedule
from gui.pages.page_audio_studio import PageAudioStudio
from gui.pages.page_settings import PageSettings
from gui.pages.page_about import PageAbout
from gui.pages.page_guide import PageGuide

from backend.service import tts_service
from backend.version import APP_VERSION, APP_NAME, APP_DISPLAY_NAME, APP_AUTHOR


class ModelLoaderThread(QThread):
    """Tiểu trình nạp trước mô hình VieNeu-TTS v3 Turbo ONNX trong luồng nền."""
    loaded = Signal(bool, str)

    def run(self):
        try:
            ok = tts_service.initialize_model()
            if ok:
                self.loaded.emit(True, "VieNeu-TTS v3 Turbo (ONNX CPU) - Sẵn sàng")
            else:
                self.loaded.emit(False, tts_service._model_error or "Không thể nạp mô hình.")
        except Exception as e:
            self.loaded.emit(False, str(e))



class MainWindow(QMainWindow):
    """Cửa sổ ứng dụng desktop chính của T-TTS v3.0."""

    def __init__(self):
        super().__init__()
        self.setObjectName("MainRoot")
        self.setWindowTitle(f"{APP_DISPLAY_NAME} (Tác giả: {APP_AUTHOR})")
        self.setMinimumSize(1024, 700)
        self.resize(1300, 840)

        # Chế độ màu mặc định: k20_dark
        self.current_theme = "k20_dark"
        self.setStyleSheet(get_theme_qss(self.current_theme))

        # Đặt biểu tượng ứng dụng nếu có
        icon_path = self._find_app_icon()
        if icon_path:
            self.setWindowIcon(QIcon(str(icon_path)))

        self.nav_buttons: list[QPushButton] = []
        self._build_ui()

        # Nạp mô hình trong nền
        self.loader_thread: Optional[ModelLoaderThread] = None
        self._start_background_model_loader()

        # Cập nhật huy hiệu bản quyền
        self._update_license_badge()

        # Kiểm tra bản quyền sau khi hiển thị
        QTimer.singleShot(600, self._check_initial_license)

        # Kiểm tra cập nhật phần mềm trong nền
        QTimer.singleShot(1500, self._check_background_update)

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
        h_layout.setContentsMargins(16, 8, 16, 8)
        h_layout.setSpacing(12)

        # Logo Quân đội nhỏ trên header
        lbl_top_logo = QLabel()
        logo_path = Path(__file__).resolve().parent / "assets" / "logo_quan_doi.png"
        if not logo_path.exists():
            logo_path = Path.cwd() / "gui" / "assets" / "logo_quan_doi.png"
        if logo_path.exists():
            pm = QPixmap(str(logo_path)).scaled(32, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_top_logo.setPixmap(pm)
        else:
            lbl_top_logo.setText("⭐")
            lbl_top_logo.setStyleSheet("font-size: 24px; color: #FFD700;")
        h_layout.addWidget(lbl_top_logo)

        # Tiêu đề ứng dụng
        title_box = QVBoxLayout()
        title_box.setSpacing(1)

        title_lbl = QLabel(f"{APP_NAME} v{APP_VERSION} — HỆ THỐNG TRỢ LÝ GIỌNG NÓI QUÂN ĐỘI")
        title_lbl.setObjectName("AppTitle")
        title_box.addWidget(title_lbl)

        sub_lbl = QLabel("Chuyển Văn Bản Thành Giọng Nói Tiếng Việt")
        sub_lbl.setObjectName("AppSubtitle")
        title_box.addWidget(sub_lbl)

        h_layout.addLayout(title_box)
        h_layout.addStretch()

        # Badge trạng thái mô hình
        self.model_status_badge = QLabel("⏳ Đang nạp mô hình...")
        self.model_status_badge.setObjectName("BadgeModelLoading")
        self.model_status_badge.setAlignment(Qt.AlignCenter)
        h_layout.addWidget(self.model_status_badge)

        # Badge bản quyền
        self.license_badge = QPushButton("🛡️ Kiểm tra bản quyền...")
        self.license_badge.setObjectName("BadgeLicenseActive")
        self.license_badge.setCursor(Qt.PointingHandCursor)
        self.license_badge.clicked.connect(self._open_activation_dialog)
        h_layout.addWidget(self.license_badge)

        central_layout.addWidget(header)

        # -------------------------------------------------------------
        # 2. KHU VỰC THÂN CHÍNH (SIDEBAR + WORKSPACE)
        # -------------------------------------------------------------
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar điều hướng bên trái
        sidebar = QFrame()
        sidebar.setObjectName("NavFrame")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(8, 12, 8, 12)
        sb_layout.setSpacing(4)

        # Nhãn nhóm 1
        lbl_g1 = QLabel("Chức năng chính")
        lbl_g1.setProperty("class", "NavGroupLabel")
        sb_layout.addWidget(lbl_g1)

        nav_items = [
            ("🎙️  Tạo Giọng Nói", 0),
            ("🧬  Nhân Bản Giọng", 1),
            ("⚡  Xử Lý Hàng Loạt", 2),
            ("📻  Bản Tin Phát Thanh", 3),
            ("🎙️  Kịch Bản Podcast", 4),
            ("👥  Quản Lý Giọng", 5),
            ("📖  Từ Điển Phát Âm", 6),
            ("📜  Lịch Sử Tạo", 7),
            ("⏰  Lịch Phát Thanh", 8),
            ("🎚️  Biên Tập Studio", 9),
        ]
        for text, idx in nav_items:
            btn = QPushButton(text)
            btn.setProperty("class", "NavBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, index=idx: self._switch_tab(index))
            sb_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        # Nhãn nhóm 2
        lbl_g2 = QLabel("Hệ thống & Bản quyền")
        lbl_g2.setProperty("class", "NavGroupLabel")
        sb_layout.addWidget(lbl_g2)

        nav_items_2 = [
            ("⚙️  Cài Đặt & Cấu Hình", 10),
            ("🛡️  Bản Quyền & Tác Giả", 11),
            ("❓  Hướng Dẫn Sử Dụng", 12),
        ]
        for text, idx in nav_items_2:
            btn = QPushButton(text)
            btn.setProperty("class", "NavBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, index=idx: self._switch_tab(index))
            sb_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sb_layout.addStretch()

        btn_open_audio_dir = QPushButton("📁  Thư Mục Âm Thanh")
        btn_open_audio_dir.setProperty("class", "SecondaryBtn")
        btn_open_audio_dir.setCursor(Qt.PointingHandCursor)
        btn_open_audio_dir.setToolTip("Mở thư mục chứa các file âm thanh đã xuất trên máy tính")
        btn_open_audio_dir.clicked.connect(lambda: tts_service.open_output_folder())
        sb_layout.addWidget(btn_open_audio_dir)

        # =========================================================================
        # BANNER TÁC GIẢ NỔI BẬT Ở CHÂN SIDEBAR (KÈM PHÙ HIỆU QUÂN ĐỘI)
        # =========================================================================
        author_sidebar_card = QFrame()
        author_sidebar_card.setObjectName("SidebarAuthorCard")
        author_sidebar_card.setCursor(Qt.PointingHandCursor)
        author_sidebar_card.mousePressEvent = lambda e: self._switch_tab(11)

        asc_layout = QHBoxLayout(author_sidebar_card)
        asc_layout.setContentsMargins(8, 8, 8, 8)
        asc_layout.setSpacing(8)

        lbl_asc_logo = QLabel()
        if logo_path.exists():
            pm_sb = QPixmap(str(logo_path)).scaled(32, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_asc_logo.setPixmap(pm_sb)
        else:
            lbl_asc_logo.setText("⭐")
            lbl_asc_logo.setStyleSheet("font-size: 22px; color: #FFD700;")
        asc_layout.addWidget(lbl_asc_logo)

        asc_info = QVBoxLayout()
        asc_info.setSpacing(2)

        lbl_p = QLabel("TÁC GIẢ")
        lbl_p.setStyleSheet("color: #FFD700; font-size: 11px; font-weight: 800; letter-spacing: 1px;")
        asc_info.addWidget(lbl_p)

        lbl_author_sb = QLabel("Nguyễn Văn Tiệp")
        lbl_author_sb.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: 900; letter-spacing: 0.3px;")
        asc_info.addWidget(lbl_author_sb)

        asc_layout.addLayout(asc_info, 1)
        sb_layout.addWidget(author_sidebar_card)

        body_layout.addWidget(sidebar)

        # -------------------------------------------------------------
        # 3. WORKSPACE (QSTACKEDWIDGET 11 TRANG)
        # -------------------------------------------------------------
        self.stack = QStackedWidget()

        self.page_synth = PageSynthesize()
        self.page_clone = PageClone()
        self.page_batch = PageBatch()
        self.page_broadcast = PageBroadcast()
        self.page_podcast = PagePodcast()
        self.page_voices = PageVoices()
        self.page_dict = PagePronDict()
        self.page_history = PageHistory()
        self.page_schedule = PageSchedule()
        self.page_audio_studio = PageAudioStudio()
        self.page_settings = PageSettings()
        self.page_about = PageAbout()
        self.page_guide = PageGuide()

        self.stack.addWidget(self.page_synth)        # 0
        self.stack.addWidget(self.page_clone)        # 1
        self.stack.addWidget(self.page_batch)        # 2
        self.stack.addWidget(self.page_broadcast)    # 3
        self.stack.addWidget(self.page_podcast)      # 4
        self.stack.addWidget(self.page_voices)       # 5
        self.stack.addWidget(self.page_dict)         # 6
        self.stack.addWidget(self.page_history)      # 7
        self.stack.addWidget(self.page_schedule)     # 8
        self.stack.addWidget(self.page_audio_studio) # 9
        self.stack.addWidget(self.page_settings)     # 10
        self.stack.addWidget(self.page_about)        # 11
        self.stack.addWidget(self.page_guide)        # 12

        # Kết nối sự kiện giữa các trang
        self.page_synth.audio_generated.connect(lambda _: self.page_history.reload_history())
        self.page_synth.send_to_audio_studio.connect(self._on_synth_to_audio_studio)
        self.page_synth.send_to_broadcast.connect(self._on_synth_to_broadcast)
        self.page_audio_studio.send_to_broadcast.connect(self._on_audio_studio_to_broadcast)
        self.page_audio_studio.send_to_schedule.connect(self._on_audio_studio_to_schedule)
        self.page_clone.voice_cloned.connect(self._on_voice_cloned)
        self.page_voices.voices_updated.connect(self._on_voices_updated)
        self.page_about.request_open_activation.connect(self._open_activation_dialog)
        self.page_batch.transfer_to_broadcast.connect(self._on_transfer_to_broadcast)

        body_layout.addWidget(self.stack, 1)
        central_layout.addWidget(body_widget, 1)
        self.setCentralWidget(central)

        # Chọn tab mặc định: 0 (Tạo Giọng Nói)
        self._switch_tab(0)

    def _switch_tab(self, index: int):
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            for i, btn in enumerate(self.nav_buttons):
                is_active = (i == index)
                btn.setChecked(is_active)
                btn.setProperty("active", "true" if is_active else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)

            # Tự động làm mới dữ liệu trang khi người dùng mở
            current_widget = self.stack.currentWidget()
            if hasattr(current_widget, "reload_history"):
                current_widget.reload_history()
            elif hasattr(current_widget, "reload_voices"):
                current_widget.reload_voices()
            elif hasattr(current_widget, "reload_license_info"):
                current_widget.reload_license_info()

    def _start_background_model_loader(self):
        self.model_status_badge.setText("⏳ Đang nạp mô hình...")
        self.model_status_badge.setObjectName("BadgeModelLoading")
        self.model_status_badge.style().unpolish(self.model_status_badge)
        self.model_status_badge.style().polish(self.model_status_badge)

        self.loader_thread = ModelLoaderThread()
        self.loader_thread.loaded.connect(self._on_model_loaded)
        self.loader_thread.start()

    def _on_model_loaded(self, success: bool, message: str):
        if success:
            self.model_status_badge.setText("🟢 Mô hình: VieNeu-TTS v3 Turbo ONNX (Sẵn sàng)")
            self.model_status_badge.setObjectName("BadgeModelReady")
            # Cập nhật danh sách giọng cho trang Tạo giọng nói
            if hasattr(self.page_synth, "refresh_voices"):
                self.page_synth.refresh_voices()
        else:
            self.model_status_badge.setText("🔴 Lỗi nạp mô hình")
            self.model_status_badge.setObjectName("BadgeModelError")
            self.model_status_badge.setToolTip(f"Chi tiết lỗi: {message}")

        self.model_status_badge.style().unpolish(self.model_status_badge)
        self.model_status_badge.style().polish(self.model_status_badge)

    def _update_license_badge(self):
        try:
            info = tts_service.get_license_info() or {}
        except Exception:
            info = {}

        status = str(info.get("status") or "unknown").lower()
        plan = str(info.get("plan") or "none").upper()
        rem_str = str(info.get("remaining_formatted") or "")

        if status == "active":
            if "PERM" in plan or plan == "PERMANENT":
                self.license_badge.setText("⭐ Bản quyền: Vĩnh Viễn")
            else:
                self.license_badge.setText(f"🛡️ Bản quyền ({plan}): {rem_str}")
        elif status == "trial":
            self.license_badge.setText(f"⏳ Dùng thử: {rem_str}")
        elif status == "expired":
            self.license_badge.setText("⚠️ Bản quyền đã hết hạn")
        else:
            self.license_badge.setText("🔑 Chưa kích hoạt")

    def _check_initial_license(self):
        try:
            info = tts_service.get_license_info() or {}
        except Exception:
            info = {}
        if not info.get("is_active", False):
            self._open_activation_dialog()

    def _open_activation_dialog(self):
        dlg = LicenseDialog(self)
        dlg.setStyleSheet(FRIENDLY_LIGHT_QSS)
        dlg.license_activated.connect(self._on_license_activated)
        dlg.exec()

    def _on_license_activated(self, info: dict):
        self._update_license_badge()
        if hasattr(self.page_about, "reload_license_info"):
            self.page_about.reload_license_info()
        plan_str = str(info.get("plan") or "").upper()
        QMessageBox.information(
            self,
            "Kích Hoạt Thành Công",
            f"Bản quyền hệ thống {APP_NAME} v{APP_VERSION} đã được kích hoạt thành công!\n"
            f"Gói bản quyền: {plan_str}"
        )

    def _on_transfer_to_broadcast(self, items: list):
        self.page_broadcast.add_batch_items(items)
        self._switch_tab(3)

    def _on_synth_to_audio_studio(self, file_path: str):
        self._switch_tab(9)
        self.page_audio_studio.load_audio_file(file_path)

    def _on_synth_to_broadcast(self, seg_dict: dict):
        self._switch_tab(3)
        self.page_broadcast.add_segment(seg_dict)

    def _on_audio_studio_to_broadcast(self, seg_dict: dict):
        self._switch_tab(3)
        self.page_broadcast.add_segment(seg_dict)

    def _on_audio_studio_to_schedule(self, item_dict: dict):
        self._switch_tab(8)
        self.page_schedule.add_schedule_for_audio(item_dict.get("file_path", ""), item_dict.get("title", ""))

    def _check_background_update(self):
        """Khởi chạy tiểu trình kiểm tra cập nhật nền (không làm chậm ứng dụng)."""
        try:
            from backend.updater import CheckUpdateWorker, UpdateManager
            self.update_manager = UpdateManager(tts_service.data_dir)
            if not self.update_manager.config.get("auto_check_on_startup", True):
                return

            self.update_check_worker = CheckUpdateWorker(tts_service.data_dir)
            self.update_check_worker.check_finished.connect(self._on_background_update_checked)
            self.update_check_worker.start()
        except Exception:
            pass

    def _on_background_update_checked(self, info):
        if info and getattr(info, "available", False):
            from gui.dialog_update import UpdateDialog
            dlg = UpdateDialog(self.update_manager, info, self)
            dlg.exec()

    def _on_voice_cloned(self, voice_id: str):
        if hasattr(self.page_synth, "refresh_voices"):
            self.page_synth.refresh_voices()
        if hasattr(self.page_batch, "refresh_voices"):
            self.page_batch.refresh_voices()
        if hasattr(self.page_voices, "reload_voices"):
            self.page_voices.reload_voices()

    def _on_voices_updated(self):
        if hasattr(self.page_synth, "refresh_voices"):
            self.page_synth.refresh_voices()
        if hasattr(self.page_batch, "refresh_voices"):
            self.page_batch.refresh_voices()

    def closeEvent(self, event):
        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.wait(1000)
        event.accept()
