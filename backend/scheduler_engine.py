"""backend/scheduler_engine.py — ĐỘNG CƠ ĐẶT LỊCH PHÁT THANH & NHẮC VIỆC TỰ ĐỘNG
=============================================================================
Đóng gói logic tính toán lịch trình, lưu trữ dự án lịch bền vững (disk),
phát hiện lịch bị bỏ lỡ khi mở app, và thực thi tác vụ nền:
- Hỗ trợ phát danh sách âm thanh (Audio Playlist) tuần tự, kiểm tra tệp nguồn,
  khoảng nghỉ giữa các tệp (pause_after), báo tệp mất (missing) và relink.
- Hỗ trợ Đọc văn bản tự động AI (VieNeu-TTS).
- Hỗ trợ Thông báo nhắc việc.
- Hỗ trợ Dừng / Tạm dừng / Tiếp tục phát sóng ngầm không làm treo UI.
"""

from __future__ import annotations

import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from .project_manager import project_manager, get_projects_dir
from .service import tts_service
from .audio_utils import get_audio_duration_safe
from .audio_player import audio_player
from .storage import init_storage

_STORAGE = init_storage()
DATA_DIR: Path = _STORAGE["data_dir"]
SCHEDULES_DIR: Path = get_projects_dir("schedules")


def compute_next_run(
    repeat_type: str,
    target_time_str: str,
    target_date_str: Optional[str] = None,
    repeat_days: Optional[List[int]] = None,
    interval_minutes: int = 60,
    from_time: Optional[datetime] = None,
) -> Optional[str]:
    """Tính toán thời điểm chạy tiếp theo (YYYY-MM-DD HH:MM:SS).
    repeat_type: 'once' | 'daily' | 'weekly' | 'interval'
    target_time_str: 'HH:MM:SS' hoặc 'HH:MM'
    repeat_days: danh sách thứ 0 (Thứ 2) đến 6 (Chủ nhật)
    """
    now = from_time or datetime.now()

    # Parse target time
    t_parts = [int(p) for p in target_time_str.strip().split(":")[:3]]
    t_hour = t_parts[0] if len(t_parts) > 0 else 0
    t_min = t_parts[1] if len(t_parts) > 1 else 0
    t_sec = t_parts[2] if len(t_parts) > 2 else 0

    if repeat_type == "once":
        if not target_date_str:
            target_date_str = now.strftime("%Y-%m-%d")
        d_parts = [int(p) for p in target_date_str.strip().split("-")[:3]]
        dt = datetime(d_parts[0], d_parts[1], d_parts[2], t_hour, t_min, t_sec)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    elif repeat_type == "daily":
        candidate = now.replace(hour=t_hour, minute=t_min, second=t_sec, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate.strftime("%Y-%m-%d %H:%M:%S")

    elif repeat_type == "weekly":
        if not repeat_days:
            repeat_days = [0, 1, 2, 3, 4]  # Mặc định thứ 2 đến thứ 6
        for day_offset in range(0, 8):
            candidate = (now + timedelta(days=day_offset)).replace(
                hour=t_hour, minute=t_min, second=t_sec, microsecond=0
            )
            if candidate > now and candidate.weekday() in repeat_days:
                return candidate.strftime("%Y-%m-%d %H:%M:%S")
        # Fallback sau 7 ngày
        return (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    elif repeat_type == "interval":
        mins = max(1, int(interval_minutes))
        candidate = now + timedelta(minutes=mins)
        return candidate.strftime("%Y-%m-%d %H:%M:%S")

    return None


class SchedulerEngine(QObject):
    """Bộ điều phối lịch phát thanh & nhắc việc chạy ngầm định kỳ."""

    schedule_triggered = Signal(dict)       # Khi một lịch đến hạn
    schedule_completed = Signal(dict, dict) # schedule_dict, result_dict
    schedule_failed = Signal(dict, str)     # schedule_dict, error_msg
    schedule_missed = Signal(dict)          # schedule_dict bị bỏ lỡ
    schedules_updated = Signal()            # Danh sách lịch thay đổi

    # Tín hiệu phát thanh Playlist chi tiết
    playlist_item_started = Signal(dict, dict, int, int)    # sched, item, index, total
    playlist_item_finished = Signal(dict, dict, int, int)   # sched, item, index, total
    playlist_state_changed = Signal(str, str)              # sched_id, state ('playing'/'paused'/'stopped')

    _instance = None

    @classmethod
    def instance(cls) -> SchedulerEngine:
        if cls._instance is None:
            cls._instance = SchedulerEngine()
        return cls._instance

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.schedules: Dict[str, Dict[str, Any]] = {}
        self._running_tasks: set[str] = set()
        self._active_workers: Dict[str, Any] = {}

        # Quản lý phát nhạc Playlist
        self._stop_requested: set[str] = set()
        self._pause_requested: set[str] = set()
        self._current_playing_sched_id: Optional[str] = None
        self._current_playing_item: Optional[Dict[str, Any]] = None

        # Timer kiểm tra lịch mỗi 5 giây
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self.check_due_schedules)

        self.load_all_schedules()
        self.check_missed_on_startup()
        self._timer.start()

    def load_all_schedules(self):
        """Nạp toàn bộ lịch từ đĩa (data/projects/schedules/)."""
        self.schedules.clear()
        projects = project_manager.list_projects("schedules")
        for p_meta in projects:
            full_data = project_manager.load_project("schedules", p_meta["id"])
            if full_data and "id" in full_data:
                self.schedules[full_data["id"]] = full_data
            elif full_data:
                full_data["id"] = p_meta.get("id", "sched_unknown")
                self.schedules[full_data["id"]] = full_data
        self.schedules_updated.emit()

    def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        return self.schedules.get(schedule_id)

    def list_schedules(self) -> List[Dict[str, Any]]:
        """Trả về danh sách lịch sắp xếp theo thời gian chạy tiếp theo gần nhất."""
        items = list(self.schedules.values())
        items.sort(key=lambda x: x.get("next_run") or "9999-99-99")
        return items

    def save_schedule(self, schedule_data: Dict[str, Any]) -> str:
        """Lưu hoặc cập nhật lịch xuống tệp JSON."""
        sid = schedule_data.get("id")
        if not sid:
            sid = f"sched_{int(time.time())}_{os.urandom(3).hex()}"
            schedule_data["id"] = sid

        if "is_enabled" not in schedule_data:
            schedule_data["is_enabled"] = True

        # Tính toán lại next_run nếu chưa có
        if "next_run" not in schedule_data or schedule_data["next_run"] is None:
            if schedule_data.get("is_enabled"):
                nr = compute_next_run(
                    repeat_type=schedule_data.get("repeat_type", "once"),
                    target_time_str=schedule_data.get("target_time", "08:00:00"),
                    target_date_str=schedule_data.get("target_date"),
                    repeat_days=schedule_data.get("repeat_days"),
                    interval_minutes=schedule_data.get("interval_minutes", 60),
                )
                schedule_data["next_run"] = nr
        elif not schedule_data.get("is_enabled"):
            schedule_data["next_run"] = None

        project_manager.save_project("schedules", schedule_data)
        self.schedules[sid] = schedule_data
        self.schedules_updated.emit()
        return sid

    def delete_schedule(self, schedule_id: str) -> bool:
        """Xóa một lịch."""
        if schedule_id in self.schedules:
            del self.schedules[schedule_id]
        ok = project_manager.delete_project("schedules", schedule_id)
        self.schedules_updated.emit()
        return ok

    def toggle_schedule(self, schedule_id: str, enable: Optional[bool] = None) -> bool:
        """Bật hoặc tắt trạng thái hoạt động của lịch."""
        sched = self.get_schedule(schedule_id)
        if not sched:
            return False

        if enable is None:
            sched["is_enabled"] = not sched.get("is_enabled", True)
        else:
            sched["is_enabled"] = bool(enable)

        if sched["is_enabled"]:
            sched["next_run"] = compute_next_run(
                repeat_type=sched.get("repeat_type", "once"),
                target_time_str=sched.get("target_time", "08:00:00"),
                target_date_str=sched.get("target_date"),
                repeat_days=sched.get("repeat_days"),
                interval_minutes=sched.get("interval_minutes", 60),
            )
        else:
            sched["next_run"] = None

        self.save_schedule(sched)
        return sched["is_enabled"]

    # -------------------------------------------------------------
    # ĐIỀU KHIỂN PHÁT SÓNG PLAYLIST THỜI GIAN THỰC
    # -------------------------------------------------------------
    def stop_schedule_playback(self, schedule_id: str):
        """Dừng phát sóng ngay lập tức."""
        self._stop_requested.add(schedule_id)
        self._pause_requested.discard(schedule_id)
        audio_player.stop()
        self.playlist_state_changed.emit(schedule_id, "stopped")

    def pause_schedule_playback(self, schedule_id: str):
        """Tạm dừng phát sóng."""
        self._pause_requested.add(schedule_id)
        audio_player.pause()
        self.playlist_state_changed.emit(schedule_id, "paused")

    def resume_schedule_playback(self, schedule_id: str):
        """Tiếp tục phát sóng."""
        self._pause_requested.discard(schedule_id)
        audio_player.resume()
        self.playlist_state_changed.emit(schedule_id, "playing")

    def is_schedule_playing(self, schedule_id: str) -> bool:
        return self._current_playing_sched_id == schedule_id

    def run_schedule_now(self, schedule_id: str):
        """Kích hoạt chạy ngay một lịch trình cụ thể (thủ công)."""
        sched = self.get_schedule(schedule_id)
        if sched:
            return self.execute_schedule_task(sched, is_manual_run=True)
        return None

    def get_current_playing_info(self) -> Optional[Dict[str, Any]]:
        if not self._current_playing_sched_id:
            return None
        return {
            "schedule_id": self._current_playing_sched_id,
            "item": self._current_playing_item,
            "is_paused": self._current_playing_sched_id in self._pause_requested,
        }

    def check_missed_on_startup(self):
        """Kiểm tra xem có lịch nào đến hạn trong thời gian ứng dụng bị đóng không."""
        now_dt = datetime.now()
        for sid, sched in list(self.schedules.items()):
            if not sched.get("is_enabled", False):
                continue
            nr_str = sched.get("next_run")
            if not nr_str:
                continue
            try:
                nr_dt = datetime.strptime(nr_str, "%Y-%m-%d %H:%M:%S")
                if nr_dt < now_dt:
                    missed_behavior = sched.get("missed_behavior", "notify")
                    hist_entry = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "missed",
                        "message": f"Bị lỡ thời điểm chạy dự kiến ({nr_str}) do ứng dụng không mở.",
                    }
                    if "execution_history" not in sched:
                        sched["execution_history"] = []
                    sched["execution_history"].insert(0, hist_entry)

                    sched["next_run"] = compute_next_run(
                        repeat_type=sched.get("repeat_type", "once"),
                        target_time_str=sched.get("target_time", "08:00:00"),
                        target_date_str=sched.get("target_date"),
                        repeat_days=sched.get("repeat_days"),
                        interval_minutes=sched.get("interval_minutes", 60),
                    )
                    if sched.get("repeat_type") == "once":
                        sched["is_enabled"] = False
                        sched["next_run"] = None

                    self.save_schedule(sched)
                    self.schedule_missed.emit(sched)

                    if missed_behavior == "run_immediately":
                        self.execute_schedule_task(sched)
            except Exception as e:
                print(f"Lỗi kiểm tra lịch lỡ '{sid}': {e}")

    def check_due_schedules(self):
        """Được gọi bởi QTimer định kỳ mỗi 5s để phát hiện và thực thi các lịch đến hạn."""
        now_dt = datetime.now()
        for sid, sched in list(self.schedules.items()):
            if not sched.get("is_enabled", False):
                continue
            if sid in self._running_tasks:
                continue

            nr_str = sched.get("next_run")
            if not nr_str:
                continue

            try:
                nr_dt = datetime.strptime(nr_str, "%Y-%m-%d %H:%M:%S")
                if nr_dt <= now_dt:
                    self.execute_schedule_task(sched)
            except Exception as e:
                print(f"Lỗi phân tích giờ chạy lịch '{sid}': {e}")

    def execute_schedule_task(self, sched: Dict[str, Any], is_manual_run: bool = False):
        """Thực thi tác vụ của lịch trong luồng ngầm an toàn."""
        sid = sched["id"]
        self._running_tasks.add(sid)
        self._stop_requested.discard(sid)
        self._pause_requested.discard(sid)
        self.schedule_triggered.emit(sched)

        from gui.task_worker import FunctionTaskWorker

        def _do_work(progress_callback=None, cancel_check=None):
            task_type = sched.get("task_type", "tts")
            task_cfg = sched.get("task_config", {})

            # ---------------------------------------------------------
            # TÁC VỤ 1: PHÁT DANH SÁCH ÂM THANH (AUDIO PLAYLIST)
            # ---------------------------------------------------------
            if task_type == "playlist" or "playlist" in sched:
                playlist = sched.get("playlist") or task_cfg.get("playlist", [])
                if not playlist:
                    raise ValueError("Danh sách phát thanh (Playlist) đang rỗng.")

                self._current_playing_sched_id = sid
                self.playlist_state_changed.emit(sid, "playing")
                total_items = len(playlist)
                executed_items = 0
                missing_items = 0

                try:
                    for idx, item in enumerate(playlist):
                        if sid in self._stop_requested:
                            item["status"] = "stopped"
                            break

                        self._current_playing_item = item
                        fp_str = item.get("file_path", "")
                        fp = Path(fp_str).resolve() if fp_str else None

                        # Kiểm tra file có tồn tại không (Missing File check)
                        if not fp or not fp.is_file():
                            item["status"] = "missing"
                            item["error"] = f"Tệp không tồn tại: {fp_str}"
                            missing_items += 1
                            continue

                        # Phát file âm thanh
                        item["status"] = "playing"
                        self.playlist_item_started.emit(sched, item, idx + 1, total_items)

                        played_ok = audio_player.play(fp)
                        if not played_ok:
                            item["status"] = "failed"
                            item["error"] = "Không thể phát qua MCI Audio Player"
                            continue

                        # Vòng lặp chờ phát xong, theo dõi pause / stop
                        dur_sec = float(item.get("duration_sec") or 0.0)
                        if dur_sec <= 0:
                            dur_sec = get_audio_duration_safe(fp) or 5.0

                        start_play_time = time.time()
                        while True:
                            if sid in self._stop_requested:
                                audio_player.stop()
                                item["status"] = "stopped"
                                break

                            # Xử lý tạm dừng
                            if sid in self._pause_requested:
                                if audio_player.is_playing():
                                    audio_player.pause()
                                while sid in self._pause_requested:
                                    if sid in self._stop_requested:
                                        break
                                    time.sleep(0.1)
                                if sid not in self._stop_requested:
                                    audio_player.resume()

                            # Kiểm tra trạng thái phát
                            if not audio_player.is_playing() and not audio_player.is_paused():
                                # Phát xong
                                break

                            # Timeout an toàn tối đa (dur_sec + 15s)
                            if time.time() - start_play_time > (dur_sec + 15):
                                audio_player.stop()
                                break

                            time.sleep(0.1)

                        if sid in self._stop_requested:
                            break

                        item["status"] = "completed"
                        executed_items += 1
                        self.playlist_item_finished.emit(sched, item, idx + 1, total_items)

                        # Khoảng nghỉ sau phát (pause_after)
                        pause_sec = float(item.get("pause_after", 0.0))
                        if pause_sec > 0 and idx < total_items - 1:
                            t_end_pause = time.time() + pause_sec
                            while time.time() < t_end_pause:
                                if sid in self._stop_requested:
                                    break
                                time.sleep(0.1)

                finally:
                    self._current_playing_sched_id = None
                    self._current_playing_item = None
                    self.playlist_state_changed.emit(sid, "stopped")

                return {
                    "success": True,
                    "is_playlist": True,
                    "total_items": total_items,
                    "executed_items": executed_items,
                    "missing_items": missing_items,
                    "message": f"Phát xong {executed_items}/{total_items} bản tin (Thiếu: {missing_items})",
                }

            # ---------------------------------------------------------
            # TÁC VỤ 2: TỔNG HỢP GIỌNG NÓI AI (VIENEU-TTS)
            # ---------------------------------------------------------
            elif task_type == "tts":
                text = task_cfg.get("text", "").strip()
                if not text:
                    raise ValueError("Nội dung văn bản cần đọc đang rỗng.")
                voice_id = task_cfg.get("voice_id", "hn_nam_quan_doi")
                speed = float(task_cfg.get("speed", 1.0))
                out_format = task_cfg.get("out_format", "wav")
                prefix = task_cfg.get("filename_prefix", "Schedule_Audio")
                out_dir = task_cfg.get("output_dir") or None

                res = tts_service.synthesize_text(
                    text=text,
                    voice_id=voice_id,
                    speed=speed,
                    out_format=out_format,
                    filename_prefix=prefix,
                    custom_out_dir=Path(out_dir) if out_dir else None,
                )
                if not res.get("success"):
                    raise RuntimeError(res.get("error", "Lỗi tổng hợp TTS"))
                return res

            # ---------------------------------------------------------
            # TÁC VỤ 3: THÔNG BÁO NHẮC VIỆC
            # ---------------------------------------------------------
            elif task_type == "reminder":
                msg = task_cfg.get("reminder_message", "Đã đến giờ nhắc việc!")
                return {"success": True, "message": msg, "is_reminder": True}

            else:
                raise ValueError(f"Loại tác vụ không hỗ trợ: {task_type}")

        worker = FunctionTaskWorker(_do_work)

        def _on_success(res):
            self._running_tasks.discard(sid)
            self._active_workers.pop(sid, None)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sched["last_run"] = now_str

            msg_hist = "Hoàn thành tác vụ thành công"
            if res.get("is_reminder"):
                msg_hist = res.get("message")
            elif res.get("is_playlist"):
                msg_hist = res.get("message")

            hist_entry = {
                "timestamp": now_str,
                "status": "success",
                "message": msg_hist,
                "file_path": res.get("file_path", ""),
            }
            if "execution_history" not in sched:
                sched["execution_history"] = []
            sched["execution_history"].insert(0, hist_entry)
            sched["execution_history"] = sched["execution_history"][:50]

            if not is_manual_run:
                if sched.get("repeat_type") == "once":
                    sched["is_enabled"] = False
                    sched["next_run"] = None
                else:
                    sched["next_run"] = compute_next_run(
                        repeat_type=sched.get("repeat_type", "once"),
                        target_time_str=sched.get("target_time", "08:00:00"),
                        target_date_str=sched.get("target_date"),
                        repeat_days=sched.get("repeat_days"),
                        interval_minutes=sched.get("interval_minutes", 60),
                    )

            self.save_schedule(sched)
            self.schedule_completed.emit(sched, res)

        def _on_error(err_str):
            self._running_tasks.discard(sid)
            self._active_workers.pop(sid, None)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            hist_entry = {
                "timestamp": now_str,
                "status": "error",
                "message": f"Lỗi thực thi: {err_str}",
            }
            if "execution_history" not in sched:
                sched["execution_history"] = []
            sched["execution_history"].insert(0, hist_entry)

            if not is_manual_run and sched.get("repeat_type") != "once":
                sched["next_run"] = compute_next_run(
                    repeat_type=sched.get("repeat_type", "once"),
                    target_time_str=sched.get("target_time", "08:00:00"),
                    target_date_str=sched.get("target_date"),
                    repeat_days=sched.get("repeat_days"),
                    interval_minutes=sched.get("interval_minutes", 60),
                )
            self.save_schedule(sched)
            self.schedule_failed.emit(sched, str(err_str))

        worker.finished_task.connect(_on_success)
        worker.error_task.connect(_on_error)
        worker.start()
        self._active_workers[sid] = worker


scheduler_engine = SchedulerEngine.instance()
