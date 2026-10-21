"""Tải và dựng thư mục model local cho VieNeu-TTS v3 Turbo.

VÌ SAO CẦN FILE NÀY (workaround đã kiểm chứng):
  SDK `vieneu` tải từng file model bằng `huggingface_hub.hf_hub_download`,
  vốn trả về đường dẫn trong thư mục `blobs/` phẳng. Các file ONNX lại tham chiếu
  file dữ liệu ngoài bằng đường dẫn tương đối (vd `vieneu_backbone_shared.data`),
  nên onnxruntime báo lỗi:
    "External data path escapes model directory"
  và model không tải được (gặp với huggingface_hub mới, cả trên Linux lẫn Windows).

  Cách sửa: tải từng file rồi COPY ra thư mục local với đúng tên file, giữ nguyên
  cấu trúc tương đối; sau đó "vá" `OnnxV3LiteEngine._fetch` để nó dùng thư mục
  local thay vì tải lại. Chỉ chạy một lần duy nhất (lần đầu), các lần sau dùng lại.
"""
import os
import sys
import shutil
from pathlib import Path

BACKBONE_REPO = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
CODEC_REPO = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"

GRAPH_FILES = [
    "vieneu_prefill.onnx", "vieneu_decode_step.onnx",
    "vieneu_acoustic_cached.onnx", "vieneu_backbone_shared.data",
    "vieneu_v3_heads.npz", "config.json", "tokenizer.json",
    "speaker_encoder.onnx", "denoiser.onnx",
]
CODEC_FILES = [
    "moss_audio_tokenizer_decode_full.onnx", "moss_audio_tokenizer_decode_shared.data",
    "moss_audio_tokenizer_decode_step.onnx", "codec_browser_onnx_meta.json",
    "moss_audio_tokenizer_encode.onnx", "moss_audio_tokenizer_encode.data",
]

try:
    from .storage import get_app_dir, get_user_data_dir, is_dir_writable
except ImportError:
    from storage import get_app_dir, get_user_data_dir, is_dir_writable

def _get_default_models_root():
    app_models = get_app_dir() / "models"
    # Nếu thư mục model đi kèm đã đầy đủ (kể cả khi nằm trong Program Files chỉ có quyền đọc)
    if (app_models / "v3turbo_onnx").exists() and (app_models / "moss_codec").exists():
        return app_models
    # Nếu thư mục app_models có quyền ghi (chạy portable / dev)
    if is_dir_writable(app_models):
        return app_models
    # Trường hợp cài trong Program Files mà thiếu model cần tải thêm: tải về LocalAppData
    return get_user_data_dir() / "models"

DEFAULT_MODELS_ROOT = _get_default_models_root()


def _sanitize_proxy_env():
    # huggingface_hub (bản mới, dùng httpx2) parse lỗi biến no_proxy khi nó chứa
    # entry dạng [::1]; gọn nó lại để việc tải model không vỡ.
    for key in ("no_proxy", "NO_PROXY"):
        val = os.environ.get(key, "")
        if "[" in val:
            os.environ[key] = "localhost,127.0.0.1"


def _complete(d, files):
    d = Path(d)
    return all((d / f).exists() for f in files if not f.endswith(".json")) and \
           any((d / f).exists() for f in files)


def _fetch_files(repo, files, subfolder, dest):
    from huggingface_hub import hf_hub_download
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for fn in files:
        target = dest / fn
        if target.exists():
            continue
        try:
            src = hf_hub_download(repo, fn, repo_type="model",
                                  subfolder=subfolder or None)
        except Exception:
            if fn.endswith(".json"):
                continue  # meta phụ, có thể vắng
            raise
        shutil.copy(src, target)  # copy dereference: file thật, đúng tên


def ensure_local_models(models_root=None, precision="fp32", progress_cb=None):
    """Đảm bảo có thư mục model local. Trả về (onnx_dir, codec_dir) dạng str."""
    _sanitize_proxy_env()
    root = Path(models_root) if models_root else DEFAULT_MODELS_ROOT
    sub = "onnx_int8" if str(precision).lower() == "int8" else "onnx_update"
    onnx_dir = root / "v3turbo_onnx"
    codec_dir = root / "moss_codec"

    def log(m):
        if progress_cb:
            progress_cb(m)
        else:
            print(m, flush=True)

    if not _complete(onnx_dir, GRAPH_FILES):
        log(f"Đang tải model v3 Turbo ({sub})... (~165MB int8 / ~600MB fp32)")
        _fetch_files(BACKBONE_REPO, GRAPH_FILES, sub, onnx_dir)
    if not _complete(codec_dir, CODEC_FILES):
        log("Đang tải tokenizer MOSS (~91MB)...")
        _fetch_files(CODEC_REPO, CODEC_FILES, None, codec_dir)
    return str(onnx_dir), str(codec_dir)


def patch_sdk_fetch(onnx_dir, codec_dir):
    """Vá OnnxV3LiteEngine._fetch và _resolve_root_file để dùng thư mục local offline hoàn toàn."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

    from vieneu._v3_turbo_engine import onnx_runtime_lite as ort_lite

    def _patched_fetch(repo, files, subfolder):
        if "moss" in repo.lower() or "tokenizer" in repo.lower():
            return Path(codec_dir)
        return Path(onnx_dir)

    def _patched_resolve_root(self, filename: str):
        p = Path(onnx_dir)
        if (p / filename).is_file():
            return str(p / filename)
        p_root = p.parent
        if (p_root / filename).is_file():
            return str(p_root / filename)
        return None

    def _patched_ensure_speaker_encoder(self):
        if self.speaker_encoder is None:
            from vieneu._v3_turbo_engine.speaker import OnnxSpeakerEncoder
            fn = getattr(self, "speaker_encoder_filename", "speaker_encoder.onnx")
            local_spk = Path(onnx_dir) / fn
            if local_spk.is_file():
                self.speaker_encoder = OnnxSpeakerEncoder(str(local_spk), device="cpu", sess_options=self._so)
            else:
                self.speaker_encoder = OnnxSpeakerEncoder.from_pretrained(
                    str(onnx_dir), filename=fn, device="cpu", sess_options=self._so
                )
        return self.speaker_encoder

    # Vá hf_hub_download toàn cục để mọi cuộc gọi tải file trong offline mode đều trả về file local
    try:
        import huggingface_hub
        _orig_hf_download = huggingface_hub.hf_hub_download
        def _offline_hf_download(repo_id, filename, **kwargs):
            p1 = Path(onnx_dir) / filename
            if p1.is_file():
                return str(p1)
            p2 = Path(codec_dir) / filename
            if p2.is_file():
                return str(p2)
            p3 = Path(onnx_dir).parent / filename
            if p3.is_file():
                return str(p3)
            return _orig_hf_download(repo_id, filename, **kwargs)
        huggingface_hub.hf_hub_download = _offline_hf_download
    except Exception:
        pass

    ort_lite.OnnxV3LiteEngine._fetch = staticmethod(_patched_fetch)
    ort_lite.OnnxV3LiteEngine._resolve_root_file = _patched_resolve_root
    ort_lite.OnnxV3LiteEngine._ensure_speaker_encoder = _patched_ensure_speaker_encoder
