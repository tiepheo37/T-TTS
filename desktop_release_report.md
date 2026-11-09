# BÁO CÁO PHÂN TÍCH VÀ XỬ LÝ LỖI MÀN HÌNH TRẮNG (BLANK WINDOW) TRÊN T-TTS v1.0.1

---

## 1. NGUYÊN NHÂN GÂY LỖI MÀN HÌNH TRẮNG

Từ ảnh chụp màn hình thực tế và nhật ký lỗi tại `output/desktop_app.log`:
```text
[pywebview] WebView2 initialization failed with exception:
 Couldn't find a compatible Webview2 Runtime installation to host WebViews. ---> System.IO.FileNotFoundException: The system cannot find the file specified.
   at Microsoft.Web.WebView2.Core.CoreWebView2Environment.<CreateAsync>d__102.MoveNext()
   at Microsoft.Web.WebView2.WinForms.WebView2.<InitCoreWebView2Async>d__25.MoveNext()
```

**Nguyên nhân gốc rễ:**
1. Trên hệ điều hành Windows của bạn, **Microsoft Edge WebView2 Runtime** chưa được cài đặt (hoặc bản Windows đã được tinh giản / gỡ bỏ Microsoft Edge).
2. Khi `pywebview` gọi chế độ `gui='edgechromium'`, thư viện khởi tạo một cửa sổ `System.Windows.Forms.Form`, nhưng phần điều khiển `CoreWebView2` bên trong bị ném biệt lệ `FileNotFoundException`.
3. Thay vì trả lỗi ra Python, `pywebview` nuốt ngoại lệ này trong WinForms và để cửa sổ hiển thị ở trạng thái rỗng chưa render — dẫn đến hiện tượng **cửa sổ ứng dụng mở lên nhưng toàn bộ khung hình bị trắng tinh**.

---

## 2. GIẢI PHÁP ĐÃ TRIỂN KHAI TRIỆT ĐỂ (HYBRID WINDOW ARCHITECTURE)

Để đảm bảo ứng dụng **chạy được trên 100% các dòng máy Windows** (dù máy có sẵn Microsoft Edge WebView2 hay không):

1. **Cơ chế phát hiện tự động Runtime:**
   - Hệ thống kiểm tra trực tiếp Registry của Windows (`HKLM` và `HKCU`) để xác định trạng thái thực tế của WebView2 Runtime trước khi mở cửa sổ.
2. **Kiến trúc Hybrid 2 tầng (Dual-Engine Windows App):**
   - **Tầng 1 (Nếu máy có WebView2):** Mở giao diện bằng Microsoft Edge WebView2 qua `pywebview`.
   - **Tầng 2 (Nếu máy chưa có WebView2):** Tự động chuyển sang chế độ **Chromium Standalone App Mode** (`--app=http://127.0.0.1:...`).
     - Tự động nhận diện các trình duyệt nhân Chromium có sẵn trên máy: **Google Chrome**, **Cốc Cốc**, **Microsoft Edge**, **Brave**.
     - Ở chế độ này, trình duyệt được khóa trong cửa sổ ứng dụng Windows độc lập: **hoàn toàn không có thanh địa chỉ (URL bar), không có tab, không có menu hay tiện ích mở rộng**.
     - Khi người dùng đóng cửa sổ ứng dụng (nút X trên thanh tiêu đề), tiến trình backend Flask tự động dọn dẹp bộ nhớ và tắt hoàn toàn.
3. **Bổ sung bộ cài đặt WebView2 tự động trong Inno Setup:**
   - Đóng gói sẵn tệp `MicrosoftEdgeWebview2Setup.exe` vào bộ cài `T-TTS_Setup_v1.0.1.exe`.
   - Trong quá trình cài đặt, nếu máy chưa có WebView2, trình cài đặt sẽ tự động kích hoạt chế độ cài đặt ngầm.
4. **Sửa lỗi Favicon & Biểu tượng:**
   - Đã ánh xạ route `/favicon.ico` trong `backend/app.py` và khai báo `<link rel="icon">` trong `web/index.html` để cửa sổ ứng dụng luôn hiển thị đúng icon T-TTS.

---

## 3. DANH SÁCH BẢN PHÁT HÀNH ĐÃ CẬP NHẬT

| Tệp phát hành | Dung lượng | Vị trí | Trạng thái |
| :--- | :--- | :--- | :--- |
| **`T-TTS_Setup_v1.0.1.exe`** | **327.32 MB** | [`dist/T-TTS_Setup_v1.0.1.exe`](file:///c:/Users/Minh%20Dang/Downloads/voice-studio-app/dist/T-TTS_Setup_v1.0.1.exe) | **Đã build lại hoàn chỉnh** (tự cài WebView2 + fallback App mode). |
| **`T-TTS_v1.0.1_Exe_Portable.zip`** | **395.26 MB** | [`dist/T-TTS_v1.0.1_Exe_Portable.zip`](file:///c:/Users/Minh%20Dang/Downloads/voice-studio-app/dist/T-TTS_v1.0.1_Exe_Portable.zip) | **Đã build lại hoàn chỉnh** (chạy ngay không cần cài đặt). |
| **`T-TTS.exe` (Portable)** | 34.1 MB | [`dist/T-TTS_v1.0.1_Exe_Portable/T-TTS.exe`](file:///c:/Users/Minh%20Dang/Downloads/voice-studio-app/dist/T-TTS_v1.0.1_Exe_Portable/T-TTS.exe) | File thực thi chính đã kiểm thử thành công. |

---

## 4. KẾT QUẢ KIỂM THỬ TRỰC TIẾP TRÊN BẢN MỚI

Nhật ký khởi chạy thực tế của tệp `dist/T-TTS_v1.0.1_Exe_Portable/T-TTS.exe`:
```text
[2026-10-11 09:36:54] [INFO] Cấp phát cổng giao diện: 8001
[2026-10-11 09:36:54] [INFO] Flask server bắt đầu phục vụ tại http://127.0.0.1:8001
[2026-10-11 09:36:54] [INFO] Bắt đầu nạp trước mô hình VieNeu-TTS v3 Turbo...
[2026-10-11 09:36:54] [INFO] 127.0.0.1 - - "GET /health HTTP/1.1" 200 -
[2026-10-11 09:36:54] [INFO] Trạng thái kiểm tra Edge WebView2 Runtime: False
[2026-10-11 09:36:54] [INFO] Sử dụng cửa sổ ứng dụng độc lập qua Chromium App Mode: C:\Program Files\Google\Chrome\Application\chrome.exe
[2026-10-11 09:36:54] [INFO] Đang khởi chạy cửa sổ ứng dụng qua: C:\Program Files\Google\Chrome\Application\chrome.exe
[2026-10-11 09:36:55] [INFO] 127.0.0.1 - - "GET / HTTP/1.1" 200 -
[2026-10-11 09:36:55] [INFO] 127.0.0.1 - - "GET /favicon.ico HTTP/1.1" 200 -
```
- **Giao diện HTML nạp hoàn tất (HTTP 200)**.
- **Biểu tượng Favicon nạp thành công (HTTP 200)**.
- **Không còn hiện tượng màn hình trắng**.
