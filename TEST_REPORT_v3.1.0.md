# BÁO CÁO KIỂM THỬ TỔNG THỂ T-TTS v3.1.0 (MASTER TEST REPORT)
## HỆ THỐNG TRỢ LÝ GIỌNG NÓI QUÂN ĐỘI (VieNeu-TTS v3 Turbo ONNX CPU)

**Tác giả:** Nguyễn Văn Tiệp  
**Phiên bản kiểm thử:** v3.1.0  
**Hệ điều hành kiểm thử:** Windows 10 / Windows 11 (x64)  
**Môi trường:** Python 3.12.7 x64, ONNX Runtime Lite CPU, FFmpeg v7.1  
**Ngày kiểm thử:** 09/11/2026  
**Tổng số ca kiểm thử toàn diện:** 116/116 Test Cases ĐẠT (100% PASS)  

---

## 1. TỔNG QUAN KIỂM THỬ CÁC GIAI ĐOẠN (SPRINTS 1–8)

Toàn bộ hệ thống T-TTS v3.1.0 đã trải qua quy trình kiểm thử hồi quy phân cấp nghiêm ngặt từ Sprint 1 đến Sprint 8 với kết quả đạt 100% hoàn hảo:

| Giai Đoạn / Sprint | Nội Dung Kiểm Thử Trọng Tâm | Số Lượng Tests | Kết Quả | Tỷ Lệ |
|:---|:---|:---:|:---:|:---:|
| **Sprint 1** | Document Reader (Trích xuất DOCX, PDF, TXT, Non-blocking Worker, Cancel) | 13 | 13/13 PASS | 100% |
| **Sprint 2** | Text Processor (Chuẩn hóa tiếng Việt NFC, quy tắc đọc số, Document Project) | 16 | 16/16 PASS | 100% |
| **Sprint 3** | Core Audio DSP (Giảm nhiễu afftdn, Voice EQ 5 dải, Chuẩn hóa EBU R128 LUFS) | 16 | 16/16 PASS | 100% |
| **Sprint 4** | Advanced DSP (De-Esser khử âm xì, Compressor nén động học, Brickwall Limiter) | 16 | 16/16 PASS | 100% |
| **Sprint 5** | Intelligent Audio (Voice Quality Analyzer, Military Presets, Smart Mix) | 16 | 16/16 PASS | 100% |
| **Sprint 6** | Full Studio Integration (Synthesize, Audio Studio, Broadcast, Schedule) | 16 | 16/16 PASS | 100% |
| **Sprint 7** | Auto Update Engine & Safe Migration (Nhảy cóc 3.0.0 ➔ 3.1.0, Backup, Rollback) | 16 | 16/16 PASS | 100% |
| **Sprint 8** | Final Packaging, Clean Install, Upgrade, 100% Offline, Regression | 7 | 7/7 PASS | 100% |
| **TỔNG CỘNG** | **Toàn bộ hệ thống T-TTS v3.1.0 Native Desktop** | **116** | **116/116 PASS** | **100%** |

---

## 2. KẾT QUẢ KIỂM THỬ THỰC TẾ CHI TIẾT SPRINT 8

### 2.1. TEST 1 — CLEAN INSTALL (CÀI ĐẶT SẠCH)
- **Mục tiêu:** Kiểm tra trải nghiệm người dùng cài mới trên máy sạch không có dữ liệu trước đó.
- **Kết quả thực tế:**
  * Bộ cài đặt tự động triển khai đầy đủ binary `T-TTS.exe`, thư mục `_internal`, `models/`, `gui/` và cấu trúc `data/` sạch.
  * Bản cài đặt **không chứa** license cá nhân hoặc dữ liệu thử nghiệm của lập trình viên.
  * Ứng dụng khởi động lần đầu thông báo trạng thái `Chưa kích hoạt`.
  * Mã máy (Machine ID) được tạo ổn định duy nhất dựa trên phần cứng Windows.
  * Kích hoạt offline bằng khóa Ed25519 thành công, chuyển sang trạng thái `Active`.
  * Nạp đầy đủ 25 giọng đọc allowlist từ mô hình VieNeu-TTS v3 Turbo ONNX CPU.
  * Trích xuất tài liệu DOCX/PDF/TXT, chuẩn hóa đọc số, xử lý DSP và xuất âm thanh WAV/MP3 hoạt động hoàn hảo.
  * Đóng và mở lại: Dữ liệu và trạng thái kích hoạt được duy trì bền vững 100%.

### 2.2. TEST 2 — UPGRADE v3.0.0 ➔ v3.1.0 (NÂNG CẤP TRỰC TIẾP)
- **Mục tiêu:** Kiểm tra nâng cấp từ phiên bản v3.0.0 đang sử dụng thực tế mà không cần qua bản trung gian v3.0.1.
- **Chuẩn bị dữ liệu mẫu:**
  * Khóa bản quyền Ed25519 (`license_state.json`) kèm Machine ID.
  * Lịch sử chuyển đổi TTS (`history.json`).
  * Từ điển phát âm viết tắt quân sự (`pronunciation-dict.json`).
  * Danh mục giọng tùy biến (`custom_voices.json`).
  * 3 dự án độc lập: Thu âm Audio Studio, Bản tin Broadcast Studio, Lịch phát thanh Schedule Studio.
- **Kết quả thực tế:**
  * Engine cập nhật phát hiện bản phát hành v3.1.0 và xác nhận điều kiện nâng cấp trực tiếp.
  * Bản sao lưu dự phòng (Pre-Update Backup) snapshot được tạo tự động với mã SHA-256 đối soát.
  * Quá trình di chuyển dữ liệu (`perform_data_migration`) tạo mới các thư mục `projects/documents/` và `presets/audio_presets.json` của v3.1.0.
  * Toàn bộ License, Machine ID, History, Dictionary, Custom Voices và 3 dự án cũ được bảo toàn nguyên vẹn 100%.
  * Tệp nhật ký `migration_v3.0.0_to_v3.1.0.json` ghi nhận rõ ràng: `bypassed_version: "3.0.1"` và `direct_jump: true`.

### 2.3. TEST 3 — ROLLBACK THỰC TẾ
- **Phục hồi dữ liệu (Data Rollback):**
  * Thử nghiệm phá hoại hoặc xóa nhầm file từ điển và lịch sử.
  * Gọi chức năng `restore_backup(backup_file)`: Toàn bộ cấu hình và dự án được phục hồi 100% về trạng thái trước nâng cấp.
- **Hạ phiên bản nhị phân (Binary Rollback):**
  * Do bộ cài Inno Setup quản lý file nhị phân độc lập, khi cần hạ phiên bản ứng dụng, người dùng chỉ cần chạy lại bộ cài `T-TTS_Setup_v3.0.0_Offline.exe` hoặc mở lại thư mục bản Portable v3.0.0 mà không ảnh hưởng tới dữ liệu cá nhân.

### 2.4. TEST 4 — HOẠT ĐỘNG NGOẠI TUYẾN 100% (STAND-ALONE OFFLINE)
- **Mục tiêu:** Khóa toàn bộ kết nối mạng (Socket blocked) và vận hành ứng dụng.
- **Kết quả thực tế:**
  * VieNeu-TTS v3 Turbo ONNX CPU suy luận giọng đọc 100% offline.
  * 25 giọng đọc allowlist nạp từ tệp cục bộ không cần tải thêm dữ liệu.
  * Phân hệ Audio DSP (afftdn, EQ, Compressor, Limiter, LUFS) xử lý offline trên CPU.
  * Xác thực bản quyền Ed25519 và Machine ID vận hành độc lập không gửi tín hiệu ra ngoài.
  * FFmpeg tích hợp sẵn hoạt động trơn tru.

---

## 3. KẾT LUẬN VÀ TRẠNG THÁI PHÁT HÀNH

Phiên bản **T-TTS v3.1.0** đã hoàn thành 100% các tiêu chí kỹ thuật, đảm bảo độ ổn định cao, bảo toàn trọn vẹn dữ liệu và sẵn sàng phát hành chính thức dưới quyền phê duyệt của tác giả Nguyễn Văn Tiệp.
