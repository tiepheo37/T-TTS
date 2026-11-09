# 🇻🇳 T-TTS v2.0 — HỆ THỐNG TRỢ LÝ GIỌNG NÓI QUÂN ĐỘI
### PHẦN MỀM CHUYỂN VĂN BẢN THÀNH GIỌNG NÓI TIẾNG VIỆT (NATIVE WINDOWS DESKTOP)

> **TÁC GIẢ:** Nguyễn Văn Tiệp  
> **MÔ HÌNH GIỌNG NÓI:** VieNeu-TTS v3 Turbo (Bản quyền tác giả: Phạm Nguyễn Ngọc Bảo)  
> **CÔNG NGHỆ SUY LUẬN:** ONNX Runtime Lite CPU (100% Offline, không phụ thuộc GPU)  
> **GIAO DIỆN:** Desktop Native Windows (PySide6) — Phong cách K20 Quân đội Nhân dân Việt Nam  

---

## 🌟 ĐẶC ĐIỂM NỔI BẬT PHIÊN BẢN v2.0

1. **Giao Diện Desktop Windows Native Hoàn Toàn (0% Localhost):**
   - Chạy trực tiếp dưới dạng ứng dụng desktop Windows hiện đại bằng **PySide6**.
   - **Loại bỏ hoàn toàn**: Không Flask server, không cổng loopback `8001`, không mở Chrome/Edge/Cốc Cốc, không dùng Chrome App Mode, không WebView2.
   - Không còn tình trạng tự nhảy popup Google Translate của trình duyệt.

2. **Phong Cách Thiết Kế Quân Đội K20 & Modern Dark UI:**
   - Tông màu xanh rằn ri K20 trang nghiêm chuẩn Quân đội Nhân dân Việt Nam.
   - Phù hiệu Quân đội Nhân dân Việt Nam sắc nét, tách nền trong suốt chính thức.
   - Bố cục 8 tab chức năng khoa học: Tạo giọng nói, Nhân bản giọng, Xử lý hàng loạt, Quản lý giọng, Lịch sử, Cài đặt, Giới thiệu & Bản quyền, Hướng dẫn sử dụng.

3. **Công Nghệ Tổng Hợp Giọng Nói Tiếng Việt Chuyên Nghiệp:**
   - 25 giọng đọc chuẩn allowlist chia theo vùng miền (Bắc, Trung, Nam), giới tính và thể loại (Thời sự, Diễn cảm, Kể chuyện).
   - Tích hợp công nghệ nhân bản giọng nói nhanh (Voice Cloning) chỉ từ mẫu 5–15 giây.
   - Hỗ trợ chèn thẻ ngắt nghỉ chuẩn `[pause:0.5s]`, `[pause:1.0s]`.

4. **Hệ Thống Bản Quyền Offline Đa Thời Hạn:**
   - Khóa bản quyền Ed25519 liên kết chặt chẽ với phần cứng máy tính (Machine ID).
   - Hỗ trợ 5 gói bản quyền chính thức: **1 Ngày, 7 Ngày, 30 Ngày, 6 Tháng, Vĩnh Viễn**.
   - Kích hoạt bản quyền dễ dàng, bảo mật cao qua Mã máy (Machine ID) do tác giả cung cấp.

---

## 🚀 HƯỚNG DẪN KHỞI CHẠY BẢN PORTABLE

1. Mở thư mục `release_test/T-TTS_v2.0_Desktop` (hoặc `dist/T-TTS_v2.0_Desktop`).
2. Nhấp đúp vào tệp `T-TTS.exe`.
3. Ứng dụng desktop sẽ mở ra ngay lập tức với đầy đủ tính năng mà không cần kết nối mạng hay cài đặt thêm phần mềm phụ trợ.

---

## 🛠️ CÔNG CỤ CẤP BẢN QUYỀN (DÀNH CHO TÁC GIẢ / QUẢN TRỊ VIÊN)

*(Lưu ý: Công cụ này chỉ nằm ở bộ nguồn phát triển của Tác giả, người dùng khi cài đặt phần mềm sẽ không có file này để đảm bảo bảo mật bản quyền)*

Nhấp đúp vào tệp `Tao_Key_Cho_Khach.bat` ở thư mục gốc:
- Giao diện cấp key đồ họa hiển thị trực quan.
- Dán Mã Máy (Machine ID) của người dùng gửi tới.
- Chọn thời hạn: 1 Ngày, 7 Ngày, 30 Ngày, 6 Tháng hoặc Vĩnh Viễn.
- Chọn thư mục lưu key tùy ý và bấm "XUẤT & LƯU KEY".
