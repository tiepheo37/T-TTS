# KẾ HOẠCH TRIỂN KHAI NÂNG CẤP T-TTS v3.1.0
## T-TTS VERSION 3.1.0 MASTER UPGRADE PLAN
**Dự án:** T-TTS – Trợ lý Giọng nói Quân đội  
**Phiên bản nền tảng:** `v3.0.1` (đã gắn tag bảo toàn trên nhánh `master`)  
**Phiên bản mục tiêu:** `v3.1.0` (phát triển trên nhánh `dev-v3.1.0`)  
**Tác giả:** Nguyễn Văn Tiệp  
**Ngày lập kế hoạch:** 09/11/2026  

---

## I. TỔNG QUAN KIẾN TRÚC & MỤC TIÊU NÂNG CẤP

Phiên bản v3.1.0 đánh dấu bước tiến lớn trong quy trình sản xuất nội dung âm thanh của T-TTS: chuyển đổi từ công cụ đọc văn bản đơn thuần sang **Hệ thống Biên tập & Sản xuất Phát thanh Đa tầng từ Tài liệu (Document-to-Speech Production Suite)**.

### Mục tiêu then chốt:
1. **Document Import Chuyên nghiệp (Ưu tiên cao):** Nhập tài liệu trực tiếp từ Word (`.docx`), PDF (`.pdf`), Văn bản thuần (`.txt`) và hướng dẫn định dạng cũ (`.doc`), có xem trước, tùy chọn Ghi đè (Replace), Nối tiếp (Append) hoặc Tạo dự án mới, chạy ngầm với thanh tiến trình và hủy an toàn.
2. **Phase 8 — Advanced Audio Enhancement:** Bộ xử lý âm thanh hậu kỳ chuyên nghiệp 100% offline (Noise Reduction, Voice Enhancement EQ, Chuẩn hóa độ lớn LUFS EBU R128, De-Esser, Compressor, Presets phát thanh quân đội và Nghe thử đối chiếu A/B Preview).
3. **Phase 9 — Document Workflow & Productivity:** Quản lý dự án tài liệu (`DocumentProject`), chuẩn hóa văn bản thông minh (đọc số, ngày tháng, chia đoạn), tổng hợp hàng loạt (Batch TTS), và trung tâm xuất khẩu âm thanh (Export Center).
4. **Hệ thống Auto Update v3.0.1 → v3.1.0:** Tự động phát hiện phiên bản mới, tải bộ cài, kiểm tra chữ ký/checksum SHA-256, nâng cấp an toàn và bảo toàn 100% giấy phép offline Ed25519, cấu hình và dữ liệu người dùng.

---

## II. KẾT QUẢ AUDIT KIẾN TRÚC HIỆN CÓ

```mermaid
flowchart TD
    subgraph Hiện có [Đã hoàn thiện & Ổn định]
        M1["VieNeu-TTS v3 Turbo ONNX CPU (25 voices)"]
        M2["Ed25519 Offline License Manager"]
        M3["FFmpeg Bootstrap v7.1 Centralized"]
        M4["Audio Studio & Waveform Engine"]
        M5["Schedule Studio 50-item Playlist Engine"]
        M6["Broadcast Studio 2.0 Multitrack & Auto-Ducking"]
        M7["NativeAudioPlayer (Windows MCI)"]
        M8["NotificationHub & TaskWorker QThread"]
    end
    subgraph Nâng cấp [Cần cập nhật cho v3.1.0]
        U1["gui/pages/page_synthesize.py (Thêm nút Nhập tài liệu, Dán clipboard, Import Workflow)"]
        U2["backend/audio_utils.py (Bổ sung bộ lọc DSP & LUFS)"]
        U3["gui/pages/page_audio_studio.py (Tích hợp Enhancement Pipeline & A/B Preview)"]
        U4["gui/pages/page_broadcast.py (Tích hợp Enhancement cho phân đoạn phát thanh)"]
        U5["backend/updater.py (Hỗ trợ Auto Update v3.0.1 -> v3.1.0 an toàn)"]
        U6["backend/version.py (Nâng APP_VERSION = '3.1.0')"]
    end
    subgraph Tạo mới [Triển khai mới hoàn toàn]
        N1["backend/document_reader.py (Trích xuất DOCX, PDF, TXT đa mã hóa, OCR warning)"]
        N2["gui/dialog_import_document.py (Hộp thoại tiến trình, thống kê trang/từ, tùy chọn Replace/Append/Project)"]
        N3["backend/audio_enhancement.py (Pipeline xử lý DSP 8.1 - 8.8)"]
        N4["backend/text_processor.py (Chuẩn hóa số, ngày tháng tiếng Việt, chia đoạn, thống kê)"]
        N5["gui/dialog_audio_enhancement.py (Giao diện điều khiển DSP & A/B Preview)"]
        N6["gui/pages/page_document_workflow.py (Quy trình sản xuất tài liệu phát thanh)"]
    end
    Hiện có --> Nâng cấp
    Nâng cấp --> Tạo mới
```

### 1. Thư viện phụ thuộc trên máy (Đã xác minh 100% Offline)
- `python-docx` (`docx`): **ĐÃ CÓ SẴN** trong `python312`.
- `pypdf`: **ĐÃ CÓ SẴN** trong `python312`.
- `charset_normalizer`: **ĐÃ CÓ SẴN** trong `python312`.
- `imageio-ffmpeg` (FFmpeg v7.1 essentials): **ĐÃ ĐÓNG GÓI SẴN**, hỗ trợ đầy đủ các bộ lọc `afftdn`, `equalizer`, `loudnorm`, `deesser`, `acompressor`.
- `numpy`, `pydub`, `soundfile`, `PySide6`: **ĐÃ CÓ SẴN**.

---

## III. CHIẾN LƯỢC AUTO UPDATE & BẢO TOÀN DỮ LIỆU

1. **Nguyên tắc bất biến:**
   - Tuyệt đối không xóa hoặc ghi đè thư mục `data/` trong quá trình cài đặt hay cập nhật.
   - Tệp giấy phép `data/system_state.json` và bản quyền offline Ed25519 được giữ nguyên 100%.
   - Toàn bộ lịch sử TTS (`data/history.json`), từ điển phát âm (`data/pronunciation-dict.json`), các dự án Audio Studio, Broadcast Studio và Schedule Studio được bảo lưu nguyên vẹn.
2. **Cơ chế nâng cấp bộ cài Inno Setup (`setup_installer.iss`):**
   - Đánh dấu cờ `uninsneveruninstall onlyifdoesntexist` cho các thư mục `data/` và `output/`.
   - Cung cấp tính năng sao lưu dữ liệu tự động (`backup_pre_update/`) trước khi tiến hành giải nén tệp mới.
3. **Cập nhật kênh GitHub Release:**
   - Quản lý release version: tag `v3.0.1` giữ nguyên, phát hành mới tag `v3.1.0`.
   - Cung cấp tệp metadata cập nhật `update_config.json` và `checksums.txt` chứa hash SHA-256 chính xác của `T-TTS_Setup_v3.1.0_Offline.exe`.

---

## IV. LỘ TRÌNH 8 SPRINT THỰC THI

| Sprint | Nội dung trọng tâm | Kết quả bàn giao (Deliverables) |
| :---: | :--- | :--- |
| **Sprint 1** | **Document Import DOCX/PDF/TXT** | `backend/document_reader.py`, `gui/dialog_import_document.py`, cập nhật `gui/pages/page_synthesize.py` (Nút Nhập tài liệu, Dán clipboard, Preview Replace/Append), Test Suite Sprint 1. |
| **Sprint 2** | **Document Processing & Document Project** | `backend/text_processor.py`, Quản lý dự án tài liệu `DocumentProject` trong `backend/project_manager.py`, công cụ chuẩn hóa số/ngày tháng tiếng Việt, Test Suite Sprint 2. |
| **Sprint 3** | **Audio Enhancement (8.1 - 8.3)** | Noise Reduction (`afftdn`), Voice Clarity EQ (`equalizer`), Chuẩn hóa âm lượng EBU R128 LUFS (`loudnorm`), Test Suite Sprint 3. |
| **Sprint 4** | **Audio Enhancement (8.4 - 8.8)** | De-Esser, Compressor, Bộ Presets Quân đội / Tin tức, Enhancement Pipeline, A/B Preview Widget trong Audio Studio, Test Suite Sprint 4. |
| **Sprint 5** | **Batch TTS & Productivity (9.4 - 9.6)** | Xử lý tài liệu dài chia đoạn thông minh, Batch TTS Worker có Pause/Resume/Retry, Export Center đa định dạng, Test Suite Sprint 5. |
| **Sprint 6** | **UI Integration & Full Regression** | Tích hợp đồng bộ toàn bộ 13 trang chức năng, kiểm thử hồi quy toàn diện (TTS, Audio, Schedule, Broadcast, Document). |
| **Sprint 7** | **Auto Update v3.0.1 → v3.1.0** | Nâng cấp `backend/updater.py`, kiểm thử quy trình phát hiện bản mới, tải xuống, kiểm tra checksum, bảo toàn dữ liệu và license. |
| **Sprint 8** | **Packaging & Release v3.1.0** | Đóng gói PyInstaller v3.1.0, tạo Inno Setup Installer `T-TTS_Setup_v3.1.0_Offline.exe`, bản nén Portable, Release Notes & Changelog. |

---

## V. TIẾN ĐỘ THỰC HIỆN

- [x] Tạo nhánh phát triển `dev-v3.1.0` từ tag `v3.0.1`.
- [x] Lập kế hoạch chi tiết `T-TTS_V3.1.0_IMPLEMENTATION_PLAN.md`.
- [ ] **BẮT ĐẦU SPRINT 1: DOCUMENT IMPORT DOCX/PDF/TXT**.
