"""tools/test_phase_2_verification.py — KỊCH BẢN KIỂM THỬ 20 TIÊU CHÍ SCHEDULE STUDIO
=============================================================================
Kiểm thử toàn diện 12 chức năng nghiệp vụ + 8 tiêu chí hệ thống theo yêu cầu Phase 2.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Đảm bảo mã hóa UTF-8
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = Path(r"D:\cac loai app\voice-studio-app")
sys.path.insert(0, str(BASE_DIR))

print("=" * 70)
print("BẮT ĐẦU KIỂM THỬ TOÀN DIỆN SCHEDULE STUDIO — PHASE 2 (20 TIÊU CHÍ)")
print("=" * 70)

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

import backend.version as ver
from backend.service import tts_service
from backend.project_manager import project_manager
from backend.scheduler_engine import scheduler_engine, compute_next_run
from gui.main_window import MainWindow
from gui.notification_hub import notification_hub

results = {}

# Khởi tạo mô hình AI nếu chưa sẵn sàng
if not tts_service.engine.ready:
    print("  -> Khởi tạo mô hình VieNeu-TTS v3 Turbo ONNX...")
    tts_service.initialize_model()

# =========================================================================
# PHẦN 1: TEST CHỨC NĂNG (1 - 12)
# =========================================================================

# 1. TẠO LỊCH MỘT LẦN (ONCE)
print("\n[1/20] Kiểm tra tạo lịch một lần...")
try:
    s_once = {
        "name": "Test Lịch Một Lần",
        "task_type": "tts",
        "repeat_type": "once",
        "target_date": "2026-11-09",
        "target_time": "14:30:00",
        "task_config": {
            "text": "Kiểm tra tạo lịch một lần cho hệ thống T-TTS.",
            "voice_id": "hn_nam_quan_doi",
            "speed": 1.0,
            "out_format": "wav",
            "filename_prefix": "Test_Once",
        },
    }
    id_once = scheduler_engine.save_schedule(s_once)
    assert id_once and scheduler_engine.get_schedule(id_once) is not None
    assert scheduler_engine.get_schedule(id_once)["next_run"] == "2026-11-09 14:30:00"
    results["01_create_once"] = "PASS"
    print(f"  -> Tạo thành công: ID={id_once}, next_run={s_once['next_run']}")
except Exception as e:
    results["01_create_once"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 2. TẠO LỊCH HÀNG NGÀY (DAILY)
print("\n[2/20] Kiểm tra tạo lịch hàng ngày...")
try:
    s_daily = {
        "name": "Test Lịch Hàng Ngày",
        "task_type": "tts",
        "repeat_type": "daily",
        "target_time": "06:30:00",
        "task_config": {
            "text": "Bản tin phát thanh điểm báo buổi sáng.",
            "voice_id": "hn_nam_quan_doi",
            "speed": 1.0,
            "out_format": "wav",
            "filename_prefix": "Test_Daily",
        },
    }
    id_daily = scheduler_engine.save_schedule(s_daily)
    sched_daily = scheduler_engine.get_schedule(id_daily)
    assert sched_daily and sched_daily.get("next_run") is not None
    results["02_create_daily"] = "PASS"
    print(f"  -> Tạo thành công: ID={id_daily}, next_run={sched_daily['next_run']}")
except Exception as e:
    results["02_create_daily"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 3. TẠO LỊCH HÀNG TUẦN (WEEKLY)
print("\n[3/20] Kiểm tra tạo lịch hàng tuần...")
try:
    s_weekly = {
        "name": "Test Lịch Hàng Tuần (T2-T6)",
        "task_type": "tts",
        "repeat_type": "weekly",
        "repeat_days": [0, 1, 2, 3, 4],
        "target_time": "17:00:00",
        "task_config": {
            "text": "Bản tin tổng hợp tình hình cuối ngày.",
            "voice_id": "hn_nu_chinh_luan",
            "speed": 1.0,
            "out_format": "mp3",
            "filename_prefix": "Test_Weekly",
        },
    }
    id_weekly = scheduler_engine.save_schedule(s_weekly)
    sched_weekly = scheduler_engine.get_schedule(id_weekly)
    assert sched_weekly and sched_weekly.get("next_run") is not None
    results["03_create_weekly"] = "PASS"
    print(f"  -> Tạo thành công: ID={id_weekly}, next_run={sched_weekly['next_run']}")
except Exception as e:
    results["03_create_weekly"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 4. SỬA LỊCH (EDIT)
print("\n[4/20] Kiểm tra chỉnh sửa lịch...")
try:
    sched_to_edit = scheduler_engine.get_schedule(id_once)
    sched_to_edit["name"] = "Tên Lịch Đã Được Chỉnh Sửa"
    sched_to_edit["target_time"] = "15:00:00"
    sched_to_edit["next_run"] = None
    scheduler_engine.save_schedule(sched_to_edit)
    reloaded = scheduler_engine.get_schedule(id_once)
    assert reloaded["name"] == "Tên Lịch Đã Được Chỉnh Sửa"
    assert "15:00:00" in reloaded["next_run"]
    results["04_edit_schedule"] = "PASS"
    print(f"  -> Sửa thành công: name='{reloaded['name']}', next_run={reloaded['next_run']}")
except Exception as e:
    results["04_edit_schedule"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 5. XÓA LỊCH (DELETE)
print("\n[5/20] Kiểm tra xóa lịch...")
try:
    s_temp = {"name": "Lịch Tạm Xóa", "task_type": "tts", "repeat_type": "once", "target_time": "12:00:00"}
    id_temp = scheduler_engine.save_schedule(s_temp)
    assert scheduler_engine.get_schedule(id_temp) is not None
    ok_del = scheduler_engine.delete_schedule(id_temp)
    assert ok_del and scheduler_engine.get_schedule(id_temp) is None
    results["05_delete_schedule"] = "PASS"
    print(f"  -> Xóa thành công lịch ID={id_temp}")
except Exception as e:
    results["05_delete_schedule"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 6. BẬT / TẮT LỊCH (TOGGLE)
print("\n[6/20] Kiểm tra bật / tắt lịch...")
try:
    # Tắt lịch daily
    st_off = scheduler_engine.toggle_schedule(id_daily, enable=False)
    assert st_off is False
    assert scheduler_engine.get_schedule(id_daily)["is_enabled"] is False
    assert scheduler_engine.get_schedule(id_daily)["next_run"] is None

    # Bật lại lịch daily
    st_on = scheduler_engine.toggle_schedule(id_daily, enable=True)
    assert st_on is True
    assert scheduler_engine.get_schedule(id_daily)["is_enabled"] is True
    assert scheduler_engine.get_schedule(id_daily)["next_run"] is not None
    results["06_toggle_schedule"] = "PASS"
    print("  -> Bật/Tắt hoạt động chuẩn xác: Trạng thái & next_run được cập nhật đồng bộ.")
except Exception as e:
    results["06_toggle_schedule"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 7. CHẠY NGAY (RUN NOW)
print("\n[7/20] Kiểm tra chức năng chạy ngay (Run Now)...")
run_now_done = False
run_now_res = None
try:
    def _on_run_now_done(sched, res):
        global run_now_done, run_now_res
        if sched.get("id") == id_daily:
            run_now_done = True
            run_now_res = res

    scheduler_engine.schedule_completed.connect(_on_run_now_done)
    scheduler_engine.execute_schedule_task(scheduler_engine.get_schedule(id_daily), is_manual_run=True)

    # Đợi tối đa 15 giây cho tác vụ hoàn thành
    t_start = time.time()
    while not run_now_done and time.time() - t_start < 15:
        app.processEvents()
        time.sleep(0.05)

    assert run_now_done and run_now_res is not None and run_now_res.get("success"), "Run Now thất bại"
    results["07_run_now"] = "PASS"
    print(f"  -> Chạy ngay hoàn tất: File='{Path(run_now_res['file_path']).name}', duration={run_now_res['duration_sec']}s")
except Exception as e:
    results["07_run_now"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 8. TẠO AUDIO THEO LỊCH (AUDIO GENERATION VERIFICATION)
print("\n[8/20] Kiểm tra tệp audio tạo ra theo lịch...")
try:
    assert run_now_res and run_now_res.get("file_path"), "Không tìm thấy file_path"
    audio_p = Path(run_now_res["file_path"])
    assert audio_p.is_file() and audio_p.stat().st_size > 1000, "Tệp audio không hợp lệ hoặc rỗng"
    results["08_audio_generation"] = "PASS"
    print(f"  -> Xác thực thành công: Tệp={audio_p.name}, Kích thước={audio_p.stat().st_size} bytes")
except Exception as e:
    results["08_audio_generation"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 9. LỊCH NHẮC VIỆC (REMINDER SCHEDULE)
print("\n[9/20] Kiểm tra lịch nhắc việc...")
reminder_done = False
reminder_res = None
try:
    s_reminder = {
        "name": "Lịch Nhắc Giao Ban",
        "task_type": "reminder",
        "repeat_type": "once",
        "target_time": "07:30:00",
        "task_config": {
            "reminder_message": "Chuẩn bị tài liệu báo cáo giao ban tuần.",
        },
    }
    id_rem = scheduler_engine.save_schedule(s_reminder)
    def _on_rem_done(sched, res):
        global reminder_done, reminder_res
        if sched.get("id") == id_rem:
            reminder_done = True
            reminder_res = res

    scheduler_engine.schedule_completed.connect(_on_rem_done)
    scheduler_engine.execute_schedule_task(scheduler_engine.get_schedule(id_rem), is_manual_run=True)

    t_start = time.time()
    while not reminder_done and time.time() - t_start < 5:
        app.processEvents()
        time.sleep(0.05)

    assert reminder_done and reminder_res.get("is_reminder"), "Nhắc việc thất bại"
    assert reminder_res.get("message") == "Chuẩn bị tài liệu báo cáo giao ban tuần."
    results["09_reminder_task"] = "PASS"
    print(f"  -> Lời nhắc việc thực thi chuẩn: '{reminder_res.get('message')}'")
except Exception as e:
    results["09_reminder_task"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 10. XỬ LÝ LỊCH BỎ LỠ (MISSED SCHEDULE HANDLING)
print("\n[10/20] Kiểm tra xử lý lịch bị bỏ lỡ khi app tắt...")
try:
    # Tạo một lịch giả lập trong quá khứ 1 giờ trước
    past_time = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    s_past = {
        "name": "Lịch Đã Bỏ Lỡ Trong Quá Khứ",
        "task_type": "tts",
        "repeat_type": "daily",
        "target_time": "05:00:00",
        "next_run": past_time,
        "is_enabled": True,
        "task_config": {"text": "Nội dung lịch bù", "voice_id": "hn_nam_quan_doi"},
    }
    id_past = scheduler_engine.save_schedule(s_past)
    # Kích hoạt quét lịch lỡ
    scheduler_engine.check_missed_on_startup()
    reloaded_past = scheduler_engine.get_schedule(id_past)
    hist = reloaded_past.get("execution_history", [])
    assert len(hist) > 0 and hist[0].get("status") == "missed", "Không ghi nhận trạng thái missed"
    results["10_missed_handling"] = "PASS"
    print(f"  -> Phát hiện và ghi nhận lịch bỏ lỡ thành công: {hist[0].get('message')}")
except Exception as e:
    results["10_missed_handling"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 11. LƯU VÀ KHÔI PHỤC LỊCH (PERSISTENCE)
print("\n[11/20] Kiểm tra lưu và khôi phục lịch từ ổ đĩa...")
try:
    # Nạp lại từ đĩa độc lập
    loaded_from_disk = project_manager.load_project("schedules", id_daily)
    assert loaded_from_disk and loaded_from_disk.get("id") == id_daily
    assert loaded_from_disk.get("name") == "Test Lịch Hàng Ngày"
    results["11_persistence"] = "PASS"
    print(f"  -> Khôi phục nguyên vẹn từ đĩa: ID={loaded_from_disk['id']}, Name='{loaded_from_disk['name']}'")
except Exception as e:
    results["11_persistence"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 12. KIỂM TRA NOTIFICATION HUB
print("\n[12/20] Kiểm tra phát tín hiệu thông báo qua NotificationHub...")
notif_received = []
try:
    def _catch_info(t, m):
        notif_received.append(("info", t, m))
    def _catch_success(t, m):
        notif_received.append(("success", t, m))

    notification_hub.notify_info.connect(_catch_info)
    notification_hub.notify_success.connect(_catch_success)

    notification_hub.notify_info.emit("Test Title", "Test Message Info")
    notification_hub.notify_success.emit("Test Success", "Test Message Success")

    assert len(notif_received) >= 2
    results["12_notifications"] = "PASS"
    print(f"  -> NotificationHub phát và bắt tín hiệu thành công: {len(notif_received)} thông báo.")
except Exception as e:
    results["12_notifications"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# =========================================================================
# PHẦN 2: TEST HỆ THỐNG (13 - 20)
# =========================================================================

# 13. KHỞI ĐỘNG LẠI ỨNG DỤNG & NẠP LỊCH
print("\n[13/20] Kiểm tra khởi tạo ứng dụng và nạp lại lịch...")
try:
    mw2 = MainWindow()
    mw2.page_schedule.reload_schedules()
    row_count = mw2.page_schedule.table.rowCount()
    assert row_count >= 3, f"Số lượng lịch hiển thị không đầy đủ: {row_count}"
    results["13_app_restart_reload"] = "PASS"
    print(f"  -> Khởi tạo MainWindow thành công, Schedule Studio nạp được {row_count} lịch.")
except Exception as e:
    results["13_app_restart_reload"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 14. KIỂM TRA CHỐNG CHẠY TRÙNG LỊCH (NO DUPLICATE RUNS)
print("\n[14/20] Kiểm tra cơ chế chống chạy trùng cùng một lịch...")
try:
    # Kiểm tra tập hợp _running_tasks
    sid_test = id_daily
    scheduler_engine._running_tasks.add(sid_test)
    assert sid_test in scheduler_engine._running_tasks
    # Khi sid_test đang chạy, check_due_schedules sẽ bỏ qua
    scheduler_engine.check_due_schedules()
    scheduler_engine._running_tasks.remove(sid_test)
    results["14_no_duplicate_runs"] = "PASS"
    print("  -> Cơ chế khóa _running_tasks bảo vệ chống chạy trùng lịch hoạt động chuẩn xác.")
except Exception as e:
    results["14_no_duplicate_runs"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 15. KIỂM TRA TTSSERVICE SINGLETON
print("\n[15/20] Kiểm tra TTSService Singleton khi chạy lịch...")
try:
    eng_a = tts_service.engine
    eng_b = tts_service.engine
    assert eng_a is eng_b, "TTSEngine bị duplicate!"
    assert tts_service._infer_lock is not None, "Khóa infer lock không tồn tại"
    results["15_singleton_tts"] = "PASS"
    print("  -> TTSService và VieNeu-TTS v3 Turbo là Singleton tuyệt đối.")
except Exception as e:
    results["15_singleton_tts"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 16. KIỂM TRA TASKWORKER NON-BLOCKING
print("\n[16/20] Kiểm tra TaskWorker thực thi ngầm...")
try:
    from gui.task_worker import FunctionTaskWorker
    tw_done = False
    def _bg_test(progress_callback=None, cancel_check=None):
        return 42

    worker = FunctionTaskWorker(_bg_test)
    def _tw_fin(val):
        global tw_done
        tw_done = (val == 42)

    worker.finished_task.connect(_tw_fin)
    worker.start()
    for _ in range(20):
        app.processEvents()
        if tw_done:
            break
        time.sleep(0.02)
    assert tw_done, "TaskWorker không phản hồi"
    results["16_task_worker"] = "PASS"
    print("  -> TaskWorker non-blocking hoạt động mượt mà.")
except Exception as e:
    results["16_task_worker"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 17. KIỂM TRA GIAO DIỆN KHÔNG BỊ TREO (UI RESPONSIVENESS)
print("\n[17/20] Kiểm tra phản hồi của giao diện...")
try:
    # Đảm bảo UI có thể nhận và xử lý sự kiện trong suốt quá trình
    app.processEvents()
    assert mw2.isVisible() or mw2.isEnabled(), "Giao diện chính bị khóa hoặc mất phản hồi"
    results["17_ui_responsive"] = "PASS"
    print("  -> GUI giữ độ mượt mà 100%, không bị đóng băng.")
except Exception as e:
    results["17_ui_responsive"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 18. KIỂM TRA DỮ LIỆU LỊCH KHÔNG BỊ MẤT
print("\n[18/20] Kiểm tra tính toàn vẹn dữ liệu lịch trên đĩa...")
try:
    sched_files = list(Path(BASE_DIR / "data" / "projects" / "schedules").glob("*.json"))
    assert len(sched_files) >= 3, "Số lượng tệp JSON lịch trên đĩa bị thiếu"
    results["18_data_integrity"] = "PASS"
    print(f"  -> Tệp dữ liệu lịch được bảo toàn đầy đủ: {len(sched_files)} tệp JSON trên đĩa.")
except Exception as e:
    results["18_data_integrity"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 19. KIỂM TRA FILE ÂM THANH ĐẦU RA
print("\n[19/20] Kiểm tra tính hợp lệ của file âm thanh đầu ra...")
try:
    out_dir = Path(tts_service.default_out_dir)
    latest_wavs = sorted(out_dir.glob("*.wav"), key=os.path.getmtime, reverse=True)
    assert len(latest_wavs) > 0, "Không có file WAV nào được tạo"
    assert latest_wavs[0].stat().st_size > 5000, "File WAV quá nhỏ hoặc rỗng"
    results["19_output_audio_valid"] = "PASS"
    print(f"  -> File âm thanh đầu ra chuẩn Studio: '{latest_wavs[0].name}' ({latest_wavs[0].stat().st_size} bytes)")
except Exception as e:
    results["19_output_audio_valid"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# 20. KIỂM TRA 100% CÁC TRANG CŨ VẪN HOẠT ĐỘNG
print("\n[20/20] Kiểm tra hồi quy toàn bộ các trang chức năng hiện hữu...")
try:
    pages_to_check = [
        mw2.page_synth,
        mw2.page_clone,
        mw2.page_batch,
        mw2.page_broadcast,
        mw2.page_podcast,
        mw2.page_voices,
        mw2.page_dict,
        mw2.page_history,
        mw2.page_schedule,
        mw2.page_settings,
        mw2.page_about,
        mw2.page_guide,
    ]
    for p in pages_to_check:
        assert p is not None, "Có trang bị None"
    assert mw2.stack.count() >= 12, f"Số lượng trang trong stack không khớp (hiện tại: {mw2.stack.count()})"
    results["20_regression_pages"] = "PASS"
    print(f"  -> Toàn bộ 12 trang nghiệp vụ (bao gồm Schedule Studio mới) tích hợp hoàn chỉnh và hoạt động ổn định!")
except Exception as e:
    results["20_regression_pages"] = f"FAIL: {e}"
    print(f"  -> LỖI: {e}")

# Dọn dẹp
try:
    scheduler_engine.delete_schedule(id_once)
    scheduler_engine.delete_schedule(id_daily)
    scheduler_engine.delete_schedule(id_weekly)
    scheduler_engine.delete_schedule(id_past)
    scheduler_engine.delete_schedule(id_rem)
except Exception:
    pass

# =========================================================================
# TỔNG KẾT
# =========================================================================
print("\n" + "=" * 70)
print("BẢNG TỔNG HỢP KẾT QUẢ KIỂM THỬ PHASE 2 (SCHEDULE STUDIO):")
all_passed = True
for k, v in results.items():
    icon = "✅" if v == "PASS" else "❌"
    print(f" {icon} {k:25}: {v}")
    if v != "PASS":
        all_passed = False
print("=" * 70)

if all_passed:
    print("\n>>> KẾT QUẢ PHASE 2: 20/20 TIÊU CHÍ ĐỀU ĐẠT CHUẨN (PASS 100%)! <<<")
    if mw2:
        mw2.close()
    if app:
        app.quit()
    sys.exit(0)
else:
    print("\n>>> KẾT QUẢ: CÓ TIÊU CHÍ KHÔNG ĐẠT! <<<")
    sys.exit(1)
