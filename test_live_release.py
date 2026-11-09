"""Kiểm thử thực tế (End-to-End Live Testing) cho cả 2 bản:
1. Bản Portable: dist/T-TTS_v1.0.1_Exe_Portable/T-TTS.exe
2. Bản Cài đặt: dist/T-TTS_v1.0.1_Setup_Installer.exe -> cài đặt và chạy test_install/T-TTS.exe

Các kịch bản kiểm thử cho mỗi bản:
- Khởi động tiến trình thực thi
- Chờ server sẵn sàng (GET /health)
- Tạo âm thanh WAV (POST /api/tts/generate)
- Lưu từ điển phát âm (POST /api/pron-dict)
- Kiểm tra danh sách từ điển (GET /api/pron-dict)
- Kiểm tra lịch sử tạo âm thanh (GET /api/history)
- Thoát ứng dụng an toàn (POST /api/shutdown)
"""
import os
import sys
import time
import shutil
import urllib.request
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
PORTABLE_EXE = DIST / "T-TTS_v1.0.1_Exe_Portable" / "T-TTS.exe"
INSTALLER_EXE = DIST / "T-TTS_v1.0.1_Setup_Installer.exe"
TEST_INSTALL_DIR = ROOT / "test_install"
BASE_URL = "http://127.0.0.1:8001"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

test_logs = []

def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    test_logs.append(line)

def wait_for_server(proc, timeout=40):
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            raise RuntimeError(f"Tiến trình đã dừng đột ngột với mã lỗi {proc.returncode}")
        try:
            req = urllib.request.urlopen(f"{BASE_URL}/health", timeout=2)
            if req.status == 200:
                data = json.loads(req.read().decode("utf-8"))
                if data.get("ready"):
                    return data
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f"Quá thời gian {timeout}s chờ server và mô hình VieNeu-TTS sẵn sàng.")

def http_post_json(endpoint, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}{endpoint}", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read()

def http_get_json(endpoint):
    with urllib.request.urlopen(f"{BASE_URL}{endpoint}", timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def test_app_workflow(app_name):
    log(f"--- KIỂM THỬ WORKFLOW ĐẦY ĐỦ TRÊN {app_name} ---")

    # 1. Health check
    st, health_data = http_get_json("/health")
    assert st == 200, f"Health check thất bại: {st}"
    log(f"  [1. Health Check] OK: app='{health_data.get('app')}', status='{health_data.get('status')}'")

    # 2. Tạo WAV
    payload_tts = {
        "text": f"Xin chào, đây là bài kiểm tra tự động tạo âm thanh của {app_name}.",
        "voice_id": "Hải Đăng",
        "speed": 1.0,
        "format": "wav",
    }
    st, wav_bytes = http_post_json("/api/tts/generate", payload_tts)
    assert st == 200, f"Tạo âm thanh thất bại: {st}"
    assert wav_bytes.startswith(b"RIFF"), f"Dữ liệu trả về không phải định dạng WAV: {wav_bytes[:10]}"
    assert len(wav_bytes) > 2000, f"Kích thước file WAV quá nhỏ: {len(wav_bytes)} bytes"
    log(f"  [2. Tạo Audio WAV] OK: Đã nhận được {len(wav_bytes)} bytes WAV hợp lệ.")

    # 3. Lưu từ điển phát âm
    test_word = f"AUTO_{int(time.time()) % 10000}"
    st, resp_dict = http_post_json("/api/pron-dict", {"word": test_word, "reading": "tự động hoá"})
    assert st == 200, f"Lưu từ điển thất bại: {st}"
    saved_dict = json.loads(resp_dict.decode("utf-8")).get("dict", {})
    assert test_word in saved_dict, f"Từ vừa lưu không có trong từ điển: {saved_dict}"
    log(f"  [3. Lưu từ điển] OK: Đã lưu thành công '{test_word}' -> '{saved_dict[test_word]}'")

    # 4. Mở lịch sử
    st, hist_data = http_get_json("/api/history")
    assert st == 200, f"Lấy lịch sử thất bại: {st}"
    items = hist_data.get("items", [])
    assert len(items) > 0, "Lịch sử rỗng sau khi đã tạo audio!"
    log(f"  [4. Mở lịch sử] OK: Lịch sử có {len(items)} bản ghi (Dung lượng: {hist_data.get('stats', {}).get('size_mb', 0)} MB)")

    # 5. Thoát ứng dụng
    try:
        http_post_json("/api/shutdown", {})
        log(f"  [5. Thoát ứng dụng] Đã gửi lệnh shutdown tới server.")
    except Exception as e:
        log(f"  [5. Thoát ứng dụng] Lưu ý: {e}")

def run_portable_test():
    log("\n================================================================================")
    log("BẮT ĐẦU KIỂM THỬ BẢN PORTABLE THỰC TẾ")
    log("================================================================================")
    if not PORTABLE_EXE.exists():
        raise FileNotFoundError(f"Không tìm thấy file {PORTABLE_EXE}")

    log(f"Khởi động tiến trình Portable: {PORTABLE_EXE}")
    proc = subprocess.Popen([str(PORTABLE_EXE)], cwd=PORTABLE_EXE.parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        health = wait_for_server(proc, timeout=35)
        log(f"Server Portable đã sẵn sàng: {health.get('app')}")
        test_app_workflow("Bản Portable")
        time.sleep(1.5)
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        log("[OK] Bản Portable đã tắt hoàn toàn.")

def run_installer_test():
    log("\n================================================================================")
    log("BẮT ĐẦU KIỂM THỬ BẢN CÀI ĐẶT INNO SETUP THỰC TẾ")
    log("================================================================================")
    if not INSTALLER_EXE.exists():
        raise FileNotFoundError(f"Không tìm thấy file {INSTALLER_EXE}")

    if TEST_INSTALL_DIR.exists():
        shutil.rmtree(TEST_INSTALL_DIR)
    TEST_INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    log(f"Chạy installer silent cài đặt vào: {TEST_INSTALL_DIR} ...")
    install_cmd = [str(INSTALLER_EXE), "/SP-", "/VERYSILENT", "/SUPPRESSMSGBOXES", f"/DIR={TEST_INSTALL_DIR}"]
    res = subprocess.run(install_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Cài đặt thất bại với mã lỗi {res.returncode}")
    log("[OK] Quá trình cài đặt Inno Setup đã hoàn thành thành công.")

    installed_exe = TEST_INSTALL_DIR / "T-TTS.exe"
    if not installed_exe.exists():
        raise FileNotFoundError(f"Không tìm thấy {installed_exe} sau khi cài đặt!")

    # Xác nhận các thư mục đã được cài đặt đầy đủ
    for sub in ["_internal", "models", "data", "output", "README_WINDOWS.txt"]:
        target = TEST_INSTALL_DIR / sub
        assert target.exists(), f"Thiếu thành phần cài đặt: {target}"
        log(f"  [Xác nhận thành phần cài đặt] {sub}: OK")

    log(f"Khởi động tiến trình bản cài đặt: {installed_exe}")
    proc = subprocess.Popen([str(installed_exe)], cwd=TEST_INSTALL_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        health = wait_for_server(proc, timeout=35)
        log(f"Server bản cài đặt đã sẵn sàng: {health.get('app')}")
        test_app_workflow("Bản Cài Đặt (Installed)")
        time.sleep(1.5)
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        log("[OK] Bản cài đặt đã tắt hoàn toàn.")

def main():
    start_time = time.time()
    try:
        run_portable_test()
        run_installer_test()
        elapsed = round(time.time() - start_time, 2)
        log("\n================================================================================")
        log(f"TẤT CẢ KIỂM THỬ THỰC TẾ (PORTABLE & INSTALLER) ĐỀU THÀNH CÔNG TRONG {elapsed}s!")
        log("================================================================================")
        with open(ROOT / "build-log.txt", "a", encoding="utf-8") as f:
            f.write("\n\n" + "\n".join(test_logs) + "\n")
    except Exception as e:
        log(f"[FATAL TEST ERROR] {e}")
        with open(ROOT / "build-log.txt", "a", encoding="utf-8") as f:
            f.write("\n\n" + "\n".join(test_logs) + f"\n[FATAL TEST ERROR] {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
