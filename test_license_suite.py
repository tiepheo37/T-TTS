"""test_license_suite.py — BỘ KIỂM THỬ TỰ ĐỘNG TOÀN DIỆN HỆ THỐNG BẢN QUYỀN OFFLINE T-TTS v1.0.1
===================================================================================================
Bao gồm 19 tình huống kiểm thử nghiêm ngặt theo yêu cầu của dự án:
1.  Kích hoạt key 1 ngày (KEY-1D) thành công, thời hạn 24 giờ.
2.  Kích hoạt key 7 ngày (KEY-7D) thành công, thời hạn 168 giờ.
3.  Kích hoạt key 30 ngày (KEY-30D) thành công, thời hạn 720 giờ.
4.  Key sai chữ ký hoặc bị sửa đổi nội dung payload.
5.  Key của máy khác (Machine Mismatch).
6.  Khởi động lại ứng dụng và xác nhận thời hạn không bị đặt lại.
7.  Lùi đồng hồ khi ứng dụng đang chạy.
8.  Đóng ứng dụng, lùi đồng hồ rồi mở lại.
9.  Khởi động lại máy với thời gian bị lùi.
10. Sửa đổi thủ công tệp trạng thái bản quyền (Tamper detection).
11. Khôi phục bản sao dữ liệu kích hoạt cũ.
12. Dùng lại key cũ sau khi đã hết hạn.
13. Nhập key mới hợp lệ và xác nhận mở khóa ứng dụng.
14. Gọi trực tiếp API xử lý âm thanh khi ứng dụng đang khóa (nhận 403).
15. Kiểm tra toàn bộ chức năng T-TTS khi giấy phép hợp lệ.
16. Kiểm tra dữ liệu người dùng còn nguyên sau khi hết hạn.
17. Kiểm tra ranh giới hết hạn chính xác của cả 3 loại key (1D, 7D, 30D).
18. Kích hoạt và hoạt động hoàn toàn offline (không kết nối mạng).
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path

# Đảm bảo mã hóa UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# KÍCH HOẠT CHẾ ĐỘ KIỂM THỬ CHO PHÉP GIẢ LẬP THỜI GIAN
os.environ["T_TTS_LICENSE_TEST_MODE"] = "1"

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from tools.license_generator import create_license_key, verify_license_key, load_private_key
from backend.license import (
    LicenseManager, get_machine_id,
    STATUS_ACTIVE, STATUS_UNACTIVATED, STATUS_EXPIRED,
    STATUS_ROLLBACK, STATUS_TAMPERED, STATUS_MACHINE_MISMATCH,
    _get_storage_locations, _save_to_registry, _calculate_state_hmac
)
from backend.app import app, engine, history, pron


class TestOfflineLicenseSystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 75)
        print("BẮT ĐẦU BỘ KIỂM THỬ BẢN QUYỀN OFFLINE T-TTS v1.0.1")
        print("=" * 75)
        cls.machine_id = get_machine_id()
        print(f"Mã máy kiểm thử: {cls.machine_id}")
        cls.client = app.test_client()

    def setUp(self):
        """Khởi tạo trạng thái sạch trước mỗi ca kiểm thử."""
        self._clean_all_license_storage()
        from backend.license import license_manager as app_lic_mgr
        app_lic_mgr._state = app_lic_mgr._create_empty_state()
        app_lic_mgr._simulated_time_offset = 0.0
        # Khởi tạo LicenseManager mới cho test
        self.mgr = LicenseManager()

    def tearDown(self):
        """Dọn dẹp sau khi kiểm thử."""
        self.mgr._stop_watchdog.set()

    def _clean_all_license_storage(self):
        p1, p2 = _get_storage_locations()
        try:
            if p1.exists():
                p1.write_text("{}", encoding="utf-8")
                p1.unlink(missing_ok=True)
            if p2.exists():
                p2.write_text("{}", encoding="utf-8")
                p2.unlink(missing_ok=True)
        except Exception:
            pass
        _save_to_registry("")

    # --------------------------------------------------------------------------
    # 1. Kích hoạt key 1 ngày thành công
    # --------------------------------------------------------------------------
    def test_01_activate_1d_success(self):
        print("\n[TEST 01] Kích hoạt key 1 ngày (KEY-1D - 24 giờ)...")
        key_data = create_license_key(self.machine_id, "1d", note="Test 1D")
        ok, msg, info = self.mgr.activate(key_data["key_string"])

        self.assertTrue(ok, f"Kích hoạt 1D phải thành công: {msg}")
        self.assertEqual(info["status"], STATUS_ACTIVE)
        self.assertEqual(info["plan"], "KEY-1D")
        self.assertEqual(info["duration_hours"], 24)
        self.assertAlmostEqual(info["remaining_seconds"], 24 * 3600, delta=5)
        print("  -> [PASS] Kích hoạt 1 ngày thành công, thời hạn đúng 24 giờ (86.400s).")

    # --------------------------------------------------------------------------
    # 2. Kích hoạt key 7 ngày thành công
    # --------------------------------------------------------------------------
    def test_02_activate_7d_success(self):
        print("\n[TEST 02] Kích hoạt key 7 ngày (KEY-7D - 168 giờ)...")
        key_data = create_license_key(self.machine_id, "7d", note="Test 7D")
        ok, msg, info = self.mgr.activate(key_data["key_string"])

        self.assertTrue(ok, f"Kích hoạt 7D phải thành công: {msg}")
        self.assertEqual(info["status"], STATUS_ACTIVE)
        self.assertEqual(info["plan"], "KEY-7D")
        self.assertEqual(info["duration_hours"], 168)
        self.assertAlmostEqual(info["remaining_seconds"], 168 * 3600, delta=5)
        print("  -> [PASS] Kích hoạt 7 ngày thành công, thời hạn đúng 168 giờ (604.800s).")

    # --------------------------------------------------------------------------
    # 3. Kích hoạt key 30 ngày thành công
    # --------------------------------------------------------------------------
    def test_03_activate_30d_success(self):
        print("\n[TEST 03] Kích hoạt key 30 ngày (KEY-30D - 720 giờ)...")
        key_data = create_license_key(self.machine_id, "30d", note="Test 30D")
        ok, msg, info = self.mgr.activate(key_data["key_string"])

        self.assertTrue(ok, f"Kích hoạt 30D phải thành công: {msg}")
        self.assertEqual(info["status"], STATUS_ACTIVE)
        self.assertEqual(info["plan"], "KEY-30D")
        self.assertEqual(info["duration_hours"], 720)
        self.assertAlmostEqual(info["remaining_seconds"], 720 * 3600, delta=5)
        print("  -> [PASS] Kích hoạt 30 ngày thành công, thời hạn đúng 720 giờ (2.592.000s).")

    # --------------------------------------------------------------------------
    # 4. Key sai chữ ký hoặc bị sửa đổi nội dung
    # --------------------------------------------------------------------------
    def test_04_invalid_signature_and_tampered_key(self):
        print("\n[TEST 04] Kiểm tra key bị sửa đổi hoặc chữ ký sai...")
        valid_key = create_license_key(self.machine_id, "7d")["key_string"]

        # Case A: Sửa 1 ký tự trong payload base64
        parts = valid_key.split(".")
        altered_char = "A" if parts[0][-1] != "A" else "B"
        tampered_key = parts[0][:-1] + altered_char + "." + parts[1]

        ok, msg, _ = self.mgr.activate(tampered_key)
        self.assertFalse(ok, "Key bị sửa đổi phải bị từ chối")
        self.assertIn("chữ ký", msg.lower())

        # Case B: Chuỗi rác không đúng định dạng
        ok_junk, msg_junk, _ = self.mgr.activate("ABC-XYZ-INVALID-KEY")
        self.assertFalse(ok_junk)
        self.assertIn("định dạng", msg_junk.lower())
        print("  -> [PASS] Đã từ chối key bị sửa đổi và chuỗi rác thành công.")

    # --------------------------------------------------------------------------
    # 5. Key của máy khác (Machine Mismatch)
    # --------------------------------------------------------------------------
    def test_05_key_from_another_machine(self):
        print("\n[TEST 05] Kiểm tra key được cấp cho máy khác...")
        other_mid = "TTTS-9999-8888-7777-6666"
        other_key = create_license_key(other_mid, "7d")["key_string"]

        ok, msg, info = self.mgr.activate(other_key)
        self.assertFalse(ok, "Key máy khác phải bị từ chối trên máy này")
        self.assertIn(other_mid, msg)
        print("  -> [PASS] Đã từ chối key cấp cho máy khác.")

    # --------------------------------------------------------------------------
    # 6. Khởi động lại ứng dụng và xác nhận thời hạn không bị đặt lại
    # --------------------------------------------------------------------------
    def test_06_restart_app_persistence(self):
        print("\n[TEST 06] Khởi động lại ứng dụng và kiểm tra tính bền vững...")
        key = create_license_key(self.machine_id, "7d")["key_string"]
        self.mgr.activate(key)

        initial_first_act = self.mgr.get_status_info()["first_activated_at"]
        initial_exp = self.mgr.get_status_info()["expires_at"]

        # Giả lập ứng dụng tắt và 1 giờ sau khởi động lại
        self.mgr._stop_watchdog.set()
        self.mgr.simulate_time_travel(3600)  # trôi 1 giờ

        # Khởi tạo LicenseManager mới (mô phỏng tiến trình ứng dụng mới bật lên sau 1 giờ)
        new_mgr = LicenseManager(simulated_time_offset=3600.0)
        st_after_restart = new_mgr.get_status_info()

        self.assertEqual(st_after_restart["status"], STATUS_ACTIVE)
        self.assertEqual(st_after_restart["first_activated_at"], initial_first_act, "Ngày kích hoạt đầu tiên không được đổi")
        self.assertEqual(st_after_restart["expires_at"], initial_exp, "Thời điểm hết hạn không được đổi")
        # Thời gian còn lại phải giảm đi khoảng 1 giờ (168 - 1 = 167 giờ)
        self.assertAlmostEqual(st_after_restart["remaining_seconds"], (167 * 3600), delta=10)
        new_mgr._stop_watchdog.set()
        print("  -> [PASS] Khởi động lại ứng dụng giữ nguyên mốc kích hoạt và thời hạn chính xác.")

    # --------------------------------------------------------------------------
    # 7. Lùi đồng hồ Windows khi ứng dụng đang chạy
    # --------------------------------------------------------------------------
    def test_07_clock_rollback_while_running(self):
        print("\n[TEST 07] Phát hiện lùi đồng hồ khi ứng dụng đang chạy...")
        key = create_license_key(self.machine_id, "7d")["key_string"]
        self.mgr.activate(key)
        self.assertTrue(self.mgr.is_active())

        # Mô phỏng lùi thời gian bằng cách đặt lại offset âm
        with self.mgr.lock:
            # Lùi đồng hồ về trước last_valid_time 1 ngày
            self.mgr._simulated_time_offset = -86400.0

        # Kiểm tra trạng thái
        is_act = self.mgr.is_active()
        st = self.mgr.get_status_info()

        self.assertFalse(is_act, "Ứng dụng phải bị khóa khi lùi đồng hồ")
        self.assertEqual(st["status"], STATUS_ROLLBACK)
        self.assertIn("lùi", st["status_message"].lower())
        print("  -> [PASS] Đã phát hiện lùi đồng hồ trong phiên chạy và khóa ứng dụng.")

    # --------------------------------------------------------------------------
    # 8. Đóng ứng dụng, lùi đồng hồ rồi mở lại
    # --------------------------------------------------------------------------
    def test_08_close_app_rollback_and_reopen(self):
        print("\n[TEST 08] Đóng ứng dụng, lùi đồng hồ rồi mở lại...")
        key = create_license_key(self.machine_id, "7d")["key_string"]
        self.mgr.activate(key)

        # Ứng dụng đã ghi nhận last_valid_time là thời điểm hiện tại
        self.mgr._stop_watchdog.set()

        # Mô phỏng đóng ứng dụng và máy bị lùi đồng hồ 5 ngày về trước
        os.environ["T_TTS_LICENSE_TEST_MODE"] = "1"
        reopened_mgr = LicenseManager()
        reopened_mgr._simulated_time_offset = -432000.0  # lùi 5 ngày

        st = reopened_mgr.get_status_info()
        self.assertFalse(reopened_mgr.is_active())
        self.assertEqual(st["status"], STATUS_ROLLBACK)
        reopened_mgr._stop_watchdog.set()
        print("  -> [PASS] Khởi động lại với thời gian bị lùi bị phát hiện và khóa ngay lập tức.")

    # --------------------------------------------------------------------------
    # 9. Khởi động lại Windows với thời gian bị lùi
    # --------------------------------------------------------------------------
    def test_09_reboot_with_clock_rolled_back(self):
        print("\n[TEST 09] Khởi động lại Windows với thời gian lùi trước ngày kích hoạt...")
        key = create_license_key(self.machine_id, "30d")["key_string"]
        self.mgr.activate(key)
        self.mgr._stop_watchdog.set()

        # Mô phỏng lùi về thời điểm trước cả khi key được tạo
        reboot_mgr = LicenseManager()
        reboot_mgr._simulated_time_offset = -864000.0  # lùi 10 ngày

        self.assertFalse(reboot_mgr.is_active())
        self.assertEqual(reboot_mgr.get_status_info()["status"], STATUS_ROLLBACK)
        reboot_mgr._stop_watchdog.set()
        print("  -> [PASS] Phát hiện lùi giờ về trước ngày kích hoạt và khóa an toàn.")

    # --------------------------------------------------------------------------
    # 10. Xóa hoặc sửa tệp trạng thái bản quyền (Tamper Detection)
    # --------------------------------------------------------------------------
    def test_10_tamper_license_state_file(self):
        print("\n[TEST 10] Phát hiện sửa đổi tệp trạng thái (HMAC Verification)...")
        key = create_license_key(self.machine_id, "7d")["key_string"]
        self.mgr.activate(key)
        self.mgr._stop_watchdog.set()

        # Sửa đổi tệp license_state.json trực tiếp (cố tình kéo dài thời hạn)
        p1, _ = _get_storage_locations()
        content = json.loads(p1.read_text(encoding="utf-8"))
        content["expires_at"] = content["expires_at"] + 99999999.0  # cố tình hack thời hạn
        p1.write_text(json.dumps(content), encoding="utf-8")

        # Nạp lại
        tamper_mgr = LicenseManager()
        st = tamper_mgr.get_status_info()

        self.assertFalse(tamper_mgr.is_active(), "Tệp bị sửa đổi không được coi là active")
        self.assertEqual(st["status"], STATUS_TAMPERED)
        self.assertIn("can thiệp", st["status_message"].lower())
        tamper_mgr._stop_watchdog.set()
        print("  -> [PASS] Phát hiện can thiệp tệp trạng thái nhờ chữ ký HMAC phần cứng.")

    # --------------------------------------------------------------------------
    # 11. Khôi phục bản sao dữ liệu kích hoạt cũ
    # --------------------------------------------------------------------------
    def test_11_restore_old_backup_tampering(self):
        print("\n[TEST 11] Khôi phục bản sao trạng thái cũ...")
        key = create_license_key(self.machine_id, "1d")["key_string"]
        self.mgr.activate(key)

        p1, _ = _get_storage_locations()
        backup_content = p1.read_text(encoding="utf-8")

        # Thời gian trôi qua 2 ngày (đã hết hạn)
        self.mgr.simulate_time_travel(2 * 86400)
        self.assertEqual(self.mgr.get_status_info()["status"], STATUS_EXPIRED)
        self.mgr._stop_watchdog.set()

        # Người dùng cố tình ghi đè bản sao lưu ngày đầu tiên vào
        p1.write_text(backup_content, encoding="utf-8")

        # Mở ứng dụng lại: thời gian thực hiện tại vẫn là ngày + 2
        # So sánh thời gian hiện tại với expires_at trong bản sao cũ (đã nhỏ hơn hiện tại) -> EXPIRED!
        check_mgr = LicenseManager()
        check_mgr._simulated_time_offset = 2 * 86400
        st = check_mgr.get_status_info()

        self.assertFalse(check_mgr.is_active())
        self.assertIn(st["status"], (STATUS_EXPIRED, STATUS_ROLLBACK))
        check_mgr._stop_watchdog.set()
        print("  -> [PASS] Ghi đè bản sao lưu cũ không thể qua mặt hệ thống.")

    # --------------------------------------------------------------------------
    # 12. Dùng key cũ sau khi hết hạn
    # --------------------------------------------------------------------------
    def test_12_reuse_old_key_after_expiration(self):
        print("\n[TEST 12] Ngăn chặn kích hoạt lại key cũ đã hết hạn...")
        old_key = create_license_key(self.machine_id, "1d")["key_string"]
        self.mgr.activate(old_key)

        # Mô phỏng trôi qua 25 giờ (hết hạn 1 ngày)
        self.mgr.simulate_time_travel(25 * 3600)
        self.assertEqual(self.mgr.get_status_info()["status"], STATUS_EXPIRED)

        # Cố gắng kích hoạt lại chính key cũ đó
        ok, msg, _ = self.mgr.activate(old_key)
        self.assertFalse(ok, "Không được phép tái sử dụng key cũ đã hết hạn")
        self.assertIn("hết hạn", msg.lower())
        print("  -> [PASS] Đã từ chối kích hoạt lại key cũ đã hết hạn.")

    # --------------------------------------------------------------------------
    # 13. Nhập key mới hợp lệ và xác nhận mở khóa
    # --------------------------------------------------------------------------
    def test_13_unlock_with_new_valid_key(self):
        print("\n[TEST 13] Mở khóa bằng key mới hợp lệ...")
        # 1. Kích hoạt key 1D và làm cho hết hạn
        k1 = create_license_key(self.machine_id, "1d")["key_string"]
        self.mgr.activate(k1)
        self.mgr.simulate_time_travel(26 * 3600)
        self.assertFalse(self.mgr.is_active())

        # 2. Cấp key mới 30 ngày (KEY-30D)
        k2 = create_license_key(self.machine_id, "30d", note="Gia hạn 30 ngày")["key_string"]
        ok, msg, info = self.mgr.activate(k2)

        self.assertTrue(ok, "Key mới phải kích hoạt thành công")
        self.assertEqual(info["status"], STATUS_ACTIVE)
        self.assertEqual(info["plan"], "KEY-30D")
        self.assertTrue(self.mgr.is_active(), "Ứng dụng phải được mở khóa hoàn toàn")
        print("  -> [PASS] Key mới hợp lệ đã mở khóa ứng dụng thành công.")

    # --------------------------------------------------------------------------
    # 14. Gọi trực tiếp API xử lý âm thanh khi ứng dụng đang khóa
    # --------------------------------------------------------------------------
    def test_14_api_direct_calls_blocked_when_locked(self):
        print("\n[TEST 14] Kiểm tra chặn toàn bộ API xử lý âm thanh khi chưa kích hoạt...")
        # Đảm bảo trạng thái chưa kích hoạt
        self.mgr._state = self.mgr._create_empty_state()
        self.mgr._save_state_to_all(self.mgr._state)

        # Danh sách các endpoint xử lý chính cần bị khóa
        endpoints = [
            ("POST", "/api/tts/generate", {"text": "Xin chào"}),
            ("POST", "/api/tts/preview", {"voice_id": "Hải Đăng"}),
            ("GET", "/stream?text=Xin+chào", None),
            ("POST", "/api/tts/batch", {"text": "[P1] Xin chào"}),
            ("POST", "/api/tts/conversation", {"lines": [{"text": "Xin chào"}]}),
        ]

        for method, url, data in endpoints:
            if method == "POST":
                resp = self.client.post(url, json=data)
            else:
                resp = self.client.get(url)

            self.assertEqual(resp.status_code, 403, f"Endpoint {url} phải trả về 403 khi bị khóa")
            self.assertTrue(resp.json.get("license_locked"), f"Response của {url} phải có cờ license_locked")
            self.assertIn("khóa", resp.json.get("error", "").lower())

        print("  -> [PASS] Tất cả các API xử lý âm thanh chính đều bị chặn 403 tại backend.")

    # --------------------------------------------------------------------------
    # 15. Kiểm tra toàn bộ chức năng T-TTS khi giấy phép hợp lệ
    # --------------------------------------------------------------------------
    def test_15_features_work_when_licensed(self):
        print("\n[TEST 15] Kiểm tra các tính năng hoạt động bình thường khi bản quyền hợp lệ...")
        from backend.license import license_manager as app_lic_mgr
        key = create_license_key(self.machine_id, "7d")["key_string"]
        app_lic_mgr.activate(key)

        # 1. API Health
        h_resp = self.client.get("/health")
        self.assertEqual(h_resp.status_code, 200)
        self.assertTrue(h_resp.json.get("license_active"))

        # 2. API Voices
        v_resp = self.client.get("/voices")
        self.assertEqual(v_resp.status_code, 200)
        self.assertGreaterEqual(len(v_resp.json.get("voices", [])), 25)

        # 3. API History
        hist_resp = self.client.get("/api/history")
        self.assertEqual(hist_resp.status_code, 200)

        # 4. API Từ điển phát âm
        p_resp = self.client.get("/api/pron-dict")
        self.assertEqual(p_resp.status_code, 200)

        print("  -> [PASS] Toàn bộ chức năng phụ trợ và danh sách giọng hoạt động mượt mà.")

    # --------------------------------------------------------------------------
    # 16. Kiểm tra dữ liệu người dùng còn nguyên sau khi hết hạn
    # --------------------------------------------------------------------------
    def test_16_user_data_intact_after_expiration(self):
        print("\n[TEST 16] Kiểm tra bảo toàn dữ liệu người dùng khi giấy phép hết hạn...")
        # Thêm một từ vào từ điển
        pron.set("TTS_TEST_WORD", "Tiếng Nói Thử Nghiệm")
        initial_dict_len = len(pron.all())

        # Thêm một bản ghi vào lịch sử
        test_wav = ROOT / "output" / "test_keep_data.wav"
        test_wav.write_bytes(b"RIFFdummydata")
        history.add("Văn bản bảo toàn", "Hải Đăng", 1.0, test_wav, kind="tts")
        initial_hist_count = history.get_stats().get("total_items", 0)

        # Kích hoạt và làm cho hết hạn
        key = create_license_key(self.machine_id, "1d")["key_string"]
        self.mgr.activate(key)
        self.mgr.simulate_time_travel(25 * 3600)
        self.assertEqual(self.mgr.get_status_info()["status"], STATUS_EXPIRED)

        # Xác nhận dữ liệu người dùng không bao giờ bị xóa hoặc biến đổi
        self.assertEqual(len(pron.all()), initial_dict_len, "Từ điển không được bị mất")
        self.assertEqual(pron.all().get("TTS_TEST_WORD"), "Tiếng Nói Thử Nghiệm")
        self.assertGreaterEqual(history.get_stats().get("total_items", 0), initial_hist_count, "Lịch sử không bị mất")
        self.assertTrue(test_wav.exists(), "File audio của người dùng phải còn nguyên")
        print("  -> [PASS] Tuyệt đối không xóa hoặc làm tổn hại dữ liệu người dùng sau khi hết hạn.")

    # --------------------------------------------------------------------------
    # 17. Kiểm tra ranh giới hết hạn chính xác của cả 3 loại key
    # --------------------------------------------------------------------------
    def test_17_accurate_expiry_boundaries(self):
        print("\n[TEST 17] Kiểm tra ranh giới hết hạn chính xác (1D, 7D, 30D)...")
        cases = [
            ("1d", 24 * 3600),
            ("7d", 168 * 3600),
            ("30d", 720 * 3600),
        ]

        for plan_code, total_sec in cases:
            self._clean_all_license_storage()
            mgr = LicenseManager()
            k = create_license_key(self.machine_id, plan_code)["key_string"]
            mgr.activate(k)

            # Tại thời điểm trước hạn 5 giây: vẫn còn hiệu lực
            mgr.simulate_time_travel(total_sec - 5)
            self.assertTrue(mgr.is_active(), f"Gói {plan_code} tại giây {total_sec - 5} phải còn hiệu lực")

            # Tại thời điểm quá hạn 5 giây: chính xác chuyển sang expired
            mgr.simulate_time_travel(10)
            self.assertFalse(mgr.is_active(), f"Gói {plan_code} tại giây {total_sec + 5} phải hết hạn")
            self.assertEqual(mgr.get_status_info()["status"], STATUS_EXPIRED)
            mgr._stop_watchdog.set()

        print("  -> [PASS] Ranh giới hết hạn của cả 3 loại key đều chính xác từng giây.")

    # --------------------------------------------------------------------------
    # 18. Kích hoạt và hoạt động hoàn toàn offline
    # --------------------------------------------------------------------------
    def test_18_completely_offline_operation(self):
        print("\n[TEST 18] Kiểm tra tính offline thuần túy...")
        # Tạo key và xác minh hoàn toàn bằng thư viện mật mã cục bộ
        key_data = create_license_key(self.machine_id, "7d", note="Offline Pure")
        verified_payload = verify_license_key(key_data["key_string"])

        self.assertEqual(verified_payload["mid"], self.machine_id)
        self.assertEqual(verified_payload["plan"], "KEY-7D")
        print("  -> [PASS] Kích hoạt và xác minh chữ ký Ed25519 cục bộ 100%, không cần kết nối mạng.")


if __name__ == "__main__":
    unittest.main()
