"""test_comprehensive_suite.py — BỘ KIỂM THỬ TỰ ĐỘNG TOÀN DIỆN T-TTS v1.0.1
========================================================================
Kiểm thử chi tiết theo đúng các tiêu chí của Phần XIII:
A. Kiến trúc & Loại bỏ Localhost
B. Kiểm thử tạo giọng (VieNeu-TTS v3 Turbo ONNX CPU)
C. Kiểm thử bản quyền (5 thời hạn, chữ ký Ed25519, tính toàn vẹn)
D. Kiểm thử nhân bản giọng & Quản lý giọng
E. Kiểm thử xử lý hàng loạt & Cách ly lỗi
F. Kiểm thử bảo toàn dữ liệu & Lịch sử
"""

import os
import sys
import time
import wave
import json
import socket
import calendar
import datetime
from pathlib import Path

# Đảm bảo mã hóa UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
for p in [str(ROOT), str(ROOT / "backend"), str(ROOT / "gui"), str(ROOT / "tools")]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ["T_TTS_LICENSE_TEST_MODE"] = "1"

test_results = {}


def record_result(category: str, test_name: str, passed: bool, details: str = ""):
    key = f"{category} :: {test_name}"
    status = "ĐẠT (PASS)" if passed else "KHÔNG ĐẠT (FAIL)"
    test_results[key] = {"passed": passed, "status": status, "details": details}
    icon = "✅" if passed else "❌"
    print(f"[{icon}] {key} -> {status} {details and f'({details})'}", flush=True)


# ==============================================================================
# PHẦN 1: KIỂM THỬ LOẠI BỎ LOCALHOST & TRÌNH DUYỆT (PHẦN III & VII)
# ==============================================================================
def test_architecture_and_localhost_removal():
    print("\n" + "=" * 70)
    print("PHẦN 1: KIỂM THỬ LOẠI BỎ LOCALHOST, FLASK & CHROME APP MODE")
    print("=" * 70)

    # 1. Kiểm tra desktop_main.py không chứa app.run(), make_server(), hoặc chrome.exe
    desktop_code = (ROOT / "desktop_main.py").read_text(encoding="utf-8")

    no_flask_server = "make_server" not in desktop_code and "app.run" not in desktop_code
    record_result("Kiến Trúc", "Không khởi động Flask server trong desktop_main", no_flask_server)

    no_chrome_app = "--app=" not in desktop_code and "chrome.exe" not in desktop_code
    record_result("Kiến Trúc", "Không sử dụng Chrome App Mode (--app=)", no_chrome_app)

    no_webview = "pywebview" not in desktop_code and "import webview" not in desktop_code
    record_result("Kiến Trúc", "Không sử dụng pywebview / Edge WebView2", no_webview)

    uses_pyside6 = "from PySide6" in desktop_code or "import PySide6" in desktop_code
    record_result("Kiến Trúc", "Sử dụng giao diện Desktop Native PySide6", uses_pyside6)

    # 2. Kiểm tra không có tiến trình nào đang chiếm cổng 8001
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.2)
    res = s.connect_ex(("127.0.0.1", 8001))
    s.close()
    port_8001_free = (res != 0)
    record_result("Kiến Trúc", "Cổng 8001 hoàn toàn tự do (Không có local server chạy ngầm)", port_8001_free)

    # 3. Kiểm tra Google Translate notranslate tag trong index.html
    index_code = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    has_notranslate = "notranslate" in index_code
    record_result("Giao Diện", "Chặn bảng Google Translate tự động xuất hiện", has_notranslate)


# ==============================================================================
# PHẦN 2: KIỂM THỬ HỆ THỐNG BẢN QUYỀN VÀ CẤP KEY (PHẦN V & VI)
# ==============================================================================
def test_licensing_system():
    print("\n" + "=" * 70)
    print("PHẦN 2: KIỂM THỬ HỆ THỐNG BẢN QUYỀN 5 THỜI HẠN & CÔNG CỤ CẤP KEY")
    print("=" * 70)

    from tools.license_generator import create_license_key, verify_license_key
    from backend.license import LicenseManager, get_machine_id

    mid = get_machine_id()
    record_result("Bản Quyền", "Tạo Machine ID phần cứng ổn định", bool(mid and mid.startswith("TTTS-")), f"MID={mid}")

    # 1. Cấp và xác minh 5 thời hạn
    keys = {}
    for plan in ["1d", "7d", "30d", "6m", "perm"]:
        res = create_license_key(mid, plan, note=f"Kiểm thử gói {plan}")
        k_str = res["key_string"]
        keys[plan] = k_str
        # Xác minh chữ ký số Ed25519
        try:
            v_payload = verify_license_key(k_str)
            record_result("Bản Quyền", f"Ký & xác minh chữ ký Ed25519 gói {plan.upper()}", True, f"Plan={res['plan']}")
        except Exception as e:
            record_result("Bản Quyền", f"Ký & xác minh chữ ký Ed25519 gói {plan.upper()}", False, str(e))

    lm = LicenseManager()

    # 2. Thử kích hoạt key sai mã máy (Machine Mismatch)
    fake_mid = "TTTS-9999-8888-7777-6666"
    bad_mid_key = create_license_key(fake_mid, "7d")["key_string"]
    ok, msg, _ = lm.activate(bad_mid_key)
    record_result("Bản Quyền", "Từ chối key sai mã máy (Machine Mismatch)", not ok, msg)

    # 3. Thử kích hoạt key bị sửa đổi ký tự (Tampered Key)
    tampered_key = keys["7d"][:-5] + "XXXXX"
    ok, msg, _ = lm.activate(tampered_key)
    record_result("Bản Quyền", "Từ chối key bị can thiệp/sai chữ ký số", not ok, msg)

    # 4. Kích hoạt key 6 Tháng và kiểm tra quy tắc tính hạn theo ngày lịch
    k6m = keys["6m"]
    ok, msg, info6m = lm.activate(k6m)
    exp6m = info6m.get("expires_at")
    dt_now = datetime.datetime.now()
    # Kiểm tra target month cách 6 tháng
    exp_dt = datetime.datetime.fromtimestamp(exp6m) if exp6m else None
    diff_months = (exp_dt.year - dt_now.year) * 12 + (exp_dt.month - dt_now.month) if exp_dt else 0
    record_result("Bản Quyền", "Kích hoạt gói 6 Tháng theo ngày lịch", ok and diff_months == 6, f"Hạn đến: {info6m.get('expires_readable')}")

    # 5. Kích hoạt key Vĩnh Viễn
    kperm = keys["perm"]
    ok, msg, infoperm = lm.activate(kperm)
    is_perm_active = ok and infoperm.get("expires_at") is None and infoperm.get("remaining_formatted") == "Vĩnh viễn (Không giới hạn)"
    record_result("Bản Quyền", "Kích hoạt gói Vĩnh Viễn (Không thời hạn)", is_perm_active, f"Trạng thái: {infoperm.get('remaining_formatted')}")

    # 6. Kiểm tra khóa chức năng khi hết hạn (Key 1D expired test)
    k1d = keys["1d"]
    ok, msg, info1d = lm.activate(k1d)
    # Giả lập thời gian trôi 25 giờ (hơn 1 ngày)
    lm.simulate_time_travel(25 * 3600)
    is_act = lm.is_active()
    st_info = lm.get_status_info()
    record_result("Bản Quyền", "Tự động khóa ứng dụng khi key 1D hết hạn", not is_act and st_info["status"] == "expired", f"Trạng thái: {st_info['status']}")

    # 7. Nhập key mới (Vĩnh viễn) sau khi key cũ hết hạn
    ok, msg, _ = lm.activate(kperm)
    record_result("Bản Quyền", "Cho phép nhập key mới sau khi hết hạn", ok and lm.is_active(), "Đã kích hoạt lại thành công")


# ==============================================================================
# PHẦN 3: KIỂM THỬ TẠO GIỌNG NÓI VIENEU-TTS v3 TURBO ONNX CPU (PHẦN X)
# ==============================================================================
def test_tts_synthesis():
    print("\n" + "=" * 70)
    print("PHẦN 3: KIỂM THỬ TẠO GIỌNG NÓI VIENEU-TTS v3 TURBO ONNX CPU")
    print("=" * 70)

    from backend.service import tts_service

    # 1. Khởi tạo mô hình
    t0 = time.time()
    ok = tts_service.initialize_model()
    st = tts_service.get_model_status()
    record_result("Mô Hình TTS", "Khởi tạo VieNeu-TTS v3 Turbo ONNX CPU", ok and st["state"] == "ready", f"Thời gian: {time.time()-t0:.2f}s, Backend: {st['backend']}")

    # 2. Tạo âm thanh câu ngắn tiếng Việt
    short_text = "Xin chào, đây là bản thử nghiệm T-TTS v1.0.1 nâng cấp."
    res1 = tts_service.synthesize_text(short_text, voice_id="Hải Đăng", speed=1.0)
    w_ok = res1.get("success") and Path(res1.get("wav_path", "")).is_file()
    record_result("Tạo Giọng", "Tạo file WAV câu ngắn tiếng Việt", w_ok, f"Thời lượng: {res1.get('duration')}s")

    # Kiểm tra đặc tính file WAV 48kHz PCM
    if w_ok:
        with wave.open(res1["wav_path"], "rb") as wf:
            channels = wf.getnchannels()
            sr = wf.getframerate()
            sampwidth = wf.getsampwidth()
            frames = wf.getnframes()
        wav_valid = (channels == 1 and sr == 48000 and sampwidth == 2 and frames > 0)
        record_result("Tạo Giọng", "Kiểm tra chuẩn WAV 48kHz 16-bit Mono", wav_valid, f"SR={sr}, Ch={channels}, Width={sampwidth}B")

    # 3. Tạo âm thanh với văn bản dài và thẻ nghỉ [pause:0.5s]
    long_text = (
        "Chào mừng bạn đến với phần mềm chuyển văn bản thành giọng nói T-TTS. [pause:0.5s] "
        "Mô hình VieNeu-TTS v3 Turbo chạy trên nền tảng ONNX Runtime CPU hoàn toàn offline. [pause:0.5s] "
        "Phần mềm được phát triển bởi Đại úy Nguyễn Văn Tiệp, mang lại trải nghiệm tối ưu cho người dùng Windows."
    )
    res_long = tts_service.synthesize_text(long_text, voice_id="Mai Anh", speed=1.0)
    record_result("Tạo Giọng", "Tạo âm thanh văn bản dài kèm thẻ ngắt nghỉ [pause]", res_long.get("success"), f"Thời lượng: {res_long.get('duration')}s")

    # 4. Điều chỉnh tốc độ đọc (0.75x, 1.25x, 1.50x)
    for sp in [0.75, 1.25, 1.50]:
        res_sp = tts_service.synthesize_text("Kiểm tra tốc độ đọc của hệ thống.", voice_id="Hải Đăng", speed=sp)
        record_result("Tạo Giọng", f"Tạo âm thanh với tốc độ {sp:.2f}x", res_sp.get("success"), f"Tốc độ: {res_sp.get('speed')}x")

    # 5. Định dạng xuất MP3
    res_mp3 = tts_service.synthesize_text("Kiểm tra định dạng nén MP3.", voice_id="Hải Đăng", out_format="mp3")
    mp3_ok = res_mp3.get("success") and res_mp3.get("mp3_path") and Path(res_mp3["mp3_path"]).is_file()
    record_result("Tạo Giọng", "Xuất file định dạng MP3", mp3_ok, f"Tệp MP3: {res_mp3.get('mp3_path')}")


# ==============================================================================
# PHẦN 4: KIỂM THỬ NHÂN BẢN GIỌNG & QUẢN LÝ GIỌNG
# ==============================================================================
def test_voice_cloning_and_management():
    print("\n" + "=" * 70)
    print("PHẦN 4: KIỂM THỬ NHÂN BẢN GIỌNG & QUẢN LÝ 25 GIỌNG CHUẨN")
    print("=" * 70)

    from backend.service import tts_service

    # 1. Kiểm tra 25 giọng chuẩn allowlist
    voices = tts_service.list_voices()
    preset_voices = [v for v in voices if not v.get("is_custom")]
    record_result("Quản Lý Giọng", "Đủ 25 giọng chuẩn allowlist VieNeu-TTS v3 Turbo", len(preset_voices) >= 25, f"Số lượng: {len(preset_voices)}")

    # 2. Nhân bản giọng từ một file WAV hợp lệ
    # Sử dụng file WAV vừa tạo ở phần 3 làm mẫu
    history = tts_service.get_history()
    sample_wav = None
    for h in history:
        fn = h.get("wav")
        if fn:
            p = tts_service.default_out_dir / fn
            if p.is_file():
                try:
                    with wave.open(str(p), "rb") as wf:
                        dur = wf.getnframes() / float(wf.getframerate())
                        if dur >= 3.5:
                            sample_wav = str(p)
                            break
                except Exception:
                    pass

    if sample_wav:
        clone_res = tts_service.clone_voice(
            voice_name="Giọng Test Clone",
            ref_audio_path=sample_wav,
            description="Giọng kiểm thử tự động",
        )
        record_result("Nhân Bản Giọng", "Tạo thành công giọng nhân bản từ file WAV mẫu", clone_res.get("success"), clone_res.get("message", ""))

        # Kiểm tra giọng mới xuất hiện trong danh sách
        v_names = [v["id"] for v in tts_service.list_voices()]
        record_result("Nhân Bản Giọng", "Giọng nhân bản mới xuất hiện trong danh mục giọng đọc", "Giọng Test Clone" in v_names)

        # Xóa giọng nhân bản test để dọn dẹp
        del_res = tts_service.delete_custom_voice("Giọng Test Clone")
        record_result("Nhân Bản Giọng", "Xóa an toàn giọng nhân bản", del_res.get("success"))
    else:
        record_result("Nhân Bản Giọng", "Tạo thành công giọng nhân bản từ file WAV mẫu", False, "Thiếu file mẫu")

    # 3. Từ chối file âm thanh không hợp lệ (tệp rỗng hoặc không tồn tại)
    bad_clone = tts_service.clone_voice("Giọng Lỗi", "C:/invalid_non_existent_file.wav")
    record_result("Nhân Bản Giọng", "Từ chối tệp âm thanh mẫu không tồn tại", not bad_clone.get("success"), bad_clone.get("error", ""))


# ==============================================================================
# PHẦN 5: KIỂM THỬ XỬ LÝ HÀNG LOẠT (BATCH PROCESSING)
# ==============================================================================
def test_batch_processing():
    print("\n" + "=" * 70)
    print("PHẦN 5: KIỂM THỬ XỬ LÝ HÀNG LOẠT & CÁCH LY LỖI")
    print("=" * 70)

    from backend.service import tts_service

    items = [
        {"text": "Câu số 1 trong danh sách xử lý hàng loạt.", "voice": "Hải Đăng", "speed": 1.0},
        {"text": "Câu số 2 với tốc độ đọc nhanh hơn một chút.", "voice": "Mai Anh", "speed": 1.1},
        {"text": "Câu số 3 hoàn tất quy trình kiểm thử hàng loạt.", "voice": "Hải Đăng", "speed": 1.0},
    ]

    res = tts_service.process_batch(items, common_voice="Hải Đăng", common_speed=1.0)
    batch_ok = res.get("success") and res.get("completed") == 3 and res.get("failed") == 0
    record_result("Xử Lý Hàng Loạt", "Xử lý thành công 3/3 tác vụ hàng loạt", batch_ok, f"Completed: {res.get('completed')}/{res.get('total')}")


# ==============================================================================
# PHẦN 6: KIỂM THỬ DỮ LIỆU & LỊCH SỬ NGƯỜI DÙNG
# ==============================================================================
def test_data_preservation():
    print("\n" + "=" * 70)
    print("PHẦN 6: KIỂM THỬ BẢO TOÀN DỮ LIỆU & LỊCH SỬ")
    print("=" * 70)

    from backend.service import tts_service

    hist = tts_service.get_history()
    stats = tts_service.get_history_stats()
    record_result("Dữ Liệu", "Bảo toàn toàn bộ lịch sử tạo âm thanh người dùng", len(hist) > 0, f"Số bản ghi: {len(hist)}, Dung lượng: {stats['size_mb']} MB")

    out_dir_exists = tts_service.default_out_dir.is_dir()
    record_result("Dữ Liệu", "Thư mục output đầu ra hoạt động bình thường", out_dir_exists, str(tts_service.default_out_dir))

    data_dir_exists = tts_service.data_dir.is_dir()
    record_result("Dữ Liệu", "Thư mục data cấu hình người dùng hoạt động bình thường", data_dir_exists, str(tts_service.data_dir))


def main():
    test_architecture_and_localhost_removal()
    test_licensing_system()
    test_tts_synthesis()
    test_voice_cloning_and_management()
    test_batch_processing()
    test_data_preservation()

    print("\n" + "=" * 70)
    print("TỔNG KẾT KẾT QUẢ KIỂM THỬ TOÀN DIỆN")
    print("=" * 70)
    total = len(test_results)
    passed = sum(1 for v in test_results.values() if v["passed"])
    failed = total - passed

    for k, v in test_results.items():
        icon = "✅" if v["passed"] else "❌"
        print(f"{icon} {k:60s} -> {v['status']}")

    print("\n" + "-" * 70)
    print(f"KẾT QUẢ: {passed}/{total} HẠNG MỤC ĐẠT (Tỷ lệ: {passed/total*100:.1f}%)")
    print("=" * 70 + "\n")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
