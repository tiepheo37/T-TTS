# BÁO CÁO NGHIỆM THU SPRINT 7: AUTO UPDATE ENGINE & SAFE MIGRATION v3.0.0 ➔ v3.1.0
## HỆ THỐNG TRỢ LÝ GIỌNG NÓI QUÂN ĐỘI T-TTS (VieNeu-TTS v3 Turbo ONNX CPU)

**Tác giả:** Nguyễn Văn Tiệp  
**Phiên bản hiện hành:** v3.1.0  
**Phiên bản nâng cấp từ:** v3.0.0 (Bỏ qua hoàn toàn v3.0.1)  
**Nhánh Git:** `dev-v3.1.0`  
**Ngày nghiệm thu:** 09/11/2026  
**Trạng thái kiểm thử:** 16/16 Test Cases ĐẠT (100% PASS) | Toàn hệ thống (Sprints 1–7): 109/109 PASS (100%)

---

## 1. TỔNG QUAN VÀ MỤC TIÊU SPRINT 7

Sprint 7 tập trung xây dựng cơ chế **Cập nhật Tự động (Auto Update Engine)** và **Di chuyển Dữ liệu An toàn (Safe Data Migration)** trực tiếp từ phiên bản đang cài đặt **v3.0.0** lên phiên bản master **v3.1.0**.

### Các nguyên tắc cốt lõi đã tuân thủ tuyệt đối:
1. **Nhảy cóc trực tiếp v3.0.0 ➔ v3.1.0:** Bỏ qua hoàn toàn v3.0.1; không yêu cầu người dùng cài đặt trung gian; không bao giờ kiểm tra hoặc bắt buộc sự hiện diện của v3.0.1.
2. **Bảo toàn 100% dữ liệu:** Không ghi đè hoặc làm hỏng dữ liệu người dùng (`%LOCALAPPDATA%\T-TTS`):
   - Bản quyền offline Ed25519 (`license_state.json`), Machine ID, trạng thái kích hoạt và chữ ký HMAC.
   - Từ điển phiên âm quân sự (`pronunciation-dict.json`).
   - Lịch sử chuyển đổi TTS (`history.json`).
   - Giọng nói tùy biến (`custom_voices.json`).
   - Toàn bộ dự án cũ: Thu âm (`projects/audio/`), Bản tin (`projects/broadcast/`), Lịch phát sóng (`projects/schedules/`).
3. **Sao lưu trước khi nâng cấp (Pre-Update Backup):** Tự động tạo snapshot đầy đủ gồm dữ liệu cấu hình, license, toàn bộ cây thư mục dự án và mã băm SHA-256 cho từng file.
4. **Cơ chế Khôi phục / Rollback:** Hỗ trợ người dùng phục hồi trạng thái dữ liệu nguyên bản chỉ với 1 cú nhấp chuột khi có sự cố.
5. **Giao diện Quân đội K20 (Dark Military K20):** Thiết kế hộp thoại cập nhật đồng bộ nhận diện thương hiệu quân sự (#0F1E11, #FFD700, #4ADE80), hiển thị huy hiệu nâng cấp trực tiếp và thanh tiến trình tải thời gian thực.
6. **Không cập nhật ngầm (No Silent Update):** Mọi hành động tải về hoặc thực thi bộ cài đều đòi hỏi sự xác nhận tường minh của người dùng.

---

## 2. KẾT QUẢ TRIỂN KHAI KỸ THUẬT

### 2.1. Nâng cấp Engine Quản lý Cập nhật (`backend/updater.py`)
- **`UpdateManager.__init__(data_dir, current_version)`**: Hỗ trợ chỉ định linh hoạt phiên bản đang chạy (mặc định lấy `APP_VERSION`), tạo điều kiện thuận lợi cho việc mô phỏng và kiểm thử nâng cấp từ v3.0.0.
- **`parse_release_data(target_rel)`**: Phân tích chuẩn hóa phản hồi từ GitHub Releases REST API, trích xuất mã SHA-256 từ digest hoặc nội dung body, phát hiện tài sản setup (`.exe`).
- **`check_system_readiness(required_free_mb=500)`**: Kiểm tra điều kiện tiên quyết trước khi cập nhật gồm:
  * Dung lượng đĩa khả dụng trên phân vùng chứa `%LOCALAPPDATA%` (đảm bảo $\ge 500$ MB).
  * Quyền ghi (write permission) tại thư mục dữ liệu ứng dụng.
  * Quyền ghi tại thư mục tạm thời hệ thống (`%TEMP%\T-TTS_Updates`).
- **`create_pre_update_backup(target_version)`**: Tạo gói lưu trữ JSON toàn diện tại `data/backups/`:
  * Bao gồm: `update_config.json`, `custom_voices.json`, `license_state.json`, `history.json`, `pronunciation-dict.json`, `system_settings.json`.
  * Bao gồm toàn bộ file dự án trong `data/projects/`.
  * Ghi lại mã SHA-256, Machine ID, thời điểm tạo và nhãn phiên bản nguồn/đích.
- **`restore_backup(backup_file)`**: Phục hồi an toàn toàn bộ dữ liệu cấu hình và cây thư mục dự án từ snapshot JSON được chọn.
- **`list_backups()`**: Liệt kê danh sách các bản sao lưu đã tạo, sắp xếp mới nhất lên đầu với đầy đủ thông tin thời gian, phiên bản, dung lượng và số lượng dự án.
- **`perform_data_migration(from_version="3.0.0", to_version="3.1.0")`**:
  * Tự động tạo snapshot sao lưu dự phòng.
  * Khởi tạo các thư mục dữ liệu mới của v3.1.0: `data/projects/documents/`, `data/presets/`.
  * Khởi tạo file preset mẫu `audio_presets.json` nếu chưa tồn tại, tuyệt đối không ghi đè cấu hình của người dùng.
  * Xuất manifest nhật ký di chuyển `data/migration_v3.0.0_to_v3.1.0.json`, ghi rõ `bypassed_version: "3.0.1"` và `direct_jump: true`.
- **`download_update(...)`**: Tải streaming với khối 128 KB, báo cáo phần trăm, dung lượng và tốc độ MB/s; đối soát mã băm SHA-256; tự động xóa tệp tạm nếu mã băm không khớp hoặc người dùng hủy thao tác.
- **`install_and_restart(...)`**: Tự động gọi `create_pre_update_backup()`, khởi chạy trình cài đặt Inno Setup với cờ `/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS` và thoát tiến trình sạch sẽ.

### 2.2. Nâng cấp Giao diện Update Hộp thoại Quân đội K20 (`gui/dialog_update.py`)
- Áp dụng bộ stylesheet **`MILITARY_K20_UPDATE_QSS`**:
  * Nền: Xanh quân đội sẫm (`#0F1E11` / `#142817`), viền `#27472A`.
  * Điểm nhấn: Vàng kim sao vàng (`#FFD700`) và xanh lá K20 (`#4ADE80` / `#2D5A27`).
- Bổ sung Huy hiệu Nổi bật:  
  `★ NÂNG CẤP TRỰC TIẾP v3.0.0 → v3.1.0 (BẢO TOÀN 100% DỮ LIỆU & BẢN QUYỀN) ★`
- Bổ sung Nút **`↺ Khôi phục sao lưu` (Rollback)**: Cho phép xem chi tiết và khôi phục dữ liệu từ snapshot dự phòng gần nhất có xác nhận người dùng.
- Hiển thị danh mục tính năng mới trong bản phát hành v3.1.0 (Nhập tài liệu Word/PDF, Đọc số quân sự, Bộ xử lý EQ/Compressor/LUFS/De-Esser, Presets AI).

---

## 3. BẢNG KẾT QUẢ KIỂM THỬ SPRINT 7 (16/16 PASS)

Bộ kiểm thử `tools/test_sprint_7_auto_update.py` đã được thực thi thực tế trên nền tảng Python 3.12:

| STT | Tên Test Case | Mục Tiêu Kiểm Thử | Kết Quả |
|:---:|:---|:---|:---:|
| **01** | `test_01_version_comparison_and_v301_bypass` | So sánh phiên bản `(3, 1, 0) > (3, 0, 0)` và bỏ qua hoàn toàn v3.0.1 | **PASS** |
| **02** | `test_02_release_metadata_parsing` | Phân tích JSON GitHub Release v3.1.0, trích xuất SHA-256 và Setup asset | **PASS** |
| **03** | `test_03_download_integrity_and_sha256` | Tải dữ liệu, xác minh SHA-256 khớp và từ chối/xóa file khi SHA-256 sai lệch | **PASS** |
| **04** | `test_04_system_readiness_checks` | Đo dung lượng đĩa trống, kiểm tra quyền ghi thư mục dữ liệu và thư mục tạm | **PASS** |
| **05** | `test_05_pre_update_backup_creation` | Sao lưu toàn bộ config, license, dictionary, history và projects với checksum | **PASS** |
| **06** | `test_06_data_migration_v300_to_v310` | Tạo thư mục v3.1.0, ghi nhận nhật ký bỏ qua v3.0.1, bảo vệ dữ liệu cũ | **PASS** |
| **07** | `test_07_rollback_and_restore_backup` | Liệt kê danh sách backup và phục hồi nguyên vẹn dữ liệu từ snapshot JSON | **PASS** |
| **08** | `test_08_ed25519_license_preservation` | Giữ nguyên Machine ID, trạng thái bản quyền và chữ ký Ed25519/HMAC | **PASS** |
| **09** | `test_09_user_data_preservation` | Bảo toàn 100% dự án Audio, Broadcast, Schedule và Custom Voices | **PASS** |
| **10** | `test_10_interrupted_download_cleanup` | Dọn dẹp sạch tệp tạm khi người dùng hủy hoặc ngắt kết nối giữa chừng | **PASS** |
| **11** | `test_11_installer_launch_parameters` | Xác nhận cờ Inno Setup `/SILENT`, `/CLOSEAPPLICATIONS`, `/RESTARTAPPLICATIONS` | **PASS** |
| **12** | `test_12_update_dialog_military_ui` | Kiểm tra giao diện Dark Military K20, huy hiệu nâng cấp và nút Rollback | **PASS** |
| **13** | `test_13_check_update_worker_thread` | Chạy ngầm kiểm tra cập nhật trên QThread, phát tín hiệu không treo UI | **PASS** |
| **14** | `test_14_download_update_worker_thread` | Tải ngầm trên QThread, phát tín hiệu phần trăm, dung lượng, tốc độ thời gian thực | **PASS** |
| **15** | `test_15_no_silent_update_enforcement` | Đảm bảo không bao giờ cập nhật ngầm, luôn chờ người dùng bấm xác nhận | **PASS** |
| **16** | `test_16_full_regression_all_modules` | Kiểm tra hồi quy VieNeu-TTS, Document Reader, Text Processor, Audio DSP, Projects | **PASS** |

---

## 4. TỔNG HỢP KIỂM THỬ HỒI QUY TOÀN HỆ THỐNG (SPRINTS 1–7)

Tất cả các bộ kiểm thử từ Sprint 1 đến Sprint 7 đã được chạy tuần tự và đạt kết quả tuyệt đối:

| Sprint | Nội Dung | Số Test | Trạng Thái |
|:---|:---|:---:|:---:|
| **Sprint 1** | Document Import (DOCX, PDF, TXT) | 13 | **13/13 PASS** (100%) |
| **Sprint 2** | Text Normalization & Vietnamese Number Reading | 16 | **16/16 PASS** (100%) |
| **Sprint 3** | Core Audio Enhancement (Noise Reduction, EQ, LUFS) | 16 | **16/16 PASS** (100%) |
| **Sprint 4** | Advanced DSP (De-Esser, Compressor, Limiter, Pipeline) | 16 | **16/16 PASS** (100%) |
| **Sprint 5** | Intelligent Audio Processing (Analyzer, Presets, Smart Mix) | 16 | **16/16 PASS** (100%) |
| **Sprint 6** | Full Studio Integration & Cross-Module Data Flow | 16 | **16/16 PASS** (100%) |
| **Sprint 7** | Auto Update Engine & Safe Migration v3.0.0 ➔ v3.1.0 | 16 | **16/16 PASS** (100%) |
| **TỔNG CỘNG** | **Toàn bộ tính năng T-TTS v3.1.0** | **109** | **109/109 PASS (100%)** |

---

## 5. HÌNH ẢNH GIAO DIỆN SPRINT 7 (SCREENSHOTS)

Các ảnh chụp màn hình giao diện thực tế đã được xuất vào `docs/screenshots/` và thư mục Artifact:

1. **Hộp thoại Cập nhật Phong cách Quân đội K20 (Sẵn sàng nâng cấp):**  
   `docs/screenshots/sprint_7_update_dialog_military_k20.png`  
   - Huy hiệu `★ NÂNG CẤP TRỰC TIẾP v3.0.0 → v3.1.0 (BẢO TOÀN 100% DỮ LIỆU & BẢN QUYỀN) ★`.
   - Danh sách tính năng mới trong bản phát hành v3.1.0.
   - Nút `↺ Khôi phục sao lưu` (Rollback) và `🚀 Cập nhật ngay`.

2. **Tiến trình Tải Bản Cập nhật Thời Gian Thực:**  
   `docs/screenshots/sprint_7_update_progress_downloading.png`  
   - Thanh tiến trình tải màu xanh K20 gradients.
   - Báo cáo chi tiết dung lượng tải, tổng dung lượng và tốc độ tải tức thời.
   - Nút `🛑 Hủy tải` cho phép hủy an toàn và dọn dẹp bộ nhớ tạm.

---

## 6. KẾ HOẠCH BƯỚC TIẾP THEO (SPRINT 8)

Sau khi hoàn thành xuất sắc Sprint 7, hệ thống sẵn sàng bước vào **Sprint 8: Installer Packaging & Release Readiness**:
1. Cập nhật cấu hình kịch bản Inno Setup / VelopPack đóng gói bộ cài đặt chính thức v3.1.0.
2. Kiểm tra tính toàn vẹn của gói cài đặt độc lập (Stand-alone Installer), xác minh khả năng ghi đè an toàn nâng cấp từ v3.0.0.
3. Tạo checksum `sha256sum` chính thức cho file `T-TTS_v3.1.0_Setup.exe`.
4. Chuẩn bị Release Notes cuối cùng để người dùng phát hành phiên bản.
