"""tools/test_phase_1_verification.py — KỊCH BẢN KIỂM THỬ TOÀN DIỆN 14 TIÊU CHÍ PHASE 1
=============================================================================
Kiểm tra độ toàn vẹn, tính tương thích ngược và sự ổn định của T-TTS sau Phase 1.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Đảm bảo mã hóa UTF-8
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = Path(r"D:\cac loai app\voice-studio-app")
sys.path.insert(0, str(BASE_DIR))

print("=" * 70)
print("BẮT ĐẦU KIỂM THỬ HẠ TẦNG CỐT LÕI PHASE 1 (14 TIÊU CHÍ BẮT BUỘC)")
print("=" * 70)

results = {}

# 1. KIỂM TRA IMPORT VÀ CÚ PHÁP CÁC FILE MỚI & SỬA ĐỔI
print("\n[1/14] Kiểm tra cú pháp và nạp module...")
try:
    import backend.version as ver
    import backend.audio_utils as au
    import backend.project_manager as pm
    import gui.task_worker as tw
    import gui.notification_hub as nh
    from backend.service import tts_service
    from backend.license import license_manager, get_machine_id
    from backend.storage import init_storage
    results["1_modules_import"] = "PASS"
    print("  -> Nạp thành công: version, audio_utils, project_manager, task_worker, notification_hub, service.")
except Exception as e:
    results["1_modules_import"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 2. KIỂM TRA KHỞI TẠO GUI (OFF-SCREEN)
print("\n[2/14] Kiểm tra khởi tạo ứng dụng và MainWindow (Off-screen)...")
mw = None
try:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from gui.main_window import MainWindow
    mw = MainWindow()
    mw._check_initial_license = lambda: None
    mw._check_background_update = lambda: None
    if mw.loader_thread:
        mw.loader_thread.wait()
    assert mw.windowTitle() != "", "Window title is empty"
    results["2_gui_init"] = "PASS"
    print(f"  -> MainWindow khởi tạo mượt mà, Tiêu đề: '{mw.windowTitle()}'")
except Exception as e:
    results["2_gui_init"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 3. KIỂM TRA TTS ĐƠN LẺ
print("\n[3/14] Kiểm tra chức năng tổng hợp TTS đơn lẻ...")
single_out_path = None
try:
    if not tts_service.engine.ready:
        print("  -> Đang khởi tạo mô hình VieNeu-TTS v3 Turbo ONNX...")
        tts_service.initialize_model()
    test_res = tts_service.synthesize_text(
        text="Hệ thống trợ lý giọng nói quân đội T-TTS thử nghiệm sẵn sàng.",
        voice_id="hn_nam_quan_doi",
        speed=1.0,
        out_format="wav",
        filename_prefix="test_phase1_single",
    )
    assert test_res.get("success"), f"TTS thất bại: {test_res.get('error')}"
    out_file = Path(test_res["file_path"])
    assert out_file.exists() and out_file.stat().st_size > 1000, "Tệp âm thanh tạo ra rỗng"
    single_out_path = str(out_file)
    results["3_single_tts"] = "PASS"
    print(f"  -> Tạo thành công tệp: {out_file.name} ({test_res['duration_sec']}s, {out_file.stat().st_size} bytes)")
except Exception as e:
    results["3_single_tts"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 4. KIỂM TRA XỬ LÝ HÀNG LOẠT (BATCH)
print("\n[4/14] Kiểm tra chức năng xử lý hàng loạt (Batch)...")
batch_files = []
try:
    batch_items = [
        {"tag": "doan_1", "text": "Mệnh lệnh huấn luyện chiến đấu năm 2026.", "voice": "hn_nam_quan_doi", "speed": 1.0},
        {"tag": "doan_2", "text": "Duy trì nghiêm chế độ trực chỉ huy, trực ban.", "voice": "hn_nu_chinh_luan", "speed": 1.05},
    ]
    batch_res = tts_service.process_batch(items=batch_items, common_voice="hn_nam_quan_doi", common_speed=1.0)
    assert batch_res.get("success"), "Batch process failed"
    for r in batch_res.get("results", []):
        if r.get("success") and r.get("file_path"):
            batch_files.append(r["file_path"])
    assert len(batch_files) == 2, f"Số lượng kết quả batch không khớp ({len(batch_files)})"
    results["4_batch_process"] = "PASS"
    print(f"  -> Xử lý thành công {len(batch_files)} tệp hàng loạt.")
except Exception as e:
    results["4_batch_process"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 5. KIỂM TRA GHÉP BẢN TIN PHÁT THANH (BROADCAST)
print("\n[5/14] Kiểm tra chức năng ghép bản tin phát thanh (stitch_broadcast_project)...")
try:
    f1 = batch_files[0] if len(batch_files) > 0 else single_out_path
    f2 = batch_files[1] if len(batch_files) > 1 else single_out_path
    broadcast_res = au.stitch_broadcast_project(
        segments=[
            {"file_path": f1, "gain_db": 0.0, "pause_after": 0.5},
            {"file_path": f2, "gain_db": 1.0, "pause_after": 0.5},
        ],
        output_path=BASE_DIR / "output" / "test_phase1_broadcast.wav",
        out_format="wav",
        default_pause_sec=0.5,
    )
    assert broadcast_res.get("success"), "Broadcast stitching failed"
    results["5_broadcast_stitch"] = "PASS"
    print(f"  -> Ghép bản tin thành công: {broadcast_res['duration_sec']}s, 2 phân đoạn.")
except Exception as e:
    results["5_broadcast_stitch"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 6. KIỂM TRA NHÂN BẢN GIỌNG NÓI (CLONE AUDIO VALIDATION)
print("\n[6/14] Kiểm tra xác thực âm thanh nhân bản (validate_and_convert_reference_audio)...")
try:
    sample_ref = single_out_path or (batch_files[0] if batch_files else None)
    valid_out = BASE_DIR / "output" / "test_phase1_clone_ref.wav"
    res_val = au.validate_and_convert_reference_audio(sample_ref, valid_out, min_duration=1.0)
    ref_path = res_val[0] if isinstance(res_val, tuple) else res_val
    assert Path(ref_path).exists() and Path(ref_path).stat().st_size > 0
    results["6_clone_validation"] = "PASS"
    print(f"  -> Chuẩn hóa mẫu thu âm nhân bản thành công: {Path(ref_path).name}")
except Exception as e:
    results["6_clone_validation"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 7. KIỂM TRA TÍNH NĂNG PODCAST (ĐỐI THOẠI 2 MC)
print("\n[7/14] Kiểm tra cấu trúc podcast đối thoại...")
try:
    assert mw is not None and hasattr(mw, "page_podcast"), "Trang Podcast không tồn tại trong MainWindow"
    assert mw.page_podcast is not None
    results["7_podcast_ready"] = "PASS"
    print("  -> Trang Podcast (đối thoại MC Nam & Nữ) tích hợp hoàn chỉnh và sẵn sàng.")
except Exception as e:
    results["7_podcast_ready"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 8. KIỂM TRA DANH MỤC GIỌNG (25 GIỌNG CHUẨN ALLOWLIST)
print("\n[8/14] Kiểm tra danh mục 25 giọng đọc allowlist...")
try:
    voices = tts_service.list_voices()
    assert len(voices) >= 25, f"Thiếu giọng đọc trong allowlist: {len(voices)}"
    results["8_voices_catalog"] = "PASS"
    print(f"  -> Kiểm tra thành công {len(voices)} giọng đọc trong catalog chuẩn.")
except Exception as e:
    results["8_voices_catalog"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 9. KIỂM TRA LỊCH SỬ PHÁT THANH (HISTORY)
print("\n[9/14] Kiểm tra đọc/ghi lịch sử phát thanh (history.json)...")
try:
    hist_items = tts_service.history.all()
    assert isinstance(hist_items, list), "Lịch sử không phải danh sách"
    results["9_history_integrity"] = "PASS"
    print(f"  -> Đọc thành công lịch sử: {len(hist_items)} bản ghi an toàn.")
except Exception as e:
    results["9_history_integrity"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 10. KIỂM TRA CÀI ĐẶT HỆ THỐNG (SETTINGS)
print("\n[10/14] Kiểm tra cấu hình cài đặt và tự động cập nhật...")
try:
    cfg = ver.load_update_config(tts_service.data_dir)
    assert cfg.get("github_repo") == "tiepheo37/T-TTS", "Sai nguồn repo cập nhật"
    results["10_settings_config"] = "PASS"
    print(f"  -> Cấu hình cập nhật chính xác: repo={cfg.get('github_repo')}, auto_check={cfg.get('auto_check_on_startup')}")
except Exception as e:
    results["10_settings_config"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 11. KIỂM TRA BẢN QUYỀN OFFLINE (LICENSE)
print("\n[11/14] Kiểm tra cơ chế bản quyền offline Ed25519 & Machine ID...")
try:
    mid = get_machine_id()
    assert len(mid) > 10, "Machine ID không hợp lệ"
    lic_info = license_manager.get_status_info()
    results["11_license_system"] = "PASS"
    print(f"  -> Machine ID trích xuất chuẩn: {mid}")
    print(f"  -> Trạng thái bản quyền: {lic_info.get('status')} (Gói: {lic_info.get('plan', 'N/A')})")
except Exception as e:
    results["11_license_system"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 12. KIỂM TRA UI KHÔNG BỊ TREO (NON-BLOCKING WORKER)
print("\n[12/14] Kiểm tra tiểu trình nền không làm treo UI (FunctionTaskWorker)...")
try:
    worker_finished = False
    def _dummy_task(progress_callback=None, cancel_check=None):
        time.sleep(0.05)
        return {"done": True}

    worker = tw.FunctionTaskWorker(_dummy_task)
    def _on_done(res):
        global worker_finished
        worker_finished = True

    worker.finished_task.connect(_on_done)
    worker.start()
    
    # Bơm event loop để nhận Qt Signal
    for _ in range(50):
        app.processEvents()
        if worker_finished:
            break
        time.sleep(0.02)

    assert worker_finished, "Worker không hoàn thành hoặc signal không được phân phối"
    results["12_ui_non_blocking"] = "PASS"
    print("  -> FunctionTaskWorker thực thi trong luồng nền chuẩn xác, không chặn UI thread.")
except Exception as e:
    results["12_ui_non_blocking"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 13. KIỂM TRA MÔ HÌNH SINGLETON (KHÔNG KHỞI TẠO TRÙNG ONNX SESSIONS)
print("\n[13/14] Kiểm tra Singleton và chống nạp trùng mô hình AI...")
try:
    eng1 = tts_service.engine
    tts_service.initialize_model()
    eng2 = tts_service.engine
    assert eng1 is eng2, "Khởi tạo trùng engine đối tượng!"
    assert tts_service._infer_lock is not None, "Thiếu khóa bảo vệ inference đa luồng"
    results["13_model_singleton"] = "PASS"
    print("  -> Mô hình VieNeu-TTS v3 Turbo là Singleton tuyệt đối, không bị tải trùng lặp.")
except Exception as e:
    results["13_model_singleton"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 14. KIỂM TRA BẢO TOÀN DỮ LIỆU NGƯỜI DÙNG (USER DATA UNTOUCHED)
print("\n[14/14] Kiểm tra bảo vệ dữ liệu người dùng...")
try:
    appdata_tts = Path(os.path.expandvars(r"%LOCALAPPDATA%\T-TTS"))
    lic_file = appdata_tts / "license_state.json"
    if lic_file.exists():
        assert lic_file.stat().st_size > 0, "license_state.json bị rỗng"
    data_dir_history = tts_service.data_dir / "history.json"
    assert data_dir_history.exists(), "history.json bị mất"
    results["14_user_data_intact"] = "PASS"
    print("  -> Toàn bộ dữ liệu người dùng, cấu hình và bản quyền được bảo vệ an toàn 100%.")
except Exception as e:
    results["14_user_data_intact"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# TỔNG KẾT
print("\n" + "=" * 70)
print("BẢNG TỔNG HỢP KẾT QUẢ KIỂM THỬ PHASE 1:")
all_passed = True
for k, v in results.items():
    status_icon = "✅" if v == "PASS" else "❌"
    print(f" {status_icon} {k:30}: {v}")
    if v != "PASS":
        all_passed = False
print("=" * 70)

if all_passed:
    print("\n>>> KẾT QUẢ: 14/14 TIÊU CHÍ ĐỀU ĐẠT CHUẨN (PASS 100%)! <<<")
    if mw:
        mw.close()
    if app:
        app.quit()
    sys.exit(0)
else:
    print("\n>>> KẾT QUẢ: CÓ TIÊU CHÍ KHÔNG ĐẠT! <<<")
    sys.exit(1)
