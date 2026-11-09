# T-TTS v3.0.1 — BÁO CÁO NGHIỆM THU PHASE 6
# PACKAGING & RELEASE T-TTS v3.0.1 OFFLINE

**Dự án:** T-TTS — Hệ Thống Trợ Lý Giọng Nói Quân Đội (Bản Desktop Native Windows)  
**Tác giả:** Nguyễn Văn Tiệp  
**Thời gian hoàn thành:** 09/11/2026 06:00 (Giờ hệ thống)  
**Phiên bản phát hành:** `v3.0.1`  
**Trạng thái:** **PASS 100% — SẴN SÀNG PHÁT HÀNH CHÍNH THỨC**  
**Kho lưu trữ GitHub:** `https://github.com/tiepheo37/T-TTS`  

---

## I. TỔNG HỢP KẾT QUẢ ĐÓNG GÓI (BUILD RESULTS)

Hệ thống đã hoàn tất toàn bộ quy trình biên dịch nhị phân PyInstaller và đóng gói Inno Setup 6:

| Tập tin phát hành | Loại tệp | Dung lượng | Mã băm SHA-256 thực tế |
|:---|:---:|:---:|:---|
| **`T-TTS_Setup_v3.0.1_Offline.exe`** | **Bộ cài đặt Windows x64** | **421.03 MB** (441,480,828 B) | `a042a8f24681f27c8f76a8dda7617d30fd9e008d79e186e4f938712129e8fa46` |
| **`T-TTS_v3.0.1_Desktop_Portable.zip`** | **Bản nén Portable không cần cài** | **529.09 MB** (554,790,251 B) | `76aa0aaa346916e1964e89b9df07e7570829b2de77236d7d6caac11299683ac4` |
| `release_metadata.json` | Metadata JSON kiểm chứng | 2.1 KB | Chuẩn cấu trúc phục vụ Auto Update |
| `RELEASE_NOTES_v3.0.1.md` | Ghi chú phát hành GitHub | 2.6 KB | Soạn sẵn theo chuẩn định dạng Markdown |
| `checksums.txt` | Bảng mã băm toàn vẹn | 680 B | Đối soát mã băm SHA-256 các file trong `dist/` |

> [!IMPORTANT]
> **Bảo lưu an toàn:** Các bộ cài đặt phiên bản tiền nhiệm (`T-TTS_Setup_v3.0_Offline.exe`, `T-TTS_Setup_v3.0.0.Offline.exe`) và bản sao lưu Phase 0 (`backups/backup_v3.0.0_pre_v3.0.1.zip`) được giữ nguyên vẹn 100%, không bị xóa hay ghi đè.

---

## II. KẾT QUẢ KIỂM THỬ NÂNG CẤP THỰC TẾ (UPGRADE TEST v3.0.0 → v3.0.1)

Kiểm thử được thực hiện tự động trong môi trường sandbox cô lập thông qua kịch bản [`tools/test_phase_6_packaging_verification.py`](file:///D:/cac%20loai%20app/voice-studio-app/tools/test_phase_6_packaging_verification.py):

| STT | Nội dung kiểm thử | Kết quả | Chi tiết kỹ thuật |
|:---:|:---|:---:|:---|
| 1 | Xác minh bộ cài Offline v3.0.1 | **PASS** | Tệp tồn tại, kích thước 421.03 MB đạt chuẩn |
| 2 | Đối soát mã băm SHA-256 | **PASS** | Khớp 100% với `dist/release_metadata.json` |
| 3 | Kiểm tra bản Portable ZIP | **PASS** | Chứa đầy đủ `T-TTS.exe`, `models/`, `gui/`, `_internal/` |
| 4 | Kiểm tra Release Notes v3.0.1 | **PASS** | Đầy đủ 4 phân hệ mới và tài liệu kỹ thuật |
| 5 | Cài mới v3.0.1 vào sandbox | **PASS** | Inno Setup silent install `/VERYSILENT` thành công (Code 0) |
| 6 | Kiểm tra thực thi binary `T-TTS.exe` | **PASS** | Binary x64 hoàn chỉnh, không thiếu dependency |
| 7 | Kiểm tra mô hình VieNeu-TTS v3 Turbo | **PASS** | `vieneu_prefill.onnx`, `moss_audio_tokenizer` đầy đủ |
| 8 | Giả lập môi trường dữ liệu v3.0.0 | **PASS** | Nạp History (2 bản ghi), Custom Voices, License, Projects |
| 9 | Phát hiện cập nhật qua UpdateManager | **PASS** | Nhận diện chính xác `v3.0.1 > v3.0.0` |
| 10 | Tạo snapshot sao lưu Pre-Update | **PASS** | Lưu trữ `pre_update_backup_<timestamp>.json` an toàn |
| 11 | Cài đè nâng cấp v3.0.1 | **PASS** | Inno Setup thực thi nâng cấp đè không xung đột (Code 0) |
| 12 | **Bảo toàn lịch sử TTS** | **PASS** | **100% bản ghi lịch sử nguyên vẹn** |
| 13 | **Bảo toàn Custom Voices & License** | **PASS** | **Hồ sơ giọng nói và License Ed25519 nguyên vẹn** |
| 14 | **Bảo toàn toàn bộ Projects** | **PASS** | **Audio Projects, Broadcast Projects, Schedule Projects nguyên vẹn** |
| 15 | Kiểm tra khả năng Rollback | **PASS** | Phục hồi dữ liệu từ snapshot sao lưu thành công |
| 16 | Gỡ cài đặt an toàn (Uninstaller) | **PASS** | Dọn sạch binary `T-TTS.exe`, giữ lại dữ liệu người dùng |

---

## III. CÁC PHÁT HIỆN KỸ THUẬT QUAN TRỌNG & ĐÃ KHẮC PHỤC

1. **Cơ chế ghi đè dữ liệu người dùng khi nâng cấp (Inno Setup):**
   - *Phát hiện:* Ban đầu cờ trong Inno Setup chỉ có `uninsneveruninstall`. Khi cài đè phiên bản mới, Inno Setup mặc định ghi đè các tệp cùng tên trong `{app}\data` bằng tệp gốc từ bộ cài.
   - *Khắc phục:* Bổ sung cờ **`onlyifdoesntexist`** cho toàn bộ thư mục `{app}\data` và `{app}\output` trong `setup_installer.iss`. Nhờ đó:
     - Khi cài mới: Cung cấp đầy đủ tệp cấu hình mẫu.
     - Khi nâng cấp từ v3.0.0: Tuyệt đối **KHÔNG ghi đè** bất kỳ tệp dữ liệu cá nhân nào của người dùng.
2. **Xử lý chuỗi phiên bản có hậu tố:**
   - *Phát hiện:* Một số tên gói mang hậu tố `_Offline` khiến hàm so sánh phiên bản phân tách chưa triệt để.
   - *Khắc phục:* Bổ sung biểu thức chính quy `re.match(r"^(\d+)", part)` và `.split("_")[0]` trong `backend/version.py`, đảm bảo so sánh số học chính xác 100%.

---

## IV. TỔNG KẾT TẤT CẢ CÁC PHASE (145/145 TESTS PASS 100%)

- **Phase 0:** Audit & Backup an toàn (`backup_v3.0.0_pre_v3.0.1.zip`).
- **Phase 1:** Core Infrastructure (14/14 tests PASS).
- **Phase 2:** Schedule Studio (20/20 tests PASS).
- **Phase 3:** Audio Studio (28/28 tests PASS).
- **Phase 4:** Broadcast Studio 2.0 (35/35 tests PASS).
- **Phase 5:** Auto Update & GitHub Releases (32/32 tests PASS).
- **Phase 6:** Packaging & Upgrade Verification (16/16 tests PASS).
- **Tổng cộng:** **145/145 tiêu chí kiểm thử đạt PASS 100%**.

---

## V. HƯỚNG DẪN XUẤT BẢN GITHUB RELEASE v3.0.1

Bộ cài đặt đã được chuẩn bị đầy đủ trong thư mục `dist/`. Theo nguyên tắc an toàn, hệ thống **chưa tự động publish** lên GitHub mà bàn giao để bạn chủ động xuất bản:

### Các bước thực hiện trên GitHub:
1. Mở trình duyệt và truy cập:  
   `https://github.com/tiepheo37/T-TTS/releases/new`
2. Điền thông tin phát hành:
   * **Choose a tag:** Gõ `v3.0.1` -> Chọn **Create new tag: v3.0.1 on publish**.
   * **Target:** `main`.
   * **Release title:**  
     `T-TTS v3.0.1 — Bản Phát Hành Chính Thức (Schedule, Audio & Broadcast Studio 2.0)`
   * **Describe this release:**  
     Mở tệp `dist/RELEASE_NOTES_v3.0.1.md` và dán toàn bộ nội dung vào khung mô tả.
3. **Đính kèm tập tin phát hành (Attach binaries):**
   * Kéo và thả tệp:  
     `dist/T-TTS_Setup_v3.0.1_Offline.exe` (421 MB)
   * (Tùy chọn) Kéo thêm tệp Portable:  
     `dist/T-TTS_v3.0.1_Desktop_Portable.zip` (529 MB)
4. Bấm nút xanh **Publish release**.

> [!TIP]
> **Kết quả đạt được ngay sau khi Publish:**  
> Tất cả người dùng đang sử dụng bản v3.0.0 khi mở phần mềm T-TTS (hoặc vào tab Cài đặt bấm *"Kiểm tra cập nhật ngay"*) sẽ lập tức nhận được hộp thoại thông báo cập nhật lên **v3.0.1**. Người dùng chỉ cần bấm *"Cập nhật ngay"*, hệ thống sẽ tự động tải về, kiểm tra SHA-256 và cài đè an toàn mà **không mất bất kỳ dữ liệu nào**.
