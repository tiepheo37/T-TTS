# HƯỚNG DẪN CÀI ĐẶT T-TTS v3.1.0 (INSTALLATION GUIDE)
## HỆ THỐNG TRỢ LÝ GIỌNG NÓI QUÂN ĐỘI — BẢN NATIVE DESKTOP WINDOWS (x64)

**Tác giả:** Nguyễn Văn Tiệp  
**Phiên bản:** v3.1.0  
**Công nghệ:** VieNeu-TTS v3 Turbo ONNX CPU (100% Offline, không phụ thuộc GPU)  
**Tệp cài đặt:** `T-TTS_v3.1.0_Setup.exe` (hoặc `T-TTS_Setup_v3.1.0_Offline.exe`)  
**Môi trường hỗ trợ:** Windows 10 / Windows 11 (64-bit)

---

## 1. YÊU CẦU HỆ THỐNG TỐI THIỂU

- **Hệ điều hành:** Windows 10 64-bit (Build 1809 trở lên) hoặc Windows 11.
- **Bộ vi xử lý (CPU):** Intel Core i3 thế hệ 6 trở lên hoặc AMD Ryzen 3 trở lên (hỗ trợ tập lệnh AVX2).
- **Bộ nhớ RAM:** Tối thiểu 4 GB (khuyến nghị 8 GB trở lên để xử lý tài liệu dài mượt mà).
- **Dung lượng ổ cứng:** Trống tối thiểu 1.5 GB trên ổ cài đặt (khuyến nghị SSD).
- **Card đồ họa (GPU):** Không bắt buộc (phần mềm chạy thuần CPU thông qua ONNX Runtime Lite).
- **Kết nối mạng:** Không yêu cầu (hoạt động độc lập 100% Offline).
- **Phụ thuộc:** Không cần cài đặt Python, không cần cài đặt Node.js hay phần mềm bên thứ 3. Đã tích hợp sẵn FFmpeg v7.1 và Visual C++ Runtime.

---

## 2. QUY TRÌNH CÀI ĐẶT MỚI (CLEAN INSTALL)

### Bước 1: Tải bộ cài đặt và đối soát mã băm SHA-256
1. Tải tệp `T-TTS_v3.1.0_Setup.exe` từ kênh phát hành chính thức của tác giả Nguyễn Văn Tiệp.
2. Kiểm tra mã băm SHA-256 bằng PowerShell để đảm bảo tệp nguyên vẹn, không bị hỏng hoặc giả mạo:
   ```powershell
   Get-FileHash -Algorithm SHA256 "T-TTS_v3.1.0_Setup.exe"
   ```
3. Đối chiếu kết quả với tệp `SHA256SUMS.txt`.

### Bước 2: Chạy trình cài đặt
1. Nhấp đúp vào tệp `T-TTS_v3.1.0_Setup.exe`.
2. Hộp thoại chào mừng xuất hiện với thông tin tác giả và tóm tắt tính năng mới.
3. Chọn thư mục cài đặt (mặc định: `%LOCALAPPDATA%\Programs\T-TTS` hoặc `C:\Program Files\T-TTS`).
4. Tích chọn `Tạo biểu tượng trên màn hình nền (Desktop Icon)`.
5. Bấm `Cài đặt (Install)`. Quá trình giải nén và thiết lập mất khoảng 30–60 giây.
6. Bấm `Hoàn tất (Finish)` để khởi chạy T-TTS v3.1.0 ngay.

---

## 3. KHỞI CHẠY LẦN ĐẦU VÀ KÍCH HOẠT BẢN QUYỀN OFFLINE

1. Khi mở ứng dụng lần đầu, giao diện Quân đội K20 xuất hiện.
2. Nếu máy chưa kích hoạt, ứng dụng sẽ thông báo trạng thái `Chưa kích hoạt`.
3. Vào menu **Bản quyền & Giấy phép**:
   - Sao chép **Mã Máy (Machine ID)** hiển thị trên màn hình.
   - Gửi Mã Máy cho tác giả **Nguyễn Văn Tiệp** để nhận chuỗi License Key kích hoạt (hoặc tệp `.lic`).
   - Dán chuỗi key vào ô nhập và bấm **Kích Hoạt Bản Quyền**.
4. Bản quyền offline Ed25519 sẽ được kích hoạt vĩnh viễn hoặc theo gói cấp phép mà không cần bất kỳ kết nối Internet nào.

---

## 4. BẢN PORTABLE (KHÔNG CẦN CÀI ĐẶT)

Nếu không có quyền cài đặt phần mềm trên máy tính đơn vị:
1. Tải gói nén `T-TTS_v3.1.0_Desktop_Portable.zip`.
2. Giải nén vào bất kỳ thư mục nào (ví dụ: `D:\T-TTS_v3.1.0`).
3. Nhấp đúp vào `T-TTS.exe` để sử dụng ngay lập tức.
4. Mọi dữ liệu cấu hình và âm thanh tạo ra sẽ lưu cục bộ ngay trong thư mục `data/` và `output/` của phần mềm.

---

## 5. HỖ TRỢ KỸ THUẬT

- **Tác giả:** Nguyễn Văn Tiệp
- **Hỗ trợ bản quyền & Kỹ thuật:** Liên hệ trực tiếp tác giả
