# BÁO CÁO KIỂM CHỨNG INFERENCE GPU THỰC TẾ (T-TTS v1.0.1)

**Ngày thực hiện:** 11/10/2026  
**Mục tiêu:** Kiểm tra khả năng chạy GPU inference thực tế của mô hình VieNeu-TTS v3 Turbo, độc lập trên môi trường Windows Desktop hiện hành mà không build lại ứng dụng và không can thiệp làm gián đoạn môi trường CPU đang hoạt động.

---

## 1. TỔNG KẾT KẾT QUẢ KIỂM CHỨNG

| Tiêu chí | Kết quả thực tế | Trạng thái |
|---|---|---|
| **Phần cứng GPU** | NVIDIA GeForce RTX 2060 (6 GB VRAM, 5.1 GB Free, Driver 582.53) | ✅ Đạt yêu cầu phần cứng |
| **CUDA Driver API (`nvcuda.dll`)** | Sẵn sàng tại `C:\Windows\System32\nvcuda.dll` (Hỗ trợ CUDA 13.0 API) | ✅ Đạt chuẩn Driver |
| **Gói ONNX Runtime trong môi trường** | `onnxruntime==1.31.0` (Bản CPU thuần) | ❌ Không có `CUDAExecutionProvider` |
| **Khả năng nạp mô hình bằng CUDA** | 4/4 session ONNX bị fallback về `CPUExecutionProvider` | ⚠️ Không chạy GPU |
| **VieNeu-TTS SDK (`OnnxV3LiteEngine`)** | Tham số `providers=["CPUExecutionProvider"]` bị hardcode | ⚠️ Cần tiêm Provider linh hoạt |
| **Chính sách an toàn Backend (`resolve_device_policy`)** | Chặn tự động khi chọn `device='cuda'`, ngăn crash ứng dụng | ✅ Hoạt động chính xác |
| **Tạo âm thanh WAV thật (VieNeu-TTS)** | Đã tạo thành công `test_gpu_inference_output.wav` (4.08s, 48kHz, mono) | ✅ Âm thanh rõ, chuẩn |
| **Benchmark CPU Baseline (3 lượt đo)** | Trung vị Latency: **1.476s**, RTF: **0.362x** (nhanh hơn 2.76x thời gian thực) | ✅ Rất nhanh và ổn định |

> **KẾT LUẬN CHÍNH THỨC:**  
> Môi trường hiện tại **chưa thể kích hoạt suy luận GPU (CUDA)** do gói `onnxruntime` cài đặt là bản CPU (chưa phải `onnxruntime-gpu`) và thiếu các runtime DLL phụ thuộc của CUDA/cuDNN. Toàn bộ các session ONNX thực tế đều chạy trên CPU. **Không tuyên bố GPU đã được xác minh trên môi trường hiện tại.**

---

## 2. PHÂN TÍCH MÃ NGUỒN SDK VIENEU-TTS (`OnnxV3LiteEngine`)

Đã tiến hành phân tích mã nguồn thực tế của `OnnxV3LiteEngine` tại file:  
`python312/python/Lib/site-packages/vieneu/_v3_turbo_engine/onnx_runtime_lite.py`

### 2.1. Cấu hình Providers trong SDK
- Tại hàm `__init__` (dòng 91):
  ```python
  prov = ["CPUExecutionProvider"]
  self.sess_pre = ort.InferenceSession(str(vd / "vieneu_prefill.onnx"), so, providers=prov)
  self.sess_dec = ort.InferenceSession(str(vd / "vieneu_decode_step.onnx"), so, providers=prov)
  self.sess_ac = ort.InferenceSession(str(vd / "vieneu_acoustic_cached.onnx"), so, providers=prov)
  self.sess_codec_dec = ort.InferenceSession(str(cd / "moss_audio_tokenizer_decode_full.onnx"), so, providers=prov)
  ```
- **Nhận xét:** Danh sách `providers` bị **hardcode cứng là `["CPUExecutionProvider"]`**. SDK không cung cấp tham số chính thức nào trong `__init__` hoặc qua `Vieneu(mode=...)` để truyền `CUDAExecutionProvider` từ bên ngoài vào.
- **Phương án tương thích bảo trì lâu dài (Không sửa site-packages):**
  - Không sửa trực tiếp vào file của `vieneu` trong `site-packages`.
  - Thay vào đó, backend có thể sử dụng cơ chế wrapper / monkey-patching an toàn trong lớp `TTSEngine` (hoặc subclass) để thay thế `prov` khi khởi tạo session nếu hệ thống đã đủ điều kiện chạy CUDA.

### 2.2. Danh sách các phiên ONNX trong Pipeline
Pipeline VieNeu-TTS v3 Turbo khởi tạo các phiên ONNX riêng biệt:

1. **`sess_pre` (`vieneu_prefill.onnx` - 1.04 MB):** Xử lý ma trận embedding đầu vào từ văn bản và prompt âm thanh. Chạy 1 lần ở đầu câu.
2. **`sess_dec` (`vieneu_decode_step.onnx` - 1.01 MB):** Bước giải mã tự hồi quy (Autoregressive step) kèm KV Cache. Chạy lặp lại qua từng frame ($T$ lần, tương ứng ~100–300 lần/câu).
3. **`sess_ac` (`vieneu_acoustic_cached.onnx` - 6.87 MB):** Dự đoán các mã âm học qua $N_{vq}$ kênh codebook. Chạy lặp lại trong mỗi frame thời gian (khoảng $T \times 8$ lần, tương đương 800–2400 lần/câu).
4. **`sess_codec_dec` (`moss_audio_tokenizer_decode_full.onnx` - 0.65 MB + 42 MB weights):** Vocoder giải mã toàn bộ chuỗi token âm học thành tín hiệu sóng âm waveform 48,000 Hz. Chạy 1 lần ở cuối pipeline.
5. **Session phụ (Lazy):** `sess_codec_step.onnx` (streaming vocoder), `moss_audio_tokenizer_encode.onnx` (trích xuất giọng mẫu khi voice cloning), `denoiser.onnx` (khử ồn âm thanh mẫu).

### 2.3. Cơ chế phân vùng (Partitioning) & Giới hạn luồng dữ liệu CPU-GPU
- **Phân vùng Execution Provider của ONNX Runtime:** Khi chỉ định `providers=['CUDAExecutionProvider', 'CPUExecutionProvider']`, ONNX Runtime tự động thực hiện graph partitioning: các toán tử hỗ trợ CUDA chạy trên GPU, các toán tử không hỗ trợ tự động fallback về CPU.
- **Đặc thù kiến trúc của VieNeu-TTS Lite:**
  - Giữa các bước chạy `sess_dec` và `sess_ac`, các thao tác sampling, tied embeddings lookup (`audio_emb`, `text_emb`) và xvector projection được thực hiện bằng **NumPy trên CPU**.
  - Việc gọi `.run()` hàng nghìn lần từ vòng lặp Python sẽ tạo ra chi phí sao chép bộ nhớ PCIe (Host-to-Device và Device-to-Host latency) liên tục.
  - Do đó, phần `sess_codec_dec` (Vocoder) sẽ tăng tốc vượt bậc trên GPU nhờ tính toán song song khối lớn, trong khi phần autoregressive loop step-by-step sẽ bị giới hạn bởi độ trễ gọi hàm và PCIe nếu không được tối ưu hoá toàn vẹn trong C++/CUDA graph.

---

## 3. KẾT QUẢ KIỂM THỬ ĐỘC LẬP (`test_gpu_inference.py`)

Bộ script kiểm thử độc lập đã được thực thi thực tế bằng Python 3.12 (không dùng mock):

### 3.1. Phiên bản thư viện & Môi trường
- **Hệ điều hành:** Windows 10/11 64-bit
- **Python:** 3.12.7 (64-bit)
- **ONNX Runtime:** `1.31.0` (Bản CPU)
- **Available Providers từ `ort.get_available_providers()`:**  
  `['AzureExecutionProvider', 'CPUExecutionProvider']`
- **Thư viện phụ trợ:** `numpy 2.5.3`, `soundfile 0.14.0`, `vieneu 3.8.3`

### 3.2. Kiểm tra khả năng nạp 4 mô hình ONNX với yêu cầu GPU

| Mô hình | Kích thước | Yêu cầu `['CUDAExecutionProvider']` | Providers gán thực tế | Kết luận thực thi |
|---|---|---|---|---|
| **`vieneu_prefill.onnx`** | 1.04 MB | ORT Warning: *CUDAExecutionProvider not in available provider names* | `['CPUExecutionProvider']` | Chạy 100% CPU |
| **`vieneu_decode_step.onnx`** | 1.01 MB | ORT Warning: *CUDAExecutionProvider not in available provider names* | `['CPUExecutionProvider']` | Chạy 100% CPU |
| **`vieneu_acoustic_cached.onnx`** | 6.87 MB | ORT Warning: *CUDAExecutionProvider not in available provider names* | `['CPUExecutionProvider']` | Chạy 100% CPU |
| **`moss_audio_tokenizer_decode_full.onnx`** | 0.65 MB | ORT Warning: *CUDAExecutionProvider not in available provider names* | `['CPUExecutionProvider']` | Chạy 100% CPU |

### 3.3. Kiểm tra kiểm soát chính sách Backend (`resolve_device_policy`)
- Khi yêu cầu cấu hình `engine.load(device="cuda")`:
  - Hệ thống phát hiện có phần cứng RTX 2060 nhưng ORT thiếu CUDA provider.
  - Backend lập tức ném ngoại lệ rõ ràng và chặn chạy:
    > `ValueError: Phát hiện GPU NVIDIA NVIDIA GeForce RTX 2060 (VRAM 6143 MB, CUDA 13.0 (13000)), nhưng ONNX Runtime hiện tại (v1.31.0) là bản CPU và chưa tích hợp CUDAExecutionProvider.`
  - Điều này chứng minh ứng dụng không bị crash thầm lặng, không tự ý giả mạo trạng thái GPU khi chưa sẵn sàng.

---

## 4. KẾT QUẢ TỔNG HỢP ÂM THANH THẬT & BENCHMARK CPU

### 4.1. Thẩm định file âm thanh WAV (`test_gpu_inference_output.wav`)
- **Văn bản thử nghiệm:** *"Xin chào, đây là bài kiểm thử âm thanh thực tế của Voice Studio T-TTS."*
- **Giọng đọc:** `Nu-Thao` | **Tốc độ:** `1.0`
- **Kết quả phân tích định dạng và âm học:**
  - **Định dạng file:** WAV (RIFF/WAVE), 16-bit PCM Mono
  - **Sample Rate:** `48,000 Hz`
  - **Tổng số mẫu (frames):** `195,840 frames`
  - **Thời lượng:** `4.08 giây`
  - **Dung lượng file:** `391,724 bytes` (~382.5 KB)
  - **Biên độ cực đại (Peak):** `24,349` (`-2.58 dBFS`)
  - **Năng lượng RMS:** `3,686.37` (`-18.98 dBFS`)
  - **Chất lượng:** `is_silent = False`, `is_clipped = False`, `audible = True` (Âm thanh rõ ràng, không bị méo tiếng hay mất âm).

### 4.2. Benchmark CPU Baseline (3 lượt đo chính thức)

| Lượt đo | Thời gian tạo (Latency) | Thời lượng âm thanh | Real-Time Factor (RTF) | Đánh giá tốc độ |
|---|---|---|---|---|
| **Warm-up** | 0.292 s | 0.72 s | 0.405x | Khởi động cache |
| **Lượt 1** | 1.494 s | 4.16 s | 0.359x | Nhanh hơn 2.78x realtime |
| **Lượt 2** | 1.476 s | 4.00 s | 0.369x | Nhanh hơn 2.71x realtime |
| **Lượt 3** | 1.377 s | 4.08 s | 0.338x | Nhanh hơn 2.96x realtime |
| **TRUNG VỊ (Median)** | **1.476 s** | **4.08 s** | **0.362x** | **Nhanh hơn 2.76x thời gian thực** |

*Ghi chú:* Thời gian nạp mô hình vào RAM ban đầu (`engine.load()`): **4.587 s**.

---

## 5. NGUYÊN NHÂN GỐC & PHƯƠNG ÁN ĐẠT CHUẨN ĐỂ HỖ TRỢ GPU

### 5.1. Nguyên nhân gốc
1. **Thiếu thư viện `onnxruntime-gpu`:** Môi trường Python nội bộ đang cài đặt package `onnxruntime==1.31.0` (chỉ chứa binary CPU). Bản này không kèm theo `onnxruntime_providers_cuda.dll`.
2. **Thiếu CUDA Runtime DLLs:** Hệ thống đã có Driver NVIDIA 582.53 (`nvcuda.dll`), nhưng chưa có các thư viện động CUDA Runtime của NVIDIA trên Windows:
   - `cudart64_12.dll`
   - `cublas64_12.dll` / `cublasLt64_12.dll`
   - `cudnn64_9.dll` (cuDNN v9) hoặc `cudnn64_8.dll` (cuDNN v8)
3. **VieNeu SDK Hardcode:** SDK `vieneu` hardcode `prov = ["CPUExecutionProvider"]` trong mã nguồn, cần lớp tương thích (Adapter/Wrapper) ở tầng Backend để truyền `CUDAExecutionProvider` khi môi trường đã sẵn sàng.

### 5.2. Lộ trình khuyến nghị (Action Plan) khi muốn nâng cấp GPU
Tuân thủ nguyên tắc không tự ý cài đặt hàng loạt và bảo đảm an toàn cho bản phát hành:

1. **Bước 1 - Giữ nguyên môi trường CPU hiện tại:** Đảm bảo bản build CPU portable/installer hiện tại tiếp tục hoạt động ổn định 100% trên mọi máy tính.
2. **Bước 2 - Tạo môi trường GPU riêng biệt:**
   - Cài đặt `onnxruntime-gpu` (phiên bản tương thích với Python 3.12, ví dụ `onnxruntime-gpu==1.19.x` hoặc `1.20.x`).
   - Đặt các DLL NVIDIA CUDA 12.x / cuDNN vào thư mục DLLs của Python hoặc đi kèm ứng dụng.
3. **Bước 3 - Cập nhật `TTSEngine` để tiêm Provider linh hoạt:**
   - Thay vì sửa đè file site-packages, cập nhật `TTSEngine.load()` để monkey-patch hoặc kế thừa `OnnxV3LiteEngine` gán `prov = ['CUDAExecutionProvider', 'CPUExecutionProvider']` có kiểm tra fallback.
4. **Bước 4 - Chạy lại `test_gpu_inference.py` để đo benchmark đối chứng CPU vs GPU.**
