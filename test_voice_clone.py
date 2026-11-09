"""Kiểm thử toàn diện chức năng nhân bản giọng nói (Voice Cloning) trong T-TTS v1.0.1.

Bao gồm:
1. Dữ liệu rỗng (0 bytes).
2. Dữ liệu sai định dạng / tệp hỏng.
3. Dữ liệu âm thanh WebM/Opus từ MediaRecorder của trình duyệt -> chuyển đổi WAV PCM 16-bit 44.1kHz mono.
4. Thời lượng âm thanh quá ngắn (< 3 giây) -> báo lỗi tiếng Việt.
5. Tên giọng có dấu tiếng Việt: "Tiệp" -> tạo clone_Tiệp.wav và đăng ký thành công.
6. Tổng hợp âm thanh (TTS inference) bằng chính giọng "Tiệp" vừa đăng ký.
7. Kiểm tra độ bền vững (persistence): khởi động lại TTSEngine, kiểm tra giọng "Tiệp" vẫn tồn tại và tạo được audio.
8. Kiểm tra xóa giọng nhân bản.
"""
import io
import os
import sys
import json
import wave
import shutil
import unittest
import numpy as np
from pathlib import Path

# Đảm bảo import đúng backend
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from backend.storage import init_storage
from backend.audio_utils import validate_and_convert_reference_audio, save_wav
from backend.tts_engine import TTSEngine
from backend.app import app


class TestVoiceClone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = init_storage()
        cls.upload_dir = cls.storage["upload_dir"]
        cls.data_dir = cls.storage["data_dir"]
        cls.client = app.test_client()

        # Tạo file WebM giả lập và WAV giả lập bằng ffmpeg
        import imageio_ffmpeg
        import subprocess
        cls.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

        # Tạo file WebM Opus thời lượng 6 giây (hợp lệ)
        cls.sample_webm = ROOT / "scratch" / "test_simulated_browser.webm"
        cls.sample_webm.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            cls.ffmpeg, "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
            "-c:a", "libopus", "-b:a", "64k",
            str(cls.sample_webm)
        ], check=True)

        # Tạo file WebM quá ngắn (1.5 giây)
        cls.short_webm = ROOT / "scratch" / "test_short.webm"
        subprocess.run([
            cls.ffmpeg, "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
            "-c:a", "libopus", "-b:a", "64k",
            str(cls.short_webm)
        ], check=True)

    def test_01_empty_data(self):
        """Kiểm tra xử lý khi dữ liệu thu âm bị rỗng."""
        target_wav = self.upload_dir / "test_empty.wav"
        with self.assertRaises(ValueError) as ctx:
            validate_and_convert_reference_audio(b"", target_wav)
        self.assertIn("rỗng", str(ctx.exception).lower())

        # Test qua HTTP API
        data = {
            "name": "Tiệp",
            "consent": "yes",
            "audio": (io.BytesIO(b""), "mic_recording.wav"),
        }
        res = self.client.post("/api/voice-clone", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)
        self.assertIn("rỗng", res.get_json()["error"].lower())

    def test_02_corrupted_data(self):
        """Kiểm tra xử lý khi tệp âm thanh bị hỏng / không nhận dạng được."""
        target_wav = self.upload_dir / "test_corrupt.wav"
        corrupted_bytes = b"RIFF" + b"\x00" * 200 + b"random_corrupted_payload"
        with self.assertRaises(ValueError) as ctx:
            validate_and_convert_reference_audio(corrupted_bytes, target_wav)
        self.assertTrue(len(str(ctx.exception)) > 0)

        # Test qua HTTP API
        data = {
            "name": "Tiệp",
            "consent": "yes",
            "audio": (io.BytesIO(corrupted_bytes), "mic_recording.wav"),
        }
        res = self.client.post("/api/voice-clone", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)

    def test_03_short_audio(self):
        """Kiểm tra từ chối tệp thu âm quá ngắn (< 3 giây)."""
        target_wav = self.upload_dir / "test_short.wav"
        with self.assertRaises(ValueError) as ctx:
            validate_and_convert_reference_audio(self.short_webm.read_bytes(), target_wav, min_duration=3.0)
        self.assertIn("quá ngắn", str(ctx.exception))

    def test_04_webm_to_wav_conversion(self):
        """Kiểm tra chuyển đổi thành công WebM từ MediaRecorder sang WAV PCM 16-bit 44.1kHz mono."""
        target_wav = self.upload_dir / "test_converted.wav"
        out_path, dur, sr = validate_and_convert_reference_audio(self.sample_webm.read_bytes(), target_wav)
        self.assertTrue(out_path.exists())
        self.assertEqual(sr, 44100)
        self.assertGreaterEqual(dur, 5.0)

        with wave.open(str(out_path), "rb") as w:
            self.assertEqual(w.getnchannels(), 1)
            self.assertEqual(w.getsampwidth(), 2)
            self.assertEqual(w.getframerate(), 44100)
        out_path.unlink(missing_ok=True)

    def test_05_voice_clone_vietnamese_name_and_api(self):
        """Kiểm tra nhân bản giọng với tên có dấu tiếng Việt 'Tiệp' qua API đầy đủ."""
        # Chuẩn bị dữ liệu mô phỏng chính xác client gửi lên
        with open(self.sample_webm, "rb") as f_webm:
            data = {
                "name": "Tiệp",
                "consent": "yes",
                "audio": (f_webm, "mic_recording.webm"),
            }
            res = self.client.post("/api/voice-clone", data=data, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200, msg=f"API error: {res.get_json()}")
        resp_json = res.get_json()
        self.assertTrue(resp_json.get("ok"))
        self.assertEqual(resp_json.get("voice_id"), "Tiệp")

        # Kiểm tra file đã được lưu tại upload_dir
        expected_wav = self.upload_dir / "clone_Tiệp.wav"
        self.assertTrue(expected_wav.exists(), msg=f"File {expected_wav} phải tồn tại trên đĩa")

        # Kiểm tra API /voices có chứa giọng "Tiệp"
        res_voices = self.client.get("/voices")
        self.assertEqual(res_voices.status_code, 200)
        voices = res_voices.get_json().get("voices", [])
        custom_ids = [v["id"] for v in voices if v.get("is_custom")]
        self.assertIn("Tiệp", custom_ids)

    def test_06_synthesize_with_cloned_voice(self):
        """Kiểm tra tổng hợp giọng nói bằng chính giọng vừa nhân bản 'Tiệp'."""
        data = {
            "text": "Chào bạn, đây là giọng nói thử nghiệm được nhân bản của Tiệp.",
            "voice_id": "Tiệp",
            "speed": 1.0,
        }
        res = self.client.post("/api/tts/generate", json=data)
        self.assertEqual(res.status_code, 200, msg=f"Synthesize error: {res.get_json()}")
        resp_json = res.get_json()
        self.assertTrue(resp_json.get("success"))
        self.assertIn("item_id", resp_json)
        self.assertGreater(resp_json.get("duration", 0), 0.5)

    def test_07_persistence_after_engine_reload(self):
        """Kiểm tra tính bền vững: khởi động lại Engine, giọng 'Tiệp' vẫn được phục hồi tự động."""
        custom_file = self.data_dir / "custom_voices.json"
        self.assertTrue(custom_file.exists(), "Tệp custom_voices.json phải tồn tại")
        records = json.loads(custom_file.read_text(encoding="utf-8"))
        self.assertIn("Tiệp", records)
        self.assertIsNotNone(records["Tiệp"].get("speaker_emb"))

        # Khởi tạo engine mới hoàn toàn
        new_eng = TTSEngine(mode="v3turbo", precision="int8", device="cpu")
        new_eng.load()
        voices = [v["id"] for v in new_eng.list_voices() if v.get("is_custom")]
        self.assertIn("Tiệp", voices)

        # Tổng hợp bằng engine mới
        audio, sr = new_eng.synthesize("Xin chào lần thứ hai từ giọng Tiệp.", voice="Tiệp")
        self.assertGreater(len(audio), 0)
        self.assertEqual(sr, 48000)

    def test_08_delete_cloned_voice(self):
        """Kiểm tra xóa giọng nhân bản qua API DELETE /api/voice-clone/<name>."""
        res = self.client.delete("/api/voice-clone/Tiệp")
        self.assertEqual(res.status_code, 200)

        # Kiểm tra lại /voices không còn "Tiệp"
        res_voices = self.client.get("/voices")
        custom_ids = [v["id"] for v in res_voices.get_json().get("voices", []) if v.get("is_custom")]
        self.assertNotIn("Tiệp", custom_ids)


if __name__ == "__main__":
    unittest.main()
