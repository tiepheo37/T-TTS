"""Tiện ích âm thanh: lưu WAV/MP3, time-stretch (WSOLA), thẻ nghỉ, từ điển, đọc/tạo SRT, lồng tiếng."""
import io
import re
import wave
import numpy as np

SAMPLE_RATE = 48000


# ---------------------------------------------------------------- WAV & MP3
def apply_peak_limiter(audio_array: np.ndarray, ceiling: float = 0.98) -> np.ndarray:
    """Giới hạn đỉnh biên độ (Peak Limiter) chống hiện tượng vỡ tiếng / clipping méo âm."""
    arr = np.asarray(audio_array, dtype=np.float32)
    if arr.size == 0:
        return arr
    peak = float(np.max(np.abs(arr)))
    if peak > ceiling and peak > 0.0:
        arr = arr * (ceiling / peak)
    return np.clip(arr, -1.0, 1.0)


def normalize_audio_safe(audio_clip, target_dbfs: float = -3.0):
    """Chuẩn hóa âm lượng an toàn về target_dbfs, chống chia cho 0 khi audio im lặng."""
    import math
    if audio_clip is None or len(audio_clip) == 0:
        return audio_clip
    max_db = getattr(audio_clip, "max_dBFS", -float("inf"))
    if max_db <= -90.0 or math.isinf(max_db) or math.isnan(max_db):
        return audio_clip
    change_in_dbfs = target_dbfs - max_db
    return audio_clip.apply_gain(change_in_dbfs)


def save_wav(path, audio, sr=SAMPLE_RATE):
    """Lưu numpy float32 [-1, 1] ra file WAV 48kHz 16-bit PCM standard với Limiter chống clipping."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        # Nếu là âm thanh nhiều kênh (stereo), lấy trung bình cộng để hòa âm mono chuẩn
        if audio.shape[0] < audio.shape[1]:
            audio = np.mean(audio, axis=0)
        else:
            audio = np.mean(audio, axis=1)
    audio = apply_peak_limiter(audio, ceiling=0.98)
    pcm = (audio * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def wav_to_mp3(wav_path, mp3_path):
    """Chuyển WAV -> MP3 bằng imageio-ffmpeg hoặc pydub."""
    from .ffmpeg_bootstrap import get_ffmpeg_path
    exe = get_ffmpeg_path()
    if exe:
        try:
            import subprocess
            res = subprocess.run(
                [exe, "-y", "-loglevel", "error", "-i", str(wav_path),
                 "-codec:a", "libmp3lame", "-q:a", "4", str(mp3_path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            if res.returncode == 0 and mp3_path.exists():
                return True
        except Exception:
            pass
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_wav(str(wav_path))
        seg.export(str(mp3_path), format="mp3", bitrate="192k")
        return True
    except Exception:
        return False


def validate_and_convert_reference_audio(input_src, output_wav_path, min_duration=3.0, target_sr=44100):
    """Xác thực toàn diện tệp âm thanh micro và chuyển đổi chuẩn hóa sang WAV 16-bit PCM Mono.

    Quy trình kiểm tra:
    1. Kiểm tra dữ liệu rỗng (0 bytes).
    2. Nhận diện định dạng thực tế (WebM/Opus từ trình duyệt, OGG, WAV, MP3...).
    3. Chuyển đổi sang chuẩn WAV PCM 16-bit, 1 channel (mono), 44.1kHz (chuẩn VieNeu) bằng ffmpeg.
    4. Xác thực header WAV, kích thước, số kênh, bit depth, sample rate.
    5. Kiểm tra thời lượng (tối thiểu min_duration giây).
    6. Kiểm tra âm lượng (RMS) để phát hiện micro tắt tiếng / im lặng.
    7. Đảm bảo đóng tệp hoàn toàn trước khi trả về.
    """
    import os
    import tempfile
    import subprocess
    from pathlib import Path

    output_wav_path = Path(output_wav_path).resolve()
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Thu thập dữ liệu nhị phân hoặc đường dẫn nguồn
    raw_bytes = None
    src_file_path = None

    if hasattr(input_src, "read"):
        # File-like object (Flask FileStorage, BytesIO)
        try:
            input_src.seek(0)
        except Exception:
            pass
        raw_bytes = input_src.read()
    elif isinstance(input_src, (bytes, bytearray)):
        raw_bytes = bytes(input_src)
    elif isinstance(input_src, (str, Path)):
        p = Path(input_src)
        if not p.exists() or p.stat().st_size == 0:
            raise ValueError("Tệp âm thanh tải lên không tồn tại hoặc rỗng (0 bytes).")
        src_file_path = p
        raw_bytes = p.read_bytes()
    else:
        raise ValueError("Định dạng dữ liệu đầu vào không hợp lệ.")

    if not raw_bytes or len(raw_bytes) < 200:
        raise ValueError("Không nhận được dữ liệu âm thanh từ micro hoặc dữ liệu thu âm bị rỗng (0 bytes).")

    # 2. Tạo tệp tạm để ffmpeg phân tích và chuyển đổi
    temp_in = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".input_raw", delete=False) as f_tmp:
            temp_in = Path(f_tmp.name)
            f_tmp.write(raw_bytes)
            f_tmp.flush()

        temp_out = output_wav_path.with_suffix(".tmp.wav")

        # 3. Sử dụng ffmpeg chuyển đổi bất kỳ định dạng nào sang WAV PCM 16-bit mono 44.1kHz
        converted = False
        from .ffmpeg_bootstrap import get_ffmpeg_path
        ffmpeg_exe = get_ffmpeg_path()
        if ffmpeg_exe:
            try:
                cmd = [
                    ffmpeg_exe, "-y", "-loglevel", "error",
                    "-i", str(temp_in),
                    "-vn", "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(target_sr),
                    str(temp_out)
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
                if res.returncode == 0 and temp_out.exists() and temp_out.stat().st_size > 44:
                    converted = True
            except Exception:
                pass

        # Fallback qua soundfile / wave nếu ffmpeg không hoàn tất
        if not converted:
            try:
                import soundfile as sf
                wav_arr, in_sr = sf.read(str(temp_in), dtype="float32", always_2d=True)
                mono = wav_arr.mean(axis=1)
                save_wav(temp_out, mono, sr=target_sr)
                converted = True
            except Exception as sf_err:
                raise ValueError(
                    f"Định dạng âm thanh không nhận diện được và không thể giải mã: {sf_err}. "
                    "Vui lòng kiểm tra lại micro của bạn và thử lại."
                )

        if not temp_out.exists() or temp_out.stat().st_size <= 44:
            raise ValueError("Không thể tạo tệp WAV chuẩn từ dữ liệu thu âm micro.")

        # 4. Xác minh WAV header và các thông số kỹ thuật âm thanh
        with wave.open(str(temp_out), "rb") as w:
            nchannels = w.getnchannels()
            sampwidth = w.getsampwidth()
            framerate = w.getframerate()
            nframes = w.getnframes()
            duration = float(nframes) / float(framerate) if framerate > 0 else 0.0

            if nchannels != 1:
                raise ValueError(f"Số kênh âm thanh không hợp lệ ({nchannels} kênh). Yêu cầu 1 kênh mono.")
            if sampwidth != 2:
                raise ValueError(f"Độ sâu bit không hợp lệ ({sampwidth*8}-bit). Yêu cầu chuẩn 16-bit PCM.")
            if nframes == 0 or duration < 0.1:
                raise ValueError("Tệp âm thanh thu được không có khung dữ liệu (0 frames).")

        # 5. Kiểm tra thời lượng tối thiểu
        if duration < min_duration:
            temp_out.unlink(missing_ok=True)
            raise ValueError(
                f"Thời lượng thu âm quá ngắn (chỉ {duration:.1f} giây). "
                f"Bạn cần thu âm tối thiểu {min_duration:.0f} giây (khuyến nghị khoảng 8 giây và đọc hết câu xác nhận)."
            )

        # 6. Kiểm tra biên độ âm thanh (RMS) để phát hiện micro tắt tiếng hoặc quá nhỏ
        try:
            import soundfile as sf
            samples, _ = sf.read(str(temp_out), dtype="float32")
            rms = float(np.sqrt(np.mean(samples ** 2)))
            if rms < 0.0008:
                temp_out.unlink(missing_ok=True)
                raise ValueError(
                    "Dữ liệu thu âm gần như không có tiếng (âm lượng quá nhỏ hoặc micro bị tắt tiếng). "
                    "Vui lòng kiểm tra lại micro của máy tính, nói to rõ ràng và thu âm lại."
                )
        except ValueError:
            raise
        except Exception:
            pass

        # 7. Di chuyển tệp tạm thành tệp kết quả đích chính thức (đảm bảo atomic replace)
        if output_wav_path.exists():
            output_wav_path.unlink()
        temp_out.rename(output_wav_path)

        return output_wav_path, round(duration, 2), target_sr

    finally:
        if temp_in and temp_in.exists():
            try:
                temp_in.unlink()
            except Exception:
                pass
        if 'temp_out' in locals() and temp_out and temp_out.exists():
            try:
                temp_out.unlink()
            except Exception:
                pass


# ---------------------------------------------------------------- Time Stretch (WSOLA)
def time_stretch(audio, speed, sr=SAMPLE_RATE):
    """Thay đổi tốc độ đọc (0.75x - 1.50x) giữ nguyên cao độ giọng nói bằng WSOLA."""
    x = np.asarray(audio, dtype=np.float32)
    if abs(speed - 1.0) < 1e-5 or x.size == 0:
        return x
    speed = max(0.5, min(2.0, speed))
    win = int(0.020 * sr)      # 20ms window
    hop = int(0.010 * sr)      # 10ms hop
    tol = int(0.005 * sr)      # 5ms tolerance
    win_fn = np.hanning(win)
    x = np.concatenate([np.zeros(tol, dtype=np.float32), x, np.zeros(win + tol, dtype=np.float32)])
    step = hop / speed
    n_frames = max(1, int((len(x) - win) / hop))
    y = np.zeros(int(n_frames * step + win + 100), dtype=np.float32)
    norm = np.zeros_like(y)
    pa = 0.0
    ps = 0
    prev = None
    for _ in range(n_frames):
        ia = int(round(pa))
        best, best_score = ia, -np.inf
        for k in range(-tol, tol + 1):
            c = ia + k
            if c < 0 or c + win > len(x):
                continue
            if prev is None:
                score = 0.0
            else:
                ov = min(win, prev.shape[0])
                score = float(np.dot(prev[-ov:], x[c:c + ov]))
            if score > best_score:
                best_score, best = score, c
        frame = x[best:best + win] * win_fn
        end_idx = ps + win
        if end_idx > len(y):
            break
        y[ps:end_idx] += frame
        norm[ps:end_idx] += win_fn
        prev = x[best:best + win].copy()
        pa += hop
        ps += int(round(step))
    nz = norm > 1e-8
    y[nz] = y[nz] / norm[nz]
    return np.trim_zeros(y, 'b').astype(np.float32)


# ---------------------------------------------------------------- Pause & Emotion tags
PAUSE_RE = re.compile(r"\[nghỉ\s+(\d+(?:\.\d+)?)\s*(s|ms|giây)?\]", re.IGNORECASE)


def split_pause_tags(text):
    """Tách đoạn text và các mốc nghỉ [nghỉ 2s], [nghỉ 500ms] (tối đa 10s).
    Hỗ trợ đầy đủ thẻ nghỉ ở đầu, giữa, cuối văn bản và nhiều thẻ nghỉ liên tiếp.
    """
    if not text or not text.strip():
        return []
    parts = []
    last = 0
    for m in PAUSE_RE.finditer(text):
        seg = text[last:m.start()].strip()
        val = float(m.group(1))
        unit = (m.group(2) or "s").lower()
        secs = val / 1000.0 if unit == "ms" else min(val, 10.0)
        if seg:
            parts.append((seg, secs))
        elif parts:
            prev_text, prev_pause = parts[-1]
            parts[-1] = (prev_text, prev_pause + secs)
        else:
            parts.append(("", secs))
        last = m.end()

    tail = text[last:].strip()
    if tail:
        parts.append((tail, 0.0))

    return [(t, p) for t, p in parts if (t or p > 0)]


def silence(seconds, sr=SAMPLE_RATE):
    return np.zeros(max(0, int(seconds * sr)), dtype=np.float32)


# ---------------------------------------------------------------- Từ điển phát âm
def apply_pron_dict(text, pron_dict):
    """Thay thế từ viết tắt/thuật ngữ theo từ điển người dùng định nghĩa."""
    if not pron_dict:
        return text
    out = text
    for word, reading in sorted(pron_dict.items(), key=lambda kv: -len(kv[0])):
        if not word.strip():
            continue
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        out = pattern.sub(reading, out)
    return out


# ---------------------------------------------------------------- Batch [P1], [P2]...
BATCH_RE = re.compile(r"^\[(P\d+)\]\s*(.*)$", re.IGNORECASE)


def split_batch(text):
    """Tách văn bản theo mốc [P1], [P2]... ở đầu dòng -> [(nhãn, nội_dung)]."""
    items = []
    cur_label, cur_lines = None, []
    for line in text.splitlines():
        m = BATCH_RE.match(line.strip())
        if m:
            if cur_label is not None:
                items.append((cur_label, "\n".join(cur_lines).strip()))
            cur_label, cur_lines = m.group(1).upper(), [m.group(2)]
        elif cur_label is not None:
            cur_lines.append(line)
    if cur_label is not None:
        items.append((cur_label, "\n".join(cur_lines).strip()))
    items = [(l, t) for l, t in items if t]
    if not items and text.strip():
        items = [("P1", text.strip())]
    return items


# ---------------------------------------------------------------- Clean Text
MATH_FORMULA_RE = re.compile(r"(\$[^$]+\$|\\[a-zA-Z]+|\d+[\+\-\*/=\^\.]\d+|\([^\)]+\)\s*[\+=])")


def clean_text(text):
    """Bỏ khoảng trắng thừa, chuẩn hóa xuống dòng nhưng giữ nguyên công thức toán & thẻ nghỉ/cảm xúc."""
    if not text:
        return ""
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        # Normalize multiple spaces inside line
        line = re.sub(r"[ \t]+", " ", line.strip())
        if line:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


# ---------------------------------------------------------------- Subtitles & Dubbing (SRT / VTT)
def format_srt_timestamp(seconds):
    """Chuyển số giây float -> định dạng HH:MM:SS,mmm trong file .srt.
    Quy đổi mili-giây an toàn tuyệt đối tránh làm tròn tràn 1000ms.
    """
    if seconds is None or seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    millis = total_ms % 1000
    total_secs = total_ms // 1000
    secs = total_secs % 60
    mins = (total_secs // 60) % 60
    hrs = total_secs // 3600
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def parse_srt_timestamp(timestamp_str):
    """Chuyển chuỗi mốc thời gian (00:01:23,456 hoặc 00:01:23.456) thành số giây."""
    s = timestamp_str.replace(",", ".").strip()
    parts = s.split(":")
    if len(parts) == 3:
        h, m, sec = parts
        return float(h) * 3600 + float(m) * 60 + float(sec)
    elif len(parts) == 2:
        m, sec = parts
        return float(m) * 60 + float(sec)
    return float(s)


def parse_subtitles(content):
    """Parse nội dung file SRT hoặc VTT thành danh sách các item phụ đề:
    [{"index": 1, "start": 0.0, "end": 2.5, "text": "..."}]
    """
    items = []
    lines = content.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
            i += 1
            continue
        # Check if line is index
        if line.isdigit():
            i += 1
            if i >= len(lines):
                break
            line = lines[i].strip()
        # Check timestamp line (e.g. 00:00:01,000 --> 00:00:03,500)
        if "-->" in line:
            parts = line.split("-->")
            start = parse_srt_timestamp(parts[0])
            end = parse_srt_timestamp(parts[1].split()[0])
            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1
            text = " ".join(text_lines)
            if text:
                items.append({
                    "index": len(items) + 1,
                    "start": start,
                    "end": end,
                    "text": text,
                })
        i += 1
    return items


def create_srt_content(items):
    """Tạo chuỗi nội dung file .srt từ danh sách items [{"start":..., "end":..., "text":...}]"""
    blocks = []
    for idx, item in enumerate(items, 1):
        s_str = format_srt_timestamp(item["start"])
        e_str = format_srt_timestamp(item["end"])
        blocks.append(f"{idx}\n{s_str} --> {e_str}\n{item['text']}\n")
    return "\n".join(blocks)


def align_subtitles_for_dubbing(subtitles, synth_fn, default_speed=1.0):
    """Lồng tiếng theo phụ đề (.srt/.vtt):
    - Đọc từng câu đúng mốc thời gian.
    - Câu dài tự đọc nhanh dần cho vừa (tối đa 1.5x speed tổng thể).
    - Lấn khoảng lặng hoặc đẩy câu sau nếu cần — KHÔNG BAO GIỜ cắt chữ.
    - Trả về (combined_audio, updated_subtitles_list).
    """
    timeline_audio = []
    updated_subs = []
    current_time = 0.0

    for item in subtitles:
        orig_start = item["start"]
        orig_end = item["end"]
        orig_dur = max(0.5, orig_end - orig_start)
        target_start = max(current_time, orig_start)

        # Tổng hợp câu
        audio_seg, sr = synth_fn(item["text"], speed=default_speed)
        dur = len(audio_seg) / sr

        # Nếu audio dài hơn khoảng thời gian cho phép: tăng tốc độ (tối đa 1.5x tổng thể)
        if dur > orig_dur:
            needed_ratio = dur / orig_dur
            max_extra_factor = 1.5 / max(0.1, default_speed)
            extra_factor = min(max_extra_factor, needed_ratio)
            if extra_factor > 1.001:
                audio_seg = time_stretch(audio_seg, extra_factor, sr)
                dur = len(audio_seg) / sr

        # Thêm khoảng lặng dẫn đến mốc target_start nếu có gap
        if target_start > current_time:
            gap_sec = target_start - current_time
            timeline_audio.append(silence(gap_sec, sr))
            current_time = target_start

        # Thêm audio câu lồng tiếng
        timeline_audio.append(audio_seg)
        actual_end = current_time + dur

        updated_subs.append({
            "index": item.get("index", len(updated_subs) + 1),
            "start": round(current_time, 3),
            "end": round(actual_end, 3),
            "text": item["text"],
        })

        current_time = actual_end

    full_audio = np.concatenate(timeline_audio) if timeline_audio else np.zeros(0, dtype=np.float32)
    return full_audio, updated_subs


# ---------------------------------------------------------------- Ghép Bản Tin Phát Thanh (Broadcast Studio)
def load_audio_segment_safe(file_path) -> "AudioSegment":
    """Tải tệp âm thanh (WAV, MP3, M4A, FLAC, OGG, ...) thành pydub AudioSegment một cách an toàn 100%,
    kể cả khi không có ffprobe trên hệ thống Windows."""
    import os
    import subprocess
    import tempfile
    from pathlib import Path
    from .ffmpeg_bootstrap import get_ffmpeg_path
    from pydub import AudioSegment

    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Không tìm thấy tệp âm thanh: {p}")

    ffmpeg_exe = get_ffmpeg_path()
    if ffmpeg_exe:
        AudioSegment.converter = ffmpeg_exe

    # 1. Nếu là WAV chuẩn, thử đọc trực tiếp bằng from_wav (không cần ffprobe)
    if p.suffix.lower() == ".wav":
        try:
            return AudioSegment.from_wav(str(p))
        except Exception:
            pass

    # 2. Sử dụng ffmpeg để giải mã bất kỳ định dạng nào (MP3, M4A, AAC, FLAC, OGG, WMA) thành PCM WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_name = tmp.name
    try:
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", str(p),
            "-vn",
            "-acodec", "pcm_s16le",
            tmp_name,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0:
            raise RuntimeError(f"Lỗi khi giải mã âm thanh qua ffmpeg: {res.stderr}")
        with open(tmp_name, "rb") as f:
            wav_bytes = io.BytesIO(f.read())
        return AudioSegment.from_file(wav_bytes, format="wav")
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except Exception:
                pass


def get_audio_duration_safe(file_path) -> float:
    """Lấy thời lượng âm thanh (giây) hỗ trợ cả WAV, MP3, M4A, v.v."""
    import re
    import wave
    import subprocess
    from pathlib import Path
    p = Path(file_path).resolve()
    if not p.is_file():
        return 0.0

    # 1. Thử native wave cho tệp WAV (cực nhanh, không cần thư viện ngoài)
    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as w:
                nframes = w.getnframes()
                frate = w.getframerate()
                if frate > 0 and nframes > 0:
                    return round(float(nframes) / float(frate), 3)
        except Exception:
            pass

    # 2. Thử soundfile
    try:
        import soundfile as sf
        info = sf.info(str(p))
        if info.duration and info.duration > 0:
            return round(float(info.duration), 3)
    except Exception:
        pass

    # 3. Thử ffmpeg
    try:
        from .ffmpeg_bootstrap import get_ffmpeg_path
        ffmpeg_exe = get_ffmpeg_path()
        if ffmpeg_exe:
            cmd = [ffmpeg_exe, "-i", str(p)]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr)
            if m:
                h, m_, s = m.groups()
                return round(int(h) * 3600 + int(m_) * 60 + float(s), 3)
    except Exception:
        pass

    # 4. Thử pydub AudioSegment
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(str(p))
        if len(seg) > 0:
            return round(len(seg) / 1000.0, 3)
    except Exception:
        pass

    return 0.0


def apply_bgm_ducking(
    bgm_segment,
    speech_intervals: list,
    normal_gain_db: float = -10.0,
    ducked_gain_db: float = -20.0,
    fade_ms: int = 300,
):
    """Tự động hạ âm lượng nhạc nền (ducking) trong các khoảng thời gian giọng đọc đang phát."""
    from pydub import AudioSegment
    if not speech_intervals or len(bgm_segment) == 0:
        return bgm_segment + normal_gain_db

    normal_bgm = bgm_segment + normal_gain_db
    ducked_bgm = bgm_segment + ducked_gain_db
    total_len = len(bgm_segment)
    result = AudioSegment.empty()
    last_end = 0

    for s_ms, e_ms in speech_intervals:
        s_ms = max(0, min(int(s_ms), total_len))
        e_ms = max(s_ms, min(int(e_ms), total_len))
        if s_ms > last_end:
            result = result + normal_bgm[last_end:s_ms]
        if e_ms > s_ms:
            duck_part = ducked_bgm[s_ms:e_ms]
            if len(duck_part) > fade_ms * 2:
                duck_part = duck_part.fade_in(fade_ms).fade_out(fade_ms)
            result = result + duck_part
        last_end = e_ms

    if last_end < total_len:
        result = result + normal_bgm[last_end:total_len]

    return result


def stitch_broadcast_project(
    segments: list,
    output_path,
    out_format: str = "wav",
    default_pause_sec: float = 1.0,
    bg_music_path=None,
    bg_music_volume_db: float = -18.0,
    bg_music_loop: bool = True,
    bg_music_ducking: bool = True,
    bg_music_fade_in_ms: int = 1500,
    bg_music_fade_out_ms: int = 2000,
    intro_music_path=None,
    intro_music_vol_db: float = 0.0,
    outro_music_path=None,
    outro_music_vol_db: float = 0.0,
) -> dict:
    """Ghép nối danh sách các đoạn âm thanh và nhạc nền thành bản tin phát thanh hoàn chỉnh.
    Hỗ trợ WAV, MP3, thiết lập thời gian nghỉ giữa các đoạn, nhạc mở đầu, kết thúc,
    lặp lại nhạc nền và tự động hạ âm lượng nhạc nền khi có lời đọc (Auto-Ducking).
    """
    import os
    import warnings
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    from pathlib import Path
    from pydub import AudioSegment

    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    if not segments and not intro_music_path and not outro_music_path:
        raise ValueError("Danh sách đoạn phát thanh rỗng.")

    master = AudioSegment.empty()
    valid_count = 0
    speech_intervals = []

    # 1. Nhạc mở đầu chương trình (Intro Music)
    if intro_music_path and Path(intro_music_path).is_file():
        try:
            intro_clip = load_audio_segment_safe(intro_music_path)
            if abs(float(intro_music_vol_db)) > 0.01:
                intro_clip = intro_clip + float(intro_music_vol_db)
            master = master + intro_clip + AudioSegment.silent(duration=500)
            valid_count += 1
        except Exception as e:
            print(f"Lỗi nạp nhạc mở đầu: {e}")

    # 2. Các phân đoạn nội dung
    for idx, seg in enumerate(segments or []):
        stype = seg.get("type", "speech")
        if stype == "silence":
            dur_sec = float(seg.get("duration_sec", 1.0))
            if dur_sec > 0:
                master = master + AudioSegment.silent(duration=int(dur_sec * 1000))
                valid_count += 1
            continue

        fpath = seg.get("file_path")
        if not fpath or not Path(fpath).is_file():
            continue

        try:
            audio_clip = load_audio_segment_safe(fpath)
        except Exception as clip_err:
            print(f"Bỏ qua phân đoạn lỗi '{fpath}': {clip_err}")
            continue

        if audio_clip is None or len(audio_clip) == 0:
            continue

        gain = float(seg.get("gain_db", 0.0))
        fade_in = int(seg.get("fade_in_ms", 0))
        fade_out = int(seg.get("fade_out_ms", 0))
        audio_clip = apply_audio_gain_and_fade(audio_clip, gain, fade_in, fade_out)

        start_ms = len(master)
        master = master + audio_clip
        end_ms = len(master)

        if stype in ("speech", "lead_in", "news", "announcement"):
            speech_intervals.append((start_ms, end_ms))

        valid_count += 1

        pause_sec = float(seg.get("pause_after", default_pause_sec))
        if pause_sec > 0 and idx < len(segments) - 1:
            pause_clip = AudioSegment.silent(duration=int(pause_sec * 1000))
            master = master + pause_clip

    # 3. Nhạc kết thúc chương trình (Outro Music)
    if outro_music_path and Path(outro_music_path).is_file():
        try:
            outro_clip = load_audio_segment_safe(outro_music_path)
            if abs(float(outro_music_vol_db)) > 0.01:
                outro_clip = outro_clip + float(outro_music_vol_db)
            master = master + AudioSegment.silent(duration=300) + outro_clip
            valid_count += 1
        except Exception as e:
            print(f"Lỗi nạp nhạc kết thúc: {e}")

    if valid_count == 0 or len(master) == 0:
        raise ValueError("Không tìm thấy tệp âm thanh hợp lệ nào để ghép bản tin.")

    # 4. Xử lý lồng bài hát / nhạc nền (Background Music với Auto-Ducking)
    if bg_music_path and Path(bg_music_path).is_file():
        try:
            bg = load_audio_segment_safe(bg_music_path)
            if bg.frame_rate != master.frame_rate:
                bg = bg.set_frame_rate(master.frame_rate)
            if bg.channels != master.channels:
                bg = bg.set_channels(master.channels)

            if bg_music_loop and len(bg) < len(master):
                loops = int(len(master) / len(bg)) + 1
                bg = bg * loops
            bg = bg[:len(master)]

            target_ducked_db = float(bg_music_volume_db)
            target_normal_db = target_ducked_db + 8.0 # Tăng +8dB khi không có lời đọc

            if bg_music_ducking and speech_intervals:
                bg = apply_bgm_ducking(
                    bg,
                    speech_intervals,
                    normal_gain_db=target_normal_db,
                    ducked_gain_db=target_ducked_db,
                    fade_ms=300
                )
            else:
                bg = bg + target_ducked_db

            fade_in_len = min(int(bg_music_fade_in_ms), len(bg) // 4)
            fade_out_len = min(int(bg_music_fade_out_ms), len(bg) // 4)
            if fade_in_len > 0:
                bg = bg.fade_in(fade_in_len)
            if fade_out_len > 0:
                bg = bg.fade_out(fade_out_len)

            master = master.overlay(bg)
        except Exception as bg_err:
            print(f"Lỗi khi lồng nhạc nền: {bg_err}")
            raise RuntimeError(f"Lỗi khi lồng bài hát / nhạc nền '{Path(bg_music_path).name}': {bg_err}")

    # Xuất tệp
    fmt = out_format.lower().strip()
    if fmt == "mp3":
        master.export(str(out_p), format="mp3", bitrate="192k")
    else:
        master.export(str(out_p), format="wav")

    return {
        "success": True,
        "file_path": str(out_p),
        "duration_sec": round(len(master) / 1000.0, 2),
        "segments_count": valid_count,
    }


# ---------------------------------------------------------------- Audio Studio & Broadcast 2.0 Engine
def slice_audio(
    input_path,
    start_ms: int,
    end_ms: int,
    output_path,
    out_format: str = "wav",
) -> dict:
    """Cắt một phân đoạn âm thanh từ start_ms đến end_ms và lưu ra file mới.
    Phục vụ tính năng biên tập trong Audio Studio.
    """
    from pathlib import Path
    audio = load_audio_segment_safe(input_path)
    total_len = len(audio)

    s_ms = max(0, min(int(start_ms), total_len))
    e_ms = max(s_ms, min(int(end_ms), total_len)) if end_ms > 0 else total_len

    sliced = audio[s_ms:e_ms]
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    fmt = out_format.lower().strip()
    if fmt == "mp3":
        sliced.export(str(out_p), format="mp3", bitrate="192k")
    else:
        sliced.export(str(out_p), format="wav")

    return {
        "success": True,
        "file_path": str(out_p),
        "duration_sec": round(len(sliced) / 1000.0, 2),
        "start_ms": s_ms,
        "end_ms": e_ms,
    }


def apply_audio_gain_and_fade(
    audio_clip,
    gain_db: float = 0.0,
    fade_in_ms: int = 0,
    fade_out_ms: int = 0,
):
    """Điều chỉnh âm lượng (dB) và thêm hiệu ứng làm mờ đầu/cuối (fade in / fade out)."""
    if audio_clip is None or len(audio_clip) == 0:
        return audio_clip

    res = audio_clip
    if abs(gain_db) > 0.01:
        res = res + gain_db

    clip_len = len(res)
    if fade_in_ms > 0:
        actual_in = min(fade_in_ms, clip_len // 2)
        if actual_in > 0:
            res = res.fade_in(actual_in)

    if fade_out_ms > 0:
        actual_out = min(fade_out_ms, clip_len // 2)
        if actual_out > 0:
            res = res.fade_out(actual_out)

    return res


def mix_multitrack_timeline(tracks: list, master_duration_ms: int = None):
    """Trộn đa luồng âm thanh (Voice, Background Music, Jingle, Sound Effects)
    với vị trí xuất hiện (position_ms) và âm lượng từng luồng riêng biệt.
    Phục vụ Broadcast Studio 2.0 và Audio Studio.
    """
    from pydub import AudioSegment

    if not tracks:
        return AudioSegment.empty()

    # Xác định tổng độ dài cần thiết
    max_end = master_duration_ms or 0
    loaded_tracks = []

    for t in tracks:
        fpath = t.get("file_path")
        if not fpath:
            continue
        try:
            clip = load_audio_segment_safe(fpath)
            gain = float(t.get("gain_db", 0.0))
            fade_in = int(t.get("fade_in_ms", 0))
            fade_out = int(t.get("fade_out_ms", 0))
            clip = apply_audio_gain_and_fade(clip, gain, fade_in, fade_out)

            pos_ms = max(0, int(t.get("position_ms", 0)))
            track_end = pos_ms + len(clip)
            if track_end > max_end:
                max_end = track_end

            loaded_tracks.append((clip, pos_ms))
        except Exception as e:
            print(f"Bỏ qua track lỗi '{fpath}': {e}")
            continue

    if not loaded_tracks:
        return AudioSegment.empty()

    master = AudioSegment.silent(duration=max(100, max_end))
    for clip, pos in loaded_tracks:
        # Đồng bộ channel và sample rate
        if clip.frame_rate != master.frame_rate:
            clip = clip.set_frame_rate(master.frame_rate)
        if clip.channels != master.channels:
            clip = clip.set_channels(master.channels)
        master = master.overlay(clip, position=pos)

    return master


