# HƯỚNG DẪN HỆ THỐNG BẢN QUYỀN OFFLINE T-TTS v2.0
*Dành riêng cho Nhà phát triển (Developer)*

---

## 1. TỔNG QUAN KIẾN TRÚC

Hệ thống bản quyền offline của T-TTS v2.0 hoạt động theo mô hình **Mật mã bất đối xứng Ed25519** kết hợp **Hardware Fingerprinting** và **Anti-Clock-Rollback nhiều lớp**, bảo đảm tính độc lập hoàn toàn 100% không cần Internet:

```
[Máy Khách Hàng (T-TTS v2.0)]                        [Nhà Phát Triển (Nguyễn Văn Tiệp)]
  │                                                               │
  ├─ 1. Khởi động app -> Sinh Mã Máy (Machine ID)                 │
  │     (VD: TTTS-1261-7F92-41AC-7DA5)                            │
  │                                                               │
  ├─ 2. Gửi Mã Máy cho Dev ──────────────────────────────────────>│
  │                                                               │
  │                                              3. Chạy `Tao_Key_Cho_Khach.bat`
  │                                                 - Nhập Mã Máy khách
  │                                                 - Chọn hạn: 1D, 7D, 30D, 6M, LIFETIME
  │                                                 - Ký số bằng `master_private.pem`
  │                                                 - Xuất key: TTTS-LIC1-xxxx.yyyy
  │                                                               │
  │<──────────────── 4. Gửi key văn bản hoặc tệp .lic ───────────┤
  │                                                               │
  ├─ 5. Dán key vào giao diện T-TTS                               │
  │     - Xác minh chữ ký số bằng Public Key nhúng sẵn            │
  │     - Kiểm tra Mã Máy có trùng khớp không                     │
  │     - Ghi nhận `first_activated_at = now`                     │
  │     - Tính `expires_at = first_activated_at + duration`       │
  │     - Ký HMAC-SHA256 lưu trạng thái vào %LOCALAPPDATA%        │
  │     - Mở khóa toàn bộ chức năng TTS!                          │
```

---

## 2. BẢO MẬT KHÓA RIÊNG (PRIVATE KEY)

1. Khóa riêng nằm tại: `tools/keys/master_private.pem`.
2. Khóa công khai nằm tại: `tools/keys/master_public.pem`.
3. Chuỗi Public Key Raw Base64 được nhúng trực tiếp trong `backend/license.py`:
   ```python
   MASTER_PUBLIC_KEY_B64 = "NK/Fn9eXs78hKfVOGhLPtIW6IOJevBdjY8Et8CIvdtQ="
   ```
4. **Quy tắc bất di bất dịch:**
   - **TUYỆT ĐỐI KHÔNG** sao chép thư mục `tools/` hoặc tệp `master_private.pem` vào bộ phát hành (`dist/`, file cài đặt Inno Setup, bản zip).
   - Tệp `.spec` PyInstaller đã được cấu hình chặt chẽ chỉ đóng gói `web/`, `backend/`, `app_icon.ico` và thư viện phụ thuộc, **hoàn toàn loại trừ `tools/`**.
   - Hãy sao lưu `master_private.pem` ra USB an toàn hoặc kho lưu trữ mật mã cá nhân có mã hóa. Nếu mất khóa này, nhà phát triển sẽ không thể cấp key hợp lệ tiếp theo cho các bản cài đặt hiện hành.

---

## 3. CÁCH CẤP KEY CHO NGƯỜI DÙNG

Nhà phát triển có thể cấp key bằng 3 phương thức linh hoạt:

### Cách A: Sử dụng Ứng Dụng Đồ Họa Nâng Cao (GUI App — Khuyên Dùng Nhất ⭐)
Chỉ cần nhấp đôi vào tệp **`Tao_Key_Cho_Khach.bat`** ở thư mục gốc hoặc chạy trực tiếp **`tools\T-TTS_KeyGenerator.exe`**:
- **Trích xuất thông minh Mã Máy:** Bấm **[📋 Dán & Tự trích xuất]**, ứng dụng tự động bóc tách đúng mã máy `TTTS-XXXX-XXXX-XXXX-XXXX` từ đoạn chat bất kỳ của khách qua Zalo/Facebook mà không sợ dính chữ thừa.
- **Quản lý khách hàng riêng biệt:** Điền tên khách hàng (vd: `Anh Nam - Studio Hà Nội`) và SĐT/Zalo.
- **Chọn thời hạn chuẩn:** **1 Ngày** (24h), **7 Ngày** (168h), hoặc **30 Ngày** (720h) tính từ lần kích hoạt đầu tiên.
- **Tạo key & Tự động sao chép tin nhắn:** Bấm **[🚀 TẠO MÃ BẢN QUYỀN CHO KHÁCH]**. Ứng dụng tự động sao chép mẫu tin nhắn hoàn chỉnh lịch sự (kèm mã key và hướng dẫn kích hoạt 4 bước) vào Clipboard để bạn gửi ngay trên Zalo/Messenger chỉ bằng `Ctrl+V`.
- **Lưu trữ & Tra cứu lịch sử:** Tab **[📜 Lịch Sử Đã Cấp Cho Khách]** tự động lưu toàn bộ khách đã cấp, hỗ trợ tìm kiếm nhanh theo tên/SĐT/mã máy, sao chép lại key hoặc tin nhắn bất kỳ lúc nào mà không cần tạo lại.
- **Soát & Kiểm tra tính hợp lệ:** Tab **[🔍 Kiểm Tra & Soát Key]** cho phép dán bất kỳ key nào để kiểm tra tính toàn vẹn chữ ký số Ed25519 và xem thông tin máy được cấp.

### Cách B: Giao diện dòng lệnh tương tác (Menu CLI)
Chạy lệnh:
```powershell
.\python312\python\python.exe tools\license_generator.py
```
Menu sẽ hiện ra:
```
=================================================================
  🇻🇳 T-TTS v1.0.1 — CÔNG CỤ CẤP BẢN QUYỀN OFFLINE (DEVELOPER)
=================================================================
1. Tạo mới cặp khóa Master Ed25519 (Private & Public Key)
2. Cấp key mới cho người dùng (1 ngày / 7 ngày / 30 ngày)
3. Kiểm tra / Xem thông tin một key đã cấp
4. Thoát
```
- Chọn `2`.
- Dán **Mã Máy** của người dùng.
- Chọn thời hạn:
  - `1` hoặc `1d`: 1 Ngày (KEY-1D - 24 giờ kể từ khi kích hoạt).
  - `2` hoặc `7d`: 7 Ngày (KEY-7D - 168 giờ kể từ khi kích hoạt).
  - `3` hoặc `30d`: 30 Ngày (KEY-30D - 720 giờ kể từ khi kích hoạt).
- Nhập ghi chú khách hàng (ví dụ: `Anh Hùng - Dùng thử 7 ngày`).
- Công cụ sẽ in ra chuỗi key để gửi ngay qua Zalo/Email/Tin nhắn, đồng thời lưu tệp `.lic` trong `tools/exported_licenses/`.

### Cách B: Lệnh nhanh 1 dòng (One-liner CLI)
```powershell
# Cấp key 1 ngày:
python tools/license_generator.py --create --machine "TTTS-XXXX-XXXX-XXXX-XXXX" --duration 1d

# Cấp key 7 ngày:
python tools/license_generator.py --create --machine "TTTS-XXXX-XXXX-XXXX-XXXX" --duration 7d

# Cấp key 30 ngày:
python tools/license_generator.py --create --machine "TTTS-XXXX-XXXX-XXXX-XXXX" --duration 30d
```

### Cách C: Kiểm tra tính hợp lệ của key
```powershell
python tools/license_generator.py --verify "TTTS-LIC1-xxxx.yyyy"
```

---

## 4. QUY TRÌNH KÍCH HOẠT PHÍA NGƯỜI DÙNG

1. Người dùng mở ứng dụng T-TTS.
2. Nếu chưa kích hoạt hoặc hết hạn:
   - Cửa sổ bản quyền tự động bật lên.
   - Hiển thị **Mã máy tính của bạn** kèm nút **[📋 Sao chép mã máy]**.
3. Người dùng gửi Mã máy cho Nhà phát triển.
4. Nhà phát triển gửi lại chuỗi key (dạng `TTTS-LIC1-...`) hoặc gửi tệp `.lic`.
5. Người dùng dán key vào ô nhập hoặc bấm **[📁 Chọn tệp .lic]** rồi bấm **[🔓 Kích hoạt ngay]**.
6. Thời gian dùng thử bắt đầu đếm lùi chính xác theo số giờ thực tế kể từ giây phút này.

---

## 5. CƠ CHẾ CHỐNG LÙI THỜI GIAN (ANTI-CLOCK-ROLLBACK)

Trong môi trường offline hoàn toàn, hệ thống triển khai 4 tầng phòng thủ:

1. **Tầng 1 (Last Valid Time Tracking):**
   - Lưu trữ mốc thời gian hợp lệ lớn nhất đã từng ghi nhận (`last_valid_time`).
   - Mốc này được cập nhật liên tục mỗi khi có yêu cầu gọi API và qua watchdog thread 20 giây một lần.
   - Nếu `now_wall < last_valid_time - 120s`: Lập tức chuyển trạng thái sang `rollback_detected` và khóa ứng dụng vĩnh viễn cho đến khi nhập key mới.

2. **Tầng 2 (OS Monotonic Counter / GetTickCount64):**
   - Bộ đếm `time.monotonic()` của hệ điều hành Windows đo thời gian trôi kể từ khi bật máy, hoàn toàn miễn nhiễm với việc người dùng chỉnh lại ngày giờ trên thanh Taskbar.
   - Nếu monotonic trôi về phía trước nhưng đồng hồ Windows bị lùi về quá khứ -> Phát hiện gian lận ngay trong phiên chạy.

3. **Tầng 3 (Hardware-bound HMAC Integrity):**
   - Toàn bộ tệp trạng thái bản quyền `license_state.json` được ký bằng HMAC-SHA256 với khóa bí mật phái sinh từ `MachineGuid` + cấu trúc phần cứng máy.
   - Người dùng mở file ra sửa `expires_at` hay `last_valid_time` bằng Notepad sẽ làm sai HMAC -> Trạng thái chuyển thành `tampered`, ứng dụng bị khóa.

4. **Tầng 4 (Multi-vault Resilience & History Registry):**
   - Trạng thái được đồng bộ 3 vị trí: `%LOCALAPPDATA%\T-TTS\license_state.json`, `%APPDATA%\T-TTS\.sys_lic_vault.dat`, và Windows Registry (`HKCU\Software\T-TTS\License`).
   - Lịch sử các `license_id` đã từng kích hoạt và hết hạn được ghi nhận. Nếu xóa file kích hoạt và nhập lại key cũ đã hết hạn, hệ thống đối chiếu lịch sử và từ chối kích hoạt lại.

---

## 6. KHÓA CHỨC NĂNG KHI HẾT HẠN HOẶC BỊ KHÓA

Khi bản quyền không hợp lệ (`unactivated`, `expired`, `rollback_detected`, `tampered`, `machine_mismatch`):
- **BỊ KHÓA TẠI BACKEND (Trả về HTTP 403 Forbidden):**
  - `/api/tts/generate` (Tạo giọng nói đơn)
  - `/api/tts/preview` (Nghe thử giọng mẫu)
  - `/stream` (Audio streaming)
  - `/api/tts/batch` (Tạo hàng loạt [P1], [P2]...)
  - `/api/tts/generate-with-subtitles` (Tạo audio kèm phụ đề .SRT)
  - `/api/tts/dubbing` (Lồng tiếng theo phụ đề)
  - `/api/tts/conversation` (Hội thoại / Podcast)
  - `POST /api/voice-clone` (Đăng ký nhân bản giọng mới từ Micro)
- **ĐƯỢC GIỮ LẠI ĐỂ BẢO VỆ DỮ LIỆU NGƯỜI DÙNG:**
  - Lịch sử tạo trước đó (`/api/history`) vẫn xem và tải lại file audio được.
  - Từ điển phát âm (`/api/pron-dict`) vẫn nguyên vẹn.
  - Danh sách giọng đọc (`/voices`).
  - Hộp thoại lưu file và mở thư mục chứa file (`/api/storage/*`).
  - Toàn bộ file WAV/MP3 trong thư mục `output/` không bao giờ bị xóa.

---

## 7. QUY TRÌNH KIỂM THỬ TỰ ĐỘNG

Chạy toàn bộ 18 kịch bản tự động mô phỏng:
```powershell
python test_license_suite.py
```
Chạy kiểm thử chức năng nguyên bản:
```powershell
python test_smoke.py
```

---

## 8. HƯỚNG DẪN ĐÓNG GÓI BẢN PHÁT HÀNH WINDOWS

Khi đã kiểm thử hoàn tất và sẵn sàng phát hành bản đóng gói mới:
1. Đảm bảo thư viện `cryptography` đã có trong môi trường python:
   ```powershell
   python312\python\python.exe -m pip install cryptography
   ```
2. Chạy quy trình build tự động:
   ```powershell
   python build_release.py
   ```
   Kịch bản sẽ tự động:
   - Chạy PyInstaller biên dịch ra `dist/T-TTS_v1.0.1_Exe_Portable`.
   - Sao chép models, data, output, VC++ Runtime DLLs.
   - Biên dịch bộ cài đặt Inno Setup `dist/T-TTS_Setup_v1.0.1_Offline.exe`.
   - Tạo file nén `dist/T-TTS_v1.0.1_Exe_Portable.zip`.
3. Kiểm tra kích thước file và chạy thử nghiệm trên máy sạch không có Python để xác nhận.
