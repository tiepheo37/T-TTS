"""gui/dialog_audio_enhancement.py — HỘP THOẠI NÂNG CẤP ÂM THANH DSP & SO SÁNH A/B
=============================================================================
Giao diện xử lý nâng cao âm thanh Phase 8.4–8.8 chuyên nghiệp cho T-TTS v3.1.0:
- Phase 8.4 De-Esser: Triệt tiêu âm xuýt tiếng Việt (Threshold, Intensity, Frequency).
- Phase 8.5 Compressor: Dynamic speech compressor (Threshold, Ratio, Attack, Release, Makeup, Knee, Presets).
- Phase 8.6 Audio Presets: Clean Voice, Studio Voice, Podcast, Military Narration, Broadcast,
  Voice + BGM, Custom Presets (Save, Load, Edit, Duplicate, Delete Custom, Import/Export JSON).
- Phase 8.7 Pipeline: Noise Reduction → EQ → De-Esser → Compressor → LUFS → Limiter (Độc lập, Reset, Non-destructive).
- Phase 8.8 A/B Preview: So sánh A/B thời gian thực, đồng bộ Playhead, đo đạc LUFS & True Peak, Preview theo đoạn chọn.
"""

from __future__ import annotations

import json
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
    QInputDialog,
    QFileDialog,
)

from backend.audio_enhancement import (
    AudioEnhancementConfig,
    PRESETS,
    SYSTEM_PRESETS,
    COMPRESSOR_PRESETS,
    PresetManager,
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

    def __init__(
        self,
        input_path: Path,
        output_path: Path,
        config: AudioEnhancementConfig,
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
    ):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.config = config
        self.start_ms = start_ms
        self.end_ms = end_ms
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
                start_ms=self.start_ms,
                end_ms=self.end_ms,
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
    """Hộp thoại cấu hình DSP, quản lý preset và nghe thử so sánh A/B."""

    def __init__(
        self,
        input_wav_path: str | Path,
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.input_path = Path(input_wav_path).resolve()
        self.sel_start_ms = start_ms
        self.sel_end_ms = end_ms
        self.setWindowTitle("✨ Bộ Nâng Cấp Âm Thanh DSP & Pipeline Master — T-TTS")
        self.setMinimumSize(920, 760)
        self.resize(960, 800)

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
        self._refresh_presets_combo()
        self._measure_input_loudness()
        self._load_preset("clean_voice")
        self._trigger_processing()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(8)

        # 1. HEADER & PRESET SELECTOR & CRUD TOOLBAR
        header_card = QFrame()
        header_card.setStyleSheet("background-color: #122215; border: 1px solid #27472A; border-radius: 6px; padding: 6px;")
        hc_layout = QVBoxLayout(header_card)
        hc_layout.setSpacing(6)

        # Dòng 1: Tiêu đề + Master Bypass + Reset Pipeline
        top_row = QHBoxLayout()
        lbl_title = QLabel("✨ <b>BỘ NÂNG CẤP ÂM THANH DSP NÂNG CAO & PRESETS MASTER</b>")
        lbl_title.setStyleSheet("color: #4ADE80; font-size: 13px;")
        top_row.addWidget(lbl_title)
        top_row.addStretch()

        self.btn_reset_pipeline = QPushButton("🔄 Khôi Phục Mặc Định")
        self.btn_reset_pipeline.setToolTip("Khôi phục cấu hình các bộ lọc về giá trị gốc")
        self.btn_reset_pipeline.clicked.connect(self._reset_to_default_pipeline)
        top_row.addWidget(self.btn_reset_pipeline)

        self.btn_bypass = QPushButton("🔊 Bypass: TẮT")
        self.btn_bypass.setCheckable(True)
        self.btn_bypass.setChecked(False)
        self.btn_bypass.setStyleSheet("""
            QPushButton { background-color: #1E293B; color: #94A3B8; border: 1px solid #475569; padding: 4px 10px; border-radius: 4px; font-weight: bold; }
            QPushButton:checked { background-color: #B91C1C; color: #FFFFFF; border: 1px solid #EF4444; }
        """)
        self.btn_bypass.toggled.connect(self._on_bypass_toggled)
        top_row.addWidget(self.btn_bypass)
        hc_layout.addLayout(top_row)

        # Dòng 2: Chọn Preset + Nút Lưu / Nhân bản / Xóa / Xuất Nhập JSON
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("<b>Cấu hình mẫu (Preset):</b>"))
        self.combo_presets = QComboBox()
        self.combo_presets.setMinimumWidth(260)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        preset_row.addWidget(self.combo_presets)

        self.btn_save_preset = QPushButton("💾 Lưu Mới...")
        self.btn_save_preset.setToolTip("Lưu các thiết lập hiện tại thành cấu hình tùy chỉnh mới")
        self.btn_save_preset.clicked.connect(self._save_custom_preset)
        preset_row.addWidget(self.btn_save_preset)

        self.btn_dup_preset = QPushButton("📋 Nhân Bản")
        self.btn_dup_preset.setToolTip("Nhân bản cấu hình đang chọn")
        self.btn_dup_preset.clicked.connect(self._duplicate_current_preset)
        preset_row.addWidget(self.btn_dup_preset)

        self.btn_del_preset = QPushButton("🗑️ Xóa")
        self.btn_del_preset.setToolTip("Xóa cấu hình tùy chỉnh của người dùng")
        self.btn_del_preset.clicked.connect(self._delete_current_preset)
        preset_row.addWidget(self.btn_del_preset)

        self.btn_import_preset = QPushButton("📥 Nhập JSON")
        self.btn_import_preset.clicked.connect(self._import_presets)
        preset_row.addWidget(self.btn_import_preset)

        self.btn_export_preset = QPushButton("📤 Xuất JSON")
        self.btn_export_preset.clicked.connect(self._export_presets)
        preset_row.addWidget(self.btn_export_preset)

        preset_row.addStretch()
        hc_layout.addLayout(preset_row)
        main_layout.addWidget(header_card)

        # 2. BẢNG ĐO ĐẠC ĐỘ TO LUFS & SO SÁNH BIÊN ĐỘ THỜI GIAN THỰC
        meter_card = QFrame()
        meter_card.setStyleSheet("background-color: #0A140D; border: 1px solid #1E3A24; border-radius: 6px; padding: 6px 12px;")
        mc_layout = QHBoxLayout(meter_card)
        self.lbl_meter_in = QLabel("📊 <b>Độ to đầu vào:</b> Đang đo...")
        self.lbl_meter_in.setStyleSheet("color: #60A5FA; font-size: 12px;")
        mc_layout.addWidget(self.lbl_meter_in)

        mc_layout.addStretch()

        self.lbl_meter_delta = QLabel("↔️ ΔLUFS: --")
        self.lbl_meter_delta.setStyleSheet("color: #CBD5E1; font-size: 12px; font-weight: bold;")
        mc_layout.addWidget(self.lbl_meter_delta)

        mc_layout.addStretch()

        self.lbl_meter_out = QLabel("✨ <b>Độ to sau xử lý:</b> Chưa xử lý")
        self.lbl_meter_out.setStyleSheet("color: #4ADE80; font-size: 12px;")
        mc_layout.addWidget(self.lbl_meter_out)
        main_layout.addWidget(meter_card)

        # 3. KHU VỰC ĐIỀU CHỈNH THÔNG SỐ (SCROLLABLE DSP PIPELINE)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        sc_layout = QVBoxLayout(scroll_content)
        sc_layout.setSpacing(10)

        # ---------------------------------------------------------------------
        # 3.1. MODULE NOISE REDUCTION
        # ---------------------------------------------------------------------
        box_nr = QFrame()
        box_nr.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 8px;")
        bnr_layout = QVBoxLayout(box_nr)

        nr_header = QHBoxLayout()
        self.cb_nr = QCheckBox("1. Giảm nhiễu thích ứng (Adaptive Noise Reduction — afftdn)")
        self.cb_nr.setStyleSheet("font-weight: bold; color: #60A5FA;")
        self.cb_nr.toggled.connect(self._on_param_changed)
        nr_header.addWidget(self.cb_nr)
        lbl_nr_note = QLabel("<i>(Mặc định tắt cho giọng đọc TTS phòng thu)</i>")
        lbl_nr_note.setStyleSheet("color: #64748B; font-size: 11px;")
        nr_header.addWidget(lbl_nr_note)
        nr_header.addStretch()
        bnr_layout.addLayout(nr_header)

        row_nr = QHBoxLayout()
        row_nr.addWidget(QLabel("Mức giảm:"))
        self.slider_nr = QSlider(Qt.Horizontal)
        self.slider_nr.setRange(6, 24)
        self.slider_nr.setValue(12)
        self.slider_nr.valueChanged.connect(self._on_param_changed)
        row_nr.addWidget(self.slider_nr)
        self.lbl_nr_val = QLabel("12 dB")
        row_nr.addWidget(self.lbl_nr_val)

        row_nr.addSpacing(12)
        row_nr.addWidget(QLabel("Sàn nhiễu:"))
        self.slider_nf = QSlider(Qt.Horizontal)
        self.slider_nf.setRange(-70, -30)
        self.slider_nf.setValue(-50)
        self.slider_nf.valueChanged.connect(self._on_param_changed)
        row_nr.addWidget(self.slider_nf)
        self.lbl_nf_val = QLabel("-50 dB")
        row_nr.addWidget(self.lbl_nf_val)

        row_nr.addSpacing(12)
        row_nr.addWidget(QLabel("Lọc rung mic (High-pass):"))
        self.slider_hp = QSlider(Qt.Horizontal)
        self.slider_hp.setRange(50, 150)
        self.slider_hp.setValue(80)
        self.slider_hp.valueChanged.connect(self._on_param_changed)
        row_nr.addWidget(self.slider_hp)
        self.lbl_hp_val = QLabel("80 Hz")
        row_nr.addWidget(self.lbl_hp_val)
        bnr_layout.addLayout(row_nr)
        sc_layout.addWidget(box_nr)

        # ---------------------------------------------------------------------
        # 3.2. MODULE VOICE CLARITY EQUALIZER (6 DẢI)
        # ---------------------------------------------------------------------
        box_eq = QFrame()
        box_eq.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 8px;")
        beq_layout = QVBoxLayout(box_eq)
        self.cb_eq = QCheckBox("2. Cân bằng âm sắc giọng nói (Voice Clarity EQ — 6 Dải)")
        self.cb_eq.setStyleSheet("font-weight: bold; color: #F59E0B;")
        self.cb_eq.toggled.connect(self._on_param_changed)
        beq_layout.addWidget(self.cb_eq)

        grid_eq = QGridLayout()
        # Row 0: Bass & Warmth
        grid_eq.addWidget(QLabel("Trầm (Bass 100Hz):"), 0, 0)
        self.slider_bass = QSlider(Qt.Horizontal)
        self.slider_bass.setRange(-6, 6)
        self.slider_bass.setValue(1)
        self.slider_bass.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_bass, 0, 1)
        self.lbl_bass_val = QLabel("+1.0 dB")
        grid_eq.addWidget(self.lbl_bass_val, 0, 2)

        grid_eq.addWidget(QLabel("Độ ấm (250Hz):"), 0, 3)
        self.slider_warmth = QSlider(Qt.Horizontal)
        self.slider_warmth.setRange(-6, 6)
        self.slider_warmth.setValue(1)
        self.slider_warmth.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_warmth, 0, 4)
        self.lbl_warmth_val = QLabel("+1.0 dB")
        grid_eq.addWidget(self.lbl_warmth_val, 0, 5)

        # Row 1: Boxiness & Presence
        grid_eq.addWidget(QLabel("Cắt nghẹt (600Hz):"), 1, 0)
        self.slider_boxiness = QSlider(Qt.Horizontal)
        self.slider_boxiness.setRange(-6, 6)
        self.slider_boxiness.setValue(-1)
        self.slider_boxiness.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_boxiness, 1, 1)
        self.lbl_boxiness_val = QLabel("-1.0 dB")
        grid_eq.addWidget(self.lbl_boxiness_val, 1, 2)

        grid_eq.addWidget(QLabel("Rõ chữ (3.5kHz):"), 1, 3)
        self.slider_presence = QSlider(Qt.Horizontal)
        self.slider_presence.setRange(-6, 8)
        self.slider_presence.setValue(3)
        self.slider_presence.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_presence, 1, 4)
        self.lbl_presence_val = QLabel("+3.0 dB")
        grid_eq.addWidget(self.lbl_presence_val, 1, 5)

        # Row 2: Treble & Air
        grid_eq.addWidget(QLabel("Sáng trong (Treble 8kHz):"), 2, 0)
        self.slider_treble = QSlider(Qt.Horizontal)
        self.slider_treble.setRange(-6, 6)
        self.slider_treble.setValue(1)
        self.slider_treble.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_treble, 2, 1)
        self.lbl_treble_val = QLabel("+1.0 dB")
        grid_eq.addWidget(self.lbl_treble_val, 2, 2)

        grid_eq.addWidget(QLabel("Thoáng đãng (10kHz):"), 2, 3)
        self.slider_air = QSlider(Qt.Horizontal)
        self.slider_air.setRange(-6, 6)
        self.slider_air.setValue(1)
        self.slider_air.valueChanged.connect(self._on_param_changed)
        grid_eq.addWidget(self.slider_air, 2, 4)
        self.lbl_air_val = QLabel("+1.0 dB")
        grid_eq.addWidget(self.lbl_air_val, 2, 5)

        beq_layout.addLayout(grid_eq)
        sc_layout.addWidget(box_eq)

        # ---------------------------------------------------------------------
        # 3.3. MODULE DE-ESSER (TRIỆT TIÊU ÂM XUÝT TIẾNG VIỆT)
        # ---------------------------------------------------------------------
        box_de = QFrame()
        box_de.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 8px;")
        bde_layout = QVBoxLayout(box_de)
        self.cb_deesser = QCheckBox("3. Giảm âm gió & xuýt rít tiếng Việt (De-Esser — /s/, /x/, /tr/)")
        self.cb_deesser.setStyleSheet("font-weight: bold; color: #EC4899;")
        self.cb_deesser.toggled.connect(self._on_param_changed)
        bde_layout.addWidget(self.cb_deesser)

        row_de = QHBoxLayout()
        row_de.addWidget(QLabel("Ngưỡng (Threshold):"))
        self.slider_de_thresh = QSlider(Qt.Horizontal)
        self.slider_de_thresh.setRange(-35, -10)
        self.slider_de_thresh.setValue(-20)
        self.slider_de_thresh.valueChanged.connect(self._on_param_changed)
        row_de.addWidget(self.slider_de_thresh)
        self.lbl_de_thresh_val = QLabel("-20.0 dB")
        row_de.addWidget(self.lbl_de_thresh_val)

        row_de.addSpacing(12)
        row_de.addWidget(QLabel("Cường độ (Intensity):"))
        self.slider_de_int = QSlider(Qt.Horizontal)
        self.slider_de_int.setRange(10, 100)
        self.slider_de_int.setValue(45)
        self.slider_de_int.valueChanged.connect(self._on_param_changed)
        row_de.addWidget(self.slider_de_int)
        self.lbl_de_int_val = QLabel("0.45")
        row_de.addWidget(self.lbl_de_int_val)

        row_de.addSpacing(12)
        row_de.addWidget(QLabel("Tần số mục tiêu:"))
        self.slider_de_freq = QSlider(Qt.Horizontal)
        self.slider_de_freq.setRange(40, 100)
        self.slider_de_freq.setValue(60)
        self.slider_de_freq.valueChanged.connect(self._on_param_changed)
        row_de.addWidget(self.slider_de_freq)
        self.lbl_de_freq_val = QLabel("6000 Hz")
        row_de.addWidget(self.lbl_de_freq_val)

        bde_layout.addLayout(row_de)
        sc_layout.addWidget(box_de)

        # ---------------------------------------------------------------------
        # 3.4. MODULE DYNAMIC SPEECH COMPRESSOR (BỘ NÉN GIỌNG NÓI)
        # ---------------------------------------------------------------------
        box_comp = QFrame()
        box_comp.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 8px;")
        bcomp_layout = QVBoxLayout(box_comp)

        comp_head = QHBoxLayout()
        self.cb_compressor = QCheckBox("4. Bộ nén động lực học giọng nói (Dynamic Speech Compressor)")
        self.cb_compressor.setStyleSheet("font-weight: bold; color: #38BDF8;")
        self.cb_compressor.toggled.connect(self._on_param_changed)
        comp_head.addWidget(self.cb_compressor)

        comp_head.addStretch()
        comp_head.addWidget(QLabel("Preset nén:"))
        self.combo_comp_preset = QComboBox()
        self.combo_comp_preset.addItem("Nén nhẹ tự nhiên (Gentle Voice)", "gentle_voice")
        self.combo_comp_preset.addItem("Thuyết minh truyền cảm (Narration)", "narration")
        self.combo_comp_preset.addItem("Phát thanh rõ chữ (Broadcast)", "broadcast")
        self.combo_comp_preset.addItem("Tùy chỉnh thủ công", "custom")
        self.combo_comp_preset.currentIndexChanged.connect(self._on_compressor_preset_changed)
        comp_head.addWidget(self.combo_comp_preset)
        bcomp_layout.addLayout(comp_head)

        grid_comp = QGridLayout()
        # Row 0: Threshold & Ratio
        grid_comp.addWidget(QLabel("Ngưỡng nén (Threshold):"), 0, 0)
        self.slider_comp_thresh = QSlider(Qt.Horizontal)
        self.slider_comp_thresh.setRange(-30, -6)
        self.slider_comp_thresh.setValue(-18)
        self.slider_comp_thresh.valueChanged.connect(self._on_param_changed)
        grid_comp.addWidget(self.slider_comp_thresh, 0, 1)
        self.lbl_comp_thresh_val = QLabel("-18.0 dB")
        grid_comp.addWidget(self.lbl_comp_thresh_val, 0, 2)

        grid_comp.addWidget(QLabel("Tỷ lệ nén (Ratio):"), 0, 3)
        self.slider_comp_ratio = QSlider(Qt.Horizontal)
        self.slider_comp_ratio.setRange(15, 60)
        self.slider_comp_ratio.setValue(28)
        self.slider_comp_ratio.valueChanged.connect(self._on_param_changed)
        grid_comp.addWidget(self.slider_comp_ratio, 0, 4)
        self.lbl_comp_ratio_val = QLabel("2.8:1")
        grid_comp.addWidget(self.lbl_comp_ratio_val, 0, 5)

        # Row 1: Attack & Release
        grid_comp.addWidget(QLabel("Thời gian nén (Attack):"), 1, 0)
        self.slider_comp_atk = QSlider(Qt.Horizontal)
        self.slider_comp_atk.setRange(2, 60)
        self.slider_comp_atk.setValue(20)
        self.slider_comp_atk.valueChanged.connect(self._on_param_changed)
        grid_comp.addWidget(self.slider_comp_atk, 1, 1)
        self.lbl_comp_atk_val = QLabel("20 ms")
        grid_comp.addWidget(self.lbl_comp_atk_val, 1, 2)

        grid_comp.addWidget(QLabel("Thời gian nhả (Release):"), 1, 3)
        self.slider_comp_rel = QSlider(Qt.Horizontal)
        self.slider_comp_rel.setRange(50, 600)
        self.slider_comp_rel.setValue(250)
        self.slider_comp_rel.valueChanged.connect(self._on_param_changed)
        grid_comp.addWidget(self.slider_comp_rel, 1, 4)
        self.lbl_comp_rel_val = QLabel("250 ms")
        grid_comp.addWidget(self.lbl_comp_rel_val, 1, 5)

        # Row 2: Makeup Gain & Soft Knee
        grid_comp.addWidget(QLabel("Bù âm lượng (Makeup):"), 2, 0)
        self.slider_comp_makeup = QSlider(Qt.Horizontal)
        self.slider_comp_makeup.setRange(0, 80)
        self.slider_comp_makeup.setValue(15)
        self.slider_comp_makeup.valueChanged.connect(self._on_param_changed)
        grid_comp.addWidget(self.slider_comp_makeup, 2, 1)
        self.lbl_comp_makeup_val = QLabel("+1.5 dB")
        grid_comp.addWidget(self.lbl_comp_makeup_val, 2, 2)

        grid_comp.addWidget(QLabel("Độ mềm chuyển tiếp (Knee):"), 2, 3)
        self.slider_comp_knee = QSlider(Qt.Horizontal)
        self.slider_comp_knee.setRange(10, 60)
        self.slider_comp_knee.setValue(28)
        self.slider_comp_knee.valueChanged.connect(self._on_param_changed)
        grid_comp.addWidget(self.slider_comp_knee, 2, 4)
        self.lbl_comp_knee_val = QLabel("2.8 dB")
        grid_comp.addWidget(self.lbl_comp_knee_val, 2, 5)

        bcomp_layout.addLayout(grid_comp)
        sc_layout.addWidget(box_comp)

        # ---------------------------------------------------------------------
        # 3.5. MODULE EBU R128 LUFS NORMALIZATION
        # ---------------------------------------------------------------------
        box_lufs = QFrame()
        box_lufs.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 8px;")
        blufs_layout = QVBoxLayout(box_lufs)
        self.cb_loudnorm = QCheckBox("5. Chuẩn hóa âm lượng phát thanh (EBU R128 LUFS Normalization)")
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

        # ---------------------------------------------------------------------
        # 3.6. MODULE FINAL LIMITER
        # ---------------------------------------------------------------------
        box_lim = QFrame()
        box_lim.setStyleSheet("background-color: #0E1A10; border: 1px solid #1A381F; border-radius: 6px; padding: 8px;")
        blim_layout = QVBoxLayout(box_lim)
        self.cb_limiter = QCheckBox("6. Bộ trần biên độ an toàn chống quá ngưỡng (Final Brickwall Limiter)")
        self.cb_limiter.setStyleSheet("font-weight: bold; color: #A855F7;")
        self.cb_limiter.toggled.connect(self._on_param_changed)
        blim_layout.addWidget(self.cb_limiter)

        row_lim = QHBoxLayout()
        row_lim.addWidget(QLabel("Mức trần biên độ (Ceiling):"))
        self.slider_lim_ceil = QSlider(Qt.Horizontal)
        self.slider_lim_ceil.setRange(-30, -5)
        self.slider_lim_ceil.setValue(-10)
        self.slider_lim_ceil.valueChanged.connect(self._on_param_changed)
        row_lim.addWidget(self.slider_lim_ceil)
        self.lbl_lim_ceil_val = QLabel("-1.0 dBFS")
        row_lim.addWidget(self.lbl_lim_ceil_val)

        row_lim.addSpacing(20)
        row_lim.addWidget(QLabel("Thời gian nhả (Release):"))
        self.slider_lim_rel = QSlider(Qt.Horizontal)
        self.slider_lim_rel.setRange(20, 150)
        self.slider_lim_rel.setValue(50)
        self.slider_lim_rel.valueChanged.connect(self._on_param_changed)
        row_lim.addWidget(self.slider_lim_rel)
        self.lbl_lim_rel_val = QLabel("50 ms")
        row_lim.addWidget(self.lbl_lim_rel_val)
        blim_layout.addLayout(row_lim)
        sc_layout.addWidget(box_lim)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        # 4. KHU VỰC SO SÁNH A/B & TIME SLICE PREVIEW
        ab_card = QFrame()
        ab_card.setStyleSheet("background-color: #122215; border: 2px solid #22C55E; border-radius: 8px; padding: 8px 12px;")
        ab_layout = QVBoxLayout(ab_card)
        ab_layout.setSpacing(6)

        ab_header = QHBoxLayout()
        ab_header.addWidget(QLabel("🎧 <b>SO SÁNH NGHE THỬ A/B (ĐỒNG BỘ PLAYHEAD):</b>"))

        # Checkbox preview theo đoạn chọn nếu có
        self.cb_slice_preview = QCheckBox("Chỉ nghe đoạn chọn")
        if self.sel_start_ms is not None and self.sel_end_ms is not None and self.sel_end_ms > self.sel_start_ms:
            self.cb_slice_preview.setText(f"Chỉ nghe đoạn chọn ({self.sel_start_ms}ms - {self.sel_end_ms}ms)")
            self.cb_slice_preview.setChecked(True)
            self.cb_slice_preview.toggled.connect(self._trigger_processing)
            ab_header.addWidget(self.cb_slice_preview)
        else:
            self.cb_slice_preview.setVisible(False)

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

        # 5. NÚT ĐIỀU KHIỂN DƯỚI CÙNG
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
    # PRESET MANAGEMENT LOGIC
    # =========================================================================
    def _refresh_presets_combo(self):
        """Cập nhật danh sách preset trên ComboBox."""
        curr_key = self.combo_presets.currentData()
        self.combo_presets.blockSignals(True)
        self.combo_presets.clear()

        # Nhóm hệ thống
        all_presets = PresetManager.list_all_presets()
        for k in ["clean_voice", "studio_voice", "podcast", "military_narration", "broadcast", "voice_bgm"]:
            if k in all_presets:
                self.combo_presets.addItem(f"⭐ {all_presets[k].preset_name}", k)

        # Nhóm tùy chỉnh
        custom_keys = [k for k, v in all_presets.items() if getattr(v, "is_custom", False)]
        if custom_keys:
            self.combo_presets.insertSeparator(self.combo_presets.count())
            for ck in custom_keys:
                self.combo_presets.addItem(f"👤 {all_presets[ck].preset_name}", ck)

        self.combo_presets.addItem("⚙️ Tùy chỉnh thủ công", "custom")

        # Khôi phục vị trí chọn
        idx = self.combo_presets.findData(curr_key)
        if idx >= 0:
            self.combo_presets.setCurrentIndex(idx)
        else:
            self.combo_presets.setCurrentIndex(0)
        self.combo_presets.blockSignals(False)

    def _save_custom_preset(self):
        """Hộp thoại lưu cấu hình hiện tại thành preset mới."""
        name, ok = QInputDialog.getText(self, "Lưu cấu hình", "Nhập tên cấu hình tùy chỉnh mới:")
        if not ok or not name.strip():
            return
        cfg = self._get_current_config()
        saved_ok, msg = PresetManager.save_preset(name.strip(), cfg)
        if saved_ok:
            QMessageBox.information(self, "Thành công", msg)
            self._refresh_presets_combo()
            key = name.strip().lower().replace(" ", "_")
            idx = self.combo_presets.findData(key)
            if idx >= 0:
                self.combo_presets.setCurrentIndex(idx)
        else:
            QMessageBox.warning(self, "Không thể lưu", msg)

    def _duplicate_current_preset(self):
        """Nhân bản preset đang chọn."""
        curr_key = self.combo_presets.currentData()
        if not curr_key or curr_key == "custom":
            return
        new_name, ok = QInputDialog.getText(self, "Nhân bản cấu hình", "Nhập tên cho bản sao cấu hình:", text=f"{curr_key}_copy")
        if not ok or not new_name.strip():
            return
        dup_ok, msg = PresetManager.duplicate_preset(curr_key, new_name.strip())
        if dup_ok:
            QMessageBox.information(self, "Thành công", msg)
            self._refresh_presets_combo()
        else:
            QMessageBox.warning(self, "Không thể nhân bản", msg)

    def _delete_current_preset(self):
        """Xóa preset đang chọn (Chỉ cho phép xóa preset người dùng)."""
        curr_key = self.combo_presets.currentData()
        if not curr_key or curr_key in SYSTEM_PRESETS:
            QMessageBox.warning(self, "Bảo vệ hệ thống", "Không được phép xóa cấu hình hệ thống tiêu chuẩn!")
            return
        rep = QMessageBox.question(self, "Xác nhận xóa", f"Bạn có chắc muốn xóa cấu hình '{curr_key}'?", QMessageBox.Yes | QMessageBox.No)
        if rep == QMessageBox.Yes:
            del_ok, msg = PresetManager.delete_preset(curr_key)
            if del_ok:
                QMessageBox.information(self, "Thành công", msg)
                self._refresh_presets_combo()
            else:
                QMessageBox.warning(self, "Lỗi", msg)

    def _export_presets(self):
        """Xuất danh sách preset ra file JSON."""
        f, _ = QFileDialog.getSaveFileName(self, "Xuất cấu hình DSP", "dsp_presets.json", "JSON Files (*.json)")
        if f:
            ok, msg = PresetManager.export_presets_json(f)
            if ok:
                QMessageBox.information(self, "Xuất thành công", msg)
            else:
                QMessageBox.critical(self, "Lỗi xuất", msg)

    def _import_presets(self):
        """Nhập danh sách preset từ file JSON."""
        f, _ = QFileDialog.getOpenFileName(self, "Nhập cấu hình DSP", "", "JSON Files (*.json)")
        if f:
            ok, msg = PresetManager.import_presets_json(f)
            if ok:
                QMessageBox.information(self, "Nhập thành công", msg)
                self._refresh_presets_combo()
            else:
                QMessageBox.critical(self, "Lỗi nhập", msg)

    def _reset_to_default_pipeline(self):
        """Khôi phục pipeline về Clean Voice tiêu chuẩn."""
        self._load_preset("clean_voice")
        self._trigger_processing()

    # =========================================================================
    # LOUDNESS MEASUREMENT & PRESET LOAD
    # =========================================================================
    def _measure_input_loudness(self):
        try:
            res = audio_enhancement_engine.measure_loudness(self.input_path)
            if res.get("success"):
                self.input_lufs = res.get("integrated_lufs")
                self.input_tp = res.get("true_peak_dbfs")
                lra = res.get("loudness_range_lu", 0.0)
                self.lbl_meter_in.setText(
                    f"📊 <b>Độ to đầu vào:</b> {self.input_lufs:.1f} LUFS | TP: {self.input_tp:.1f} dBFS | LRA: {lra:.1f} LU"
                )
            else:
                self.lbl_meter_in.setText("📊 <b>Độ to đầu vào:</b> Không khả dụng")
        except Exception:
            self.lbl_meter_in.setText("📊 <b>Độ to đầu vào:</b> Chưa đo được")

    def _load_preset(self, preset_key: str):
        all_p = PresetManager.list_all_presets()
        if preset_key not in all_p:
            return
        cfg = all_p[preset_key]

        # 1. Noise reduction
        self.cb_nr.setChecked(cfg.enable_noise_reduction)
        self.slider_nr.setValue(int(cfg.noise_reduction_db))
        self.slider_nf.setValue(int(cfg.noise_floor_db))
        self.slider_hp.setValue(int(cfg.highpass_freq))

        # 2. EQ
        self.cb_eq.setChecked(cfg.enable_eq)
        self.slider_bass.setValue(int(cfg.bass_gain))
        self.slider_warmth.setValue(int(cfg.eq_warmth_gain))
        self.slider_boxiness.setValue(int(cfg.eq_boxiness_gain))
        self.slider_presence.setValue(int(cfg.eq_presence_gain))
        self.slider_treble.setValue(int(cfg.treble_gain))
        self.slider_air.setValue(int(cfg.eq_air_gain))

        # 3. De-Esser
        self.cb_deesser.setChecked(cfg.enable_deesser)
        self.slider_de_thresh.setValue(int(cfg.deesser_threshold))
        self.slider_de_int.setValue(int(cfg.deesser_intensity * 100))
        self.slider_de_freq.setValue(int(cfg.deesser_freq / 100.0))

        # 4. Compressor
        self.cb_compressor.setChecked(cfg.enable_compressor)
        self.slider_comp_thresh.setValue(int(cfg.compressor_threshold))
        self.slider_comp_ratio.setValue(int(cfg.compressor_ratio * 10))
        self.slider_comp_atk.setValue(int(cfg.compressor_attack))
        self.slider_comp_rel.setValue(int(cfg.compressor_release))
        self.slider_comp_makeup.setValue(int(cfg.compressor_makeup_gain * 10))
        self.slider_comp_knee.setValue(int(cfg.compressor_knee * 10))

        # 5. LUFS
        self.cb_loudnorm.setChecked(cfg.enable_loudnorm)
        self.slider_lufs.setValue(int(cfg.target_lufs))
        self.slider_tp.setValue(int(cfg.true_peak * 10))

        # 6. Limiter
        self.cb_limiter.setChecked(cfg.enable_limiter)
        self.slider_lim_ceil.setValue(int(cfg.limiter_ceiling * 10))
        self.slider_lim_rel.setValue(int(cfg.limiter_release))

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
            deesser_threshold=float(self.slider_de_thresh.value()),
            deesser_intensity=float(self.slider_de_int.value()) / 100.0,
            deesser_freq=float(self.slider_de_freq.value()) * 100.0,
            enable_compressor=self.cb_compressor.isChecked(),
            compressor_threshold=float(self.slider_comp_thresh.value()),
            compressor_ratio=float(self.slider_comp_ratio.value()) / 10.0,
            compressor_attack=float(self.slider_comp_atk.value()),
            compressor_release=float(self.slider_comp_rel.value()),
            compressor_makeup_gain=float(self.slider_comp_makeup.value()) / 10.0,
            compressor_knee=float(self.slider_comp_knee.value()) / 10.0,
            enable_loudnorm=self.cb_loudnorm.isChecked(),
            target_lufs=float(self.slider_lufs.value()),
            true_peak=float(self.slider_tp.value()) / 10.0,
            enable_limiter=self.cb_limiter.isChecked(),
            limiter_ceiling=float(self.slider_lim_ceil.value()) / 10.0,
            limiter_release=float(self.slider_lim_rel.value()),
            preset_name=self.combo_presets.currentText(),
        )

    def _on_compressor_preset_changed(self, index: int):
        key = self.combo_comp_preset.itemData(index)
        if key in COMPRESSOR_PRESETS:
            p = COMPRESSOR_PRESETS[key]
            self.slider_comp_thresh.setValue(int(p["threshold"]))
            self.slider_comp_ratio.setValue(int(p["ratio"] * 10))
            self.slider_comp_atk.setValue(int(p["attack"]))
            self.slider_comp_rel.setValue(int(p["release"]))
            self.slider_comp_makeup.setValue(int(p["makeup"] * 10))
            self.slider_comp_knee.setValue(int(p["knee"] * 10))
            self._trigger_processing()

    def _on_bypass_toggled(self, checked: bool):
        self.is_bypass = checked
        if checked:
            self.btn_bypass.setText("🔇 Bypass: BẬT (Hiệu ứng bị tắt)")
        else:
            self.btn_bypass.setText("🔊 Bypass: TẮT (DSP Hoạt động)")
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

        self.lbl_de_thresh_val.setText(f"{self.slider_de_thresh.value():.1f} dB")
        self.lbl_de_int_val.setText(f"{self.slider_de_int.value() / 100.0:.2f}")
        self.lbl_de_freq_val.setText(f"{self.slider_de_freq.value() * 100} Hz")

        self.lbl_comp_thresh_val.setText(f"{self.slider_comp_thresh.value():.1f} dB")
        self.lbl_comp_ratio_val.setText(f"{self.slider_comp_ratio.value() / 10.0:.1f}:1")
        self.lbl_comp_atk_val.setText(f"{self.slider_comp_atk.value()} ms")
        self.lbl_comp_rel_val.setText(f"{self.slider_comp_rel.value()} ms")
        self.lbl_comp_makeup_val.setText(f"+{self.slider_comp_makeup.value() / 10.0:.1f} dB")
        self.lbl_comp_knee_val.setText(f"{self.slider_comp_knee.value() / 10.0:.1f} dB")

        self.lbl_lufs_val.setText(f"{self.slider_lufs.value():.1f} LUFS")
        self.lbl_tp_val.setText(f"{self.slider_tp.value() / 10.0:.1f} dBFS")

        self.lbl_lim_ceil_val.setText(f"{self.slider_lim_ceil.value() / 10.0:.1f} dBFS")
        self.lbl_lim_rel_val.setText(f"{self.slider_lim_rel.value()} ms")

        self._trigger_processing()

    def _trigger_processing(self):
        """Khởi động xử lý file tạm thời để nghe thử so sánh."""
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(500)

        self.is_processing = True
        self.btn_cancel_process.setVisible(True)
        self.lbl_dsp_status.setText("⏳ Đang xử lý DSP âm thanh nền...")

        cfg = self._get_current_config()
        use_slice = self.cb_slice_preview.isVisible() and self.cb_slice_preview.isChecked()
        s_ms = self.sel_start_ms if use_slice else None
        e_ms = self.sel_end_ms if use_slice else None

        self.worker = AudioEnhancementWorker(
            input_path=self.input_path,
            output_path=self.enhanced_temp_path,
            config=cfg,
            start_ms=s_ms,
            end_ms=e_ms,
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

        if self.is_bypass:
            self.lbl_dsp_status.setText("🔊 Bypass đang bật: Phát nguyên bản gốc.")
            self.lbl_meter_out.setText("✨ <b>Độ to sau xử lý:</b> Giữ nguyên gốc (Bypass)")
            self.lbl_meter_delta.setText("↔️ ΔLUFS: 0.0 LU")
        else:
            self.lbl_dsp_status.setText(f"✅ Đã xử lý thành công! (Áp dụng {len(filters)} bộ lọc DSP trong pipeline)")
            try:
                meas_out = audio_enhancement_engine.measure_loudness(self.enhanced_temp_path)
                if meas_out.get("success"):
                    self.output_lufs = meas_out.get("integrated_lufs")
                    self.output_tp = meas_out.get("true_peak_dbfs")
                    self.lbl_meter_out.setText(
                        f"✨ <b>Độ to sau xử lý:</b> {self.output_lufs:.1f} LUFS | TP: {self.output_tp:.1f} dBFS"
                    )
                    if self.input_lufs is not None:
                        delta = self.output_lufs - self.input_lufs
                        sign = "+" if delta >= 0 else ""
                        self.lbl_meter_delta.setText(f"↔️ ΔLUFS: {sign}{delta:.1f} LU")
            except Exception:
                pass

    def _on_worker_error(self, err: str):
        self.is_processing = False
        self.btn_cancel_process.setVisible(False)
        self.lbl_dsp_status.setText(f"❌ {err}")

    # =========================================================================
    # A/B TESTING & PLAYBACK SYNCHRONIZATION
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
        """Chuyển đổi nguồn A/B tức thời không mất vị trí phát."""
        is_enhanced = self.rb_enhanced.isChecked()
        new_source = "enhanced" if is_enhanced else "original"
        if new_source == self.current_preview_source:
            return

        self.current_preview_source = new_source

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
        """Người dùng chấp thuận áp dụng chuỗi DSP vào dự án."""
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
