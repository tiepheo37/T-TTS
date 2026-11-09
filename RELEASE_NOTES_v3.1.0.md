# T-TTS v3.1.0 — HỆ THỐNG TRỢ LÝ GIỌNG NÓI QUÂN ĐỘI
## BẢN PHÁT HÀNH CHÍNH THỨC (MASTER RELEASE)

**Tác giả:** Nguyễn Văn Tiệp  
**Công nghệ:** VieNeu-TTS v3 Turbo ONNX CPU (100% Offline, không phụ thuộc GPU)  
**Phiên bản:** v3.1.0  
**Target Architecture:** Windows Native Desktop (x64)  
**Kênh:** Stable (Chính thức)  
**Tệp cài đặt:** `T-TTS_v3.1.0_Setup.exe`  

---

## 🌟 TỔNG QUAN BẢN PHÁT HÀNH v3.1.0

Phiên bản **T-TTS v3.1.0** đánh dấu bước đột phá toàn diện về tính năng xử lý tài liệu văn bản, tối ưu hóa âm thanh chuẩn quân sự DSP và cơ chế cập nhật trực tiếp an toàn tuyệt đối, kế thừa trọn vẹn sự ổn định của v3.0.0.

---

## 🚀 CÁC TÍNH NĂNG MỚI NỔI BẬT

### 1. 📂 Phân Hệ Nhập Tài Liệu Thông Minh (Document Import Engine)
- **Hỗ trợ đa định dạng văn bản phổ biến:**
  * **Microsoft Word (.docx):** Trích xuất cấu trúc văn bản, các đề mục và bảo toàn 100% bảng mã tiếng Việt.
  * **Adobe PDF (.pdf):** Trích xuất văn bản đa trang theo thứ tự đọc, tự động lọc bỏ đầu trang / chân trang lặp lại (strip header/footer), phát hiện bản PDF scan thiếu text layer và đưa ra cảnh báo kịp thời.
  * **Văn bản thuần (.txt):** Tự động nhận diện bảng mã (UTF-8, UTF-8 BOM, CP1258, Windows-1252).
- **Trích xuất chạy nền không chặn giao diện (Non-blocking Worker Thread):**
  * Hỗ trợ tệp tài liệu dung lượng lớn hàng trăm trang mà không làm đơ giật UI.
  * Thanh tiến trình thời gian thực với nút Hủy an toàn bất kỳ lúc nào.
- **Hộp thoại Import chuyên nghiệp:**
  * Thống kê chi tiết: số trang, số từ, số ký tự, ước tính thời lượng phát thanh.
  * Xem trước nội dung văn bản trực quan.
  * Tùy chọn linh hoạt: `Thay thế văn bản hiện tại` hoặc `Nối tiếp vào cuối văn bản`.
- **Tích hợp liền mạch trong Text Editor:**
  * Bổ sung nút `📂 Nhập tài liệu` ngay cạnh `📋 Dán từ Clipboard`.

### 2. 📝 Chuẩn Hóa Văn Bản Tiếng Việt & Đọc Số Quân Đội
- **Quy tắc chuyển đổi số tiếng Việt tự nhiên:**
  * Ngày tháng năm: `22/12/1944` ➔ `ngày hai mươi hai tháng mười hai năm một nghìn chín trăm bốn mươi tư`.
  * Giờ giấc: `08:30` ➔ `tám giờ ba mươi phút`.
  * Tỷ lệ phần trăm và số thập phân: `98.5%` ➔ `chín mươi tám phẩy năm phần trăm`.
  * Tiền tệ và số lớn: `1.500.000 VNĐ` ➔ `một triệu năm trăm nghìn đồng`.
- **Mở rộng từ viết tắt quân sự - chính trị:**
  * `QĐNDVN` ➔ `quân đội nhân dân việt nam`, `BTL` ➔ `bộ tư lệnh`, `Đ/c` ➔ `đồng chí`, `BCHQS` ➔ `ban chỉ huy quân sự`...
- **Phân đoạn văn bản thông minh (Smart Chunking):**
  * Tự động chia đoạn theo câu và dấu chấm câu, tuyệt đối không bao giờ ngắt ngang một từ tiếng Việt.

### 3. ✨ Phân Hệ Xử Lý Âm Thanh Chuyên Sâu DSP (Audio Enhancement Engine)
- **Giảm nhiễu thích ứng (Noise Reduction):** Bộ lọc FFT `afftdn` triệt tiêu tạp âm nền phòng thu và tiếng ù dải thấp, kết hợp High-Pass 80Hz và Low-Pass 12kHz.
- **Voice Clarity Equalizer (EQ 5 Dải):**
  * Dải 80 Hz: Cắt lọc rung chấn micro.
  * Dải 250 Hz: Tăng độ dầy, ấm của chất giọng thuyết minh.
  * Dải 600 Hz: Cắt giảm tần số đục, nghẹt.
  * Dải 3.5 kHz: Tăng cường độ rõ chữ, sắc nét cho phụ âm tiếng Việt.
  * Dải 10 kHz: Tăng độ thoáng, trong trẻo không gian phòng thu.
- **Khử âm xì (De-Esser):** Tự động nhận diện và nén dải tần âm gió (`/s/`, `/x/`, `/tr/`), loại bỏ hiện tượng chói gắt tai người nghe.
- **Speech Dynamic Compressor:** Nén dải động cân bằng âm lượng to/nhỏ giữa các từ, giúp giọng phát thanh chắc khỏe, đầm ấm và uy lực.
- **Brickwall Peak Limiter:** Trần âm lượng chống vỡ tiếng (Clipping Prevention), bảo đảm True Peak không vượt quá ngưỡng an toàn.
- **Chuẩn hóa âm lượng chuẩn quốc tế & quân sự (EBU R128 LUFS):** Tự động hiệu chỉnh âm lượng tích hợp về chuẩn phát thanh `-16.0 LUFS` với biên độ `LRA 7.0` và trần `-1.5 dBFS`.
- **Nghe thử A/B đồng bộ tức thì (Synchronized A/B Comparison):** Cho phép so sánh trực tiếp âm thanh gốc và âm thanh sau xử lý tại đúng vị trí con trỏ phát.

### 4. 🧠 Phân Tích Giọng Nói Thông Minh (Intelligent Audio Analyzer)
- Đánh giá chất lượng âm thanh đầu vào: SNR, Noise Floor, Dynamic Range, Clipping, Tần số trung bình.
- Tự động gợi ý Preset âm thanh tối ưu theo kịch bản sử dụng:
  * `Truyền thanh Doanh trại` (Tối ưu cho loa phóng thanh, không gian mở ngoài trời).
  * `Thuyết minh Tài liệu Quân sự` (Tối ưu cho phóng sự, phim tài liệu, giọng trầm ấm).
  * `Bộ đàm Dã chiến` (Tối ưu lọc nhiễu băng thông đàm thoại chỉ huy tác chiến).

### 5. 🎛️ Tích Hợp Toàn Diện Các Studio
- **Synthesize Studio ➔ Audio Studio / Broadcast Studio:** Chuyển nhanh âm thanh vừa tạo sang bàn dựng hoặc phòng tin tức chỉ với 1 click.
- **Batch TTS Document Support:** Đọc và xử lý hàng loạt tài liệu DOCX/PDF/TXT trực tiếp từ giao diện Batch TTS.
- **Schedule Studio Document Integration:** Đặt lịch phát thanh tự động trích xuất nội dung từ tài liệu văn bản.

### 6. 🚀 Tự Động Cập Nhật An Toàn v3.0.0 ➔ v3.1.0
- **Nhảy cóc trực tiếp:** Nâng cấp từ v3.0.0 lên v3.1.0 mà không cần cài đặt trung gian v3.0.1.
- **Bảo toàn 100% dữ liệu:** Giữ nguyên vẹn License Ed25519, Machine ID, History, Từ điển phát âm và toàn bộ các dự án đã tạo.
- **Snapshot sao lưu & Phục hồi:** Tự động tạo bản sao lưu snapshot trước khi cập nhật; hỗ trợ nút `↺ Khôi phục sao lưu` (Rollback) ngay trong ứng dụng.

---

## 🔐 CAM KẾT BẢN QUYỀN VÀ BẢO MẬT

- **100% Offline:** VieNeu-TTS v3 Turbo ONNX CPU hoạt động hoàn toàn ngoại tuyến trên máy tính người dùng. Không gửi bất kỳ dữ liệu âm thanh, văn bản hay thông tin cá nhân nào ra ngoài Internet.
- **Ed25519 Offline License:** Giữ nguyên cơ chế cấp phép chữ ký số công khai Ed25519 với Machine ID phần cứng ổn định.
