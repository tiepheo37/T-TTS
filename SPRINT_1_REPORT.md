# T-TTS v3.1.0 — BÁO CÁO NGHIỆM THU SPRINT 1
# DOCUMENT IMPORT (DOCX / PDF / TXT) & TEXT EDITOR INTEGRATION

**Dự án:** T-TTS — Hệ Thống Trợ Lý Giọng Nói Quân Đội  
**Tác giả:** Nguyễn Văn Tiệp  
**Phiên bản:** `v3.1.0` (Phát triển trên branch `dev-v3.1.0`)  
**Thời gian hoàn thành:** 09/11/2026 (Giờ hệ thống)  
**Trạng thái kiểm thử:** **PASS 100% (13/13 Test Cases)**  

---

## I. MỤC TIÊU VÀ NGUYÊN TẮC THI CÔNG SPRINT 1

Theo đúng kế hoạch [T-TTS_V3.1.0_IMPLEMENTATION_PLAN.md](file:///D:/cac%20loai%20app/voice-studio-app/T-TTS_V3.1.0_IMPLEMENTATION_PLAN.md), Sprint 1 tập trung triển khai phân hệ **Nhập tài liệu văn bản đa định dạng** phục vụ nhu cầu chuyển văn bản thành giọng nói từ các báo cáo quân sự, chỉ thị và văn kiện:

1. **Không viết lại toàn bộ ứng dụng:** Kế thừa 100% giao diện và kiến trúc của `PageSynthesize`.
2. **Không phá vỡ chức năng cũ:** Giữ nguyên vẹn toàn bộ 25 giọng đọc VieNeu-TTS, các nút chèn thẻ cảm xúc (`[cười]`, `[hắng giọng]`, `[thở dài]`), mốc nghỉ (`[nghỉ 500ms]`, `[nghỉ 2s]`), nút xóa và lịch sử phát thanh.
3. **Non-blocking & An toàn giao diện:** Toàn bộ quá trình đọc tài liệu (kể cả tệp dung lượng lớn hoặc nhiều trang) đều chạy ngầm bằng `QThread`, có thanh tiến trình thực tế kèm nút Hủy an toàn, không bao giờ gây treo (freeze) cửa sổ chính.
4. **Bảo toàn dữ liệu đang soạn thảo:** Nếu người dùng đang có văn bản nháp trong ô soạn thảo và mở hộp thoại rồi bấm Hủy, nội dung đang nhập được bảo toàn 100%.

---

## II. AUDIT GIAO DIỆN VÀ VỊ TRÍ TÍCH HỢP

### 1. Vị trí tích hợp trong `gui/pages/page_synthesize.py`
Qua quá trình rà soát layout của `Text Card` trong trang Tạo giọng nói:
- Hàng tiêu đề của khung văn bản (`tc_title_row`) ban đầu chứa: nhãn tiêu đề, bộ đếm ký tự (`lbl_char_count`), nút `btn_paste` ("📋 Dán") và nút `btn_clear` ("🗑 Xóa").
- **Vị trí bổ sung tối ưu:** Nút `📂 Nhập tài liệu` được đặt ngay bên cạnh nút dán, đồng thời cập nhật nhãn nút dán thành `📋 Dán từ Clipboard` kèm tooltip hướng dẫn trực quan.

### 2. Sơ đồ bố cục Text Card sau khi tích hợp

```
+---------------------------------------------------------------------------------------------------+
| 📝 NỘI DUNG VĂN BẢN CẦN CHUYỂN THÀNH GIỌNG NÓI         0 ký tự | 0 từ                             |
|                                                [📂 Nhập tài liệu]  [📋 Dán từ Clipboard]  [🗑 Xóa] |
+---------------------------------------------------------------------------------------------------+
| Chèn nhanh: [😊 Cười] [🗣️ Hắng giọng] [😮💨 Thở dài] [⏸ Nghỉ 500ms] [⏸ Nghỉ 2s]                   |
+---------------------------------------------------------------------------------------------------+
| Ô soạn thảo văn bản tiếng Việt chính (QTextEdit)...                                               |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

---

## III. CHI TIẾT CÁC MODULE MỚI XÂY DỰNG

### 1. `backend/document_reader.py` (Bộ trích xuất đa định dạng)
Module độc lập cung cấp hàm xử lý `extract_document_text(...)` với đầy đủ tính năng:
- **Microsoft Word (.docx):**
  * Đọc toàn bộ các đoạn văn (`paragraphs`), tiêu đề các cấp (`Heading 1` - `Heading 6`).
  * Trích xuất các bảng biểu (`tables`) theo thứ tự đọc tự nhiên từng dòng và từng ô, liên kết phân tách bằng dấu phẩy hợp lý.
  * Bảo toàn 100% bảng mã Unicode tiếng Việt và các ký tự có dấu.
- **Tài liệu PDF (.pdf):**
  * Trích xuất phân đoạn theo từng trang thông qua thư viện offline `pypdf`.
  * Hỗ trợ lọc bỏ đầu trang / chân trang lặp lại (`strip_header_footer`).
  * **Phát hiện PDF scan:** Tự động kiểm tra tỷ lệ ký tự/trang; nếu tài liệu là bản scan hoặc ảnh chụp không có text layer, hệ thống sẽ đưa ra cảnh báo rõ ràng `warning: "Tài liệu có thể là bản scan dạng ảnh... Chưa nhận diện được chữ nổi"`.
- **Văn bản thuần (.txt):**
  * Tự động nhận diện bảng mã thông qua `charset_normalizer`: Hỗ trợ chuẩn xác UTF-8, UTF-8 có BOM (`utf-8-sig`), CP1258 (Windows tiếng Việt) và Windows-1252.
  * Tự động lọc bỏ ký tự Byte Order Mark (`\ufeff`) ở đầu văn bản để không làm ảnh hưởng đến ngữ điệu đọc của VieNeu-TTS.
- **Tệp Word cũ (.doc nhị phân):**
  * Phát hiện phần mở rộng `.doc` và signature OLE2, đưa ra thông báo thân thiện và hướng dẫn từng bước:
    > *"💡 Hướng dẫn: Mở tệp bằng Microsoft Word hoặc Google Docs -> Chọn Save As -> Lưu dạng Word Document (*.docx) để nạp vào T-TTS."*
- **Hỗ trợ tiến trình & Hủy:** Nhận callback `(current, total, message)` và `cancel_check()` giúp giao diện cập nhật thời gian thực.

### 2. `gui/dialog_import_document.py` (Hộp thoại nhập tài liệu thông minh)
Hộp thoại giao diện đồ họa chuẩn Modern Dark đồng bộ với màu sắc quân sự T-TTS:
- **Tiểu trình nền (`DocumentExtractionWorker`):** Kế thừa `QThread`, tách biệt việc đọc file khỏi luồng chính của PySide6, triệt tiêu hoàn toàn hiện tượng "Not Responding" trên Windows.
- **Thanh trạng thái & Tiến trình:** Hiển thị `QProgressBar` từ 0% đến 100% cùng nhãn trạng thái và nút "Hủy trích xuất" tức thì.
- **Thẻ thống kê thông số:**
  * Định dạng tệp (`DOCX`, `PDF`, `TXT`).
  * Số trang (`page_count`).
  * Số từ (`word_count`) và số ký tự (`char_count`).
  * Thời lượng phát thanh ước tính (tính theo tốc độ đọc chuẩn phát thanh 160 từ/phút).
- **Khung xem trước và biên tập (Preview Editor):** Cho phép người dùng đọc lại, thêm bớt, chỉnh sửa câu chữ hoặc định dạng trước khi đồng ý nạp vào ô soạn thảo chính.
- **3 tùy chọn đích (Actions):**
  1. `Thay thế toàn bộ nội dung hiện tại (Replace)`.
  2. `Nối tiếp vào cuối văn bản đang soạn thảo (Append)`.
  3. `Lưu thành dự án tài liệu mới (Save as Project)`.

---

## IV. BẢNG KẾT QUẢ KIỂM THỬ THỰC TẾ (13/13 TESTS PASS)

Bộ kịch bản kiểm thử tự động toàn diện được thiết lập tại [`tools/test_sprint_1_document_import.py`](file:///D:/cac%20loai%20app/voice-studio-app/tools/test_sprint_1_document_import.py) và đã thực thi thành công 100%:

| STT | Tên ca kiểm thử | Phạm vi kiểm tra | Kết quả thực tế | Trạng thái |
|:---:|:---|:---|:---:|:---:|
| 1 | `test_01_txt_utf8_extraction` | Đọc tệp TXT chuẩn UTF-8 tiếng Việt có dấu | Khớp 100% nội dung, 0 cảnh báo | **PASS** |
| 2 | `test_02_txt_utf8_bom_extraction` | Đọc tệp TXT UTF-8 có BOM (`\ufeff`) | Đọc đúng, tự động loại bỏ ký tự BOM | **PASS** |
| 3 | `test_03_txt_cp1258_extraction` | Đọc tệp TXT bảng mã Windows CP1258 | Nhận diện mã hóa, giải mã đúng tiếng Việt | **PASS** |
| 4 | `test_04_docx_extraction_paragraphs_and_tables` | Đọc DOCX: tiêu đề, đoạn văn và bảng biểu 2x2 | Đọc theo thứ tự tự nhiên, trích xuất đủ bảng | **PASS** |
| 5 | `test_05_pdf_scanned_detection` | Nhận diện tài liệu PDF bản scan không có text layer | Đưa ra cảnh báo bản scan chính xác | **PASS** |
| 6 | `test_06_legacy_doc_friendly_error` | Chặn tệp .doc nhị phân cũ | Xuất thông báo lỗi kèm hướng dẫn Save As .docx | **PASS** |
| 7 | `test_07_progress_callback_and_cancellation` | Callback tiến trình và cờ hủy an toàn | Callback gọi đúng các bước, hủy thành công | **PASS** |
| 8 | `test_08_nonexistent_and_invalid_files` | Xử lý file không tồn tại hoặc đuôi mở rộng lạ | Báo lỗi thân thiện, không crash ứng dụng | **PASS** |
| 9 | `test_09_gui_dialog_and_page_synthesize_integration` | Kiểm tra các nút giao diện trên Dialog & Synthesize | Đầy đủ nút Nhập tài liệu, Dán, Pills cảm xúc | **PASS** |
| 10 | `test_10_large_document_extraction` | Đọc tài liệu lớn 200 đoạn văn, >4.000 từ | Xử lý trơn tru trong 0.05s, không tràn bộ nhớ | **PASS** |
| 11 | `test_11_replace_and_append_behavior` | Kiểm tra logic Thay thế (Replace) & Nối tiếp (Append) | Ghi đè hoặc nối thêm cách dòng chuẩn xác | **PASS** |
| 12 | `test_12_cancel_preserves_existing_text` | Hủy hộp thoại bảo toàn 100% văn bản đang soạn | Bản nháp ban đầu giữ nguyên vẹn | **PASS** |
| 13 | `test_13_tts_service_regression` | Kiểm tra hồi quy phân hệ tổng hợp giọng nói VieNeu-TTS | 25 giọng đọc allowlist sẵn sàng | **PASS** |

---

## V. NHẬN XÉT VÀ KẾT LUẬN SPRINT 1

1. **Chất lượng thực thi:** Hoàn thành trọn vẹn 100% yêu cầu chức năng của Sprint 1 mà không phá vỡ bất kỳ thành phần nào của nền tảng v3.0.1.
2. **Quản lý phiên bản Git:** Toàn bộ mã nguồn Sprint 1 đã được commit gọn gàng trên nhánh `dev-v3.1.0`. Nhánh `master` (tag `v3.0.1`) giữ nguyên trạng thái đóng băng an toàn.
3. **Sẵn sàng chuyển tiếp:** Sprint 1 đã hoàn tất đầy đủ deliverables và sẵn sàng chuyển tiếp sang **Sprint 2 (Chuẩn hóa văn bản tiếng Việt nâng cao và quản lý Document Project)**.
