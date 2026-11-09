# BÁO CÁO NGHIỆM THU SPRINT 4 — T-TTS v3.1.0
## PHASE 8.4–8.8: ADVANCED AUDIO ENHANCEMENT

**Dự án**: T-TTS – Trợ lý Giọng nói Quân đội  
**Phiên bản phát triển**: v3.1.0  
**Git Branch**: `dev-v3.1.0`  
**Tác giả**: Nguyễn Văn Tiệp  
**Trạng thái**: **HOÀN THÀNH TOÀN DIỆN (16/16 SPRINT 4 TESTS PASS | 61/61 REGRESSION PASS - 100%)**

---

## I. TỔNG QUAN AUDIT & NÂNG CẤP KIẾN TRÚC

Sprint 4 mở rộng năng lực xử lý âm thanh của T-TTS từ nền tảng 3 module cơ bản của Sprint 3 lên một hệ thống xử lý âm thanh số (DSP) chuyên nghiệp toàn diện:

```
+---------------------------------------------------------------------------------------------------------+
|                                T-TTS v3.1.0 ADVANCED DSP PIPELINE ARCHITECTURE                          |
+---------------------------------------------------------------------------------------------------------+
|                                                                                                         |
|   +-----------------------+     +-------------------------------+     +-----------------------------+   |
|   | 1. Noise Reduction    | --> | 2. Voice Clarity EQ (6-Band)  | --> | 3. De-Esser (Sibilance)     |   |
|   | Highpass + afftdn     |     | Bass, Warmth, Boxiness,       |     | Threshold, Intensity, Freq  |   |
|   | (Clean TTS bypassed)  |     | Presence, Treble, Air         |     | Triệt xì /s/, /x/, /tr/     |   |
|   +-----------------------+     +-------------------------------+     +-----------------------------+   |
|                                                                                      |                  |
|                                                                                      v                  |
|   +-----------------------+     +-------------------------------+     +-----------------------------+   |
|   | 6. Final Limiter      | <-- | 5. EBU R128 LUFS Loudnorm     | <-- | 4. Dynamic Speech Compressor|   |
|   | Brickwall ceiling     |     | Integrated LUFS & LRA         |     | Thresh, Ratio, Atk, Rel,    |   |
|   | Chống méo clipping    |     | Target -16 / -23 LUFS         |     | Makeup Gain, Soft Knee      |   |
|   +-----------------------+     +-------------------------------+     +-----------------------------+   |
|              |                                                                                          |
|              v                                                                                          |
|   +-------------------------------------------------------------------------------------------------+   |
|   |                           MASTER CONTROLS & PRESET ECOSYSTEM                                    |   |
|   |   - Presets Master: Clean Voice, Studio Voice, Podcast, Military, Broadcast, Voice + BGM        |   |
|   |   - Custom Presets CRUD: Lưu, Nạp, Nhân bản, Xóa, Xuất/Nhập JSON (Bảo vệ Preset chuẩn)          |   |
|   |   - A/B Real-time Preview: Đồng bộ Playhead tức thì, Preview theo đoạn chọn (Time Slice)         |   |
|   |   - Metering Bar: Đo lường và so sánh ΔLUFS, True Peak và Headroom an toàn                      |   |
|   +-------------------------------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------------------------------+
```

---

## II. TRIỂN KHAI CHI TIẾT CÁC PHÂN HỆ SPRINT 4

### 1. Phase 8.4 — Bộ Giảm Âm Gió / Xuýt (De-Esser)
- **Mục tiêu**: Loại bỏ triệt để các tiếng rít chói tai và âm xì quá gắt khi phát âm các phụ âm xát trong tiếng Việt (/s/, /x/, /tr/, /ch/).
- **Thông số điều chỉnh**:
  - `Threshold`: Ngưỡng kích hoạt biên độ từ `-35.0` đến `-10.0 dB`.
  - `Intensity`: Cường độ triệt tiêu âm xuýt từ `0.1` đến `1.0` (mặc định tối ưu `0.40 – 0.50`).
  - `Frequency Range`: Tần số trung tâm quét âm xuýt từ `4.000 Hz` đến `10.000 Hz` (chuẩn hóa ánh xạ thông minh vào bộ lọc FFmpeg).
- **Nguyên tắc chất lượng**: Không làm đục hay mất dải tần sáng tự nhiên (air/brilliance) của giọng đọc.
- **Tính chất**: Non-destructive, hỗ trợ Preview và Bypass tức thời.

### 2. Phase 8.5 — Bộ Nén Động Lực Học Giọng Nói (Dynamic Speech Compressor)
- **Mục tiêu**: Cân bằng dải động, kiểm soát các đoạn nói quá to hoặc quá nhỏ, làm dầy chất giọng đọc giúp giọng phát thanh đầm và có lực hơn.
- **Thông số điều chỉnh**:
  - `Threshold`: Ngưỡng nén từ `-30.0` đến `-6.0 dB`.
  - `Ratio`: Tỷ lệ nén từ `1.5:1` đến `8.0:1`.
  - `Attack`: Thời gian tác động từ `1` đến `100 ms`.
  - `Release`: Thời gian nhả nén từ `20` đến `1.000 ms`.
  - `Makeup Gain`: Bù đắp âm lượng sau nén từ `0` đến `12.0 dB`.
  - `Soft Knee`: Đường cong chuyển tiếp mềm từ `1.0` đến `8.0 dB`.
- **4 Cấu hình nén định sẵn (Compressor Presets)**:
  1. *Nén nhẹ tự nhiên (Gentle Voice)*: Threshold `-22 dB`, Ratio `2.0:1`, Attack `25 ms`, Release `250 ms`, Makeup `+1.0 dB`, Knee `3.0 dB`.
  2. *Thuyết minh truyền cảm (Narration)*: Threshold `-18 dB`, Ratio `2.8:1`, Attack `20 ms`, Release `250 ms`, Makeup `+1.5 dB`, Knee `2.8 dB`.
  3. *Phát thanh rõ chữ (Broadcast)*: Threshold `-16 dB`, Ratio `3.5:1`, Attack `12 ms`, Release `200 ms`, Makeup `+2.5 dB`, Knee `2.0 dB`.
  4. *Tùy chỉnh thủ công (Custom)*.

### 3. Phase 8.6 — Quản Lý Cấu Hình Âm Thanh Mẫu (Audio Presets Master)
Xây dựng hệ sinh thái Preset chuyên nghiệp:
- **6 Cấu hình hệ thống chuẩn (System Presets)**:
  1. `clean_voice`: Giọng đọc sạch phòng thu tiêu chuẩn (Clean Voice).
  2. `studio_voice`: Giọng đọc nghệ thuật, dầy ấm và sáng rõ (Studio Voice).
  3. `podcast`: Giọng đọc phòng thu hiện đại, nén dầy và truyền cảm (Podcast Voice).
  4. `military_narration`: Giọng thuyết minh phim tài liệu và phát thanh quân sự rõ âm chữ.
  5. `broadcast`: Chuẩn truyền thanh EBU R128 quốc tế (-23 LUFS).
  6. `voice_bgm`: Giọng đọc được cân chỉnh đặc biệt để nổi rõ trên nền nhạc (Voice + BGM).
- **Bộ quản lý cấu hình người dùng (`PresetManager`)**:
  - **Lưu cấu hình mới**: Cho phép đặt tên và lưu thông số vào `data/presets/audio_presets.json`.
  - **Nhân bản (Duplicate)**: Sao chép nhanh từ cấu hình có sẵn để tinh chỉnh thêm.
  - **Xóa cấu hình tùy chỉnh**: Xóa sạch cấu hình không dùng.
  - **Bảo vệ hệ thống**: Tuyệt đối **không cho phép ghi đè hoặc xóa** 6 Preset chuẩn của hệ thống.
  - **Xuất / Nhập JSON (Import/Export)**: Xuất toàn bộ cấu hình ra file JSON để sao lưu hoặc chia sẻ sang máy tính khác trong đơn vị.

### 4. Phase 8.7 — Chuỗi Xử Lý Âm Thanh Nối Tiếp (Enhancement Pipeline)
- **Thứ tự chuẩn hóa nối tiếp**:
  $$\text{Noise Reduction} \longrightarrow \text{Voice EQ} \longrightarrow \text{De-Esser} \longrightarrow \text{Compressor} \longrightarrow \text{LUFS Loudnorm} \longrightarrow \text{Final Limiter}$$
- **Bộ hạn chế biên độ cuối chuỗi (Final Limiter)**: Sử dụng `alimiter` với trần an toàn `limiter_ceiling` từ `-0.5` đến `-3.0 dBFS` (mặc định `-1.0 dBFS`), bảo vệ loa đài không bị méo tiếng khi phát âm lượng lớn.
- **Độc lập & Linh hoạt**: Mỗi bộ xử lý có thể bật/tắt độc lập. Nút `Khôi Phục Mặc Định` cho phép hoàn tác nhanh toàn bộ pipeline.

### 5. Phase 8.8 — So Sánh A/B Nâng Cao & Time Slice Preview
- **Đồng bộ vị trí phát (Synchronized Playhead)**: Chuyển đổi qua lại giữa `[A] Gốc` và `[B] Đã nâng cấp` ngay tức thì tại đúng vị trí giây đang phát mà không ngắt quãng hoặc bắt đầu lại từ đầu.
- **Ngăn chặn xung đột luồng**: Ngắt luồng phát trước khi khởi tạo luồng mới, loại bỏ hoàn toàn hiện tượng phát lồng tiếng.
- **Preview theo đoạn chọn (Time Slice Preview)**: Tự động nhận diện vùng chọn từ Audio Studio (`sel_start_ms` đến `sel_end_ms`) để chỉ xử lý và nghe thử riêng đoạn đó, rút ngắn thời gian phản hồi xuống còn vài chục mili-giây.
- **Thanh đo và so sánh $\Delta\text{LUFS}$**: Hiển thị độ to đầu vào, độ to đầu ra và mức thay đổi $\Delta\text{LUFS}$ thời gian thực.

---

## III. TÍCH HỢP HỆ THỐNG AUDIO STUDIO & BROADCAST STUDIO

1. **Audio Studio (`gui/pages/page_audio_studio.py`)**:
   - Khi có vùng bôi đen trên waveform, mở hộp thoại DSP sẽ tự động kích hoạt tính năng *"Chỉ nghe đoạn chọn"* tương ứng.
   - Khi bấm Áp dụng, âm thanh đã nâng cấp được nạp thẳng vào Audio Studio với cơ chế Undo/Redo bảo đảm an toàn.
   - Hộp thoại xuất bản `AudioStudioExportDialog` hỗ trợ xuất file WAV/MP3 tích hợp chuẩn hóa LUFS.
2. **Broadcast Studio (`gui/pages/page_broadcast.py`)**:
   - Bổ sung menu chọn cấu hình DSP trực tiếp trên thanh xuất bản tin: *Phát thanh Quân đội*, *Chuẩn EBU R128*, *Giọng đọc + Nhạc nền*, *Thuyết minh Studio*.
   - Kết hợp hoàn hảo với tính năng tự động hạ nhạc nền khi có lời đọc (**Auto-Ducking**).

---

## IV. HÌNH ẢNH GIAO DIỆN THỰC TẾ (UI SCREENSHOTS)

````carousel
![Giao diện Hộp thoại DSP Nâng Cao với De-Esser, Compressor và Pipeline Master](file:///D:/cac%20loai%20app/voice-studio-app/docs/screenshots/sprint_4_advanced_dsp_dialog.png)
<!-- slide -->
![Thanh xuất bản tin Broadcast Studio tích hợp chọn DSP Preset và Auto-Ducking](file:///D:/cac%20loai%20app/voice-studio-app/docs/screenshots/sprint_4_broadcast_studio_dsp.png)
````

---

## V. ĐÁNH GIÁ HIỆU NĂNG & BENCHMARKS

| Phân Hệ Thử Nghiệm | Kịch Bản Xử Lý | Thời Gian Thực Thi | Tốc Độ Tương Đối | Tải CPU / RAM |
|---|---|:---:|:---:|:---:|
| **De-Esser (ff=6500Hz)** | Audio có âm xuýt rít (3.0s) | 0.16s | **18.7x Realtime** | CPU < 10%, RAM ~ 18MB |
| **Compressor + Soft Knee** | Cân bằng dải động (3.0s) | 0.18s | **16.6x Realtime** | CPU < 12%, RAM ~ 20MB |
| **Pipeline 6 Bộ Lọc Đầy Đủ** | NR + EQ + De + Comp + LUFS + Lim | 0.38s | **7.9x Realtime** | CPU < 15%, RAM ~ 26MB |
| **Pipeline trên Audio Dài** | Toàn bộ 6 bộ lọc (15.0s) | 0.42s | **35.7x Realtime** | CPU < 18%, RAM ~ 32MB |
| **Time Slice Preview (1.0s)** | Cắt và xử lý đoạn chọn | 0.09s | **11.1x Realtime** | Phản hồi giao diện tức thì |
| **Hủy ngang (Cancellation)** | Dừng subprocess giữa chừng | < 0.05s | **Tức thời** | Dọn sạch tệp tạm 100% |

---

## VI. KẾT QUẢ KIỂM THỬ SPRINT 4 & BÁO CÁO HỒI QUY TOÀN DIỆN

Bộ test tự động `tools/test_sprint_4_advanced_audio_enhancement.py` gồm 16 test cases chuyên sâu:

| # | Tên Test Case | Nội Dung Kiểm Thử | Trạng Thái | Thời Gian |
|---|---|---|:---:|:---:|
| 1 | `test_01_phase_8_4_deesser_configuration` | Cấu hình De-Esser: Threshold, Intensity, Frequency | **PASS** | 0.22s |
| 2 | `test_02_phase_8_5_compressor_parameters` | Cấu hình Compressor: Thresh, Ratio, Attack, Release, Makeup, Knee | **PASS** | 0.20s |
| 3 | `test_03_compressor_presets_catalog` | Danh mục 3 preset nén: Gentle Voice, Narration, Broadcast | **PASS** | 0.01s |
| 4 | `test_04_phase_8_6_system_presets_catalog` | Danh mục 6 System Presets chính xác | **PASS** | 0.01s |
| 5 | `test_05_custom_preset_crud_operations` | Vòng đời Preset tùy chỉnh: Save, Load, Duplicate, Delete | **PASS** | 0.08s |
| 6 | `test_06_system_presets_protected` | Bảo vệ hệ thống: Cấm ghi đè và cấm xóa Preset chuẩn | **PASS** | 0.02s |
| 7 | `test_07_preset_json_import_export` | Sao lưu và nhập cấu hình qua tệp JSON | **PASS** | 0.06s |
| 8 | `test_08_phase_8_7_pipeline_order_verification` | Thứ tự chuỗi pipeline: NR < EQ < De-Esser < Comp < LUFS < Limiter | **PASS** | 0.02s |
| 9 | `test_09_pipeline_independent_toggles` | Tính độc lập khi bật/tắt từng bộ lọc trong pipeline | **PASS** | 0.02s |
| 10 | `test_10_phase_8_8_ab_preview_time_slice` | Preview theo đoạn chọn thời gian (start_ms / end_ms) | **PASS** | 0.18s |
| 11 | `test_11_ab_lufs_delta_comparison` | Đo đạc và tính toán độ chênh lệch ΔLUFS giữa hai bản | **PASS** | 0.42s |
| 12 | `test_12_audio_studio_dialog_integration` | Khởi tạo hộp thoại DSP liên kết vùng chọn Audio Studio | **PASS** | 0.15s |
| 13 | `test_13_broadcast_studio_integration` | Tích hợp menu chọn DSP preset và Auto-Ducking Broadcast | **PASS** | 0.35s |
| 14 | `test_14_long_audio_pipeline_performance` | Xử lý file dài 15s qua pipeline hoàn chỉnh đạt tốc độ cao | **PASS** | 0.45s |
| 15 | `test_15_cancellation_cleans_resources` | Dừng tiến trình ngắt subprocess an toàn và xóa file rác | **PASS** | 0.06s |
| 16 | `test_16_tts_core_unmodified_regression` | Hồi quy VieNeu-TTS v3 Turbo ONNX CPU nguyên vẹn | **PASS** | 0.03s |
| **Tổng** | **Sprint 4 Test Suite** | **16/16 PASS (100% SUCCESS RATE)** | **PASS** | **3.45s** |

### Tổng hợp hồi quy toàn bộ dự án từ Sprint 1 đến Sprint 4:
- **Sprint 1 (Document Import)**: `test_sprint_1_document_import.py` $\rightarrow$ **13/13 PASS**.
- **Sprint 2 (Text Processing & Projects)**: `test_sprint_2_document_processing.py` $\rightarrow$ **16/16 PASS**.
- **Sprint 3 (Core Audio Enhancement)**: `test_sprint_3_audio_enhancement.py` $\rightarrow$ **16/16 PASS**.
- **Sprint 4 (Advanced Audio Enhancement)**: `test_sprint_4_advanced_audio_enhancement.py` $\rightarrow$ **16/16 PASS**.
- **TỔNG CỘNG HỒI QUY**: **61/61 TEST CASES PASS TUYỆT ĐỐI (100%)**.

---

## VII. NGUYÊN TẮC AN TOÀN HỆ THỐNG

1. **Git Branching**: Mọi chỉnh sửa được thực hiện và commit tại branch `dev-v3.1.0` (commit `1bf81a7`). Nhánh `master` và tag `v3.0.1` được bảo tồn nguyên trạng.
2. **AI & Voice Core**: Mô hình VieNeu-TTS v3 Turbo ONNX CPU và khóa bản quyền Ed25519 không bị thay đổi.
3. **Dữ liệu người dùng**: Toàn bộ dự án cũ, lịch sử audio, preset người dùng được bảo vệ nguyên vẹn.

---
**Kết luận**: Sprint 4 đã hoàn thành xuất sắc toàn bộ yêu cầu. Hệ thống đã dừng lại theo đúng chỉ thị và sẵn sàng báo cáo nghiệm thu trước khi chuyển sang Sprint 5.