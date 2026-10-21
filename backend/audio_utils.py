"""Tiện ích âm thanh: lưu WAV/MP3, time-stretch (WSOLA), thẻ nghỉ, từ điển, đọc/tạo SRT, lồng tiếng."""
import io
import re
import wave
import numpy as np

SAMPLE_RATE = 48000


# ---------------------------------------------------------------- WAV & MP3
def save_wav(path, audio, sr=SAMPLE_RATE):
    """Lưu numpy float32 [-1, 1] ra file WAV 48kHz 16-bit PCM standard."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.flatten()
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def wav_to_mp3(wav_path, mp3_path):
    """Chuyển WAV -> MP3 bằng imageio-ffmpeg hoặc pydub."""
    try:
        import imageio_ffmpeg
        import subprocess
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        res = subprocess.run(
            [exe, "-y", "-loglevel", "error", "-i", str(wav_path),
             "-codec:a", "libmp3lame", "-q:a", "4", str(mp3_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        return res.returncode == 0 and mp3_path.exists()
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
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
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
