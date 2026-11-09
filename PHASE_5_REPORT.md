# T-TTS v3.0 — BÁO CÁO NGHIỆM THU PHASE 5
# AUTO UPDATE & GITHUB RELEASES SUBSYSTEM AUDIT & HARDENING

**Dự án:** T-TTS — Hệ Thống Trợ Lý Giọng Nói Quân Đội (Bản Desktop Native Windows)  
**Tác giả:** Nguyễn Văn Tiệp  
**Thời gian thực hiện:** 08/11/2026 22:05 (Giờ hệ thống)  
**Phiên bản hiện tại:** `v3.0.0` (Bảo lưu nghiêm ngặt, chưa nâng version trước khi được phê duyệt)  
**Phiên bản mục tiêu:** `v3.0.1`  
**Kho lưu trữ GitHub chính thức:** `https://github.com/tiepheo37/T-TTS`  

---

## I. TỔNG QUAN AUDIT HỆ THỐNG AUTO UPDATE

Hệ thống cập nhật tự động của T-TTS đã được kiểm toán toàn diện trên các thành phần cốt lõi:
1. `backend/updater.py`: Quản lý truy vấn GitHub Releases API, streaming download, xác minh SHA-256, khởi chạy installer và tạo snapshot sao lưu an toàn.
2. `gui/dialog_update.py`: Giao diện thông báo cập nhật chuẩn Dark Navy Blue (#0B192C / #2563EB), hiển thị ghi chú phiên bản (Release Notes), ngày phát hành, dung lượng tệp, tiến trình tải thời gian thực và tùy chọn không bắt buộc (người dùng hoàn toàn có thể chọn *"Để sau"*).
3. `backend/version.py`: Cơ chế phân tích phiên bản toán học `parse_version()` và `is_newer_version()` với tuple số nguyên đa phân đoạn, loại bỏ hoàn toàn lỗi so sánh chuỗi từ vựng thông thường.
4. `setup_installer.iss`: Cấu hình Inno Setup với cờ `RestartApplications=yes`, `CloseApplications=yes`, và `uninsneveruninstall` bảo vệ dữ liệu thư mục `{app}\data` và `{app}\output`.
5. `dist/release_metadata.json`: Bản ghi metadata kiểm chứng tính toàn vẹn gói cài đặt.

---

## II. XỬ LÝ TRIỆT ĐỂ LỖI HTTP 404 & CẢI TIẾN API GITHUB

### 1. Nguyên nhân gốc rễ của lỗi 404 (Ảnh người dùng cung cấp)
- **Tình huống thực tế:** Khi người dùng bấm *"Kiểm tra cập nhật ngay"* tại thời điểm kho lưu trữ chưa có Release nào hoặc Release đang ở chế độ Draft / Private, GitHub trả về HTTP 404.
- **Hiện trạng:** Kho `tiepheo37/T-TTS` hiện đã phát hành Release `v3.0.0` công khai (`https://github.com/tiepheo37/T-TTS/releases/tag/v3.0.0`) với tệp cài đặt `T-TTS_Setup_v3.0.0.Offline.exe` (429 MB). Kết nối kiểm tra hiện tại đạt **HTTP 200 OK**.

### 2. Kiến trúc truy vấn GitHub API mới
* **Ưu tiên kênh Stable:** Truy vấn thẳng vào endpoint chuẩn của GitHub:  
  `https://api.github.com/repos/tiepheo37/T-TTS/releases/latest`
* **Cơ chế Fallback thông minh:** Nếu endpoint `/latest` trả về 404 (do phiên bản mới nhất là prerelease hoặc chưa gán cờ latest), hệ thống tự động fallback truy vấn `/releases` để quét danh sách.
* **Xử lý mã lỗi phân biệt rõ ràng:**
  - `HTTP 404`: Thông báo *"Kho lưu trữ GitHub chưa có bản phát hành nào hoặc đang ở chế độ riêng tư"*, tuyệt đối không coi là lỗi nghiêm trọng, không làm đóng băng hay crash ứng dụng.
  - `HTTP 403 / 429`: Nhận diện quá hạn ngạch Rate Limit và hướng dẫn thử lại sau ít phút.
  - `Timeout / URLError`: Nhận diện ngắt kết nối mạng hoặc timeout, thông báo kiểm tra Internet.

---

## III. THUẬT TOÁN SO SÁNH PHIÊN BẢN (VERSION COMPARISON)

Để tránh hoàn toàn lỗi so sánh chuỗi (ví dụ `"3.0.10" < "3.0.2"` trong chuỗi ASCII), thuật toán trong `backend/version.py` đã được chuẩn hóa:
```python
def parse_version(ver_str: str) -> Tuple[int, ...]:
    cleaned = str(ver_str).strip().lstrip("vV").split("-")[0].split("+")[0].split("_")[0]
    parts = []
    for part in cleaned.split("."):
        m = re.match(r"^(\d+)", part)
        parts.append(int(m.group(1)) if m else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)
```
* **Kiểm chứng toán học:**
  - `3.0.0 < 3.0.1` : **True**
  - `3.0.1 < 3.0.10` : **True**
  - `3.0.10 > 3.0.2` : **True**
  - `3.1.0 > 3.0.10` : **True**
  - `4.0.0 > 3.1.0` : **True**
  - `3.0.0 == 3.0.0` : **False (Không kích hoạt popup cập nhật khi bằng nhau)**

---

## IV. BẢO MẬT TẢI VỀ & CƠ CHẾ ROLLBACK

1. **Tải về an toàn (Streaming Download):**
   - Tải tệp theo chunk 128 KB qua kết nối HTTPS có xác thực chứng chỉ SSL.
   - Cơ chế tự động thử lại (Retry) tối đa 3 lần khi đường truyền bị gián đoạn giữa chừng.
   - Thư mục lưu tạm chuyên biệt: `%TEMP%\T-TTS_Updates\` (không ghi đè bản cài đặt trong `dist/`).
2. **Xác minh mã băm toàn vẹn (SHA-256):**
   - Tự động băm SHA-256 trực tiếp trong quá trình stream tải.
   - So khớp với mã SHA-256 từ Release Digest hoặc Release Body.
   - **Chính sách từ chối:** Nếu mã SHA-256 sai lệch dù chỉ 1 bit, tệp tải về sẽ bị xóa lập tức và quá trình cập nhật bị hủy bỏ với cảnh báo an ninh rõ ràng.
3. **Cơ chế Rollback & Sao lưu trước nâng cấp (Pre-update Snapshot):**
   - Hàm `create_pre_update_backup()` tự động sao lưu cấu hình, license và các dự án vào thư mục `data/backups/pre_update_backup_<timestamp>.json` trước khi khởi chạy bộ cài đặt mới.
   - Tệp cài đặt Inno Setup được cấu hình cờ `uninsneveruninstall` cho toàn bộ `{app}\data` và `{app}\output`, đảm bảo:
     - Giữ nguyên Machine ID và License offline Ed25519.
     - Giữ nguyên lịch sử chuyển đổi giọng nói (`history.json`).
     - Giữ nguyên hồ sơ giọng nói tùy chỉnh (`custom_voices.json`).
     - Giữ nguyên toàn bộ dự án Audio Studio, Broadcast Studio 2.0 và Schedule Studio.

---

## V. KẾT QUẢ BỘ KIỂM THỬ TỰ ĐỘNG PHASE 5 (32/32 TIÊU CHÍ PASS)

Bộ test `tools/test_phase_5_auto_update.py` đã thực thi kiểm thử 32 tiêu chí:

| STT | Tiêu chí kiểm thử | Kết quả | Ghi chú kỹ thuật |
|:---:|:---|:---:|:---|
| 1 | API Release Repo & Configuration | **PASS** | Tự động đọc đúng `tiepheo37/T-TTS` và kênh `stable` |
| 2 | HTTP 200 Response & JSON Parsing | **PASS** | Phân tích siêu dữ liệu phiên bản mới chính xác |
| 3 | HTTP 404 Error Handling | **PASS** | Bắt lỗi 404 êm ái, hướng dẫn rõ ràng, không crash UI |
| 4 | HTTP 403 / 429 Rate Limit Detection | **PASS** | Nhận diện quá hạn ngạch truy vấn GitHub |
| 5 | Network Timeout Handling | **PASS** | Xử lý timeout kết nối mượt mà, không treo luồng giao diện |
| 6 | Version Comparison Arithmetic | **PASS** | So sánh tuple số nguyên chuẩn xác đa phân đoạn |
| 7 | Same Version Check | **PASS** | Phiên bản 3.0.0 == 3.0.0 không kích hoạt cập nhật |
| 8 | New Version Detection | **PASS** | Nhận diện chính xác 3.0.1 > 3.0.0 |
| 9 | Download Streaming & Progress | **PASS** | Báo cáo tiến trình thời gian thực (`pct`, `MB`, `MB/s`) |
| 10 | Download Retry on Network Glitch | **PASS** | Hỗ trợ 3 lần retry khi kết nối mạng chập chờn |
| 11 | SHA-256 Valid Verification | **PASS** | Xác minh mã băm toàn vẹn tệp thành công |
| 12 | SHA-256 Invalid Tamper Detection | **PASS** | Phát hiện mã băm sai lệch, lập tức xóa tệp giả mạo |
| 13 | Missing Download Asset Handling | **PASS** | Bắt lỗi thiếu asset và từ chối an toàn |
| 14 | Installer Launch Flags | **PASS** | Khởi chạy `/SILENT`, `/CLOSEAPPLICATIONS`, `/RESTARTAPPLICATIONS` |
| 15 | App Shutdown Workflow | **PASS** | Quy trình đóng ứng dụng an toàn trước khi chạy setup |
| 16 | Restart App Configuration in ISS | **PASS** | Xác thực cờ tự động mở lại app trong Inno Setup script |
| 17 | User Data Preservation | **PASS** | Thư mục dữ liệu người dùng không bị ảnh hưởng |
| 18 | License Offline Ed25519 Preservation| **PASS** | Trạng thái bản quyền `ACTIVE` được bảo toàn |
| 19 | History Preservation | **PASS** | Toàn bộ 145 bản ghi lịch sử TTS nguyên vẹn |
| 20 | Custom Voice Profiles Preservation | **PASS** | Dữ liệu `custom_voices.json` được bảo toàn |
| 21 | Audio Studio Project Preservation | **PASS** | Dự án âm thanh không bị ghi đè hay xóa |
| 22 | Broadcast Studio 2.0 Project Preservation| **PASS** | Dự án phát thanh nhiều phân đoạn được bảo toàn |
| 23 | Schedule Studio Project Preservation| **PASS** | Dự án lịch phát tự động được bảo toàn |
| 24 | Rollback & Pre-update Backup Snapshot| **PASS** | Snapshot JSON sao lưu thành công trước khi cài |
| 25 | DownloadUpdateWorker Qt Signals | **PASS** | Phát tín hiệu tiến trình Qt chuẩn xác |
| 26 | UpdateDialog State Transitions | **PASS** | Chuyển đổi trạng thái giao diện linh hoạt, không ép buộc |
| 27 | Regression: Schedule Studio | **PASS** | Khởi tạo bảng lịch và quản lý tác vụ hoạt động chuẩn |
| 28 | Regression: Audio Studio | **PASS** | Waveform widget, fade in/out và hiệu ứng hoàn hảo |
| 29 | Regression: Broadcast Studio 2.0 | **PASS** | Phân đoạn phát thanh, nhạc nền auto-ducking nguyên vẹn |
| 30 | Regression: VieNeu-TTS Singleton | **PASS** | TTSService Singleton nạp mô hình ONNX ổn định |
| 31 | Regression: Offline License Verify | **PASS** | Machine ID `TTTS-1261-7F92-41AC-7DA5` xác thực hợp lệ |
| 32 | Inno Setup `uninsneveruninstall` | **PASS** | Bảo vệ tuyệt đối thư mục `{app}\data` khi gỡ/nâng cấp |

---

## VI. TỔNG KẾT HỒI QUY TOÀN BỘ CÁC GIAI ĐOẠN

* **Phase 1 (Hạ tầng cốt lõi):** 14/14 tests **PASS**.
* **Phase 2 (Schedule Studio):** 20/20 tests **PASS**.
* **Phase 3 (Audio Studio):** 28/28 tests **PASS**.
* **Phase 4 (Broadcast Studio 2.0):** 35/35 tests **PASS**.
* **Phase 5 (Auto Update & GitHub Releases):** 32/32 tests **PASS**.
* **Tổng cộng:** **129/129 bài kiểm thử đạt kết quả PASS 100%**.

---

## VII. ĐÁNH GIÁ MỨC ĐỘ SẴN SÀNG PHÁT HÀNH v3.0.1

1. **Hạ tầng Auto Update:** Đã hoàn thiện 100%, sẵn sàng phục vụ phân phối bản mới cho toàn bộ người dùng đang dùng bản v3.0.0.
2. **Quy trình khi người dùng v3.0.0 nhận bản mới:**
   - Ngay sau khi bản phát hành `v3.0.1` được publish lên GitHub kèm bộ cài `T-TTS_Setup_v3.0.1_Offline.exe`:
     - Người dùng v3.0.0 khi mở phần mềm sẽ nhận được hộp thoại thông báo nâng cấp tự động.
     - Người dùng chỉ cần bấm *"Cập nhật ngay"*, ứng dụng sẽ tải về ngầm, kiểm tra checksum SHA-256, sao lưu dữ liệu và tự động cài đè bản mới.
3. **Các nội dung chưa thực hiện trong Phase 5 (Tuân thủ nguyên tắc giới hạn):**
   - Chưa nâng chuỗi phiên bản trong `backend/version.py` (vẫn đang giữ nguyên `3.0.0`).
   - Chưa chạy script đóng gói Inno Setup tạo file `T-TTS_Setup_v3.0.1_Offline.exe`.
   - Chưa tạo Release tag `v3.0.1` trên GitHub.
4. **Trạng thái:** **SẴN SÀNG CHO GIAI ĐOẠN PHÁT HÀNH (PHASE 6: PACKAGING & RELEASE v3.0.1)**.
