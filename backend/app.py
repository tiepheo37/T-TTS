"""Voice Studio — Server Flask & Local API Engine.

Mở ứng dụng: http://127.0.0.1:8001
Trang tài liệu API: http://127.0.0.1:8001/docs
"""
import io
import os
import re
import sys
import time
import base64
import shutil
import threading
import traceback
import zipfile
from pathlib import Path
import numpy as np

# Đảm bảo mã hóa UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from flask import Flask, jsonify, request, send_file, send_from_directory, Response

# Thêm thư mục hiện tại chứa module backend vào sys.path để hỗ trợ PyInstaller frozen mode
_backend_dir = Path(__file__).resolve().parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

try:
    from .storage import init_storage, native_save_file_dialog
    from .tts_engine import TTSEngine
    from .pron_dict import PronDict
    from .history import History
    from .license import license_manager, get_machine_id, STATUS_ACTIVE
    from .audio_utils import (
        save_wav, wav_to_mp3, SAMPLE_RATE, clean_text,
        create_srt_content, parse_subtitles, align_subtitles_for_dubbing,
        split_batch, time_stretch, silence, validate_and_convert_reference_audio,
    )
except ImportError:
    from storage import init_storage, native_save_file_dialog
    from tts_engine import TTSEngine
    from pron_dict import PronDict
    from history import History
    from license import license_manager, get_machine_id, STATUS_ACTIVE
    from audio_utils import (
        save_wav, wav_to_mp3, SAMPLE_RATE, clean_text,
        create_srt_content, parse_subtitles, align_subtitles_for_dubbing,
        split_batch, time_stretch, silence, validate_and_convert_reference_audio,
    )

_STORAGE_INFO = init_storage()
APP_DIR = _STORAGE_INFO["app_dir"]
OUT_DIR = _STORAGE_INFO["out_dir"]
UPLOAD_DIR = _STORAGE_INFO["upload_dir"]

if getattr(sys, "frozen", False):
    BASE = Path(sys._MEIPASS)
else:
    BASE = Path(__file__).resolve().parent.parent

WEB_DIR = BASE / "web"

engine = TTSEngine(mode="v3turbo", precision="int8")
pron = PronDict()
history = History(out_dir=OUT_DIR)
infer_lock = threading.Lock()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024


import math

def validate_speed(val, default=1.0):
    """Xác thực và chuyển đổi tốc độ đọc (0.75x - 1.50x). Trả về float hoặc raise ValueError."""
    if val is None or val == "":
        return float(default)
    try:
        s = float(val)
    except (ValueError, TypeError):
        raise ValueError("Tốc độ đọc (speed) phải là một số thực hợp lệ (từ 0.75x đến 1.50x).")
    if math.isnan(s) or math.isinf(s):
        raise ValueError("Tốc độ đọc không được là NaN hoặc vô cực.")
    if not (0.75 <= s <= 1.50):
        raise ValueError(f"Tốc độ đọc ({s:.2f}x) nằm ngoài giới hạn cho phép (0.75x đến 1.50x).")
    return s


def validate_voice(voice_id):
    """Xác thực voice_id có tồn tại trong danh sách giọng hợp lệ hay không."""
    if not voice_id:
        return engine.resolve_voice(None)
    vid = str(voice_id).strip()
    if not engine.is_valid_voice(vid):
        raise ValueError(f"Giọng đọc '{vid}' không tồn tại. Vui lòng chọn giọng đọc hợp lệ từ danh sách.")
    return vid


def _safe_name(s, default="audio"):
    s = re.sub(r"[^\w\- ]+", "", s or "", flags=re.UNICODE).strip().replace(" ", "_")
    return s[:40] or default


def _synthesize_to_files(text, voice_id, speed, tag="audio"):
    """Tổng hợp văn bản -> (wav_path, mp3_path|None)."""
    with infer_lock:
        audio, sr = engine.synthesize(text, voice=voice_id, speed=speed, pron_dict=pron.all())
    stamp = _safe_name(tag)
    fname = f"{int(time.time()*1000)}_{stamp}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wav_path = OUT_DIR / f"{fname}.wav"
    save_wav(wav_path, audio, sr)
    mp3_path = OUT_DIR / f"{fname}.mp3"
    ok = wav_to_mp3(wav_path, mp3_path)
    return wav_path, (mp3_path if ok else None), audio, sr


# ---------------------------------------------------------------- GIAO DIỆN CHÍNH
@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/favicon.ico")
def favicon():
    for cand in [BASE / "app_icon.ico", WEB_DIR / "favicon.ico", BASE / "app_icon.png"]:
        if cand.is_file():
            return send_file(str(cand), mimetype="image/x-icon")
    return ("", 204)


# ---------------------------------------------------------------- TRANG API DOCS (/docs)
@app.get("/docs")
def api_docs():
    """Trang hướng dẫn & Tài liệu API Local (Swagger Style UI)."""
    docs_html = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<title>T-TTS v1.0.1 — Tài liệu Local API</title>
<style>
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; background:#f8f9fa; color:#212529; margin:0; padding:30px; }
  .container { max-width:960px; margin:0 auto; background:#fff; border-radius:10px; border:1px solid #e9ecef; padding:30px; box-shadow:0 4px 12px rgba(0,0,0,0.05); }
  h1 { font-family:"Times New Roman",serif; color:#1F3D16; border-bottom:2px solid #DA251D; padding-bottom:10px; font-size:26px; }
  .badge { background:#1F3D16; color:#FFDD00; font-size:12px; padding:4px 10px; border-radius:12px; font-weight:bold; }
  .endpoint { background:#f8f9fa; border:1px solid #dee2e6; border-left:5px solid #1F3D16; margin:16px 0; border-radius:6px; padding:16px; }
  .method { font-weight:bold; display:inline-block; padding:4px 8px; border-radius:4px; font-size:12px; color:#fff; }
  .get { background:#28a745; }
  .post { background:#007bff; }
  .delete { background:#dc3545; }
  .path { font-family:monospace; font-size:16px; font-weight:bold; margin-left:10px; }
  pre { background:#272822; color:#f8f8f2; padding:14px; border-radius:6px; overflow-x:auto; font-size:13px; }
  code { font-family:Consolas,monospace; }
</style>
</head>
<body>
<div class="container">
  <h1>🇻🇳 T-TTS v1.0.1 — LOCAL API DOCUMENTATION <span class="badge">v1.0.1 Offline</span></h1>
  <p>PHẦN MỀM CHUYỂN VĂN BẢN THÀNH GIỌNG NÓI TIẾNG VIỆT</p>
  <p style="font-size:13px; color:#555;"><i>T-TTS do Tiệp Nguyễn phát triển. Sử dụng mô hình giọng nói VieNeu-TTS của tác giả Phạm Nguyễn Ngọc Bảo.</i></p>
  <p>Địa chỉ máy chủ cục bộ: <code>http://127.0.0.1:8001</code>.</p>
  
  <div class="endpoint">
    <span class="method get">GET</span><span class="path">/health</span>
    <p>Kiểm tra trạng thái máy chủ & mô hình VieNeu-TTS.</p>
    <pre>curl http://127.0.0.1:8001/health</pre>
  </div>

  <div class="endpoint">
    <span class="method get">GET</span><span class="path">/voices</span>
    <p>Lấy danh sách 25 giọng preset được phép và giọng nhân bản.</p>
    <pre>curl http://127.0.0.1:8001/voices</pre>
  </div>

  <div class="endpoint">
    <span class="method post">POST</span><span class="path">/api/tts/generate</span>
    <p>Tạo giọng nói từ văn bản (xuất WAV hoặc MP3).</p>
    <pre>curl -X POST http://127.0.0.1:8001/api/tts/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "Xin chào Việt Nam", "voice_id": "Hải Đăng", "speed": 1.0, "format": "wav"}' \
  --output result.wav</pre>
  </div>
</div>
</body>
</html>"""
    return docs_html


# ---------------------------------------------------------------- BẢO VỆ BẢN QUYỀN OFFLINE
PROTECTED_TTS_ENDPOINTS = {
    "/api/tts/generate",
    "/api/tts/preview",
    "/stream",
    "/api/tts/generate-with-subtitles",
    "/api/tts/dubbing",
    "/api/tts/conversation",
    "/api/tts/batch",
}


@app.before_request
def enforce_license_gate():
    path = request.path
    # Khóa toàn bộ các tác vụ xử lý âm thanh chính nếu bản quyền không hợp lệ
    if path in PROTECTED_TTS_ENDPOINTS or (path == "/api/voice-clone" and request.method == "POST"):
        if not license_manager.is_active():
            info = license_manager.get_status_info()
            return jsonify({
                "error": f"Chức năng xử lý bị khóa: {info['status_message']}",
                "license_locked": True,
                "status": info["status"],
                "machine_id": info["machine_id"],
                "message": info["status_message"],
            }), 403


# ---------------------------------------------------------------- API: BẢN QUYỀN & MÃ MÁY
@app.get("/api/license/status")
def api_license_status():
    return jsonify(license_manager.get_status_info())


@app.get("/api/license/machine-id")
def api_license_machine_id():
    return jsonify({"machine_id": get_machine_id()})


@app.post("/api/license/activate")
def api_license_activate():
    key_str = ""
    if request.is_json:
        data = request.get_json(silent=True) or {}
        key_str = data.get("key") or ""
    elif "key_file" in request.files:
        f = request.files["key_file"]
        key_str = f.read().decode("utf-8", errors="ignore")
    else:
        key_str = request.form.get("key") or ""

    ok, msg, info = license_manager.activate(key_str)
    return jsonify({
        "success": ok,
        "ok": ok,
        "message": msg,
        "info": info,
    }), (200 if ok else 400)


# ---------------------------------------------------------------- API: HEALTH & VOICES
@app.get("/health")
def health():
    st = engine.get_hardware_status()
    lic_info = license_manager.get_status_info()
    st.update({
        "app": "T-TTS v1.0.1",
        "description": "PHẦN MỀM CHUYỂN VĂN BẢN THÀNH GIỌNG NÓI TIẾNG VIỆT",
        "developer": "Tiệp Nguyễn",
        "model_author": "Phạm Nguyễn Ngọc Bảo",
        "status": "ok",
        "model": f"VieNeu-TTS {engine.mode.upper()}",
        "sample_rate": SAMPLE_RATE,
        "gpu_available": st.get("cuda_available", False),
        "license_status": lic_info.get("status"),
        "license_active": lic_info.get("is_active", False),
    })
    return jsonify(st)


@app.get("/voices")
def voices():
    try:
        return jsonify({"voices": engine.list_voices()})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------- API: AUDIO STREAMING (/stream)
@app.route("/stream", methods=["GET", "POST"])
def stream_audio():
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        text = data.get("text", "")
        raw_voice = data.get("voice_id", "Hải Đăng")
        raw_speed = data.get("speed", 1.0)
    else:
        text = request.args.get("text", "")
        raw_voice = request.args.get("voice_id", "Hải Đăng")
        raw_speed = request.args.get("speed", 1.0)

    text = text.strip()
    if not text:
        return jsonify({"error": "Thiếu văn bản text."}), 400

    try:
        voice_id = validate_voice(raw_voice)
        speed = validate_speed(raw_speed)
        wav_path, _, _, _ = _synthesize_to_files(text, voice_id, speed, tag="stream")
        return send_file(str(wav_path), mimetype="audio/wav")
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Lỗi streaming: {e}"}), 500


# ---------------------------------------------------------------- API: TẠO GIỌNG NÓI SINGLE
@app.post("/api/tts/generate")
def api_generate():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Thiếu văn bản (text)."}), 400

    try:
        voice_id = validate_voice(data.get("voice_id"))
        speed = validate_speed(data.get("speed"))
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    fmt = (data.get("format") or "wav").lower()
    if fmt not in ("wav", "mp3"):
        return jsonify({"error": "Định dạng chỉ chấp nhận wav hoặc mp3."}), 400

    try:
        wav_path, mp3_path, audio_data, sr = _synthesize_to_files(text, voice_id, speed, tag=text[:20])
        item = history.add(text, voice_id, speed, wav_path, mp3_path, kind="tts")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Lỗi tổng hợp giọng nói: {e}"}), 500

    target_path = mp3_path if (fmt == "mp3" and mp3_path) else wav_path

    # Hỗ trợ cờ ?download=1 hoặc ?raw=1 nếu người dùng gọi qua curl hoặc script bên ngoài cần nhận trực tiếp file nhị phân
    if request.args.get("download") == "1" or request.args.get("raw") == "1":
        if fmt == "mp3" and mp3_path:
            return send_file(str(mp3_path), mimetype="audio/mpeg", as_attachment=True, download_name=f"{item['id']}.mp3")
        return send_file(str(wav_path), mimetype="audio/wav", as_attachment=True, download_name=f"{item['id']}.wav")

    # MẶC ĐỊNH: Trả về JSON để tuyệt đối KHÔNG kích hoạt IDM (Internet Download Manager) hay hộp thoại Download File Info
    try:
        with open(target_path, "rb") as af:
            audio_b64 = base64.b64encode(af.read()).decode("ascii")
    except Exception:
        audio_b64 = ""

    return jsonify({
        "success": True,
        "ok": True,
        "item_id": item["id"],
        "filename": target_path.name,
        "filepath": str(target_path.resolve()),
        "format": fmt,
        "duration": round(len(audio_data) / sr, 2),
        "size_bytes": target_path.stat().st_size,
        "audio_b64": audio_b64,
        "message": f"Đã lưu thành công tại {target_path.resolve()}"
    })


@app.post("/api/tts/preview")
def api_preview():
    """Nghe thử giọng mẫu."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        voice_id = validate_voice(data.get("voice_id"))
        speed = validate_speed(data.get("speed"), default=1.0)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    sample = data.get("text") or "Xin chào, đây là giọng đọc mẫu của Voice Studio."
    try:
        wav_path, _, _, _ = _synthesize_to_files(sample[:120], voice_id, speed, tag="preview")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Lỗi nghe thử giọng: {e}"}), 500

    if request.args.get("raw") == "1":
        return send_file(str(wav_path), mimetype="audio/wav")

    try:
        with open(wav_path, "rb") as af:
            audio_b64 = base64.b64encode(af.read()).decode("ascii")
    except Exception:
        audio_b64 = ""

    return jsonify({"success": True, "audio_b64": audio_b64})


# ---------------------------------------------------------------- API: PHỤ ĐỀ (.SRT)
@app.post("/api/tts/generate-with-subtitles")
def api_generate_with_subtitles():
    """Tạo audio kèm file .srt mốc thời gian từng câu."""
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Thiếu văn bản."}), 400

    try:
        voice_id = validate_voice(data.get("voice_id"))
        speed = validate_speed(data.get("speed"))
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    sentences = [s.strip() for s in re.split(r"(?<=[.!?\n])\s+", text) if s.strip()]
    if not sentences:
        sentences = [text]

    audio_chunks = []
    srt_items = []
    current_time = 0.0

    try:
        with infer_lock:
            for idx, s in enumerate(sentences, 1):
                chunk, sr = engine.synthesize(s, voice=voice_id, speed=speed, pron_dict=pron.all())
                dur = len(chunk) / sr
                audio_chunks.append(chunk)
                pause_chunk = silence(0.3, sr)
                audio_chunks.append(pause_chunk)

                srt_items.append({
                    "start": current_time,
                    "end": current_time + dur,
                    "text": s
                })
                current_time += (dur + 0.3)

        full_audio = np.concatenate(audio_chunks) if audio_chunks else np.zeros(0, dtype=np.float32)
        stamp = f"{int(time.time()*1000)}"
        wav_path = OUT_DIR / f"{stamp}_subtitled.wav"
        save_wav(wav_path, full_audio, SAMPLE_RATE)

        srt_text = create_srt_content(srt_items)
        srt_path = OUT_DIR / f"{stamp}_subtitled.srt"
        srt_path.write_text(srt_text, encoding="utf-8")

        history.add(text, voice_id, speed, wav_path, srt_path=srt_path, kind="subtitle")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(str(wav_path), "audio.wav")
            zf.write(str(srt_path), "subtitles.srt")
        buf.seek(0)

        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="voice-studio-subtitles.zip")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Lỗi tạo phụ đề: {e}"}), 500


# ---------------------------------------------------------------- API: LỒNG TIẾNG THEO PHỤ ĐỀ (DUBBING)
@app.post("/api/tts/dubbing")
def api_dubbing():
    if "subtitle_file" not in request.files:
        return jsonify({"error": "Thiếu file phụ đề (subtitle_file)."}), 400

    try:
        voice_id = validate_voice(request.form.get("voice_id"))
        speed = validate_speed(request.form.get("speed"))
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    f = request.files["subtitle_file"]
    content = f.read().decode("utf-8", errors="ignore")

    subtitles = parse_subtitles(content)
    if not subtitles:
        return jsonify({"error": "File phụ đề rỗng hoặc không đúng định dạng SRT/VTT."}), 400

    def synth_fn(t, speed=1.0):
        with infer_lock:
            return engine.synthesize(t, voice=voice_id, speed=speed, pron_dict=pron.all())

    try:
        full_audio, updated_subs = align_subtitles_for_dubbing(subtitles, synth_fn, default_speed=speed)
        stamp = f"{int(time.time()*1000)}_dubbed"
        wav_path = OUT_DIR / f"{stamp}.wav"
        save_wav(wav_path, full_audio, SAMPLE_RATE)

        updated_srt = create_srt_content(updated_subs)
        srt_path = OUT_DIR / f"{stamp}.srt"
        srt_path.write_text(updated_srt, encoding="utf-8")

        history.add(f"Lồng tiếng ({len(subtitles)} câu)", voice_id, speed, wav_path, srt_path=srt_path, kind="dubbing")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(str(wav_path), "dubbed_audio.wav")
            zf.write(str(srt_path), "adjusted_subtitles.srt")
        buf.seek(0)
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="voice-studio-dubbing.zip")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Lỗi lồng tiếng: {e}"}), 500


# ---------------------------------------------------------------- API: HỘI THOẠI / PODCAST
@app.post("/api/tts/conversation")
def api_conversation():
    data = request.get_json(force=True, silent=True) or {}
    lines = data.get("lines") or []
    if not lines or not isinstance(lines, list):
        return jsonify({"error": "Thiếu danh sách các câu thoại (lines)."}), 400

    audio_chunks = []
    summary_text = []

    try:
        parsed_lines = []
        for item in lines:
            speaker = item.get("speaker", "Nhân vật")
            v_id = validate_voice(item.get("voice_id"))
            spd = validate_speed(item.get("speed"))
            txt = (item.get("text") or "").strip()
            pause_after = float(item.get("pause_after") or 0.5)
            if txt:
                parsed_lines.append((speaker, v_id, spd, txt, pause_after))
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    try:
        with infer_lock:
            for speaker, v_id, spd, txt, pause_after in parsed_lines:
                summary_text.append(f"{speaker}: {txt}")
                seg_audio, sr = engine.synthesize(txt, voice=v_id, speed=spd, pron_dict=pron.all())
                audio_chunks.append(seg_audio)
                if pause_after > 0:
                    audio_chunks.append(silence(pause_after, sr))

        full_audio = np.concatenate(audio_chunks) if audio_chunks else np.zeros(0, dtype=np.float32)
        stamp = f"{int(time.time()*1000)}_podcast"
        wav_path = OUT_DIR / f"{stamp}.wav"
        save_wav(wav_path, full_audio, SAMPLE_RATE)

        item_hist = history.add("\n".join(summary_text[:3]), "Nhiều giọng", 1.0, wav_path, kind="podcast")
        return send_file(str(wav_path), mimetype="audio/wav", as_attachment=True, download_name=f"podcast_{item_hist['id']}.wav")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Lỗi tạo hội thoại: {e}"}), 500


# ---------------------------------------------------------------- API: TẠO HÀNG LOẠT ([P1], [P2]...)
@app.post("/api/tts/batch")
def api_batch():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Thiếu văn bản (text)."}), 400

    try:
        voice_id = validate_voice(data.get("voice_id"))
        speed = validate_speed(data.get("speed"))
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    items = split_batch(text)
    if not items:
        return jsonify({"error": "Không tìm thấy mốc [P1], [P2]... trong văn bản."}), 400

    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for label, seg in items:
                wav_path, _, _, _ = _synthesize_to_files(seg, voice_id, speed, tag=label)
                history.add(seg, voice_id, speed, wav_path, kind="batch")
                zf.write(str(wav_path), f"{label}_{_safe_name(seg[:20])}.wav")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Lỗi tạo hàng loạt: {e}"}), 500

    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="voice-studio-batch.zip")


# ---------------------------------------------------------------- API: LÀM SẠCH VĂN BẢN & ĐỌC FILE (PDF/DOCX/TXT)
@app.post("/api/text/clean")
def api_clean_text():
    data = request.get_json(force=True, silent=True) or {}
    t = data.get("text", "")
    return jsonify({"cleaned": clean_text(t)})


@app.post("/api/file/read")
def api_read_file():
    if "file" not in request.files:
        return jsonify({"error": "Thiếu file đính kèm."}), 400
    f = request.files["file"]
    fn = f.filename.lower()
    content = ""
    try:
        if fn.endswith(".txt"):
            content = f.read().decode("utf-8", errors="ignore")
        elif fn.endswith(".docx"):
            import docx
            doc = docx.Document(io.BytesIO(f.read()))
            content = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        elif fn.endswith(".pdf"):
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(f.read()))
            pages_text = []
            for page in reader.pages:
                txt = page.extract_text()
                if txt:
                    pages_text.append(txt)
            content = "\n".join(pages_text)
        else:
            return jsonify({"error": "Chỉ hỗ trợ file .txt, .docx, .pdf"}), 400

        return jsonify({"text": content, "cleaned": clean_text(content)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Không đọc được file: {e}"}), 500


# ---------------------------------------------------------------- API: TỪ ĐIỂN PHÁT ÂM
@app.get("/api/pron-dict")
def pron_list():
    return jsonify({"dict": pron.all()})


@app.post("/api/pron-dict")
def pron_set():
    data = request.get_json(force=True, silent=True) or {}
    try:
        pron.set(data.get("word"), data.get("reading"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"dict": pron.all()})


@app.delete("/api/pron-dict/<word>")
def pron_delete(word):
    pron.delete(word)
    return jsonify({"dict": pron.all()})


# ---------------------------------------------------------------- API: LỊCH SỬ & QUẢN LÝ Ổ ĐĨA
@app.get("/api/history")
def hist_list():
    return jsonify({
        "items": history.all(),
        "stats": history.get_stats(),
    })


@app.get("/api/history/<item_id>/download")
def hist_download(item_id):
    fmt = request.args.get("fmt", "wav")
    item = history.get(item_id)
    if not item:
        return jsonify({"error": "Không tìm thấy bản ghi lịch sử."}), 404
    p = history.resolve(item, fmt if fmt in ("wav", "mp3", "srt") else "wav")
    if not p:
        return jsonify({"error": "File không còn trên ổ đĩa."}), 404
    mt = "audio/mpeg" if p.suffix == ".mp3" else ("text/plain" if p.suffix == ".srt" else "audio/wav")
    return send_file(str(p), mimetype=mt, as_attachment=True, download_name=p.name)


@app.delete("/api/history/<item_id>")
def hist_delete(item_id):
    ok = history.delete(item_id)
    return jsonify({"ok": ok, "stats": history.get_stats()})


@app.post("/api/history/clear")
def hist_clear():
    history.clear()
    return jsonify({"ok": True, "stats": history.get_stats()})


# ---------------------------------------------------------------- API: MỞ THƯ MỤC LƯU FILE TRÊN MÁY (WINDOWS EXPLORER)
@app.route("/api/storage/open-output", methods=["GET", "POST"])
def open_output_folder():
    """Mở thư mục lưu file trực tiếp trong Windows Explorer."""
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(OUT_DIR))
        return jsonify({"ok": True, "path": str(OUT_DIR)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/storage/info", methods=["GET"])
def storage_info():
    """Trả về đường dẫn lưu file thực tế trên ổ cứng."""
    return jsonify({
        "out_dir": str(OUT_DIR),
        "app_dir": str(APP_DIR),
        "upload_dir": str(UPLOAD_DIR),
    })


@app.post("/api/storage/save-as")
def save_file_as():
    """Mở hộp thoại Save As native của Windows và lưu bản sao ra vị trí người dùng chọn."""
    data = request.get_json(force=True, silent=True) or {}
    item_id = data.get("item_id")
    custom_name = data.get("filename")

    if not item_id:
        return jsonify({"error": "Thiếu item_id."}), 400

    item = history.get(item_id)
    if not item:
        return jsonify({"error": "Không tìm thấy file trong lịch sử."}), 404

    src_path = history.resolve(item, "wav")
    if not src_path or not src_path.exists():
        return jsonify({"error": "File nguồn không còn tồn tại trên ổ đĩa."}), 404

    default_name = custom_name or src_path.name
    dest_path = native_save_file_dialog(default_name=default_name, default_dir=str(OUT_DIR))
    if not dest_path:
        return jsonify({"cancelled": True, "message": "Đã hủy lưu file."})

    try:
        dest = Path(dest_path)
        shutil.copy2(src_path, dest)
        return jsonify({
            "success": True,
            "cancelled": False,
            "path": str(dest.resolve()),
            "filename": dest.name,
            "message": f"Đã lưu thành công ra: {dest.resolve()}"
        })
    except Exception as e:
        return jsonify({"error": f"Lỗi sao chép file: {e}"}), 500


# ---------------------------------------------------------------- API: NHÂN BẢN GIỌNG NÓI (MICRO)
CONSENT_SENTENCE = "Tôi đồng ý cho ứng dụng tạo giọng đọc mô phỏng giọng nói của chính tôi."


@app.get("/api/voice-clone/consent")
def clone_consent():
    return jsonify({"consent_sentence": CONSENT_SENTENCE})


@app.post("/api/voice-clone")
def voice_clone():
    name = (request.form.get("name") or "").strip()
    consent = request.form.get("consent") == "yes"
    f = request.files.get("audio")

    if not name:
        return jsonify({"error": "Vui lòng nhập tên giọng nhân bản."}), 400
    if not consent:
        return jsonify({"error": "CẢNH BÁO: Bạn phải đọc và xác nhận đây là giọng của chính bạn."}), 400
    if f is None or not getattr(f, "filename", None):
        return jsonify({"error": "Không nhận được dữ liệu thu âm từ micro hoặc dữ liệu bị rỗng."}), 400

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    up_path = (UPLOAD_DIR / f"clone_{_safe_name(name)}.wav").resolve()

    # Xác thực và chuyển đổi chuẩn hóa tệp âm thanh sang WAV 16-bit PCM mono 44.1kHz
    try:
        final_wav_path, dur, sr = validate_and_convert_reference_audio(f, up_path, min_duration=3.0, target_sr=44100)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as conv_err:
        traceback.print_exc()
        return jsonify({"error": f"Lỗi xử lý tệp âm thanh micro: {conv_err}"}), 400

    try:
        with infer_lock:
            saved_name = engine.add_custom_voice(name, str(final_wav_path))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Lỗi đăng ký giọng nhân bản vào mô hình AI: {e}"}), 500

    return jsonify({"ok": True, "voice_id": saved_name, "duration": dur})


@app.delete("/api/voice-clone/<name>")
def voice_clone_delete(name):
    try:
        engine.remove_custom_voice(name)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------- API: QUẢN LÝ MÔ HÌNH & GPU
@app.get("/api/model/status")
def model_status():
    return jsonify(engine.get_hardware_status())


@app.post("/api/model/configure")
def model_configure():
    data = request.get_json(force=True, silent=True) or {}
    precision = data.get("precision", "int8")
    mode = data.get("mode", "v3turbo")
    device = data.get("device", "cpu")
    try:
        engine.load(mode=mode, precision=precision, device=device)
        st = engine.get_hardware_status()
        return jsonify({"success": True, "status": st, **st})
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Lỗi chuyển cấu hình mô hình: {e}"}), 500


# ---------------------------------------------------------------- API: THOÁT ỨNG DỤNG AN TOÀN
@app.route("/api/shutdown", methods=["GET", "POST"])
def app_shutdown():
    """Endpoint cho phép tắt ứng dụng an toàn (dành cho automation testing & UI shutdown)."""
    def _delayed_exit():
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=_delayed_exit, daemon=True).start()
    return jsonify({"status": "ok", "message": "Đang tắt ứng dụng..."})


def main():
    import webbrowser
    print("------------------------------------------------------------")
    print("T-TTS v1.0.1 - PHAN MEM CHUYEN VAN BAN THANH GIONG NOI TIENG VIET")
    print("Phat trien boi Tiep Nguyen. Su dung mo hinh VieNeu-TTS cua Pham Nguyen Ngoc Bao.")
    print("Dang khoi tao mo hinh VieNeu-TTS v3 Turbo...")
    print("------------------------------------------------------------")

    def _bg_load():
        try:
            engine.load()
            print("[OK] Mo hinh VieNeu-TTS va Tokenizer da san sang!")
        except Exception as e:
            print(f"CANH BAO: Chua tai xong model ({e}). Server van mo tai http://127.0.0.1:8001")

    def _open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open("http://127.0.0.1:8001")
        except Exception:
            pass

    threading.Thread(target=_bg_load, daemon=True).start()
    threading.Thread(target=_open_browser, daemon=True).start()
    print("Mo giao dien ung dung: http://127.0.0.1:8001")
    print("Trang tai lieu API: http://127.0.0.1:8001/docs")
    app.run(host="127.0.0.1", port=8001, threaded=True)


if __name__ == "__main__":
    main()
