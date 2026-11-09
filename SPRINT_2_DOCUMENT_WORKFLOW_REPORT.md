# BÁO CÁO NGHIỆM THU SPRINT 2 — T-TTS v3.1.0
## TEXT PROCESSING & DOCUMENT PROJECT WORKFLOW

**Dự án**: T-TTS – Trợ lý Giọng nói Quân đội  
**Phiên bản phát triển**: v3.1.0  
**Git Branch**: `dev-v3.1.0`  
**Tác giả**: Nguyễn Văn Tiệp  
**Trạng thái**: **HOÀN THÀNH TOÀN DIỆN (16/16 TESTS PASS - 100%)**

---

## I. TỔNG QUAN SPRINT 2

Sprint 2 tập trung xây dựng năng lực biên tập và tiền xử lý văn bản thông minh trước khi đưa vào mô hình sinh giọng nói VieNeu-TTS v3 Turbo, đồng thời hoàn thiện hệ thống quản lý dự án tài liệu (**DocumentProject**) cho phép lưu trữ trạng thái biên tập dài hạn, cấu hình giọng đọc và danh mục phân đoạn âm thanh.

```
+---------------------------------------------------------------------------------------------------------+
|                                    T-TTS v3.1.0 TEXT & PROJECT WORKFLOW                                |
+---------------------------------------------------------------------------------------------------------+
|                                                                                                         |
|   +-----------------------+     +-------------------------------+     +-----------------------------+   |
|   |   Document Import     | --> |   Text Normalization (NFC)    | --> |  Military Token Protection  |   |
|   |  (DOCX, PDF, TXT)     |     |   Whitespace, Punctuation     |     |  (AK-47, K-54, Su-30, B-52) |   |
|   +-----------------------+     +-------------------------------+     +-----------------------------+   |
|                                                                                      |                  |
|                                                                                      v                  |
|   +-----------------------+     +-------------------------------+     +-----------------------------+   |
|   |  Synthesis Segments   | <-- |   Smart Chunking (Sentences)  | <-- |   Vietnamese Number Engine  |   |
|   |   & Preview Player    |     |   Word boundary protection    |     |   Cardinals, Decimals, Docs |   |
|   +-----------------------+     +-------------------------------+     +-----------------------------+   |
|              ^                                                                       ^                  |
|              |                                                                       |                  |
|              +------------------------------+----------------------------------------+                  |
|                                             |                                                           |
|                               +-----------------------------+                                           |
|                               |   DocumentProject Manager   |                                           |
|                               |  Create, Save, Open, Clone  |                                           |
|                               |  Corrupted File Quarantine  |                                           |
|                               +-----------------------------+                                           |
+---------------------------------------------------------------------------------------------------------+
```

---

## II. BỘ XỬ LÝ VĂN BẢN TIẾNG VIỆT (`backend/text_processor.py`)

Module `backend/text_processor.py` triển khai lớp `VietnameseTextProcessor` và `TextProcessingConfig` với 12 quy tắc xử lý có thể cấu hình linh hoạt:

### 1. Chuẩn hóa văn bản & Unicode NFC
- **Unicode NFC**: Tự động đưa mọi ký tự có dấu rời (NFD) về dạng chuẩn hóa đồng nhất NFC.
- **Khoảng trắng & Dấu câu**: Thu gọn chuỗi khoảng trắng thừa, căn chỉnh chuẩn dấu chấm, phẩy, hai chấm, chấm phẩy (không có khoảng trắng trước dấu, đúng 1 khoảng trắng sau dấu).
- **Ký tự lạ**: Quét và báo cáo ký tự điều khiển hoặc ký tự ngoài bảng mã tiếng Việt/ASCII thông dụng.

### 2. Bộ chuyển đổi đọc số tiếng Việt (Vietnamese Number Reading)
Quy chuẩn phát âm tiếng Việt chuẩn quân đội và truyền thông:
- **Số nguyên (Cardinals)**: Đọc chính xác đến hàng nghìn tỷ (`1234567890` $\rightarrow$ *"một tỷ hai trăm ba mươi tư triệu năm trăm sáu mươi bảy nghìn tám trăm chín mươi"*).
- **Quy tắc hàng đơn vị đặc thù**:
  - Hàng chục > 1 kết thúc bằng 1: đọc là *"mốt"* (vd: `21` $\rightarrow$ *"hai mươi mốt"*).
  - Hàng chục $\ge$ 1 kết thúc bằng 5: đọc là *"lăm"* hoặc *"nhăm"* (vd: `15` $\rightarrow$ *"mười lăm"*, `25` $\rightarrow$ *"hai mươi lăm"*).
  - Hàng chục $\ge$ 2 kết thúc bằng 4: đọc là *"tư"* (vd: `24` $\rightarrow$ *"hai mươi tư"*, `1944` $\rightarrow$ *"nghìn chín trăm bốn mươi tư"*).
- **Số thập phân (Decimals)**: Hỗ trợ cả dấu phẩy và chấm (`3,5 kg` $\rightarrow$ *"ba phẩy năm kg"*, `0.75` $\rightarrow$ *"không phẩy bảy mươi lăm"*).
- **Số âm**: `-5` $\rightarrow$ *"âm năm"*, `-12 độ` $\rightarrow$ *"âm mười hai độ"*.
- **Phần trăm**: `100%` $\rightarrow$ *"một trăm phần trăm"*, `5,5%` $\rightarrow$ *"năm phẩy năm phần trăm"*.
- **Tiền tệ**: `500.000 VNĐ` $\rightarrow$ *"năm trăm nghìn đồng"*, `$100` $\rightarrow$ *"một trăm đô la"*.
- **Số thứ tự**: `thứ 1` $\rightarrow$ *"thứ nhất"*, `thứ 4` $\rightarrow$ *"thứ tư"*, `thứ 10` $\rightarrow$ *"thứ mười"*.
- **Số điện thoại**: Tách và đọc từng chữ số rõ ràng (`0912.345.678` $\rightarrow$ *"không chín một hai ba bốn năm sáu bảy tám"*).
- **Số hiệu văn bản**: Nhận diện định dạng công văn quân đội (`Số 123/QĐ-BQP` $\rightarrow$ *"Số một trăm hai mươi ba trên Quyết định Bộ Quốc phòng"*).
- **Ký hiệu đơn vị quân sự**: Chuyển đổi chính xác các ký hiệu quy ước:
  - `f324` $\rightarrow$ *"Sư đoàn 324"*
  - `e1` $\rightarrow$ *"Trung đoàn 1"*
  - `d4` $\rightarrow$ *"Tiểu đoàn 4"*
  - `c1` $\rightarrow$ *"Đại đội 1"*

### 3. Cơ chế bảo vệ mã hiệu vũ khí & thiết bị (Ambiguous Number Protection)
Tránh đọc nhầm các mã hiệu quân sự có dấu gạch ngang thành phép trừ hay số âm:
- Nhận dạng và bảo vệ qua token masking: `AK-47`, `AK-74`, `K-54`, `K-59`, `B-52`, `Su-30`, `Su-27`, `MiG-21`, `F-35`, `T-90`, `T-72`, `BMP-1`, `RPG-7`, `C-130`, `M-16`, `M-4`, `UH-1`, `AN-26`, `Mi-8`, `Mi-17`...
- Sau khi engine đọc số hoàn tất, các token mã hiệu được phục hồi nguyên trạng chính xác 100%.

### 4. Smart Chunking & Thống kê văn bản
- **Phân đoạn thông minh**: Cắt câu tại các ranh giới tự nhiên (`.`, `!`, `?`, `\n`) mà không bẻ gãy từ hoặc số, đảm bảo chiều dài mỗi chunk không vượt quá giới hạn mô hình (`max_chars=350`).
- **Thống kê chuyên sâu**: Đo lường số ký tự, số từ, số dòng/đoạn, ước tính thời lượng phát sóng dựa trên tốc độ đọc (`speed`), và số lượng segment âm thanh sẽ tạo ra.

### 5. Engine Tìm kiếm & Thay thế (Find & Replace)
- Tìm kiếm chính xác hoặc không phân biệt hoa thường (`case_sensitive`).
- Hỗ trợ biểu thức chính quy (`regex`).
- Xem trước số lượng vị trí khớp (`count`), thay thế từng vị trí hoặc thay thế hàng loạt (`replace_all`).

---

## III. NÂNG CẤP DOCUMENT PROJECT (`backend/project_manager.py`)

Hệ sinh thái dự án của T-TTS đã được bổ sung nhóm dự án `documents` độc lập với `audio`, `broadcast`, và `schedules`:

1. **Vòng đời dự án tài liệu đầy đủ**:
   - `create_document_project(name, text, ...)`: Khởi tạo schema chuẩn gồm id, name, text, voice, speed, chunk_settings, audio_history, timestamps.
   - `save_document_project(data)`: Ghi file JSON với mã hóa UTF-8 an toàn.
   - `save_as_document_project(source_id, new_name)`: Lưu thành dự án mới giữ nguyên toàn bộ dữ liệu nội dung.
   - `load_document_project(project_id)`: Nạp dữ liệu dự án.
   - `rename_document_project(project_id, new_name)`: Đổi tên dự án.
   - `duplicate_document_project(project_id, new_name)`: Nhân bản dự án độc lập.
   - `delete_document_project(project_id, delete_audio=False)`: Xóa dự án an toàn, có tùy chọn bảo lưu file âm thanh đã sinh.
   - `get_recent_document_projects(limit=10)`: Liệt kê danh sách dự án mở gần đây nhất.
2. **Cơ chế phục hồi tệp hỏng (Corrupted File Recovery & Quarantine)**:
   - Khi phát hiện tệp JSON bị hỏng cú pháp (do mất điện đột ngột hoặc lỗi đĩa), hệ thống tự động cách ly tệp thành `*.corrupted_<timestamp>`, ghi log cảnh báo và trả về `None` mà **tuyệt đối không làm crash ứng dụng**.

---

## IV. TÍCH HỢP GIAO DIỆN NGƯỜI DÙNG (UI INTEGRATION)

### 1. Bổ sung các hộp thoại chuyên dụng
- `gui/dialog_text_processor.py`: Cung cấp giao diện trực quan với 12 checkbox tùy chọn chuẩn hóa, bảng thống kê thời gian thực (Ký tự, Từ, Đoạn, Phân đoạn, Ước tính thời lượng) và 2 tab so sánh "So sánh Trước / Sau" hoặc "Văn bản sau xử lý".
- `gui/dialog_find_replace.py`: Hộp thoại Tìm & Thay thế hiện đại, hỗ trợ đếm số kết quả tức thì, điều hướng highlight con trỏ trên `QTextEdit`, tùy chọn phân biệt chữ hoa/thường và Regular Expression.
- `gui/dialog_document_project.py`: Quản lý danh sách dự án tài liệu dạng bảng lưới trực quan, nút Mở, Nhân bản, Đổi tên, và Xóa với hộp thoại xác nhận an toàn tiếng Việt.

### 2. Tích hợp thanh công cụ Synthesize (`gui/pages/page_synthesize.py`)
Thanh công cụ Text Editor (`tags_bar`) được bố trí hài hòa, bảo toàn trọn vẹn toàn bộ các nút cảm xúc hiện có:
- `📂 Nhập tài liệu` (Sprint 1)
- `⚙️ Chuẩn Hóa` (Mở `TextProcessorDialog`)
- `🔍 Tìm/Thay Thế` (Mở `FindReplaceDialog`)
- `📁 Dự Án` (Menu tùy chọn: *Lưu dự án hiện tại*, *Mở danh sách dự án*)
- Các nút cảm xúc và thao tác nhanh: `[cười]`, `[hắng giọng]`, `[thở dài]`, `[nghỉ 500ms]`, `[nghỉ 2s]`, `[xóa]`, `[📋 Dán từ Clipboard]`.

---

## V. KẾT QUẢ KIỂM THỬ TỰ ĐỘNG SPRINT 2 (16/16 PASS)

Bộ test toàn diện tại `tools/test_sprint_2_document_processing.py` được thực thi với Python 3.12 nội bộ:

| # | Tên Test Case | Mục Tiêu Kiểm Thử | Trạng Thái | Thời Gian |
|---|---|---|:---:|:---:|
| 1 | `test_01_text_normalization_nfc_and_whitespace` | Chuẩn hóa NFD $\rightarrow$ NFC, gộp khoảng trắng thừa, căn lề dấu câu | **PASS** | 0.05s |
| 2 | `test_02_unusual_characters_detection` | Phát hiện ký tự lạ, ký tự điều khiển ngoài bảng mã tiếng Việt | **PASS** | 0.04s |
| 3 | `test_03_vietnamese_cardinal_numbers` | Đọc số nguyên, quy tắc chữ số hàng chục "mốt", "tư", "lăm/nhăm" | **PASS** | 0.08s |
| 4 | `test_04_vietnamese_decimals_and_percentages` | Đọc số thập phân (dấu phẩy/chấm) và tỷ lệ phần trăm | **PASS** | 0.06s |
| 5 | `test_05_vietnamese_negative_numbers` | Đọc số âm thông thường và trong ngữ cảnh đo lường/nhiệt độ | **PASS** | 0.05s |
| 6 | `test_06_vietnamese_currencies` | Đọc chuẩn định dạng tiền tệ VNĐ và Đô la Mỹ | **PASS** | 0.05s |
| 7 | `test_07_vietnamese_ordinals` | Đọc số thứ tự "thứ 1" $\rightarrow$ "thứ nhất", "thứ 4" $\rightarrow$ "thứ tư" | **PASS** | 0.05s |
| 8 | `test_08_phone_numbers_reading` | Tách và đọc số điện thoại theo từng chữ số | **PASS** | 0.06s |
| 9 | `test_09_document_and_military_codes` | Đọc số văn bản quân sự `123/QĐ-BQP`, phiên hiệu `f324`, `e1`, `d4`, `c1` | **PASS** | 0.07s |
| 10 | `test_10_ambiguous_number_protection` | Bảo vệ các mã vũ khí `AK-47`, `K-54`, `F-35`, `Su-30` không bị đọc nhầm | **PASS** | 0.06s |
| 11 | `test_11_smart_sentence_chunking` | Phân đoạn câu tự nhiên, bảo toàn từ nguyên vẹn, không vỡ số | **PASS** | 0.07s |
| 12 | `test_12_find_and_replace_engine` | Tìm kiếm và thay thế chính xác, hỗ trợ case sensitive và Regex | **PASS** | 0.06s |
| 13 | `test_13_document_project_lifecycle` | Vòng đời Tạo, Lưu, Save As, Mở, Đổi tên, Nhân bản, Xóa DocumentProject | **PASS** | 0.12s |
| 14 | `test_14_corrupted_project_recovery` | Cách ly file JSON hỏng thành `.corrupted`, nạp an toàn không crash UI | **PASS** | 0.08s |
| 15 | `test_15_existing_projects_compatibility` | Đảm bảo tính độc lập tuyệt đối với dự án Audio, Broadcast, Schedule | **PASS** | 0.05s |
| 16 | `test_16_ui_dialogs_integration` | Khởi tạo và kiểm tra cấu trúc giao diện dialogs và `page_synthesize` | **PASS** | 0.15s |
| **Tổng** | **16 Test Cases** | **16/16 PASS (100% SUCCESS RATE)** | **PASS** | **1.14s** |

---

## VI. TUÂN THỦ NGUYÊN TẮC AN TOÀN HỆ THỐNG

1. **Version Control**: Hoạt động hoàn toàn trên branch `dev-v3.1.0`. Tag `v3.0.1` trên nhánh `master` được bảo toàn nguyên trạng.
2. **AI & Audio Core**: Không chỉnh sửa VieNeu-TTS v3 Turbo ONNX Runtime CPU. Không cài thêm PyTorch. Không gọi Cloud API.
3. **Bản quyền & Bảo mật**: Giữ nguyên cơ chế License Ed25519 offline.
4. **Dữ liệu người dùng**: Toàn bộ dữ liệu âm thanh, lịch sử phát sóng, dự án cũ không bị thay đổi.
5. **Git Commit**: Commit rõ ràng `86fc54b`: *"feat(sprint-2): Implement Vietnamese text processor, DocumentProject lifecycle, find-replace, and synthesis UI integration"*.

---
**Kết luận**: Sprint 2 đã hoàn thành xuất sắc và sẵn sàng cho Sprint 3 (Batch Processing & Long Document Audio Synthesis).