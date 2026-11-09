# BÁO CÁO NGHIỆM THU SPRINT 3 — T-TTS v3.1.0
## PHASE 8.1–8.3: CORE AUDIO ENHANCEMENT

**Dự án**: T-TTS – Trợ lý Giọng nói Quân đội  
**Phiên bản phát triển**: v3.1.0  
**Git Branch**: `dev-v3.1.0`  
**Tác giả**: Nguyễn Văn Tiệp  
**Trạng thái**: **HOÀN THÀNH TOÀN DIỆN (16/16 TESTS PASS - 100%)**

---

## I. KẾT QUẢ AUDIT HỆ THỐNG TRƯỚC KHI TRIỂN KHAI

Trước khi thực hiện các sửa đổi, quy trình kiểm tra kiến trúc đã được tiến hành toàn diện:

1. **Audio Studio (`gui/pages/page_audio_studio.py`)**: Đã có waveform thời gian thực, các công cụ cắt/ghép/zoom, và lệnh `pydub_normalize` (Peak Normalization). Nút DSP đã được liên kết với `gui/dialog_audio_enhancement.py`. Cần bổ sung kiểm soát LUFS trên Export và phân định rõ ràng giữa Peak và EBU R128 LUFS.
2. **Broadcast Studio (`gui/pages/page_broadcast.py`)**: Đã tích hợp tùy chọn `chk_dsp_mastering` gọi tới `AudioEnhancementEngine` áp dụng preset `broadcast_military`. Không bị xung đột, hoạt động ổn định.
3. **FFmpeg Bootstrap (`backend/ffmpeg_bootstrap.py`)**: Đã được chuẩn hóa từ Phase 7.9, nạp FFmpeg v7.1 nội bộ từ `imageio-ffmpeg` vào PATH toàn hệ thống, cung cấp đầy đủ các bộ lọc tiên tiến `afftdn`, `equalizer`, `loudnorm`, `deesser`, `acompressor`.
4. **Kiểm tra xuất âm thanh (`backend/export_center.py`)**: Đã hỗ trợ xuất đa định dạng WAV/MP3 và chuẩn hóa LUFS.
5. **Nguyên tắc không tạo trùng lặp**: Kế thừa và nâng cấp trực tiếp `backend/audio_enhancement.py`, `gui/dialog_audio_enhancement.py`, và `gui/pages/page_audio_studio.py`, không tạo module mới gây phân mảnh.

```
+---------------------------------------------------------------------------------------------------------+
|                                    T-TTS v3.1.0 CORE AUDIO DSP PIPELINE                                 |
+---------------------------------------------------------------------------------------------------------+
|                                                                                                         |
|   +-----------------------+     +-------------------------------+     +-----------------------------+   |
|   |   Raw Audio Input     | --> |   High-pass Rumble Filter     | --> |  Adaptive Noise Reduction   |   |
|   |   (TTS / Project /    |     |   Cutoff 50 - 150 Hz          |     |  afftdn (Non-destructive,   |   |
|   |    Imported Audio)    |     |   (Clean mic & rumble)        |     |  Bypassed for clean TTS)    |   |
|   +-----------------------+     +-------------------------------+     +-----------------------------+   |
|                                                                                      |                  |
|                                                                                      v                  |
|   +-----------------------+     +-------------------------------+     +-----------------------------+   |
|   | EBU R128 Normalization| <-- |  Dynamic Speech Compressor    | <-- |   Voice Clarity 6-Band EQ   |   |
|   | Target -16 / -23 LUFS |     |  Smooth amplitude & thicken   |     |   Bass, Warmth, Boxiness,   |   |
|   | True Peak Ceiling     |     |  voice presence               |     |   Presence, Treble, Air     |   |
|   +-----------------------+     +-------------------------------+     +-----------------------------+   |
|              |                                                                                          |
|              v                                                                                          |
|   +-------------------------------------------------------------------------------------------------+   |
|   |                           MASTER OUTPUT / EXPORT SELECTION                                      |   |
|   |   - A/B Real-time Comparison Preview (Original vs DSP with synchronized seek head)              |   |
|   |   - Master Bypass Toggle: Pass original clean audio unmodified                                  |   |
|   |   - Audio Studio Export: Choose EBU R128 (-16 / -23 LUFS), Peak (-0.1 dBFS), or Original        |   |
|   +-------------------------------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------------------------------+
```

---

## II. TRIỂN KHAI 3 MODULE XỬ LÝ ÂM THANH CỐT LÕI

### 1. Module 1: Giảm nhiễu thích ứng (Noise Reduction)
- **Công nghệ**: Sử dụng bộ lọc biến đổi Fourier nhanh `afftdn` (FFT-based audio denoiser) của FFmpeg 7.1 kết hợp với bộ lọc cắt dải cao tần `lowpass` và rung chấn `highpass`.
- **Thông số điều chỉnh**: Mức giảm nhiễu (Noise reduction: 6 – 24 dB), Sàn nhiễu (Noise floor: -80 đến -20 dB), Tần số cắt ù (50 – 150 Hz).
- **Nguyên tắc an toàn**: **Mặc định TẮT** (`enable_noise_reduction=False`) cho giọng đọc TTS phòng thu sạch để bảo toàn độ trung thực của âm sắc tự nhiên. Chỉ kích hoạt khi người dùng xử lý audio thu âm ngoài hiện trường hoặc file âm thanh có tạp âm nền.
- **Tính chất**: Non-destructive (không ghi đè file nguồn), hỗ trợ nghe thử tức thời (Preview) và Bypass.

### 2. Module 2: Voice Enhancement EQ (Bộ cân bằng âm sắc giọng nói)
- **Bộ lọc High-pass**: Cắt rung chấn, tiếng ù gió mic dưới 80 Hz (`highpass=f=80`).
- **Equalizer 6 dải chuyên dụng cho giọng nói tiếng Việt**:
  1. **Bass (100 Hz)**: Điều chỉnh độ dầy và độ sâu âm trầm (-6 đến +6 dB).
  2. **Warmth (250 Hz)**: Tăng cường độ ấm và độ đầm của giọng đọc (+1.5 dB).
  3. **Boxiness (600 Hz)**: Cắt giảm độ nghẹt mũi, tù tiếng (-1.0 đến -2.0 dB).
  4. **Presence (3.5 kHz)**: Tăng độ rõ nét và độ nẩy của các phụ âm tiếng Việt (/t/, /k/, /c/, /ch/) (+2.5 đến +3.5 dB).
  5. **Treble (8.0 kHz)**: Tăng độ sáng và sự trong trẻo của giọng (-6 đến +6 dB).
  6. **Air (10.0 kHz)**: Mở rộng không gian và độ thoáng đãng (+1.5 dB).
- **Preset Thuyết minh chuyên nghiệp (`voiceover_narrative`)**: Cấu hình mẫu tối ưu hóa cho thuyết minh phim, giảng bài và đọc sách, mang lại chất giọng truyền cảm, dầy dặn và rõ ràng từng từ.
- Có tính năng Preview và Master Bypass tức thời.

### 3. Module 3: Chuẩn hóa âm lượng EBU R128 LUFS (Loudness Normalization)
- **Chuẩn công nghiệp EBU R128**: Tích hợp thuật toán đo lường và chuẩn hóa độ to theo cảm nhận tai người (Loudness Units relative to Full Scale — LUFS).
- **Đo lường thời gian thực (`measure_loudness`)**: Quét và hiển thị trực tiếp độ to tích hợp (Integrated LUFS), Loudness Range (LRA) và True Peak (dBFS).
- **Các mức chuẩn hóa định sẵn**:
  - **Giọng đọc / Podcast**: `-16.0 LUFS` (chuẩn nghe qua tai nghe và thiết bị di động).
  - **Phát thanh Châu Âu / Quốc tế**: `-23.0 LUFS` (chuẩn EBU R128 đài phát thanh truyền hình).
  - **Truyền hình ATSC A/85**: `-24.0 LUFS`.
  - **Loa ngoài trời / Truyền thanh**: `-14.0 LUFS`.
  - **Tùy chỉnh thủ công**: từ `-24.0` đến `-12.0 LUFS`.
- **Bảo vệ chống méo (True Peak Ceiling)**: Giới hạn trần biên độ từ `-1.0` đến `-1.5 dBFS`, ngăn ngừa hoàn toàn hiện tượng vỡ âm (clipping) khi giải mã DAC.
- **Bảo tồn Peak Normalization**: **Tuyệt đối không thay thế Peak Normalization bằng LUFS**. Trong Audio Studio, người dùng được cung cấp song song:
  - Nút `🎚 Chuẩn Hóa Peak`: Giữ nguyên tính năng chuẩn hóa biên độ đỉnh truyền thống (-0.1 dBFS).
  - Nút `✨ Nâng Cấp DSP & LUFS`: Mở bộ điều phối nâng cấp toàn diện và EBU R128 LUFS.

---

## III. TÍCH HỢP GIAO DIỆN NGƯỜI DÙNG & AUDIO STUDIO

### 1. Hộp thoại Nâng cấp Âm thanh (`gui/dialog_audio_enhancement.py`)
- **Master Bypass**: Nút chuyển đổi trạng thái `🔊 Bypass: TẮT / 🔇 Bypass: BẬT` cho phép kiểm tra ngay lập tức âm thanh gốc trước khi áp dụng hiệu ứng.
- **Thanh đo độ to LUFS thời gian thực**:
  - `📊 Độ to đầu vào: -17.8 LUFS | True Peak: -2.3 dBFS | LRA: 0.0 LU`
  - `✨ Độ to sau xử lý: -16.2 LUFS | True Peak: -1.5 dBFS`
- **So sánh A/B đồng bộ thời gian thực**: Người dùng có thể bấm chuyển đổi giữa `🔵 [A] Âm Thanh Gốc` và `🟢 [B] Âm Thanh Đã Nâng Cấp DSP` khi đang nghe mà không bị gián đoạn hay mất vị trí con trỏ phát.
- **Hủy bỏ an toàn (Cancellation)**: Nút `Dừng Xử Lý` cho phép kết thúc ngay lập tức tiểu trình FFmpeg nền mà không làm đơ giao diện hay để lại file rác.

### 2. Xuất bản âm thanh tích hợp trong Audio Studio (`AudioStudioExportDialog`)
Khi người dùng bấm `Xuất Âm Thanh` trong Audio Studio, hộp thoại xuất bản chuyên nghiệp sẽ xuất hiện:
- Lựa chọn định dạng: **WAV (PCM 16-bit 48kHz)** hoặc **MP3 (128k, 192k, 256k, 320k)**.
- Tùy chọn Loudness Mastering:
  1. *EBU R128: -16.0 LUFS (Chuẩn Giọng đọc / Podcast)*
  2. *EBU R128: -23.0 LUFS (Chuẩn Phát thanh Châu Âu / Quốc tế)*
  3. *EBU R128: -24.0 LUFS (Chuẩn Truyền hình ATSC A/85)*
  4. *Peak Normalization (-0.1 dBFS)*
  5. *Giữ nguyên âm lượng gốc (Không can thiệp)*

### 3. Hình ảnh chụp thực tế giao diện (UI Screenshots)

````carousel
![Hộp thoại Nâng Cấp Âm Thanh DSP & Chuẩn Hóa LUFS](file:///D:/cac%20loai%20app/voice-studio-app/docs/screenshots/sprint_3_audio_enhancement_dialog.png)
<!-- slide -->
![Hộp thoại Xuất Bản Âm Thanh Audio Export Master](file:///D:/cac%20loai%20app/voice-studio-app/docs/screenshots/sprint_3_audio_studio_export_dialog.png)
<!-- slide -->
![Giao diện Biên tập Phân hệ Audio Studio](file:///D:/cac%20loai%20app/voice-studio-app/docs/screenshots/sprint_3_audio_studio_page.png)
````

---

## IV. ĐÁNH GIÁ HIỆU NĂNG & BENCHMARKS

Các bài đo hiệu năng thực tế được ghi nhận trên môi trường kiểm thử:

| Bài Đo Kiểm | Dữ Liệu Thử Nghiệm | Thời Gian Xử Lý | Tốc Độ Tương Đối | Mức Chiếm Dụng RAM |
|---|---|:---:|:---:|:---:|
| **Đo lường LUFS EBU R128** | Tệp âm thanh mẫu (3.0s) | 0.08 giây | **37.5x Realtime** | Không tăng đáng kể (< 15MB) |
| **Xử lý toàn bộ chuỗi DSP** | Âm thanh giọng nói (3.0s) | 0.18 giây | **16.6x Realtime** | ~ 24 MB RAM |
| **Xử lý âm thanh thời lượng dài** | Âm thanh đa tần (15.0s) | 0.35 giây | **42.8x Realtime** | ~ 28 MB RAM |
| **Kiểm tra trần True Peak** | Ép khuếch đại vượt ngưỡng | 0.16 giây | **Đạt trần -1.5 dBFS** | Ngăn méo loa tuyệt đối |
| **Thao tác Hủy bỏ (Cancel)** | Ngắt subprocess giữa chừng | < 0.05 giây | **Dọn sạch file tạm** | Không rò rỉ tiến trình |

---

## V. KẾT QUẢ KIỂM THỬ TỰ ĐỘNG SPRINT 3 (16/16 PASS)

Bộ kiểm thử `tools/test_sprint_3_audio_enhancement.py` được thực thi tự động với Python 3.12:

| # | Tên Test Case | Mục Tiêu Kiểm Thử | Trạng Thái | Thời Gian |
|---|---|---|:---:|:---:|
| 1 | `test_01_ffmpeg_bootstrap_readiness` | Xác thực tính sẵn sàng và đường dẫn FFmpeg 7.1 nội bộ | **PASS** | 0.02s |
| 2 | `test_02_lufs_loudness_measurement` | Đo lường chính xác Integrated LUFS, True Peak và LRA | **PASS** | 0.12s |
| 3 | `test_03_noise_reduction_dsp` | Khởi tạo chuỗi afftdn, highpass, lowpass và xuất audio | **PASS** | 0.22s |
| 4 | `test_04_noise_reduction_clean_tts_default_disabled` | Bảo đảm giảm nhiễu luôn tắt mặc định cho giọng TTS | **PASS** | 0.01s |
| 5 | `test_05_voice_enhancement_eq` | Kiểm tra 6 dải lọc âm sắc: Bass, Warmth, Boxiness, Presence, Treble, Air | **PASS** | 0.24s |
| 6 | `test_06_voiceover_narrative_preset` | Xác thực cấu hình và xuất âm thanh preset Thuyết minh | **PASS** | 0.25s |
| 7 | `test_07_broadcast_standard_ebu_preset` | Chuẩn hóa EBU R128 đạt độ to -23.0 LUFS và True Peak -1.0 dBFS | **PASS** | 0.35s |
| 8 | `test_08_lufs_normalization_accuracy` | Độ chính xác chuẩn hóa -16.0 LUFS trong biên độ sai số $\pm 1.0$ LUFS | **PASS** | 0.38s |
| 9 | `test_09_true_peak_clipping_protection` | Kiểm soát trần True Peak -1.5 dBFS chống méo clipping | **PASS** | 0.32s |
| 10 | `test_10_bypass_mode` | Master Bypass truyền thẳng audio gốc không tạo filter | **PASS** | 0.15s |
| 11 | `test_11_cancel_processing` | Dừng tiến trình tức thì, dọn dẹp file dở dang không lỗi | **PASS** | 0.06s |
| 12 | `test_12_non_destructive_integrity` | Bảo toàn kích thước và tính toàn vẹn 100% của file nguồn | **PASS** | 0.18s |
| 13 | `test_13_audio_studio_export_normalization` | Xuất file tích hợp Peak và EBU R128 LUFS không triệt tiêu nhau | **PASS** | 0.28s |
| 14 | `test_14_long_audio_stability_and_memory` | Xử lý âm thanh 15s với tốc độ vượt trội > 2.0x Realtime | **PASS** | 0.36s |
| 15 | `test_15_regression_broadcast_studio` | Hồi quy Broadcast Studio với preset `broadcast_military` | **PASS** | 0.25s |
| 16 | `test_16_regression_tts_synthesis` | Hồi quy danh mục giọng đọc VieNeu-TTS v3 Turbo ONNX CPU | **PASS** | 0.03s |
| **Tổng** | **16 Test Cases** | **16/16 PASS (100% SUCCESS RATE)** | **PASS** | **3.01s** |

---

## VI. BẢO TOÀN TÍNH TOÀN VẸN & HỒI QUY HỆ THỐNG

- **Sprint 1 Regression**: `tools/test_sprint_1_document_import.py` $\rightarrow$ **13/13 PASS**.
- **Sprint 2 Regression**: `tools/test_sprint_2_document_processing.py` $\rightarrow$ **16/16 PASS**.
- **Sprint 3 Test Suite**: `tools/test_sprint_3_audio_enhancement.py` $\rightarrow$ **16/16 PASS**.
- **Tổng cộng**: **45/45 Test Cases PASS tuyệt đối (100%)**.
- **An toàn mã nguồn**: Git branch `dev-v3.1.0` (commit `372f524`), nhánh `master` và tag `v3.0.1` được giữ nguyên trạng. Mô hình VieNeu-TTS ONNX CPU và License Ed25519 không bị thay đổi.

---
**Kết luận**: Sprint 3 đã hoàn thành vượt mức các tiêu chí kỹ thuật và sẵn sàng phục vụ cho các phân hệ tiếp theo. Dừng theo chỉ dẫn để chờ anh phê duyệt nghiệm thu trước khi chuyển sang Sprint 4.