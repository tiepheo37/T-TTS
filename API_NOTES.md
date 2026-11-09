# Ghi chép API SDK `vieneu` (VieNeu-TTS v3 Turbo)

Nguồn: đọc trực tiếp source repo pnnbao97/VieNeu-TTS (nhánh main, 10/2026).
Giấy phép repo: **Apache 2.0** — được sao chép, sửa đổi, dùng thương mại.

## Cài đặt & khởi tạo

```bash
pip install vieneu
```

```python
from vieneu import Vieneu
tts = Vieneu(mode="v3turbo")          # mặc định đã là v3turbo
tts = Vieneu(mode="v3turbo", precision="int8")  # nhanh ~3x trên CPU (cần CPU có VNNI để không méo)
```

- `backend="auto"`: CPU → ONNX, GPU → PyTorch. Ép bằng `backend="onnx"` / `"pytorch"`.
- Lần đầu chạy sẽ tải model từ Hugging Face (đo thực tế 10/2026):
  - `pnnbao-ump/VieNeu-TTS-v3-Turbo/onnx_int8`: **~165 MB**
  - `OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano` (ONNX): **~91 MB**
  - Tổng ~256 MB — nhẹ, không cần GPU.
- `sample_rate` luôn **48000 Hz**; `infer()` trả về `np.ndarray` float32.

## Giọng đọc

```python
tts.list_preset_voices()   # -> [(label, voice_id), ...], 25 giọng; 10 giọng "featured" có ⭐ đứng đầu
tts.resolve_voice_name("Minh Quân")  # -> "Hải Đăng" (tự xử lý tên cũ/alias)
tts.get_preset_voice("Hải Đăng")     # -> dict metadata (gender, region, style, description)
```

- Giọng mặc định: **"Hải Đăng"**.
- Một số tên cũ vẫn dùng được nhờ alias (vd "Minh Quân"/"Minh Quân Pro" → "Hải Đăng").

## Tổng hợp

```python
wav = tts.infer(text, voice="Hải Đăng")   # voice: tên str hoặc dict; trả về np.ndarray 48kHz
```

Tham số chính của `infer()`: `temperature=0.8`, `top_k=25`, `top_p=0.95`,
`max_new_frames=300`, `repetition_penalty=1.2`, `max_chars=256` (tự cắt chunk),
`silence_p=0.15`, `apply_watermark=True`.

- **Thẻ cảm xúc** (thử nghiệm, chèn trực tiếp trong văn bản): `[cười]`, `[thở dài]`, `[hắng giọng]`.
- `style` đã **bỏ** ở v3 Turbo (phong cách đi theo giọng mẫu, luôn tự nhiên).
- **Không có tham số tốc độ** trong SDK → app tự làm time-stretch (WSOLA) sau khi infer.

## Nhân bản giọng

```python
tts.add_voice("Tên giọng", "duong/dan/file_mau.wav", denoise=True)
tts.save_voices()          # lưu lại để dùng cho lần sau
tts.remove_voice("Tên giọng", save=True)
tts.encode_reference("file.wav")  # -> (wav_44.1k, sample_rate), có khử nhiễu
```

- File mẫu chỉ cần **3–8 giây**; SDK tự khử nhiễu.
- CIT Voice Studio yêu cầu thu trực tiếp bằng micro + đọc câu đồng ý (~8s),
  kiểm tra ngay trên máy rồi mới lưu; **cấm** upload file có sẵn.

## Streaming (không dùng trong app này, ghi để tham khảo)

`tts.infer_stream(text, ...)` yield từng chunk 48kHz; chunk đầu ~115ms trên GPU.

## Giới hạn bản mở

- v3 Turbo là bản mã nguồn mở **mới nhất**; v4 độc quyền (chỉ qua vieneu.io).
- Các tính năng **Lồng tiếng (Dubbing), Bài giảng, Sách nói** chỉ có trong app
  chính thức của tác giả — repo này chỉ có SDK + demo Gradio. App này tự xây
  các tính năng đó trên nền SDK.

## Workaround đã kiểm chứng (10/2026): lỗi tải model của SDK

`vieneu` 3.8.x + `huggingface_hub` mới: `OnnxV3LiteEngine._fetch` dùng
`hf_hub_download` trả về đường dẫn trong `blobs/` phẳng, trong khi file ONNX tham
chiếu external data bằng đường dẫn tương đối → onnxruntime báo
"External data path escapes model directory" và model không load được.

App này tự xử lý trong `backend/models_bootstrap.py`: tải từng file rồi copy ra
`models/v3turbo_onnx/` + `models/moss_codec/` với đúng tên file, rồi vá
`OnnxV3LiteEngine._fetch` để dùng thư mục local. Chạy 1 lần duy nhất ở lần đầu.
