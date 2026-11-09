"""gui/notification_hub.py — TRUNG TÂM PHÁT TÍN HIỆU THÔNG BÁO TẬP TRUNG
=============================================================================
Sử dụng Qt Signals/Slots để phát thông báo toàn cục:
- Hoàn thành tác vụ
- Lỗi xử lý
- Tiến trình
- Lịch phát thanh bị bỏ lỡ
- Có bản cập nhật phần mềm mới
"""

from __future__ import annotations

from typing import Any, Dict
from PySide6.QtCore import QObject, Signal


class NotificationHub(QObject):
    """Trung tâm thông báo toàn cục ứng dụng."""

    notify_info = Signal(str, str)            # title, message
    notify_success = Signal(str, str)         # title, message
    notify_warning = Signal(str, str)         # title, message
    notify_error = Signal(str, str)           # title, message
    notify_schedule_missed = Signal(dict)     # schedule_info
    notify_schedule_due = Signal(dict)        # schedule_info
    notify_update_ready = Signal(dict)        # update_info

    _instance = None

    @classmethod
    def instance(cls) -> NotificationHub:
        if cls._instance is None:
            cls._instance = NotificationHub()
        return cls._instance


notification_hub = NotificationHub.instance()
