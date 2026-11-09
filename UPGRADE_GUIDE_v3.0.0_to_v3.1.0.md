# HƯỚNG DẪN NÂNG CẤP TRỰC TIẾP T-TTS v3.0.0 ➔ v3.1.0
## BỎ QUA HOÀN TOÀN v3.0.1 — BẢO TOÀN 100% BẢN QUYỀN VÀ DỮ LIỆU

**Tác giả:** Nguyễn Văn Tiệp  
**Phiên bản đích:** v3.1.0  
**Phiên bản nguồn:** v3.0.0 (hoặc v3.0)  
**Nhảy cóc trung gian:** Không cần cài đặt v3.0.1  

---

## 1. NGUYÊN TẮC AN TOÀN NÂNG CẤP

Hệ thống nâng cấp T-TTS v3.1.0 tuân thủ các cam kết an toàn tuyệt đối:
1. **Bảo toàn Bản quyền Ed25519:** Khóa kích hoạt, Machine ID và trạng thái bản quyền của bạn được bảo vệ nguyên vẹn 100%. Bạn **không** cần phải xin lại key hoặc kích hoạt lại sau khi cập nhật.
2. **Bảo toàn Dữ liệu Người Dùng:**
   - Toàn bộ lịch sử phát thanh (`history.json`).
   - Toàn bộ từ điển phát âm viết tắt quân sự (`pronunciation-dict.json`).
   - Danh sách giọng đọc tùy biến (`custom_voices.json`).
   - Các dự án Studio: Thu âm (`projects/audio/`), Bản tin (`projects/broadcast/`), Lịch phát sóng (`projects/schedules/`).
3. **Sao lưu Tự Động (Pre-Update Backup):** Một bản sao lưu snapshot đầy đủ kèm mã băm SHA-256 sẽ được tạo tự động tại `%LOCALAPPDATA%\T-TTS\data\backups\` trước khi bắt đầu nâng cấp.
4. **Không phụ thuộc v3.0.1:** Cơ chế nâng cấp được lập trình để nhảy cóc trực tiếp `3.0.0 ➔ 3.1.0` theo quan hệ số học `(3, 1, 0) > (3, 0, 0)`.

---

## 2. PHƯƠNG PHÁP 1: NÂNG CẤP TỰ ĐỘNG QUA ỨNG DỤNG (KHUYẾN NGHỊ)

Nếu máy tính của bạn có kết nối mạng Internet khi kiểm tra cập nhật:

1. Mở phần mềm **T-TTS v3.0.0** đang sử dụng.
2. Ứng dụng sẽ tự động phát hiện bản nâng cấp mới hoặc bạn có thể vào menu **Cài đặt ➔ Kiểm tra cập nhật**.
3. Hộp thoại **Cập Nhật Phần Mềm T-TTS (Dark Military K20)** xuất hiện:
   - Huy hiệu hiển thị rõ: `★ NÂNG CẤP TRỰC TIẾP v3.0.0 → v3.1.0 (BẢO TOÀN 100% DỮ LIỆU & BẢN QUYỀN) ★`.
   - Đọc danh mục các cải tiến mới trong bản v3.1.0 (Document Reader, Audio DSP EQ/Compressor/LUFS, AI Analyzer).
4. Bấm **🚀 Cập nhật ngay**:
   - Ứng dụng tự động kiểm tra điều kiện hệ thống (Dung lượng đĩa trống $\ge 500$ MB, quyền ghi).
   - Tự động tạo bản sao lưu dữ liệu toàn diện.
   - Tải tệp cập nhật và đối soát mã băm SHA-256 thời gian thực.
5. Khi tải xong, ứng dụng sẽ khởi động trình cài đặt Inno Setup với các cờ `/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS`.
6. Sau khoảng 30 giây, T-TTS v3.1.0 sẽ tự động khởi động lại với toàn bộ dữ liệu và license của bạn được giữ nguyên vẹn.

---

## 3. PHƯƠNG PHÁP 2: CÀI ĐÈ THỦ CÔNG BẰNG BỘ CÀI ĐẶT

Nếu máy tính của bạn hoạt động trong mạng nội bộ quân sự không có Internet:

1. Tải bộ cài `T-TTS_v3.1.0_Setup.exe` từ thiết bị ngoài.
2. Kiểm tra mã SHA-256 bằng PowerShell:
   ```powershell
   Get-FileHash -Algorithm SHA256 "T-TTS_v3.1.0_Setup.exe"
   ```
3. Đóng phần mềm T-TTS v3.0.0 đang chạy.
4. Chạy `T-TTS_v3.1.0_Setup.exe`.
5. Chọn đúng thư mục cài đặt của phiên bản v3.0.0 trước đó (mặc định trình cài đặt sẽ tự động nhận diện).
6. Bấm `Cài đặt`. Trình cài đặt Inno Setup đã được thiết lập cờ `onlyifdoesntexist` cho thư mục `data/`, đảm bảo **không bao giờ ghi đè** dữ liệu hoặc license cũ của bạn.
7. Khởi động lại T-TTS: Phiên bản v3.1.0 sẽ tự động thực hiện quy trình di chuyển dữ liệu nhẹ (`perform_data_migration`), tạo các thư mục mới của v3.1.0 (`projects/documents/`, `presets/`) mà không làm thay đổi các file cũ.

---

## 4. HƯỚNG DẪN KHÔI PHỤC (ROLLBACK) KHI CẦN THIẾT

Nếu vì bất kỳ lý do gì bạn muốn khôi phục lại dữ liệu trước thời điểm nâng cấp:

### Khôi phục Dữ liệu (Data Rollback):
1. Mở T-TTS ➔ Hộp thoại Cập nhật.
2. Bấm nút **`↺ Khôi phục sao lưu` (Rollback)**.
3. Chọn bản sao lưu gần nhất trước khi nâng cấp (có hiển thị thời gian và phiên bản v3.0.0).
4. Bấm `Xác nhận`: Toàn bộ cấu hình, license và các dự án sẽ được đưa về chính xác trạng thái trước khi nâng cấp.

### Hạ Phiên Bản Ứng Dụng (Binary Rollback):
- Nếu muốn quay lại chạy file nhị phân v3.0.0 cũ, bạn chỉ cần chạy lại bộ cài `T-TTS_Setup_v3.0.0_Offline.exe` hoặc mở lại thư mục bản Portable v3.0.0. Dữ liệu của bạn luôn được bảo vệ an toàn.
