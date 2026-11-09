"""gui/dialog_audio_enhancement.py — HỘP THOẠI NÂNG CẤP ÂM THANH DSP & SO SÁNH A/B
=============================================================================
Giao diện xử lý nâng cao âm thanh Phase 8 chuyên nghiệp cho T-TTS v3.1.0:
- Chọn cấu hình nhanh (Presets): Thuyết minh chuyên nghiệp, Chuẩn EBU R128, Phát thanh Quân đội, Giọng ấm, Ngoài trời, Podcast.
- Tinh chỉnh 3 module cốt lõi:
  1. Giảm nhiễu thích ứng (Noise Reduction afftdn + Highpass + Lowpass). Không áp dụng mặc định cho TTS sạch.
  2. Equalizer tối ưu giọng nói (Voice Clarity EQ 6 dải: Bass 100Hz, Warmth 250Hz, Boxiness 600Hz, Presence 3.5kHz, Treble 8kHz, Air 10kHz).
  3. Chuẩn hóa âm lượng EBU R128 LUFS (-16 LUFS Voice/Podcast, -23 LUFS Broadcast, True Peak Ceiling -1.5 dBFS).
- Đo đạc thông số LUFS thời gian thực (Input vs Output Loudness Metering).
- Master Bypass và So sánh A/B thời gian thực (A/B Test Preview) đồng bộ vị trí con trỏ phát.
- Tiến trình nền (Worker Thread) không đơ UI, có thể Hủy bỏ (Cancel) an toàn.
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
# WORKER THREAD XỬ LÝ DSP ÂM THANH CÓ KHẢ NĂNG HỦY (CANCELLATION)
# =============================================================================
class AudioEnhancementWorker(QThread):
    """Tiểu trình xử lý chuỗi filter DSP chạy ngầm hỗ trợ dừng tức thì."""

    progress_updated = Signal(int, str)
    finished_success = Signal(dict)
    finished_error = Signal(str)

    def __init__(self, input_path: Path, output_path: Path, config: AudioEnhancementConfig):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.config = config
        self._is_cancelled = False

    def cancel(self):
        """Yêu cầu dừng tiến trình xử lý."""
        self._is_cancelled = True

    def run(self):
        try:
            def _cb(p, msg):
                if not self._is_cancelled:
                    self.progress_updated.emit(p, msg)

            res = audio_enhancement_engine.enhance_audio(
                input_file=self.input_path,
                output_file=self.output_path,
                config=self.config,
                progress_callback=_cb,
                cancel_check=lambda: self._is_cancelled,
            )

            if self._is_cancelled or res.get("cancelled"):
                self.finished_error.emit("Đã hủy xử lý.")
                return

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
    """Hộp thoại cấu hình DSP, đo lường LUFS và nghe thử so sánh A/B."""

    def __init__(self, input_wav_path: str | Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.input_path = Path(input_wav_path).resolve()
        self.setWindowTitle("✨ Bộ Nâng Cấp Âm Thanh DSP & Chuẩn Hóa LUFS — T-TTS")
        self.setMinimumSize(860, 720)
        self.resize(900, 760)

        self.enhanced_temp_path = Path(tempfile.gettempdir()) / f"tts_enhanced_{os.getpid()}_{id(self)}.wav"
        self.current_preview_source: str = "enhanced"  # "original" | "enhanced"
        self.last_playback_pos_ms: int = 0
        self.is_processing: bool = False
        self.processed_ready: bool = False
        self.is_bypass: bool = False
        self.worker: Optional[AudioEnhancementWorker] = None

        self.input_lufs: Optional[float] = None
        self.input_tp: Optional[float] = None
        self.output_lufs: Optional[float] = None
        self.output_tp: Optional[float] = None

        self._init_ui()
        self._measure_input_loudness()
        self._load_preset("voiceover_narrative")
        self._trigger_processing()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        # 1. HEADER & PRESET SELECTOR & BYPASS
        header_card = QFrame()
        header_card.setStyleSheet("background-color: #122215; border: 1px solid #27472A; border-radius: 6px; padding: 8px;")
        hc_layout = QHBoxLayout(header_card)

        lbl_title = QLabel("✨ <b>BỘ XỬ LÝ NÂNG CAO CHẤT LƯỢNG ÂM THANH (DSP)</b>")
        lbl_title.setStyleSheet("color: #4ADE80; font-size: 14px;")
        hc_layout.addWidget(lbl_title)
        hc_layout.addStretch()

        # Nút Master Bypass
        self.btn_bypass = QPushButton("🔊 Bypass: TẮT")
        self.btn_bypass.setCheckable(True)
        self.btn_bypass.setChecked(False)
        self.btn_bypass.setStyleSheet("""
            QPushButton { background-color: #1E293B; color: #94A3B8; border: 1px solid #475569; padding: 5px 12px; border-radius: 4px; font-weight: bold; }
            QPushButton:checked { background-color: #B91C1C; color: #FFFFFF; border: 1px solid #EF4444; }
        """)
        self.btn_bypass.toggled.connect(self._on_bypass_toggled)
        hc_layout.addWidget(self.btn_bypass)

        hc_layout.addSpacing(10)
        hc_layout.addWidget(QLabel("Cấu hình (Preset):"))
        self.combo_presets = QComboBox()
        self.combo_presets.addItem("🎙️ Thuyết minh chuyên nghiệp (Voiceover / Giảng bài)", "voiceover_narrative")
        self.combo_presets.addItem("📻 Chuẩn truyền thanh EBU R128 (-23 LUFS)", "broadcast_standard_ebu")
        self.combo_presets.addItem("🎖️ Phát thanh Quân đội tiêu chuẩn (-16 LUFS)", "broadcast_military")
        self.combo_presets.addItem("📖 Giọng ấm truyền cảm (Văn học)", "warm_narrative")
        self.combo_presets.addItem("📢 Rõ tiếng ngoài trời / Loa phóng thanh (-14 LUFS)", "outdoor_loudspeaker")
        self.combo_presets.addItem("🎧 Phòng thu Podcast hiện đại (-16 LUFS)", "podcast_studio")
        self.combo_presets.addItem("⚙️ Tùy chỉnh thủ công", "custom")
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        hc_layout.addWidget(self.combo_presets)

        main_layout.addWidget(header_card)

        # 2. BẢNG ĐO ĐẠC ĐỘ TO THỜI GIAN THỰC (LOUDNESS METERING BAR)
        meter_card = QFrame()
        meter_card.setStyleSheet("background-color: #0A140D; border: 1px solid #1E3A24; border-radius: 6px; padding: 6px 12px;")
        mc_layout = QHBoxLayout(meter_card)
        self.lbl_meter_in = QLabel("📊 <b>Độ to đầu vào:</b> Đang đo...")
        self.lbl_meter_in.setStyleSheet("color: #60A5FA; font-size: 12px;")
        mc_layout.addWidget(self.lbl_meter_in)

        mc_layout.addStretch()

        self.lbl_meter_out = QLabel("✨ <b>Độ to sau xử lý:</b> Chưa xử lý")
        self.lbl_meter_out.setStyleSheet("color: #4ADE80; font-size: 12px;")
        mc_layout.addWidget(self.lbl_meter_out)
        main_layout.addWidget(meter_card)

        # 3. KHU VỰC ĐIỀU CHỈNH THÔNG SỐ (SCROLLABLE DSP PARAMETERS)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        sc_layout = QVBoxLayout(scroll_content)
        sc_layout.setSpacing(10)

        # Module 1: Giảm nhiễu thích ứng (Noise Reduction)
        box_nr = QFrame()
        box_nr.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 10px;")
        bnr_layout = QVBoxLayout(box_nr)

        nr_header = QHBoxLayout()
        self.cb_nr = QCheckBox("1. Giảm nhiễu thích ứng (Adaptive Noise Reduction)")
        self.cb_nr.setStyleSheet("font-weight: bold; color: #60A5FA;")
        self.cb_nr.toggled.connect(self._on_param_changed)
        nr_header.addWidget(self.cb_nr)

        lbl_nr_note = QLabel("<i>(Mặc định tắt cho giọng đọc TTS sạch)</i>")
        lbl_nr_note.setStyleSheet("color: #64748B; font-size: 11px;")
        nr_header.addWidget(lbl_nr_note)
        nr_header.addStretch()
        bnr_layout.addLayout(nr_header)

        row_nr = QHBoxLayout()
        row_nr.addWidget(QLabel("Mức giảm nhiễu:"))
        self.slider_nr = QSlider(Qt.Horizontal)
        self.slider_nr.setRange(6, 24)
        self.slider_nr.setValue(12)
        self.slider_nr.valueChanged.connect(self._on_param_changed)
        row_nr.addWidget(self.slider_nr)
        self.lbl_nr_val = QLabel("12 dB")
        row_nr.addWidget(self.lbl_nr_val)

        row_nr.addSpacing(15)
        row_nr.addWidget(QLabel("Sàn nhiễu:"))
        self.slider_nf = QSlider(Qt.Horizontal)
        self.slider_nf.setRange(-70, -30)
        self.slider_nf.setValue(-50)
        self.slider_nf.valueChanged.connect(self._on_param_changed)
        row_nr.addWidget(self.slider_nf)
        self.lbl_nf_val = QLabel("-50 dB")
        row_nr.addWidget(self.lbl_nf_val)

        row_nr.addSpacing(15)
        row_nr.addWidget(QLabel("Cắt rung ù (High-pass):"))
        self.slider_hp = QSlider(Qt.Horizontal)
        self.slider_hp.setRange(50, 150)
        self.slider_hp.setValue(80)
        self.slider_hp.valueChanged.connect(self._on_param_changed)
        row_nr.addWidget(self.slider_hp)
        self.lbl_hp_val = QLabel("80 Hz")
        row_nr.addWidget(self.lbl_hp_val)
        bnr_layout.addLayout(row_nr)
        sc_layout.addWidget(box_nr)

        # Module 2: Voice Clarity EQ (Equalizer giọng nói tiếng Việt)
        box_eq = QFrame()
        box_eq.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 10px;")
        beq_layout = QVBoxLayout(box_eq)
        self.cb_eq = QCheckBox("2. Cân bằng âm sắc giọng nói (Voice Clarity EQ — 6 Dải)")
        self.cb_eq.setStyleSheet("font-weight: bold; color: #F59E0B;")
        self.cb_eq.toggled.connect(self._on_param_changed)
        beq_layout.addWidget(self.cb_eq)

        grid_eq = QGridLayout()
        # Row 0: Bass & Warmth & Boxiness
        grid_eq.addWidget(QLabel("Âm trầm (Bass 100Hz):"), 0, 0)
        self.slider_bass = QSlider(Qt.Horizontal)
        self.slider_bass.setRange(-6, 6)
        self.slider_bass.setValue(1)
        self.slider_bass.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_bass, 0, 1)
        self.lbl_bass_val = QLabel("+1.0 dB")
        grid_eq.addWidget(self.lbl_bass_val, 0, 2)

        grid_eq.addWidget(QLabel("Độ ấm / Dầy (250Hz):"), 0, 3)
        self.slider_warmth = QSlider(Qt.Horizontal)
        self.slider_warmth.setRange(-6, 6)
        self.slider_warmth.setValue(1)
        self.slider_warmth.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_warmth, 0, 4)
        self.lbl_warmth_val = QLabel("+1.5 dB")
        grid_eq.addWidget(self.lbl_warmth_val, 0, 5)

        # Row 1: Boxiness & Presence & Treble
        grid_eq.addWidget(QLabel("Cắt nghẹt tiếng (600Hz):"), 1, 0)
        self.slider_boxiness = QSlider(Qt.Horizontal)
        self.slider_boxiness.setRange(-6, 6)
        self.slider_boxiness.setValue(-1)
        self.slider_boxiness.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_boxiness, 1, 1)
        self.lbl_boxiness_val = QLabel("-1.0 dB")
        grid_eq.addWidget(self.lbl_boxiness_val, 1, 2)

        grid_eq.addWidget(QLabel("Rõ chữ tiếng Việt (3.5kHz):"), 1, 3)
        self.slider_presence = QSlider(Qt.Horizontal)
        self.slider_presence.setRange(-6, 8)
        self.slider_presence.setValue(3)
        self.slider_presence.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_presence, 1, 4)
        self.lbl_presence_val = QLabel("+2.5 dB")
        grid_eq.addWidget(self.lbl_presence_val, 1, 5)

        # Row 2: Treble & Air
        grid_eq.addWidget(QLabel("Âm cao (Treble 8kHz):"), 2, 0)
        self.slider_treble = QSlider(Qt.Horizontal)
        self.slider_treble.setRange(-6, 6)
        self.slider_treble.setValue(1)
        self.slider_treble.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_treble, 2, 1)
        self.lbl_treble_val = QLabel("+1.5 dB")
        grid_eq.addWidget(self.lbl_treble_val, 2, 2)

        grid_eq.addWidget(QLabel("Độ thoáng không gian (10kHz):"), 2, 3)
        self.slider_air = QSlider(Qt.Horizontal)
        self.slider_air.setRange(-6, 6)
        self.slider_air.setValue(1)
        self.slider_air.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_air, 2, 4)
        self.lbl_air_val = QLabel("+1.5 dB")
        grid_eq.addWidget(self.lbl_air_val, 2, 5)

        beq_layout.addLayout(grid_eq)
        sc_layout.addWidget(box_eq)

        # Module 3: Chuẩn hóa âm lượng EBU R128 LUFS
        box_lufs = QFrame()
        box_lufs.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 10px;")
        blufs_layout = QVBoxLayout(box_lufs)
        self.cb_loudnorm = QCheckBox("3. Chuẩn hóa âm lượng phát thanh (EBU R128 LUFS Normalization)")
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
        row_lufs.addWidget(QLabel("True Peak trần (Chống méo):"))
        self.slider_tp = QSlider(Qt.Horizontal)
        self.slider_tp.setRange(-30, -5)
        self.slider_tp.setValue(-15)
        self.slider_tp.valueChanged.connect(self._on_param_changed)
        row_lufs.addWidget(self.slider_tp)
        self.lbl_tp_val = QLabel("-1.5 dBFS")
        row_lufs.addWidget(self.lbl_tp_val)

        blufs_layout.addLayout(row_lufs)
        sc_layout.addWidget(box_lufs)

        # Module 4: De-Esser & Dynamic Compressor
        box_dyn = QFrame()
        box_dyn.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 10px;")
        bdyn_layout = QVBoxLayout(box_dyn)
        lbl_dyn_title = QLabel("4. Xử lý động lực học & Giảm âm gió (Dynamics & De-Esser)")
        lbl_dyn_title.setStyleSheet("font-weight: bold; color: #EC4899;")
        bdyn_layout.addWidget(lbl_dyn_title)

        row_dyn = QHBoxLayout()
        self.cb_deesser = QCheckBox("Bật De-Esser (Triệt âm xì /s/, /x/)")
        self.cb_deesser.toggled.connect(self._on_param_changed)
        row_dyn.addWidget(self.cb_deesser)

        row_dyn.addSpacing(20)
        self.cb_compressor = QCheckBox("Bật Compressor (Cân bằng độ dày giọng)")
        self.cb_compressor.toggled.connect(self._on_param_changed)
        row_dyn.addWidget(self.cb_compressor)

        row_dyn.addStretch()
        bdyn_layout.addLayout(row_dyn)
        sc_layout.addWidget(box_dyn)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        # 4. KHU VỰC SO SÁNH A/B (A/B TESTING & PLAYBACK)
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

        # Thanh trạng thái và tiến trình DSP
        status_row = QHBoxLayout()
        self.lbl_dsp_status = QLabel("Trạng thái: Sẵn sàng.")
        self.lbl_dsp_status.setStyleSheet("color: #94A3B8; font-size: 11px;")
        status_row.addWidget(self.lbl_dsp_status)

        status_row.addStretch()
        self.btn_cancel_process = QPushButton("Dừng Xử Lý")
        self.btn_cancel_process.setVisible(False)
        self.btn_cancel_process.setStyleSheet("background-color: #7F1D1D; color: #FCA5A5; padding: 2px 8px; border-radius: 4px;")
        self.btn_cancel_process.clicked.connect(self._cancel_processing)
        status_row.addWidget(self.btn_cancel_process)

        ab_layout.addLayout(status_row)
        main_layout.addWidget(ab_card)

        # 5. NÚT ĐIỀU KHIỂN DƯỚI CÙNG (CONFIRM / CANCEL)
        bottom_row = QHBoxLayout()
        self.btn_cancel = QPushButton("Đóng")
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
    # ĐO ĐẠC ĐỘ TO LUFS & TẢI CẤU HÌNH PRESET
    # =========================================================================
    def _measure_input_loudness(self):
        """Đo lường độ to tệp đầu vào."""
        try:
            res = audio_enhancement_engine.measure_loudness(self.input_path)
            if res.get("success"):
                self.input_lufs = res.get("integrated_lufs")
                self.input_tp = res.get("true_peak_dbfs")
                lra = res.get("loudness_range_lu", 0.0)
                self.lbl_meter_in.setText(
                    f"📊 <b>Độ to đầu vào:</b> {self.input_lufs:.1f} LUFS | True Peak: {self.input_tp:.1f} dBFS | LRA: {lra:.1f} LU"
                )
            else:
                self.lbl_meter_in.setText("📊 <b>Độ to đầu vào:</b> Không khả dụng")
        except Exception:
            self.lbl_meter_in.setText("📊 <b>Độ to đầu vào:</b> Chưa đo được")

    def _load_preset(self, preset_key: str):
        if preset_key not in PRESETS:
            return
        cfg = PRESETS[preset_key]

        self.cb_nr.setChecked(cfg.enable_noise_reduction)
        self.slider_nr.setValue(int(cfg.noise_reduction_db))
        self.slider_nf.setValue(int(cfg.noise_floor_db))
        self.slider_hp.setValue(int(cfg.highpass_freq))

        self.cb_eq.setChecked(cfg.enable_eq)
        self.slider_bass.setValue(int(cfg.bass_gain))
        self.slider_warmth.setValue(int(cfg.eq_warmth_gain))
        self.slider_boxiness.setValue(int(cfg.eq_boxiness_gain))
        self.slider_presence.setValue(int(cfg.eq_presence_gain))
        self.slider_treble.setValue(int(cfg.treble_gain))
        self.slider_air.setValue(int(cfg.eq_air_gain))

        self.cb_deesser.setChecked(cfg.enable_deesser)
        self.cb_compressor.setChecked(cfg.enable_compressor)

        self.cb_loudnorm.setChecked(cfg.enable_loudnorm)
        self.slider_lufs.setValue(int(cfg.target_lufs))
        self.slider_tp.setValue(int(cfg.true_peak * 10))

    def _get_current_config(self) -> AudioEnhancementConfig:
        return AudioEnhancementConfig(
            bypass=self.is_bypass,
            enable_noise_reduction=self.cb_nr.isChecked(),
            noise_reduction_db=float(self.slider_nr.value()),
            noise_floor_db=float(self.slider_nf.value()),
            enable_highpass=True,
            highpass_freq=float(self.slider_hp.value()),
            lowpass_freq=12000.0,
            enable_eq=self.cb_eq.isChecked(),
            bass_gain=float(self.slider_bass.value()),
            eq_warmth_gain=float(self.slider_warmth.value()),
            eq_boxiness_gain=float(self.slider_boxiness.value()),
            eq_presence_gain=float(self.slider_presence.value()),
            treble_gain=float(self.slider_treble.value()),
            eq_air_gain=float(self.slider_air.value()),
            enable_deesser=self.cb_deesser.isChecked(),
            enable_compressor=self.cb_compressor.isChecked(),
            enable_loudnorm=self.cb_loudnorm.isChecked(),
            target_lufs=float(self.slider_lufs.value()),
            true_peak=float(self.slider_tp.value()) / 10.0,
            preset_name=self.combo_presets.currentText(),
        )

    def _on_bypass_toggled(self, checked: bool):
        self.is_bypass = checked
        if checked:
            self.btn_bypass.setText("🔇 Bypass: BẬT (Hiệu ứng bị tắt)")
        else:
            self.btn_bypass.setText("🔊 Bypass: TẮT (DSP Đang hoạt động)")
        self._trigger_processing()

    def _on_preset_changed(self, index: int):
        key = self.combo_presets.itemData(index)
        if key and key != "custom":
            self._load_preset(key)
            self._trigger_processing()

    def _on_param_changed(self):
        # Update text labels
        self.lbl_nr_val.setText(f"{self.slider_nr.value()} dB")
        self.lbl_nf_val.setText(f"{self.slider_nf.value()} dB")
        self.lbl_hp_val.setText(f"{self.slider_hp.value()} Hz")
        self.lbl_bass_val.setText(f"{self.slider_bass.value():+d}.0 dB")
        self.lbl_warmth_val.setText(f"{self.slider_warmth.value():+d}.0 dB")
        self.lbl_boxiness_val.setText(f"{self.slider_boxiness.value():+d}.0 dB")
        self.lbl_presence_val.setText(f"{self.slider_presence.value():+d}.0 dB")
        self.lbl_treble_val.setText(f"{self.slider_treble.value():+d}.0 dB")
        self.lbl_air_val.setText(f"{self.slider_air.value():+d}.0 dB")
        self.lbl_lufs_val.setText(f"{self.slider_lufs.value():.1f} LUFS")
        self.lbl_tp_val.setText(f"{self.slider_tp.value() / 10.0:.1f} dBFS")

        self._trigger_processing()

    def _trigger_processing(self):
        """Khởi động xử lý file tạm thời để nghe thử so sánh."""
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(500)

        self.is_processing = True
        self.btn_cancel_process.setVisible(True)
        self.lbl_dsp_status.setText("⏳ Đang xử lý DSP âm thanh...")

        cfg = self._get_current_config()
        self.worker = AudioEnhancementWorker(
            input_path=self.input_path,
            output_path=self.enhanced_temp_path,
            config=cfg,
        )
        self.worker.progress_updated.connect(lambda p, msg: self.lbl_dsp_status.setText(f"⏳ {msg} ({p}%)"))
        self.worker.finished_success.connect(self._on_worker_success)
        self.worker.finished_error.connect(self._on_worker_error)
        self.worker.start()

    def _cancel_processing(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.lbl_dsp_status.setText("⏹ Đã hủy tiến trình xử lý.")
            self.btn_cancel_process.setVisible(False)
            self.is_processing = False

    def _on_worker_success(self, res: dict):
        self.is_processing = False
        self.processed_ready = True
        self.btn_cancel_process.setVisible(False)
        filters = res.get("applied_filters", [])

        # Cập nhật kết quả đo sau xử lý
        if self.is_bypass:
            self.lbl_dsp_status.setText("🔊 Bypass đang bật: Phát nguyên bản gốc.")
            self.lbl_meter_out.setText("✨ <b>Độ to sau xử lý:</b> Giữ nguyên gốc (Bypass)")
        else:
            self.lbl_dsp_status.setText(f"✅ Đã xử lý thành công! (Áp dụng {len(filters)} bộ lọc DSP)")
            try:
                meas_out = audio_enhancement_engine.measure_loudness(self.enhanced_temp_path)
                if meas_out.get("success"):
                    self.output_lufs = meas_out.get("integrated_lufs")
                    self.output_tp = meas_out.get("true_peak_dbfs")
                    self.lbl_meter_out.setText(
                        f"✨ <b>Độ to sau xử lý:</b> {self.output_lufs:.1f} LUFS | True Peak: {self.output_tp:.1f} dBFS"
                    )
            except Exception:
                pass

    def _on_worker_error(self, err: str):
        self.is_processing = False
        self.btn_cancel_process.setVisible(False)
        self.lbl_dsp_status.setText(f"❌ {err}")

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
        target_file = self.enhanced_temp_path if (self.current_preview_source == "enhanced" and not self.is_bypass) else self.input_path
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
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(500)
        self.reject()

    def closeEvent(self, event):
        self._stop_preview_playback()
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(500)
        super().closeEvent(event)
