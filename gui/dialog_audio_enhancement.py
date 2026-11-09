"""gui/dialog_audio_enhancement.py — HỘP THOẠI NÂNG CẤP ÂM THANH DSP & SO SÁNH A/B
=============================================================================
Giao diện xử lý nâng cao âm thanh Phase 8 chuyên nghiệp cho T-TTS v3.1.0:
- Chọn cấu hình nhanh (Presets): Phát thanh Quân đội, Giọng ấm, Ngoài trời, Podcast.
- Tinh chỉnh thông số: Giảm nhiễu (Noise Reduction), 5-Band Voice EQ, Chuẩn hóa EBU R128 LUFS,
  De-Esser (Giảm âm xuýt rít), Dynamic Speech Compressor.
- So sánh A/B thời gian thực (A/B Test Preview): Chuyển đổi qua lại giữa bản Gốc và bản Đã xử lý
  ngay lập tức tại cùng vị trí con trỏ phát (Synchronized Playback).
- Chạy ngầm bằng Worker Thread không gây đơ giao diện.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QSlider,
    QComboBox,
    QCheckBox,
    QProgressBar,
    QRadioButton,
    QButtonGroup,
    QFrame,
    QScrollArea,
    QMessageBox,
)

from backend.audio_enhancement import (
    AudioEnhancementConfig,
    PRESETS,
    audio_enhancement_engine,
)
from backend.audio_player import audio_player


# =============================================================================
# WORKER THREAD XỬ LÝ DSP ÂM THANH
# =============================================================================
class AudioEnhancementWorker(QThread):
    """Tiểu trình xử lý chuỗi filter DSP chạy ngầm."""

    progress_updated = Signal(int, str)
    finished_success = Signal(dict)
    finished_error = Signal(str)

    def __init__(self, input_path: Path, output_path: Path, config: AudioEnhancementConfig):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.config = config

    def run(self):
        try:
            def _cb(p, msg):
                self.progress_updated.emit(p, msg)

            res = audio_enhancement_engine.enhance_audio(
                input_file=self.input_path,
                output_file=self.output_path,
                config=self.config,
                progress_callback=_cb,
            )

            if res.get("success", False):
                self.finished_success.emit(res)
            else:
                self.finished_error.emit(res.get("error") or "Lỗi xử lý âm thanh.")
        except Exception as e:
            self.finished_error.emit(str(e))


# =============================================================================
# HỘP THOẠI NÂNG CẤP ÂM THANH CHÍNH
# =============================================================================
class AudioEnhancementDialog(QDialog):
    """Hộp thoại cấu hình DSP và nghe thử so sánh A/B."""

    def __init__(self, input_wav_path: str | Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.input_path = Path(input_wav_path).resolve()
        self.setWindowTitle("✨ Bộ Nâng Cấp Âm Thanh DSP Chuyên Nghiệp — T-TTS")
        self.setMinimumSize(820, 680)
        self.resize(860, 720)

        self.enhanced_temp_path = Path(tempfile.gettempdir()) / f"tts_enhanced_{os.getpid()}_{id(self)}.wav"
        self.current_preview_source: str = "enhanced"  # "original" | "enhanced"
        self.last_playback_pos_ms: int = 0
        self.is_processing: bool = False
        self.processed_ready: bool = False
        self.worker: Optional[AudioEnhancementWorker] = None

        self._init_ui()
        self._load_preset("broadcast_military")
        self._trigger_processing()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(12)

        # 1. HEADER & PRESET SELECTOR
        header_card = QFrame()
        header_card.setStyleSheet("background-color: #122215; border: 1px solid #27472A; border-radius: 6px; padding: 8px;")
        hc_layout = QHBoxLayout(header_card)

        lbl_title = QLabel("✨ <b>BỘ XỬ LÝ NÂNG CAO CHẤT LƯỢNG ÂM THANH (DSP)</b>")
        lbl_title.setStyleSheet("color: #4ADE80; font-size: 14px;")
        hc_layout.addWidget(lbl_title)
        hc_layout.addStretch()

        hc_layout.addWidget(QLabel("Cấu hình sẵn (Preset):"))
        self.combo_presets = QComboBox()
        self.combo_presets.addItem("🎙️ Phát thanh Quân đội tiêu chuẩn", "broadcast_military")
        self.combo_presets.addItem("📖 Giọng ấm truyền cảm (Văn học)", "warm_narrative")
        self.combo_presets.addItem("📢 Rõ tiếng ngoài trời / Loa truyền thanh", "outdoor_loudspeaker")
        self.combo_presets.addItem("🎧 Phòng thu Podcast hiện đại", "podcast_studio")
        self.combo_presets.addItem("⚙️ Tùy chỉnh thủ công", "custom")
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        hc_layout.addWidget(self.combo_presets)

        main_layout.addWidget(header_card)

        # 2. KHU VỰC ĐIỀU CHỈNH THÔNG SỐ (SCROLLABLE DSP PARAMETERS)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        sc_layout = QVBoxLayout(scroll_content)
        sc_layout.setSpacing(12)

        # Module A: Giảm nhiễu thích ứng
        box_nr = QFrame()
        box_nr.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 10px;")
        bnr_layout = QVBoxLayout(box_nr)
        self.cb_nr = QCheckBox("1. Giảm nhiễu thích ứng (Adaptive Noise Reduction)")
        self.cb_nr.setStyleSheet("font-weight: bold; color: #60A5FA;")
        self.cb_nr.toggled.connect(self._on_param_changed)
        bnr_layout.addWidget(self.cb_nr)

        row_nr = QHBoxLayout()
        row_nr.addWidget(QLabel("Mức giảm:"))
        self.slider_nr = QSlider(Qt.Horizontal)
        self.slider_nr.setRange(6, 24)
        self.slider_nr.setValue(12)
        self.slider_nr.valueChanged.connect(self._on_param_changed)
        row_nr.addWidget(self.slider_nr)
        self.lbl_nr_val = QLabel("12 dB")
        row_nr.addWidget(self.lbl_nr_val)

        row_nr.addWidget(QLabel("Cắt tần số thấp:"))
        self.slider_hp = QSlider(Qt.Horizontal)
        self.slider_hp.setRange(50, 150)
        self.slider_hp.setValue(80)
        self.slider_hp.valueChanged.connect(self._on_param_changed)
        row_nr.addWidget(self.slider_hp)
        self.lbl_hp_val = QLabel("80 Hz")
        row_nr.addWidget(self.lbl_hp_val)
        bnr_layout.addLayout(row_nr)
        sc_layout.addWidget(box_nr)

        # Module B: Voice Clarity EQ 5-Band
        box_eq = QFrame()
        box_eq.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 10px;")
        beq_layout = QVBoxLayout(box_eq)
        self.cb_eq = QCheckBox("2. Cân bằng âm thanh giọng nói tiếng Việt (Voice Clarity EQ)")
        self.cb_eq.setStyleSheet("font-weight: bold; color: #F59E0B;")
        self.cb_eq.toggled.connect(self._on_param_changed)
        beq_layout.addWidget(self.cb_eq)

        grid_eq = QGridLayout()
        # Warmth (250 Hz)
        grid_eq.addWidget(QLabel("Độ ấm / Dầy (250Hz):"), 0, 0)
        self.slider_warmth = QSlider(Qt.Horizontal)
        self.slider_warmth.setRange(-6, 6)
        self.slider_warmth.setValue(2)
        self.slider_warmth.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_warmth, 0, 1)
        self.lbl_warmth_val = QLabel("+2.0 dB")
        grid_eq.addWidget(self.lbl_warmth_val, 0, 2)

        # Boxiness (600 Hz)
        grid_eq.addWidget(QLabel("Cắt nghẹt tiếng (600Hz):"), 0, 3)
        self.slider_boxiness = QSlider(Qt.Horizontal)
        self.slider_boxiness.setRange(-6, 6)
        self.slider_boxiness.setValue(-2)
        self.slider_boxiness.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_boxiness, 0, 4)
        self.lbl_boxiness_val = QLabel("-2.0 dB")
        grid_eq.addWidget(self.lbl_boxiness_val, 0, 5)

        # Presence (3500 Hz)
        grid_eq.addWidget(QLabel("Rõ chữ tiếng Việt (3.5kHz):"), 1, 0)
        self.slider_presence = QSlider(Qt.Horizontal)
        self.slider_presence.setRange(-6, 8)
        self.slider_presence.setValue(3)
        self.slider_presence.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_presence, 1, 1)
        self.lbl_presence_val = QLabel("+3.0 dB")
        grid_eq.addWidget(self.lbl_presence_val, 1, 2)

        # Air (10 kHz)
        grid_eq.addWidget(QLabel("Độ thoáng không gian (10kHz):"), 1, 3)
        self.slider_air = QSlider(Qt.Horizontal)
        self.slider_air.setRange(-6, 6)
        self.slider_air.setValue(2)
        self.slider_air.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_air, 1, 4)
        self.lbl_air_val = QLabel("+2.0 dB")
        grid_eq.addWidget(self.lbl_air_val, 1, 5)

        beq_layout.addLayout(grid_eq)
        sc_layout.addWidget(box_eq)

        # Module C: De-Esser & Dynamic Compressor
        box_dyn = QFrame()
        box_dyn.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 10px;")
        bdyn_layout = QVBoxLayout(box_dyn)
        lbl_dyn_title = QLabel("3. Xử lý động lực học & Triệt tiêu âm gió (Dynamics & De-Esser)")
        lbl_dyn_title.setStyleSheet("font-weight: bold; color: #EC4899;")
        bdyn_layout.addWidget(lbl_dyn_title)

        row_dyn = QHBoxLayout()
        self.cb_deesser = QCheckBox("Bật De-Esser (Giảm xì /s/, /x/)")
        self.cb_deesser.toggled.connect(self._on_param_changed)
        row_dyn.addWidget(self.cb_deesser)

        row_dyn.addSpacing(20)
        self.cb_compressor = QCheckBox("Bật Compressor (Nén cân bằng giọng)")
        self.cb_compressor.toggled.connect(self._on_param_changed)
        row_dyn.addWidget(self.cb_compressor)

        row_dyn.addStretch()
        bdyn_layout.addLayout(row_dyn)
        sc_layout.addWidget(box_dyn)

        # Module D: Chuẩn hóa âm lượng EBU R128 LUFS
        box_lufs = QFrame()
        box_lufs.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 10px;")
        blufs_layout = QVBoxLayout(box_lufs)
        self.cb_loudnorm = QCheckBox("4. Chuẩn hóa âm lượng phát thanh (EBU R128 LUFS Normalization)")
        self.cb_loudnorm.setStyleSheet("font-weight: bold; color: #4ADE80;")
        self.cb_loudnorm.toggled.connect(self._on_param_changed)
        blufs_layout.addWidget(self.cb_loudnorm)

        row_lufs = QHBoxLayout()
        row_lufs.addWidget(QLabel("Mục tiêu LUFS:"))
        self.slider_lufs = QSlider(Qt.Horizontal)
        self.slider_lufs.setRange(-24, -12)
        self.slider_lufs.setValue(-16)
        self.slider_lufs.valueChanged.connect(self._on_param_changed)
        row_lufs.addWidget(self.slider_lufs)
        self.lbl_lufs_val = QLabel("-16.0 LUFS")
        row_lufs.addWidget(self.lbl_lufs_val)

        row_lufs.addSpacing(20)
        row_lufs.addWidget(QLabel("True Peak trần:"))
        self.slider_tp = QSlider(Qt.Horizontal)
        self.slider_tp.setRange(-30, -5)
        self.slider_tp.setValue(-15)
        self.slider_tp.valueChanged.connect(self._on_param_changed)
        row_lufs.addWidget(self.slider_tp)
        self.lbl_tp_val = QLabel("-1.5 dBFS")
        row_lufs.addWidget(self.lbl_tp_val)

        blufs_layout.addLayout(row_lufs)
        sc_layout.addWidget(box_lufs)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        # 3. KHU VỰC SO SÁNH A/B (A/B TESTING & PLAYBACK)
        ab_card = QFrame()
        ab_card.setStyleSheet("background-color: #122215; border: 2px solid #22C55E; border-radius: 8px; padding: 10px;")
        ab_layout = QVBoxLayout(ab_card)

        ab_header = QHBoxLayout()
        ab_header.addWidget(QLabel("🎧 <b>SO SÁNH NGHE THỬ A/B (ĐỒNG BỘ THỜI GIAN THỰC):</b>"))
        ab_header.addStretch()

        self.btn_preview_play = QPushButton("▶ Nghe Thử")
        self.btn_preview_play.setProperty("class", "PrimaryBtn")
        self.btn_preview_play.clicked.connect(self._toggle_preview_playback)
        ab_header.addWidget(self.btn_preview_play)

        self.btn_preview_stop = QPushButton("⏹ Dừng")
        self.btn_preview_stop.clicked.connect(self._stop_preview_playback)
        ab_header.addWidget(self.btn_preview_stop)
        ab_layout.addLayout(ab_header)

        # Nút chuyển đổi nguồn A/B tức thì
        ab_switch_row = QHBoxLayout()
        ab_switch_row.setSpacing(25)

        self.rb_original = QRadioButton("🔵 [A] Âm Thanh Gốc (Original)")
        self.rb_original.setStyleSheet("font-size: 13px; color: #60A5FA; font-weight: bold;")
        self.rb_original.toggled.connect(self._on_ab_source_toggled)

        self.rb_enhanced = QRadioButton("🟢 [B] Âm Thanh Đã Nâng Cấp DSP (Enhanced)")
        self.rb_enhanced.setStyleSheet("font-size: 13px; color: #4ADE80; font-weight: bold;")
        self.rb_enhanced.setChecked(True)
        self.rb_enhanced.toggled.connect(self._on_ab_source_toggled)

        self.bg_ab = QButtonGroup(self)
        self.bg_ab.addButton(self.rb_original)
        self.bg_ab.addButton(self.rb_enhanced)

        ab_switch_row.addStretch()
        ab_switch_row.addWidget(self.rb_original)
        ab_switch_row.addWidget(self.rb_enhanced)
        ab_switch_row.addStretch()
        ab_layout.addLayout(ab_switch_row)

        self.lbl_dsp_status = QLabel("Trạng thái: Sẵn sàng.")
        self.lbl_dsp_status.setStyleSheet("color: #94A3B8; font-size: 11px;")
        ab_layout.addWidget(self.lbl_dsp_status)

        main_layout.addWidget(ab_card)

        # 4. NÚT ĐIỀU KHIỂN DƯỚI CÙNG (CONFIRM / CANCEL)
        bottom_row = QHBoxLayout()
        self.btn_cancel = QPushButton("Hủy Bỏ")
        self.btn_cancel.clicked.connect(self._on_cancel)
        bottom_row.addWidget(self.btn_cancel)

        bottom_row.addStretch()

        self.btn_apply = QPushButton("✨ Áp Dụng Nâng Cấp Vào Dự Án")
        self.btn_apply.setProperty("class", "PrimaryBtn")
        self.btn_apply.setMinimumHeight(36)
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        bottom_row.addWidget(self.btn_apply)

        main_layout.addLayout(bottom_row)

    # =========================================================================
    # LOGIC CẤU HÌNH & XỬ LÝ DSP
    # =========================================================================
    def _load_preset(self, preset_key: str):
        if preset_key not in PRESETS:
            return
        cfg = PRESETS[preset_key]

        self.cb_nr.setChecked(cfg.enable_noise_reduction)
        self.slider_nr.setValue(int(cfg.noise_reduction_db))
        self.slider_hp.setValue(int(cfg.highpass_freq))

        self.cb_eq.setChecked(cfg.enable_eq)
        self.slider_warmth.setValue(int(cfg.eq_warmth_gain))
        self.slider_boxiness.setValue(int(cfg.eq_boxiness_gain))
        self.slider_presence.setValue(int(cfg.eq_presence_gain))
        self.slider_air.setValue(int(cfg.eq_air_gain))

        self.cb_deesser.setChecked(cfg.enable_deesser)
        self.cb_compressor.setChecked(cfg.enable_compressor)

        self.cb_loudnorm.setChecked(cfg.enable_loudnorm)
        self.slider_lufs.setValue(int(cfg.target_lufs))
        self.slider_tp.setValue(int(cfg.true_peak * 10))

    def _get_current_config(self) -> AudioEnhancementConfig:
        return AudioEnhancementConfig(
            enable_noise_reduction=self.cb_nr.isChecked(),
            noise_reduction_db=float(self.slider_nr.value()),
            highpass_freq=float(self.slider_hp.value()),
            lowpass_freq=12000.0,
            enable_eq=self.cb_eq.isChecked(),
            eq_warmth_gain=float(self.slider_warmth.value()),
            eq_boxiness_gain=float(self.slider_boxiness.value()),
            eq_presence_gain=float(self.slider_presence.value()),
            eq_air_gain=float(self.slider_air.value()),
            enable_deesser=self.cb_deesser.isChecked(),
            enable_compressor=self.cb_compressor.isChecked(),
            enable_loudnorm=self.cb_loudnorm.isChecked(),
            target_lufs=float(self.slider_lufs.value()),
            true_peak=float(self.slider_tp.value()) / 10.0,
            preset_name=self.combo_presets.currentText(),
        )

    def _on_preset_changed(self, index: int):
        key = self.combo_presets.itemData(index)
        if key and key != "custom":
            self._load_preset(key)
            self._trigger_processing()

    def _on_param_changed(self):
        # Update text labels
        self.lbl_nr_val.setText(f"{self.slider_nr.value()} dB")
        self.lbl_hp_val.setText(f"{self.slider_hp.value()} Hz")
        self.lbl_warmth_val.setText(f"{self.slider_warmth.value():+d}.0 dB")
        self.lbl_boxiness_val.setText(f"{self.slider_boxiness.value():+d}.0 dB")
        self.lbl_presence_val.setText(f"{self.slider_presence.value():+d}.0 dB")
        self.lbl_air_val.setText(f"{self.slider_air.value():+d}.0 dB")
        self.lbl_lufs_val.setText(f"{self.slider_lufs.value():.1f} LUFS")
        self.lbl_tp_val.setText(f"{self.slider_tp.value() / 10.0:.1f} dBFS")

        self._trigger_processing()

    def _trigger_processing(self):
        """Khởi động xử lý file tạm thời để nghe thử so sánh."""
        if self.worker and self.worker.isRunning():
            return

        self.is_processing = True
        self.lbl_dsp_status.setText("⏳ Đang xử lý DSP âm thanh nền...")

        cfg = self._get_current_config()
        self.worker = AudioEnhancementWorker(
            input_path=self.input_path,
            output_path=self.enhanced_temp_path,
            config=cfg,
        )
        self.worker.finished_success.connect(self._on_worker_success)
        self.worker.finished_error.connect(self._on_worker_error)
        self.worker.start()

    def _on_worker_success(self, res: dict):
        self.is_processing = False
        self.processed_ready = True
        filters = res.get("applied_filters", [])
        self.lbl_dsp_status.setText(f"✅ Đã xử lý thành công! (Áp dụng {len(filters)} bộ lọc DSP)")

    def _on_worker_error(self, err: str):
        self.is_processing = False
        self.lbl_dsp_status.setText(f"❌ Lỗi DSP: {err}")

    # =========================================================================
    # SO SÁNH A/B ĐỒNG BỘ THỜI GIAN THỰC
    # =========================================================================
    def _toggle_preview_playback(self):
        if audio_player.state == "playing":
            self.last_playback_pos_ms = audio_player.get_position()
            audio_player.pause()
            self.btn_preview_play.setText("▶ Tiếp Tục")
        elif audio_player.state == "paused":
            audio_player.resume()
            self.btn_preview_play.setText("⏸ Tạm Dừng")
        else:
            self._start_preview_at(self.last_playback_pos_ms)

    def _stop_preview_playback(self):
        audio_player.stop()
        self.last_playback_pos_ms = 0
        self.btn_preview_play.setText("▶ Nghe Thử")

    def _on_ab_source_toggled(self):
        """Chuyển đổi nguồn A/B mượt mà không mất vị trí con trỏ phát."""
        is_enhanced = self.rb_enhanced.isChecked()
        new_source = "enhanced" if is_enhanced else "original"
        if new_source == self.current_preview_source:
            return

        self.current_preview_source = new_source

        # Nếu đang phát, chuyển đổi sang nguồn mới ngay tại thời điểm hiện tại
        if audio_player.state == "playing":
            curr_pos = audio_player.get_position()
            audio_player.stop()
            self._start_preview_at(curr_pos)

    def _start_preview_at(self, pos_ms: int):
        target_file = self.enhanced_temp_path if self.current_preview_source == "enhanced" else self.input_path
        if not target_file.is_file():
            target_file = self.input_path

        audio_player.play(str(target_file))
        if pos_ms > 0:
            audio_player.seek(pos_ms)
        self.btn_preview_play.setText("⏸ Tạm Dừng")

    def _on_apply_clicked(self):
        """Người dùng chấp thuận nâng cấp âm thanh."""
        self._stop_preview_playback()
        self.final_enhanced_path = self.enhanced_temp_path
        self.final_config = self._get_current_config()
        self.accept()

    def _on_cancel(self):
        self._stop_preview_playback()
        self.reject()

    def closeEvent(self, event):
        self._stop_preview_playback()
        super().closeEvent(event)
