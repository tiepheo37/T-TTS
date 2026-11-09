# BÁO CÁO THỬ NGHIỆM BẬT GPU THỰC TẾ (T-TTS v1.0.1)

**Ngày thực hiện:** 11/10/2026  
**Môi trường thử nghiệm:** Windows 10/11 x64 | Python 3.12.7  
**Phần cứng:** NVIDIA GeForce RTX 2060 (6 GB GDDR6 VRAM, Driver 582.53, CUDA Driver API 13.0)  
**Phân loại kết quả chính thức:**  
> **2. GPU chưa chạy do thiếu thư viện hoặc không tương thích (và SDK cần cơ chế tiêm Provider)**

---

## 1. TỔNG KẾT VÀ PHÂN LOẠI KẾT QUẢ

| Hạng mục kiểm tra | Trạng thái thực tế | Đánh giá kỹ thuật |
|---|---|---|
| **Bản CPU & Bộ cài hiện hành** | Giữ nguyên 100%, không sửa `venv` CPU, không build lại bộ cài | ✅ An toàn tuyệt đối |
| **Phần cứng NVIDIA RTX 2060** | Phát hiện GPU RTX 2060 (6143 MB VRAM, ~4650 MB khả dụng, Driver 582.53) | ✅ Đạt phần cứng |
| **CUDA Driver API (`nvcuda.dll`)** | Có sẵn tại `C:\Windows\System32\nvcuda.dll` (CUDA Driver 13.0) | ✅ Driver OS sẵn sàng |
| **Gói ONNX Runtime hiện hành** | `onnxruntime==1.31.0` (Bản CPU-only, providers: `['AzureExecutionProvider', 'CPUExecutionProvider']`) | ❌ Không có `CUDAExecutionProvider` |
| **Thư viện CUDA/cuDNN Runtime** | Thiếu toàn bộ DLL: `cudart64_12.dll`, `cublas64_12.dll`, `cudnn64_9.dll`... | ❌ Thiếu runtime DLLs |
| **VieNeu-TTS SDK (`OnnxV3LiteEngine`)** | Hardcode `prov = ["CPUExecutionProvider"]` và `_Dev.type = "cpu"`, không có tham số API nhận execution providers | ⚠️ Cần lớp Adapter/Subclass |
| **Script kiểm thử GPU độc lập** | `test_gpu_only.py` dừng ngay khi phát hiện thiếu provider, ghi log chi tiết, không fallback CPU | ✅ Đúng tiêu chí nghiêm ngặt |
| **File log & Báo cáo bàn giao** | Đầy đủ `test_gpu_only.log`, `test_gpu_only_results.json`, `gpu_only_test_report.md` | ✅ Đầy đủ |

> **KẾT LUẬN CHÍNH THỨC:**  
> Hệ thống hiện tại **chưa thể thực hiện suy luận GPU thật** do hai nguyên nhân độc lập:  
> 1. Môi trường Python thiếu gói `onnxruntime-gpu` và hệ điều hành thiếu các runtime DLL bắt buộc của CUDA 12.x/cuDNN 9.x (`cudart64_12.dll`, `cublas64_12.dll`, `cudnn64_9.dll`).  
> 2. Mã nguồn VieNeu-TTS SDK (`OnnxV3LiteEngine`) hardcode `providers=["CPUExecutionProvider"]` bên trong hàm khởi tạo, không cho phép truyền provider từ bên ngoài qua API chính thức.  
> 
> **Ứng dụng được giữ nguyên vẹn ở chế độ CPU hoàn toàn ổn định (Baseline: Latency trung vị 1.476s, RTF 0.362x). Tuyệt đối không build lại bộ cài Windows khi GPU inference chưa đạt chuẩn.**

---

## 2. KHẢO SÁT CHI TIẾT MÃ NGUỒN SDK VIENEU-TTS (`OnnxV3LiteEngine`)

Đã tiến hành đọc và phân tích trực tiếp mã nguồn tại:  
`vieneu/_v3_turbo_engine/onnx_runtime_lite.py` (tổng cộng 633 dòng code).

### 2.1. Cách khởi tạo 4 session ONNX trong SDK

Tại `OnnxV3LiteEngine.__init__` (dòng 157–164):
```python
prov = ["CPUExecutionProvider"]
self.sess_pre = ort.InferenceSession(str(vd / "vieneu_prefill.onnx"), so, providers=prov)
self.sess_dec = ort.InferenceSession(str(vd / "vieneu_decode_step.onnx"), so, providers=prov)
self.sess_ac = ort.InferenceSession(str(vd / "vieneu_acoustic_cached.onnx"), so, providers=prov)
self.sess_codec_dec = ort.InferenceSession(
    str(cd / "moss_audio_tokenizer_decode_full.onnx"), so, providers=prov)
```

Ngoài ra còn có 2 session khởi tạo phụ / lười (lazy):
- `sess_codec_step` (dòng 172): `moss_audio_tokenizer_decode_step.onnx` (dùng cho streaming inference), truyền `providers=prov`.
- `_sess_codec_enc` (dòng 611): `moss_audio_tokenizer_encode.onnx` (dùng cho voice cloning), hardcode `providers=["CPUExecutionProvider"]`.

Đồng thời, tại dòng 56–59 và dòng 84:
```python
class _Dev:
    """Minimal stand-in so callers' ``engine.device.type == 'cuda'`` works."""
    type = "cpu"
...
self.device = _Dev()
```

### 2.2. Kiểm tra API chính thức

- **Hàm `OnnxV3LiteEngine.__init__`:**
  ```python
  def __init__(self, checkpoint_path=_V3_REPO, onnx_repo=None, codec_repo=_CODEC_REPO,
               onnx_dir=None, onnx_subfolder="onnx_update", codec_dir=None, threads=0, **_kw):
  ```
  **Không có tham số** nào như `providers`, `execution_providers` hay `device` được chấp nhận để cấu hình execution provider cho các session. Biến `prov` là biến cục bộ (local variable) nằm cứng trong hàm.
- **Hàm `V3TurboVieNeuTTS.__init__` (`v3turbo.py` dòng 161–184):**
  Khi `device="cuda"` và `backend="auto"`, SDK tự động chuyển sang `VieNeuTTSv3Turbo` (yêu cầu **PyTorch GPU** đầy đủ dung lượng 2.5 GB, không dùng đường ONNX Runtime Lite). Nếu ép `backend="onnx"`, nó gọi `OnnxV3LiteEngine` nhưng **không thể truyền device hoặc provider**.
- **Factory `Vieneu(mode="v3turbo")`:** Hoàn toàn không truyền được provider xuống ONNX Runtime Lite.

### 2.3. Đánh giá phương án kiến trúc: Adapter / Subclass lâu dài

Theo yêu cầu: *Không sửa trực tiếp `site-packages` và không monkey-patch toàn cục nếu chưa chứng minh an toàn.*

Có 2 phương án khả thi:
1. **Phương án 1 — Subclass / Wrapper chuyên dụng (`GpuOnnxV3LiteEngine`):**
   - Kế thừa `OnnxV3LiteEngine`.
   - Ghi đè phương thức khởi tạo session hoặc cung cấp tham số `providers: list[str] = ("CUDAExecutionProvider", "CPUExecutionProvider")`.
   - Ưu điểm: Độc lập hoàn toàn với `site-packages`, nâng cấp `vieneu` qua pip không bị mất code, an toàn cho kiểu dữ liệu và đa luồng.
2. **Phương án 2 — Context Manager Scoped Injection trong `backend/tts_engine.py`:**
   - Trong quá trình gọi `engine.load()`, tạm thời bọc việc khởi tạo `ort.InferenceSession.__init__` trong phạm vi hẹp bằng context manager:
     ```python
     @contextmanager
     def scoped_ort_providers(providers):
         orig_init = ort.InferenceSession.__init__
         def patched_init(self, *args, **kwargs):
             kwargs["providers"] = providers
             orig_init(self, *args, **kwargs)
         ort.InferenceSession.__init__ = patched_init
         try:
             yield
         finally:
             ort.InferenceSession.__init__ = orig_init
     ```
   - Khôi phục `orig_init` ngay khi khởi tạo xong, bảo đảm không có monkey-patch toàn cục kéo dài.

### 2.4. Phân tích chi tiết 4 Session: Chạy CUDA hay CPU và Lý do kỹ thuật

Kiến trúc VieNeu-TTS v3 Turbo là sự kết hợp giữa mô hình Transformer Autoregressive, Acoustic Codebook và Vocoder sóng âm:

| Session | File mô hình ONNX | Kích thước | Tần suất gọi | Thiết bị khuyến nghị | Lý do kỹ thuật |
|---|---|---|---|---|---|
| **`sess_pre`** | `vieneu_prefill.onnx` | 1.04 MB | 1 lần/câu | **CUDA** | Xử lý toàn bộ prompt văn bản + audio ban đầu thành KV Cache. Tính toán khối song song, chạy nhanh trên GPU. |
| **`sess_dec`** | `vieneu_decode_step.onnx` | 1.01 MB | $T$ lần (~100–300 lần/câu) | **CUDA hoặc CPU** | Bước autoregressive qua từng frame kèm KV Cache. Kích thước ma trận nhỏ ($1 \times 1 \times H$). Nếu chạy GPU, cần lưu ý chi phí gọi kernel và PCIe copy qua từng bước. |
| **`sess_ac`** | `vieneu_acoustic_cached.onnx` | 6.87 MB | $T \times 8$ lần (~800–2400 lần/câu) | **CPU (hoặc CUDA nếu gom batch)** | Dự đoán token cho 8 codebook. Ở giữa mỗi codebook, SDK thực hiện lookup embedding và sampling ngẫu nhiên bằng **NumPy trên CPU**. Việc gọi `.run()` 1600 lần từ Python sẽ tạo độ trễ Host-to-Device/Device-to-Host liên tục qua bus PCIe, có thể làm GPU chạy chậm hơn CPU nếu tính toán đơn lẻ từng token. |
| **`sess_codec_dec`** | `moss_audio_tokenizer_decode_full.onnx` | 0.65 MB (+ 42 MB weights) | 1 lần/câu | **CUDA** | Vocoder tích chập (Conv/TransposedConv) giải mã toàn bộ chuỗi token âm học thành 192,000+ mẫu âm thanh 48kHz. Tính toán khối cực lớn, GPU tăng tốc vượt trội (dự kiến giảm từ ~0.4s CPU xuống <0.05s GPU). |

---

## 3. KHẢO SÁT MÔI TRƯỜNG GPU RIÊNG & TỔ HỢP TƯƠNG THÍCH

Đã tạo môi trường cách ly riêng `venv_gpu` (dùng Python 3.12.7 từ `python312/python/python.exe`), hoàn toàn không can thiệp vào `venv` CPU gốc.

### 3.1. Phân tích ma trận tương thích (Compatibility Matrix)

Theo tài liệu chính thức từ ONNX Runtime và NVIDIA:
- **Python:** 3.12 (64-bit).
- **Hệ điều hành:** Windows 10/11 x64.
- **Card đồ họa:** NVIDIA GeForce RTX 2060 (Kiến trúc Turing TU106, Compute Capability 7.5).
- **Driver hiện tại:** `582.53` (Cung cấp `nvcuda.dll` hỗ trợ CUDA Driver API đến 13.0).

| Thành phần | Phiên bản tương thích chuẩn | Ghi chú kỹ thuật |
|---|---|---|
| `onnxruntime-gpu` | **`1.20.0`** hoặc **`1.20.1`** | Bản ổn định nhất cho Python 3.12 trên Windows, yêu cầu CUDA 12.x và cuDNN 9.x. Bản `1.31.0` vừa phát hành (10/2026) nhắm tới CUDA 13.0 nhưng hệ sinh thái thư viện CUDA 13 chưa hoàn thiện. |
| **CUDA Toolkit** | **CUDA 12.4** hoặc **12.6** (cu12) | Cung cấp `cudart64_12.dll`, `cublas64_12.dll`, `cublasLt64_12.dll`. Driver 582.53 hoàn toàn tương thích ngược với CUDA 12.x. |
| **cuDNN** | **cuDNN 9.x** (ví dụ: `9.1` hoặc `9.3`) | Cung cấp `cudnn64_9.dll`. `onnxruntime-gpu>=1.20` bắt buộc cuDNN 9.x, không nhận cuDNN 8.x. |
| **MSVC Runtime** | `vcruntime140.dll` / `msvcp140.dll` (v14.40+) | Đã có sẵn trên hệ thống Windows. |

### 3.2. Xác định các DLL bắt buộc và cơ chế phân phối trên Windows

Để `onnxruntime_providers_cuda.dll` nạp thành công trên Windows (không bị `Error 126: The specified module could not be found`), các DLL sau bắt buộc phải có mặt:

1. `cudart64_12.dll` (CUDA Runtime)
2. `cublas64_12.dll` & `cublasLt64_12.dll` (NVIDIA cuBLAS)
3. `cudnn64_9.dll` (NVIDIA cuDNN v9)
4. `cufft64_11.dll` (NVIDIA cuFFT)
5. `curand64_10.dll` (NVIDIA cuRAND)

**Cơ chế tìm kiếm DLL trên Windows (Python 3.8+):**  
Kể từ Python 3.8, Windows không tự động quét thư mục trong `PATH` hệ thống cho các thư viện C++. Do đó, nếu phân phối DLL đi kèm ứng dụng hoặc cài qua pip wheel (`nvidia-*-cu12`), bắt buộc phải gọi:
```python
os.add_dll_directory(r"đường_dẫn_chứa_cuda_dlls")
```
trước khi `import onnxruntime` để Windows nạp đúng `CUDAExecutionProvider`.

### 3.3. Cảnh báo xung đột quan trọng: Tránh cài đồng thời `onnxruntime` và `onnxruntime-gpu`

Package `vieneu` khai báo trong `METADATA`:
```text
Requires-Dist: onnxruntime>=1.20.0
```
Nếu chạy lệnh `pip install vieneu` thông thường, pip sẽ tự động kéo bản `onnxruntime` CPU về và ghi đè lên thư mục `Lib/site-packages/onnxruntime`. Cả hai gói dùng chung namespace, dẫn đến xung đột file và mất file `onnxruntime_providers_cuda.dll`.

**Quy trình cài đặt đúng chuẩn nếu cấu hình GPU:**
```bash
# 1. Cài đặt onnxruntime-gpu trước (không cài bản CPU)
pip install onnxruntime-gpu==1.20.0

# 2. Cài đặt các phụ thuộc của vieneu mà bỏ qua onnxruntime CPU
pip install sea-g2p numpy soundfile soxr kaldi-native-fbank tokenizers huggingface_hub PyYAML librosa
pip install vieneu --no-deps
```

---

## 4. KẾT QUẢ THỰC THI KIỂM THỬ ĐỘC LẬP (`test_gpu_only.py`)

Bộ script `test_gpu_only.py` đã được tạo mới hoàn toàn, độc lập với bộ nghiệm thu phát hành, tuân thủ nguyên tắc không mock và không fallback im lặng.

### 4.1. Lệnh thực thi thực tế
```powershell
venv\Scripts\python.exe test_gpu_only.py
```

### 4.2. Trích xuất Log thực tế từ lần chạy (`test_gpu_only.log`)

```text
[2026-10-11 08:22:25] [INFO] ======================================================================
[2026-10-11 08:22:25] [INFO]   BẮT ĐẦU KIỂM THỬ GPU SUY LUẬN ĐỘC LẬP (test_gpu_only.py)
[2026-10-11 08:22:25] [INFO] ======================================================================
[2026-10-11 08:22:25] [INFO] 1. Kiểm tra phần cứng NVIDIA...
[2026-10-11 08:22:25] [INFO]   [OK] Phát hiện GPU: NVIDIA GeForce RTX 2060 (VRAM: 6143 MB, Free: 4652 MB)
[2026-10-11 08:22:25] [INFO]   [OK] Driver: 582.53 | CUDA Driver Version: 13.0 (raw: 13000)
[2026-10-11 08:22:25] [INFO] 2. Kiểm tra thư viện ONNX Runtime và Execution Providers...
[2026-10-11 08:22:25] [INFO]   Phiên bản ONNX Runtime: 1.31.0
[2026-10-11 08:22:25] [INFO]   Đường dẫn: C:\Users\Minh Dang\Downloads\voice-studio-app\venv\Lib\site-packages\onnxruntime
[2026-10-11 08:22:25] [INFO]   Danh sách Providers sẵn có: ['AzureExecutionProvider', 'CPUExecutionProvider']
[2026-10-11 08:22:25] [INFO] 3. Kiểm tra các thư viện động CUDA / cuDNN Runtime...
[2026-10-11 08:22:25] [INFO]   [THIẾU] cudart64_12.dll
[2026-10-11 08:22:25] [INFO]   [THIẾU] cudart64_110.dll
[2026-10-11 08:22:25] [INFO]   [THIẾU] cublas64_12.dll
[2026-10-11 08:22:25] [INFO]   [THIẾU] cublasLt64_12.dll
[2026-10-11 08:22:25] [INFO]   [THIẾU] cudnn64_9.dll
[2026-10-11 08:22:25] [INFO]   [THIẾU] cudnn64_8.dll
[2026-10-11 08:22:25] [INFO]   [THIẾU] cufft64_11.dll
[2026-10-11 08:22:25] [INFO]   [THIẾU] curand64_10.dll
[2026-10-11 08:22:25] [ERROR] ======================================================================
[2026-10-11 08:22:25] [ERROR] DỪNG KIỂM THỬ: Không tìm thấy 'CUDAExecutionProvider' trong ONNX Runtime!
[2026-10-11 08:22:25] [ERROR] Nguyên nhân gốc rễ:
[2026-10-11 08:22:25] [ERROR]   1. Gói onnxruntime hiện hành (1.31.0) là bản CPU thuần (CPU-only wheel).
[2026-10-11 08:22:25] [ERROR]   2. Chưa cài đặt onnxruntime-gpu (ví dụ: onnxruntime-gpu==1.20.0 hoặc 1.31.0).
[2026-10-11 08:22:25] [ERROR]   3. Hệ thống thiếu các DLL phụ thuộc của CUDA Toolkit và cuDNN:
[2026-10-11 08:22:25] [ERROR]      - Thiếu: cudart64_12.dll
[2026-10-11 08:22:25] [ERROR]      - Thiếu: cudart64_110.dll
[2026-10-11 08:22:25] [ERROR]      - Thiếu: cublas64_12.dll
[2026-10-11 08:22:25] [ERROR]      - Thiếu: cublasLt64_12.dll
[2026-10-11 08:22:25] [ERROR]      - Thiếu: cudnn64_9.dll
[2026-10-11 08:22:25] [ERROR]      - Thiếu: cudnn64_8.dll
[2026-10-11 08:22:25] [ERROR]      - Thiếu: cufft64_11.dll
[2026-10-11 08:22:25] [ERROR]      - Thiếu: curand64_10.dll
[2026-10-11 08:22:25] [ERROR] Không được phép tự ý fallback sang CPU trong bài test GPU độc lập.
[2026-10-11 08:22:25] [ERROR] ======================================================================
[2026-10-11 08:22:25] [INFO] ======================================================================
[2026-10-11 08:22:25] [INFO]   KẾT THÚC KIỂM THỬ GPU
[2026-10-11 08:22:25] [INFO] ======================================================================
[2026-10-11 08:22:25] [INFO] Phân loại kết quả: GPU chưa chạy do thiếu thư viện hoặc không tương thích
[2026-10-11 08:22:25] [INFO] Tóm tắt: Dừng kiểm thử vì onnxruntime hiện tại (v1.31.0) là bản CPU thuần, không có CUDAExecutionProvider và thiếu các DLL runtime CUDA/cuDNN trên Windows.
[2026-10-11 08:22:25] [INFO] Đã lưu kết quả chi tiết tại: C:\Users\Minh Dang\Downloads\voice-studio-app\test_gpu_only_results.json
```

---

## 5. BẢNG SO SÁNH BASELINE CPU VÀ TRẠNG THÁI GPU

| Chỉ số | Baseline CPU (Đo chuẩn 3 lượt) | GPU NVIDIA RTX 2060 (Thực tế) |
|---|---|---|
| **Execution Provider** | `CPUExecutionProvider` | Chưa kích hoạt được (Dừng an toàn) |
| **Model Load Time** | 4.587 s | Chưa khả dụng |
| **Latency Lượt 1** | 1.494 s (Âm thanh 4.16s) | — |
| **Latency Lượt 2** | 1.476 s (Âm thanh 4.00s) | — |
| **Latency Lượt 3** | 1.377 s (Âm thanh 4.08s) | — |
| **Trung vị Latency (Median)** | **1.476 s** | — |
| **Real-Time Factor (RTF)** | **0.362x** (Nhanh hơn 2.76x thời gian thực) | — |
| **Chất lượng WAV** | 48,000 Hz, 16-bit PCM Mono, Peak -2.58 dBFS, RMS -18.98 dBFS | — |
| **VRAM tiêu thụ** | 0 MB VRAM GPU | 0 MB (Chưa nạp kernel vào VRAM) |
| **Kết luận tốc độ** | Ổn định cao trên CPU | **Không tuyên bố GPU nhanh hơn khi chưa có số đo thực nghiệm** |

---

## 6. DANH SÁCH DEPENDENCY CẦN THIẾT NẾU TRIỂN KHAI GPU TRONG TƯƠNG LAI

Nếu dự án quyết định đóng gói thêm phiên bản tùy chọn GPU (bản cài đặt riêng cho người dùng có card rời NVIDIA):

### 6.1. Python Packages
```text
onnxruntime-gpu==1.20.0
numpy>=1.24,<2.6
soundfile>=0.12
soxr>=1.1.0
kaldi-native-fbank==1.22.3
tokenizers>=0.20
sea-g2p>=0.9.1
librosa>=0.11.0
vieneu==3.8.3
```

### 6.2. Bộ Dynamic Link Libraries (DLLs) đi kèm thư mục ứng dụng
Người dùng cuối trên Windows thông thường **không có sẵn CUDA Toolkit hay cuDNN**. Do đó, bộ phân phối GPU bắt buộc phải đóng gói kèm các DLL sau vào thư mục `bin` hoặc `DLLs`:
- `cudart64_12.dll` (~600 KB)
- `cublas64_12.dll` (~400 MB)
- `cublasLt64_12.dll` (~450 MB)
- `cudnn64_9.dll` + các module tích chập cuDNN (~600 MB)
- `cufft64_11.dll` (~150 MB)
- `curand64_10.dll` (~80 MB)

*(Tổng dung lượng thư viện CUDA/cuDNN phân phối thêm xấp xỉ ~1.6 GB. Đây là lý do kiến trúc giữ bản CPU mặc định dung lượng nhẹ ~190 MB hiện tại là hoàn toàn chính xác).*

---

## 7. KIẾN NGHỊ VÀ HƯỚNG ĐI TIẾP THEO

1. **Tuyệt đối không build lại bộ cài Windows hiện hành:**
   Bản cài đặt `Voice Studio v1.0.1` CPU hiện tại đang hoạt động 100% ổn định, tốc độ sinh giọng vượt trội (RTF 0.36x), tương thích với mọi máy tính Windows (kể cả máy không có card NVIDIA).
2. **Không tuyên bố hỗ trợ GPU khi môi trường chưa đủ DLL:**
   Cơ chế an toàn trong `backend/hardware.py` (`resolve_device_policy`) tiếp tục duy trì: Nếu người dùng cố chọn `device='cuda'`, hệ thống báo lỗi rõ ràng về việc thiếu provider thay vì giả lập hoặc crash ứng dụng.
3. **Nếu phát triển phiên bản GPU (v1.1.0-GPU):**
   Cần tạo một package riêng (hoặc add-on pack tải thêm DLL CUDA khi người dùng bấm "Kích hoạt GPU"), kết hợp với lớp `GpuOnnxV3LiteEngine` adapter để phân vùng linh hoạt: `sess_codec_dec` chạy trên CUDA, `sess_ac` chạy trên CPU nhằm đạt hiệu năng tối ưu nhất.
