"""Kịch bản kiểm thử toàn diện (Unit & Integration Smoke Tests) cho Voice Studio v3.8.
"""
import os
import sys
import time
import wave
import math
import tempfile
import unittest
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from backend.tts_engine import TTSEngine
from backend.audio_utils import (
    SAMPLE_RATE, split_pause_tags, apply_pron_dict, split_batch,
    format_srt_timestamp, parse_srt_timestamp, parse_subtitles,
    align_subtitles_for_dubbing, save_wav,
)
from backend.pron_dict import PronDict
from backend.history import History
from backend.app import app, validate_speed, validate_voice, engine


class TestVoiceStudioV38(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print("\n=== KIỂM THỬ TỰ ĐỘNG VOICE STUDIO v3.8 ===", flush=True)
        print("1. Khởi tạo TTSEngine VieNeu-TTS...", flush=True)
        cls.engine = engine
        cls.engine.ensure()
        cls.client = app.test_client()

        # Kích hoạt bản quyền kiểm thử để kiểm tra toàn bộ tính năng gốc
        from backend.license import license_manager, get_machine_id
        from tools.license_generator import create_license_key
        test_key = create_license_key(get_machine_id(), "30d")["key_string"]
        license_manager.activate(test_key)

    def test_01_voice_list_and_validation(self):
        print("2. Kiểm tra danh sách giọng và xác thực voice...", flush=True)
        voices = self.engine.list_voices()
        self.assertGreaterEqual(len(voices), 25, "Phải có ít nhất 25 giọng preset")
        
        # Test allowlist constraint
        preset_voices = [v for v in voices if not v.get("is_custom")]
        self.assertEqual(len(preset_voices), 25, "Danh sách giọng preset phải có chính xác 25 giọng theo allowlist")

        # Test valid voices
        self.assertTrue(self.engine.is_valid_voice("Hải Đăng"))
        self.assertTrue(self.engine.is_valid_voice("Mai Anh"))
        
        # Test fake / non-existent voice
        self.assertFalse(self.engine.is_valid_voice("Vân Mai"))
        self.assertFalse(self.engine.is_valid_voice("Giọng Không Tồn Tại"))
        
        # Test validate_voice helper
        self.assertEqual(validate_voice("Hải Đăng"), "Hải Đăng")
        with self.assertRaises(ValueError):
            validate_voice("Vân Mai")

    def test_02_speed_validation(self):
        print("3. Kiểm tra xác thực tốc độ đọc (speed 0.75x - 1.50x)...", flush=True)
        self.assertEqual(validate_speed(1.0), 1.0)
        self.assertEqual(validate_speed("0.75"), 0.75)
        self.assertEqual(validate_speed("1.50"), 1.50)
        self.assertEqual(validate_speed(None, default=1.0), 1.0)

        # Invalid speed values
        with self.assertRaises(ValueError):
            validate_speed(0.5)
        with self.assertRaises(ValueError):
            validate_speed(1.6)
        with self.assertRaises(ValueError):
            validate_speed("abc")
        with self.assertRaises(ValueError):
            validate_speed(float("nan"))
        with self.assertRaises(ValueError):
            validate_speed(float("inf"))

    def test_03_pause_tags_leading_middle_trailing(self):
        print("4. Kiểm tra phân tách thẻ nghỉ ở đầu, giữa, cuối và liên tiếp...", flush=True)
        # Leading pause tag
        parts1 = split_pause_tags("[nghỉ 2s] Xin chào")
        self.assertEqual(len(parts1), 2)
        self.assertEqual(parts1[0], ("", 2.0))
        self.assertEqual(parts1[1], ("Xin chào", 0.0))

        # Middle pause tag
        parts2 = split_pause_tags("Đồng chí [nghỉ 500ms] nghe rõ không")
        self.assertEqual(len(parts2), 2)
        self.assertEqual(parts2[0], ("Đồng chí", 0.5))
        self.assertEqual(parts2[1], ("nghe rõ không", 0.0))

        # Trailing pause tag
        parts3 = split_pause_tags("Hết câu [nghỉ 1s]")
        self.assertEqual(len(parts3), 1)
        self.assertEqual(parts3[0], ("Hết câu", 1.0))

        # Consecutive pause tags
        parts4 = split_pause_tags("[nghỉ 1s][nghỉ 2s] Bắt đầu")
        self.assertEqual(len(parts4), 2)
        self.assertEqual(parts4[0], ("", 3.0))

    def test_04_srt_timestamps(self):
        print("5. Kiểm tra định dạng mốc thời gian SRT...", flush=True)
        self.assertEqual(format_srt_timestamp(0.0), "00:00:00,000")
        self.assertEqual(format_srt_timestamp(65.432), "00:01:05,432")
        self.assertEqual(format_srt_timestamp(3661.005), "01:01:01,005")
        
        # Test round off overflow 999.6ms -> 1000ms -> +1 sec
        self.assertEqual(format_srt_timestamp(59.9996), "00:01:00,000")

    def test_05_history_management(self):
        print("6. Kiểm tra quản lý lịch sử và dung lượng ổ đĩa...", flush=True)
        with tempfile.TemporaryDirectory() as tmp_dir:
            h = History(out_dir=tmp_dir, index_path=Path(tmp_dir) / "hist.json")
            f1 = Path(tmp_dir) / "test1.wav"
            f1.write_bytes(b"0" * 1024)
            f2 = Path(tmp_dir) / "test1.mp3"
            f2.write_bytes(b"0" * 2048)

            item = h.add("Test text", "Hải Đăng", 1.0, f1, f2, kind="tts")
            self.assertEqual(item["size"], 3072)
            
            stats = h.get_stats()
            self.assertEqual(stats["count"], 1)
            self.assertEqual(stats["size_bytes"], 3072)

            # Test safe handling when file is deleted physically
            f1.unlink()
            stats_after = h.get_stats()
            self.assertEqual(stats_after["count"], 1)
            self.assertEqual(stats_after["size_bytes"], 2048)

    def test_06_flask_api_endpoints(self):
        print("7. Kiểm tra các endpoint API Flask Server...", flush=True)
        # Health check
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json["status"], "ok")
        self.assertEqual(res.json["app"], "T-TTS v1.0.1")

        # Model status endpoint
        res_st = self.client.get("/api/model/status")
        self.assertEqual(res_st.status_code, 200)
        self.assertIn("hardware", res_st.json)
        self.assertIn("config", res_st.json)

        # Model configure endpoint
        res_cfg = self.client.post("/api/model/configure", json={"device": "cpu", "precision": "int8"})
        self.assertEqual(res_cfg.status_code, 200)
        self.assertTrue(res_cfg.json["success"])

        # Voices list
        res = self.client.get("/voices")
        self.assertEqual(res.status_code, 200)
        self.assertIn("voices", res.json)

        # Generate single valid request
        res = self.client.post("/api/tts/generate", json={
            "text": "Kiểm thử API thành công",
            "voice_id": "Hải Đăng",
            "speed": 1.0,
            "format": "wav"
        })
        self.assertEqual(res.status_code, 200)
        if res.is_json:
            import base64
            b = base64.b64decode(res.json.get("audio_b64", ""))
            self.assertTrue(b.startswith(b"RIFF"))
        else:
            self.assertTrue(res.data.startswith(b"RIFF"))

        # Generate invalid voice request (must return HTTP 400 Bad Request)
        res_inv_voice = self.client.post("/api/tts/generate", json={
            "text": "Kiểm thử giọng sai",
            "voice_id": "Vân Mai",
            "speed": 1.0
        })
        self.assertEqual(res_inv_voice.status_code, 400)
        self.assertIn("không tồn tại", res_inv_voice.json["error"])

        # Generate invalid speed request (must return HTTP 400 Bad Request)
        res_inv_speed = self.client.post("/api/tts/generate", json={
            "text": "Kiểm thử tốc độ sai",
            "voice_id": "Hải Đăng",
            "speed": 2.5
        })
        self.assertEqual(res_inv_speed.status_code, 400)
        self.assertIn("nằm ngoài giới hạn", res_inv_speed.json["error"])


if __name__ == "__main__":
    unittest.main()

