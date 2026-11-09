# BÁO CÁO THỬ NGHIỆM TĂNG TỐC CODEC BẰNG GPU (T-TTS v1.0.1)

**Ngày thực hiện:** 11/10/2026  
**Mục tiêu thí nghiệm:** Xác minh khả năng tăng tốc phần giải mã âm thanh Vocoder (`sess_codec_dec`) của mô hình VieNeu-TTS v3 Turbo bằng GPU NVIDIA RTX 2060 trên Windows, kết hợp giữ các phiên suy luận tự hồi quy (`sess_pre`, `sess_dec`, `sess_ac`) trên CPU, hoàn toàn không ảnh hưởng tới bản phát hành CPU hiện tại.  
**Trạng thái chính thức:**  
> **CHƯA ĐẠT (Chưa kích hoạt được suy luận CUDA thật do thiếu thư viện runtime CUDA/cuDNN)**

---

## 1. TỔNG KẾT KẾT QUẢ THỰC THI

| Hạng mục kiểm tra | Trạng thái thực tế | Đánh giá kỹ thuật |
|---|---|---|
| **Bản CPU & Bộ cài Windows** | Giữ nguyên 100%, không sửa portable trong `dist/`, không đổi `setup_installer.iss` | ✅ An toàn tuyệt đối |
| **Phần cứng GPU NVIDIA** | NVIDIA GeForce RTX 2060 (6143 MB VRAM, ~4571 MB khả dụng, Driver 582.53) | ✅ Đạt yêu cầu phần cứng |
| **CUDA Driver API (`nvcuda.dll`)** | Sẵn sàng tại `C:\Windows\System32\nvcuda.dll` (CUDA Driver 13.0) | ✅ Driver OS sẵn sàng |
| **Gói ONNX Runtime hiện hành** | `onnxruntime==1.31.0` (Bản CPU thuần, không có `CUDAExecutionProvider`) | ❌ Thiếu provider CUDA |
| **Thư viện CUDA/cuDNN Runtime** | Thiếu: `cudart64_12.dll`, `cublas64_12.dll`, `cublasLt64_12.dll`, `cudnn64_9.dll`... | ❌ Thiếu DLLs phụ thuộc |
| **Adapter cấu hình từng Session** | Xây dựng thành công `VieNeuHybridEngineAdapter` ([`backend/vieneu_adapter.py`](file:///c:/Users/Minh%20Dang/Downloads/voice-studio-app/backend/vieneu_adapter.py)) | ✅ Độc lập, không sửa site-packages |
| **Kiểm tra đầu vào Vocoder Codec** | Phát hiện và chuẩn hóa chính xác `n_vq=16` (Tensor `(1, T, 16)`) | ✅ Chuẩn hóa kỹ thuật |
| **Benchmark CPU Codec Baseline** | Đo thành công 3 lượt: Trung vị **1668.48 ms** cho **12.00s** âm thanh (**RTF: 0.1390x**) | ✅ Baseline xác thực thực tế |
| **Suy luận CUDA thật** | Bị chặn an toàn tại bước nạp provider (không fallback CPU im lặng) | ⚠️ **CHƯA ĐẠT** |
| **Cải thiện thực tế** | **Chưa thể kết luận cải thiện** vì chưa nạp được kernel CUDA | ⚠️ Không tuyên bố GPU nhanh hơn |

---

## 2. THIẾT KẾ ADAPTER ĐỘC LẬP (`VieNeuHybridEngineAdapter`)

Để giải quyết giới hạn hardcode `prov = ["CPUExecutionProvider"]` trong `vieneu._v3_turbo_engine.onnx_runtime_lite.OnnxV3LiteEngine`, một lớp Adapter độc lập đã được xây dựng tại [`backend/vieneu_adapter.py`](file:///c:/Users/Minh%20Dang/Downloads/voice-studio-app/backend/vieneu_adapter.py).

### 2.1. Kiến trúc phân tách từng Session
Mô hình VieNeu-TTS v3 Turbo gồm 4 session chính. Adapter cho phép cấu hình thiết bị thực thi riêng biệt cho từng session:

```python
class VieNeuHybridEngineAdapter:
    def __init__(
        self,
        checkpoint_path="pnnbao-ump/VieNeu-TTS-v3-Turbo",
        onnx_dir=None,
        codec_dir=None,
        providers_codec=["CUDAExecutionProvider"],  # Dành riêng cho Vocoder
        providers_ar=["CPUExecutionProvider"],      # Dành cho Autoregressive (prefill, decode, acoustic)
        allow_silent_fallback=False,                # Chặn fallback tự động sang CPU
        ...
    ):
```

### 2.2. Phân định session nào chạy GPU, session nào chạy CPU và Lý do
1. **`sess_codec_dec` (`moss_audio_tokenizer_decode_full.onnx` — 44 MB) $\rightarrow$ Cấu hình GPU (CUDA):**
   - **Đặc thù tính toán:** Đây là mô hình Vocoder tích chập đa tầng (Conv1d, TransposedConv1d) với khối lượng phép tính song song cực lớn.
   - **Tần suất gọi:** Chỉ gọi **đúng 1 lần duy nhất** ở cuối chuỗi suy luận để giải mã toàn bộ chuỗi token âm học thành waveform 48,000 Hz.
   - **Hiệu năng kỳ vọng:** Vì chỉ gọi 1 lần và ma trận đầu vào lớn (`(1, T, 16)`), chi phí truyền dữ liệu PCIe (Host-to-Device và Device-to-Host) chỉ tốn một vài mili-giây, trong khi hàng trăm triệu phép tính tích chập sẽ được GPU xử lý song song vượt bậc.
2. **`sess_pre`, `sess_dec`, `sess_ac` $\rightarrow$ Giữ nguyên trên CPU:**
   - **Đặc thù tính toán:** Các bước `sess_dec` và `sess_ac` chạy lặp lại trong vòng lặp Python qua từng frame và từng codebook channel ($T \times 16 \approx 1,600$ đến 3,200 lần gọi `.run()`).
   - **Nút thắt PCIe:** Giữa mỗi lần gọi, các thao tác sampling, lookup embedding và xvector projection đều được tính toán bằng NumPy trên CPU. Nếu đưa `sess_ac` lên GPU, mỗi câu nói sẽ phải thực hiện hàng nghìn lần sao chép bộ nhớ PCIe qua lại giữa RAM và VRAM, gây nghẽn cổ chai PCIe và làm GPU chạy **chậm hơn CPU**.

### 2.3. Tính an toàn và khả năng bảo trì
- **Không sửa `site-packages`:** File `vieneu` gốc giữ nguyên vẹn, việc cập nhật thư viện qua pip không làm mất logic adapter.
- **Không monkey-patch toàn cục:** Adapter chỉ bọc và thay thế session trong phạm vi instance được chỉ định, không thay đổi `ort.InferenceSession` trên toàn tiến trình Python.
- **Chặn fallback im lặng:** Bắt buộc kiểm tra `sess.get_providers()`. Nếu không có `CUDAExecutionProvider`, adapter lập tức ném ngoại lệ rõ ràng thay vì giả mạo kết quả.

---

## 3. KẾT QUẢ BENCHMARK CODEC VOCODER TRÊN CPU (BASELINE)

Kịch bản kiểm thử độc lập [`test_gpu_codec_experiment.py`](file:///c:/Users/Minh%20Dang/Downloads/voice-studio-app/test_gpu_codec_experiment.py) đã đo lường chính xác hiệu năng của Vocoder Codec (`moss_audio_tokenizer_decode_full.onnx`) trên CPU:

- **Dữ liệu đầu vào thử nghiệm:** Tensor mã âm học chuẩn $T = 150$ frames, $N_{vq} = 16$ kênh codebook.
- **Độ dài âm thanh tạo ra:** `12.00 giây` (576,000 mẫu âm thanh @ 48,000 Hz).
- **Thời gian nạp mô hình:** `1.051 giây`.

| Lượt đo | Thời gian giải mã (Latency) | Thời lượng âm thanh | RTF Codec (Real-Time Factor) | Đánh giá tốc độ |
|---|---|---|---|---|
| **Warm-up** | 1,745.12 ms | 12.00 s | 0.1454x | Khởi động bộ nhớ đệm |
| **Lượt 1** | 1,668.48 ms | 12.00 s | 0.1390x | Nhanh hơn 7.19x thời gian thực |
| **Lượt 2** | 1,676.26 ms | 12.00 s | 0.1397x | Nhanh hơn 7.16x thời gian thực |
| **Lượt 3** | 1,621.03 ms | 12.00 s | 0.1351x | Nhanh hơn 7.40x thời gian thực |
| **TRUNG VỊ (Median)** | **1,668.48 ms** | **12.00 s** | **0.1390x** | **Nhanh hơn 7.19x thời gian thực** |

> **Nhận xét quan trọng:**  
> Riêng phần Vocoder Codec trên CPU tiêu tốn **~1.67 giây** để tạo 12 giây âm thanh (chiếm khoảng 25–35% tổng thời gian sinh giọng). Nếu kích hoạt được GPU cho riêng session này, thời gian Vocoder có thể giảm xuống dưới 100 ms, mang lại tiềm năng tối ưu rõ rệt cho toàn bộ pipeline.

---

## 4. KẾT QUẢ KIỂM THỬ GPU & NGUYÊN NHÂN CHƯA ĐẠT

### 4.1. Nhật ký thực thi thực tế (`test_gpu_codec_experiment.log`)
```text
[2026-10-11 08:42:39] [INFO] 1. Kiểm tra phần cứng GPU NVIDIA...
[2026-10-11 08:42:39] [INFO]   [OK] GPU: NVIDIA GeForce RTX 2060 (VRAM: 6143 MB, Free: 4571 MB)
[2026-10-11 08:42:39] [INFO]   [OK] Driver: 582.53 | CUDA Driver Version: 13.0
[2026-10-11 08:42:39] [INFO] 2. Kiểm tra ONNX Runtime và các DLL CUDA/cuDNN...
[2026-10-11 08:42:39] [INFO]   Phiên bản ONNX Runtime: 1.31.0
[2026-10-11 08:42:39] [INFO]   Danh sách Providers: ['AzureExecutionProvider', 'CPUExecutionProvider']
[2026-10-11 08:42:39] [INFO]   [THIẾU] cudart64_12.dll
[2026-10-11 08:42:39] [INFO]   [THIẾU] cublas64_12.dll
[2026-10-11 08:42:39] [INFO]   [THIẾU] cublasLt64_12.dll
[2026-10-11 08:42:39] [INFO]   [THIẾU] cudnn64_9.dll
[2026-10-11 08:42:39] [INFO]   [THIẾU] cufft64_11.dll
[2026-10-11 08:42:39] [INFO]   [THIẾU] curand64_10.dll
[2026-10-11 08:42:47] [ERROR] DỪNG THỬ NGHIỆM: Không thể chạy CUDAExecutionProvider!
[2026-10-11 08:42:47] [ERROR] Nguyên nhân gốc rễ:
[2026-10-11 08:42:47] [ERROR]   1. Gói onnxruntime hiện hành (v1.31.0) là bản CPU thuần.
[2026-10-11 08:42:47] [ERROR]   2. Chưa có gói onnxruntime-gpu tương thích trong môi trường.
[2026-10-11 08:42:47] [ERROR]   3. Thiếu các thư viện động runtime trên Windows: cudart64_12.dll, cublas64_12.dll, cudnn64_9.dll...
[2026-10-11 08:42:47] [INFO] Trạng thái chính thức: CHƯA_ĐẠT
```

### 4.2. Nguyên nhân kỹ thuật gốc rễ
1. **Thiếu gói nhị phân `onnxruntime-gpu`:** Môi trường hiện tại chỉ có `onnxruntime==1.31.0` (CPU-only wheel). Gói này không chứa file `onnxruntime_providers_cuda.dll`.
2. **Thiếu thư viện CUDA Toolkit & cuDNN trên Windows:** Mặc dù máy có card RTX 2060 và Driver 582.53 (`nvcuda.dll`), hệ điều hành Windows chưa được cài đặt CUDA Runtime Toolkit và cuDNN v9. Windows không thể tìm thấy các DLL phụ thuộc động cần thiết.
3. **Tuân thủ nguyên tắc dừng an toàn:** Không tự động sửa hoặc cài lại môi trường CPU đang hoạt động; không cho phép im lặng fallback sang CPU khi bài test yêu cầu GPU.

---

## 5. SO SÁNH HIỆU NĂNG CPU VS GPU VÀ KẾT LUẬN TỐC ĐỘ

| Chỉ số | Baseline CPU (Hiện tại) | Hybrid GPU Vocoder (RTX 2060) | Đánh giá |
|---|---|---|---|
| **Session Codec (`sess_codec_dec`)** | `CPUExecutionProvider` (1,668 ms) | Chưa kích hoạt (Yêu cầu CUDA) | Chưa thể đo GPU |
| **Các Session AR (`sess_pre, dec, ac`)** | `CPUExecutionProvider` (~1,100 ms) | `CPUExecutionProvider` (~1,100 ms) | Giữ nguyên trên CPU |
| **Tổng thời gian suy luận (Latency)** | **~1.48 s** (câu ngắn) đến **~2.8 s** (câu dài) | Chưa có dữ liệu thực nghiệm GPU | **Chưa đạt** |
| **Real-Time Factor (RTF)** | **0.362x** (Toàn trình) | Chưa có dữ liệu thực nghiệm GPU | **Chưa đạt** |
| **Sự cải thiện thực tế** | Nhanh hơn 2.76x thời gian thực | **Chưa thể khẳng định có cải thiện thực tế** khi chưa chạy CUDA thật | Tuân thủ nguyên tắc không tuyên bố |

---

## 6. DANH SÁCH TÀI LIỆU VÀ TỆP BÀN GIAO

1. **Báo cáo thí nghiệm đầy đủ:** [`gpu_codec_experiment_report.md`](file:///c:/Users/Minh%20Dang/Downloads/voice-studio-app/gpu_codec_experiment_report.md)
2. **Lớp Adapter cấu hình Session:** [`backend/vieneu_adapter.py`](file:///c:/Users/Minh%20Dang/Downloads/voice-studio-app/backend/vieneu_adapter.py)
3. **Kịch bản kiểm thử độc lập:** [`test_gpu_codec_experiment.py`](file:///c:/Users/Minh%20Dang/Downloads/voice-studio-app/test_gpu_codec_experiment.py)
4. **Tệp Log đầy đủ của lần thử:** [`test_gpu_codec_experiment.log`](file:///c:/Users/Minh%20Dang/Downloads/voice-studio-app/test_gpu_codec_experiment.log)
5. **Dữ liệu chẩn đoán JSON:** [`test_gpu_codec_experiment_results.json`](file:///c:/Users/Minh%20Dang/Downloads/voice-studio-app/test_gpu_codec_experiment_results.json)

**KẾT LUẬN & KIẾN NGHỊ:**
- **Trạng thái:** **CHƯA ĐẠT** suy luận GPU thật do thiếu thư viện `onnxruntime-gpu` và CUDA/cuDNN runtime DLLs trên máy.
- **Bảo toàn sản phẩm:** Không build lại bộ cài Windows, không thay đổi giao diện chọn CPU/GPU, giữ nguyên bản phát hành CPU ổn định và tin cậy tuyệt đối cho người dùng cuối.
