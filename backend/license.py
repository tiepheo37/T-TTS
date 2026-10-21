"""backend/license.py — HỆ THỐNG XÁC MINH VÀ QUẢN LÝ BẢN QUYỀN OFFLINE T-TTS v1.0.1
===================================================================================
Tính năng cốt lõi:
1. Xác minh chữ ký số Ed25519 hoàn toàn offline (chỉ chứa Public Key, không có Private Key).
2. Tạo Mã Máy (Machine ID) ổn định, độc lập với tên tài khoản và thư mục cài đặt.
3. Hỗ trợ đúng 3 thời hạn:
   - KEY-1D  (24 giờ   - 86.400 giây)
   - KEY-7D  (168 giờ  - 604.800 giây)
   - KEY-30D (720 giờ  - 2.592.000 giây)
   Thời hạn tính chính xác từ thời điểm kích hoạt thành công đầu tiên trên máy.
4. Cơ chế chống lùi thời gian hệ thống (Anti-Clock-Rollback) nhiều lớp:
   - Theo dõi mốc thời gian hợp lệ gần nhất (last_valid_time).
   - Bộ đếm thời gian đơn điệu hệ điều hành (OS Monotonic / GetTickCount64).
   - Bảo vệ tính toàn vẹn trạng thái bằng HMAC-SHA256 liên kết phần cứng máy tính.
   - Lưu trữ dự phòng đa vị trí (AppData, Shadow Vault, Windows Registry).
   - Ngăn chặn nhập lại key cũ sau khi đã hết hạn.
5. Cung cấp API và hàm chặn truy cập cho các chức năng chính khi hết hạn hoặc bị khóa.
"""

from __future__ import annotations

import base64
import calendar
import ctypes
import datetime
import hashlib
import hmac
import json
import logging
import os
import platform
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

# Đảm bảo mã hóa UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("T_TTS_License")

# ==============================================================================
# 1. KHÓA CÔNG KHAI MASTER ED25519 (CHỈ CHỨA PUBLIC KEY - HOÀN TOÀN AN TOÀN)
# ==============================================================================
# Khóa công khai này tương ứng với master_private.pem của nhà phát triển.
# Tuyệt đối không chứa private key trong toàn bộ mã nguồn phân phối.
MASTER_PUBLIC_KEY_B64 = "NK/Fn9eXs78hKfVOGhLPtIW6IOJevBdjY8Et8CIvdtQ="


def calculate_6_months_expiration(start_timestamp: float) -> float:
    """Tính mốc thời gian hết hạn sau đúng 6 tháng theo ngày lịch từ mốc kích hoạt.

    Quy tắc:
    - Bắt đầu tính từ thời điểm kích hoạt thành công đầu tiên.
    - Chuyển sang ngày theo múi giờ địa phương.
    - Cộng 6 tháng vào trường tháng.
    - Nếu tháng đích có số ngày ít hơn ngày kích hoạt, lấy ngày cuối cùng của tháng đó.
    - Giữ nguyên giờ, phút, giây của thời điểm kích hoạt.
    """
    dt = datetime.datetime.fromtimestamp(start_timestamp)
    target_year = dt.year + (dt.month + 6 - 1) // 12
    target_month = (dt.month + 6 - 1) % 12 + 1
    max_days_in_target = calendar.monthrange(target_year, target_month)[1]
    target_day = min(dt.day, max_days_in_target)
    target_dt = dt.replace(year=target_year, month=target_month, day=target_day)
    return target_dt.timestamp()


# 5 loại key bản quyền được hỗ trợ chính thức
VALID_PLANS = {
    "KEY-1D": {"hours": 24, "seconds": 24 * 3600, "name": "1 Ngày (24 giờ)", "type": "fixed_seconds"},
    "KEY-7D": {"hours": 168, "seconds": 168 * 3600, "name": "7 Ngày (168 giờ)", "type": "fixed_seconds"},
    "KEY-30D": {"hours": 720, "seconds": 720 * 3600, "name": "30 Ngày (720 giờ)", "type": "fixed_seconds"},
    "KEY-6M": {"months": 6, "name": "6 Tháng (Theo lịch)", "type": "calendar_6m"},
    "KEY-PERM": {"name": "Vĩnh viễn (Trọn đời)", "type": "permanent"},
}

# 6 trạng thái bản quyền chuẩn hoá theo yêu cầu
STATUS_UNACTIVATED = "unactivated"             # 1. Chưa kích hoạt
STATUS_ACTIVE = "active"                       # 2. Đang sử dụng hợp lệ
STATUS_EXPIRED = "expired"                     # 3. Hết hạn
STATUS_ROLLBACK = "rollback_detected"          # 4. Phát hiện lùi thời gian
STATUS_TAMPERED = "tampered"                   # 5. Giấy phép bị sửa / dữ liệu không hợp lệ
STATUS_MACHINE_MISMATCH = "machine_mismatch"   # 6. Key không đúng máy

STATUS_MESSAGES = {
    STATUS_UNACTIVATED: "Ứng dụng chưa được kích hoạt bản quyền. Vui lòng gửi Mã Máy cho nhà phát triển để nhận mã kích hoạt dùng thử.",
    STATUS_ACTIVE: "Bản quyền hợp lệ và đang hoạt động bình thường.",
    STATUS_EXPIRED: "Giấy phép dùng thử đã hết hạn. Vui lòng liên hệ nhà phát triển để nhận key mới để tiếp tục sử dụng.",
    STATUS_ROLLBACK: "CẢNH BÁO: Phát hiện thời gian hệ thống bị lùi hoặc bất thường. Ứng dụng đã bị khóa bảo vệ. Vui lòng hiệu chỉnh đúng giờ hệ thống và nhập key mới.",
    STATUS_TAMPERED: "CẢNH BÁO: Dữ liệu bản quyền bị can thiệp trái phép hoặc bị hỏng. Ứng dụng đã bị khóa bảo vệ. Vui lòng nhập key hợp lệ.",
    STATUS_MACHINE_MISMATCH: "Mã máy không trùng khớp. Key này được cấp cho một thiết bị máy tính khác.",
}


# ==============================================================================
# 2. XÁC ĐỊNH MÃ MÁY (MACHINE ID) ỔN ĐỊNH TRÊN WINDOWS
# ==============================================================================
_CACHED_MACHINE_ID: str | None = None


def get_machine_id() -> str:
    """Tạo mã máy ổn định duy nhất cho từng máy Windows.

    - Không phụ thuộc vào tên tài khoản người dùng hoặc đường dẫn cài đặt.
    - Không thu thập dữ liệu cá nhân không cần thiết.
    - Bền vững qua các lần khởi động lại máy hoặc đổi tên thư mục cài đặt.
    """
    global _CACHED_MACHINE_ID
    if _CACHED_MACHINE_ID is not None:
        return _CACHED_MACHINE_ID

    guid = ""
    # 1. Lấy MachineGuid từ Windows Registry (luôn cố định cho bản cài đặt Windows)
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                val, _ = winreg.QueryValueEx(key, "MachineGuid")
                if val:
                    guid = str(val).strip().lower()
        except Exception as e:
            logger.debug(f"Không thể đọc MachineGuid từ registry: {e}")

    # 2. Thu thập định danh phần cứng bộ xử lý / CPU
    cpu_info = ""
    try:
        cpu_info = platform.processor() or platform.machine()
    except Exception:
        pass

    # Nếu không đọc được registry (trường hợp cực hiếm), dùng định danh node mạng dự phòng
    if not guid:
        guid = platform.node() or "TTTS-DEFAULT-HOST"

    # Kết hợp và băm SHA-256 tạo mã định danh máy chuẩn hoá
    raw_combine = f"TTTS_HW_FINGERPRINT_V1::{guid}::{cpu_info}"
    digest = hashlib.sha256(raw_combine.encode("utf-8")).hexdigest().upper()

    # Định dạng dễ đọc: TTTS-XXXX-XXXX-XXXX-XXXX
    formatted_id = f"TTTS-{digest[0:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:16]}"
    _CACHED_MACHINE_ID = formatted_id
    return _CACHED_MACHINE_ID


# ==============================================================================
# 3. QUẢN LÝ LƯU TRỮ VÀ TOÀN VẸN DỮ LIỆU BẢN QUYỀN
# ==============================================================================
def _get_storage_locations() -> tuple[Path, Path]:
    """Trả về các vị trí lưu trữ trạng thái bản quyền (chính và dự phòng)."""
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        roaming_app = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        local_app = str(Path.home() / ".local" / "share")
        roaming_app = str(Path.home() / ".config")

    primary_dir = Path(local_app) / "T-TTS"
    secondary_dir = Path(roaming_app) / "T-TTS"

    primary_dir.mkdir(parents=True, exist_ok=True)
    secondary_dir.mkdir(parents=True, exist_ok=True)

    primary_file = primary_dir / "license_state.json"
    secondary_file = secondary_dir / ".sys_lic_vault.dat"
    return primary_file, secondary_file


def _derive_machine_hmac_key(machine_id: str) -> bytes:
    """Tạo khóa HMAC bí mật liên kết chặt chẽ với phần cứng máy tính."""
    seed = f"TTTS_OFFLINE_LICENSE_HMAC_SALT_2026_{machine_id}_INTEGRITY"
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _calculate_state_hmac(state_dict: dict, machine_id: str) -> str:
    """Tính toán chữ ký HMAC-SHA256 trên nội dung trạng thái bản quyền."""
    key = _derive_machine_hmac_key(machine_id)
    # Loại bỏ trường hmac khi tính toán
    clean_dict = {k: v for k, v in state_dict.items() if k != "hmac"}
    canonical_data = json.dumps(clean_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, canonical_data, hashlib.sha256).hexdigest()


# ==============================================================================
# 4. HỖ TRỢ REGISTRY DỰ PHÒNG TRÊN WINDOWS
# ==============================================================================
REG_KEY_PATH = r"Software\T-TTS\License"


def _save_to_registry(data_str: str) -> None:
    """Lưu trữ dự phòng trạng thái bản quyền vào Windows Registry."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH) as key:
            winreg.SetValueEx(key, "StateVault", 0, winreg.REG_SZ, data_str)
    except Exception as e:
        logger.debug(f"Không thể ghi vào Windows Registry: {e}")


def _load_from_registry() -> str | None:
    """Đọc dữ liệu dự phòng từ Windows Registry."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH) as key:
            val, _ = winreg.QueryValueEx(key, "StateVault")
            return str(val) if val else None
    except Exception:
        return None


# ==============================================================================
# 5. LỚP ĐIỀU PHỐI XÁC MINH VÀ QUẢN LÝ BẢN QUYỀN (LICENSE MANAGER)
# ==============================================================================
class LicenseManager:
    """Bộ quản lý bản quyền offline cho T-TTS v1.0.1."""

    def __init__(self, public_key_b64: str = MASTER_PUBLIC_KEY_B64, simulated_time_offset: float = 0.0) -> None:
        self.public_key_b64 = public_key_b64
        self.machine_id = get_machine_id()
        self.lock = threading.RLock()

        self.primary_file, self.secondary_file = _get_storage_locations()

        # Biến theo dõi đơn điệu trong phiên chạy hiện tại
        self._last_monotonic = time.monotonic()
        self._simulated_time_offset: float = simulated_time_offset  # Dành cho test suite giả lập thời gian trôi

        # Tải khóa công khai Ed25519
        self._ed25519_public_key = self._load_embedded_public_key()

        # Nạp trạng thái hiện tại từ đĩa
        self._state: dict[str, Any] = self._load_state()

        # Khởi động tiểu trình giám sát ngầm kiểm tra định kỳ (watchdog)
        self._stop_watchdog = threading.Event()
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def _load_embedded_public_key(self):
        """Khởi tạo đối tượng xác minh Ed25519 từ Public Key nhúng sẵn."""
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            raw_pub = base64.b64decode(self.public_key_b64)
            return ed25519.Ed25519PublicKey.from_public_bytes(raw_pub)
        except Exception as e:
            logger.error(f"Lỗi khởi tạo Ed25519 public key: {e}")
            return None

    def _get_current_time(self) -> float:
        """Lấy thời gian hiện tại có tính đến offset mô phỏng kiểm thử (nếu có)."""
        base_time = time.time()
        # Chỉ áp dụng giả lập khi có biến môi trường T_TTS_LICENSE_TEST_MODE
        if os.environ.get("T_TTS_LICENSE_TEST_MODE") == "1":
            return base_time + self._simulated_time_offset
        return base_time

    def simulate_time_travel(self, seconds_forward: float) -> None:
        """Hàm kiểm thử: mô phỏng thời gian trôi về phía trước có kiểm soát.

        Tuyệt đối không hoạt động trong môi trường sản phẩm thực tế nếu không bật cờ TEST_MODE.
        """
        if os.environ.get("T_TTS_LICENSE_TEST_MODE") != "1":
            raise RuntimeError("Chỉ được phép gọi simulate_time_travel trong môi trường kiểm thử!")
        with self.lock:
            self._simulated_time_offset += seconds_forward
            self._check_and_update_state()

    def _create_empty_state(self) -> dict:
        """Tạo cấu trúc trạng thái mặc định khi chưa kích hoạt."""
        return {
            "v": 1,
            "machine_id": self.machine_id,
            "status": STATUS_UNACTIVATED,
            "license_id": None,
            "plan": None,
            "duration_hours": None,
            "first_activated_at": None,
            "expires_at": None,
            "last_valid_time": self._get_current_time(),
            "accumulated_runtime": 0.0,
            "key_string": None,
            "used_licenses": {},  # Lưu lịch sử các key đã từng kích hoạt để chặn tái sử dụng key cũ
            "hmac": "",
        }

    def _load_state(self) -> dict:
        """Nạp trạng thái bản quyền từ vị trí chính, dự phòng hoặc Registry."""
        state = None
        loaded_source = None

        # 1. Thử đọc từ tệp chính
        if self.primary_file.exists():
            try:
                content = self.primary_file.read_text(encoding="utf-8")
                state = json.loads(content)
                loaded_source = "primary"
            except Exception as e:
                logger.warning(f"Không thể đọc tệp trạng thái chính: {e}")

        # 2. Thử đọc từ tệp dự phòng (shadow vault)
        if state is None and self.secondary_file.exists():
            try:
                content = self.secondary_file.read_text(encoding="utf-8")
                state = json.loads(content)
                loaded_source = "secondary"
            except Exception as e:
                logger.warning(f"Không thể đọc shadow vault: {e}")

        # 3. Thử đọc từ Windows Registry
        if state is None:
            reg_content = _load_from_registry()
            if reg_content:
                try:
                    state = json.loads(reg_content)
                    loaded_source = "registry"
                except Exception:
                    pass

        # Nếu hoàn toàn chưa có dữ liệu nào: khởi tạo trạng thái mới chưa kích hoạt
        if state is None:
            new_st = self._create_empty_state()
            new_st["hmac"] = _calculate_state_hmac(new_st, self.machine_id)
            self._save_state_to_all(new_st)
            return new_st

        # Kiểm tra tính toàn vẹn bằng HMAC
        stored_hmac = state.get("hmac", "")
        expected_hmac = _calculate_state_hmac(state, self.machine_id)

        if not stored_hmac or not hmac.compare_digest(stored_hmac, expected_hmac):
            logger.error("Chữ ký HMAC của tệp trạng thái không khớp! Phát hiện dữ liệu bị can thiệp.")
            state["status"] = STATUS_TAMPERED
            return state

        # Kiểm tra mã máy lưu trong tệp có khớp với máy hiện tại không
        if state.get("machine_id") != self.machine_id:
            logger.warning("Mã máy trong dữ liệu trạng thái không khớp với máy hiện tại.")
            state["status"] = STATUS_MACHINE_MISMATCH
            return state

        # Nếu đọc thành công từ nguồn dự phòng, phục hồi lại các nguồn khác
        if loaded_source != "primary":
            self._save_state_to_all(state)

        return state

    def _save_state_to_all(self, state: dict) -> None:
        """Ghi trạng thái an toàn vào toàn bộ các vị trí lưu trữ có tính chữ ký HMAC."""
        state["hmac"] = _calculate_state_hmac(state, self.machine_id)
        raw_json = json.dumps(state, indent=2, ensure_ascii=False)

        # 1. Ghi tệp chính
        try:
            self.primary_file.parent.mkdir(parents=True, exist_ok=True)
            self.primary_file.write_text(raw_json, encoding="utf-8")
        except Exception as e:
            logger.error(f"Lỗi ghi tệp trạng thái chính: {e}")

        # 2. Ghi tệp dự phòng
        try:
            self.secondary_file.parent.mkdir(parents=True, exist_ok=True)
            self.secondary_file.write_text(raw_json, encoding="utf-8")
        except Exception as e:
            logger.debug(f"Lỗi ghi shadow vault: {e}")

        # 3. Ghi Windows Registry
        _save_to_registry(raw_json)

    def _check_and_update_state(self) -> dict:
        """Kiểm tra thời gian hệ thống và cập nhật trạng thái bản quyền (với khóa thread-safe)."""
        with self.lock:
            state = self._state

            # Nếu trạng thái đang bị khoá vĩnh viễn (do rollback, tampered, v.v.), giữ nguyên
            if state.get("status") in (STATUS_TAMPERED, STATUS_ROLLBACK):
                return state

            # Nếu chưa kích hoạt, không cần kiểm tra thời hạn
            if state.get("status") == STATUS_UNACTIVATED:
                return state

            now_wall = self._get_current_time()
            now_mono = time.monotonic()
            last_valid = state.get("last_valid_time") or now_wall
            first_act = state.get("first_activated_at") or now_wall
            plan_code = state.get("plan")
            is_permanent = (plan_code == "KEY-PERM")
            expires_at = state.get("expires_at")

            # -------------------------------------------------------------
            # PHÁT HIỆN LÙI THỜI GIAN HỆ THỐNG (ANTI-ROLLBACK DETECTION)
            # Dung sai 120 giây để thích ứng đồng bộ NTP tự động của Windows
            # -------------------------------------------------------------
            TOLERANCE = 120.0

            # Kiểm tra 1: Thời gian hệ thống hiện tại nhỏ hơn mốc thời gian hợp lệ gần nhất
            if now_wall < (last_valid - TOLERANCE):
                logger.error(
                    f"PHÁT HIỆN LÙI ĐỒNG HỒ WINDOWS: hiện tại={now_wall:.1f}, "
                    f"mốc hợp lệ gần nhất={last_valid:.1f} (chênh lệch {last_valid - now_wall:.1f}s)"
                )
                state["status"] = STATUS_ROLLBACK
                self._save_state_to_all(state)
                return state

            # Kiểm tra 2: Thời gian hệ thống hiện tại nhỏ hơn ngày kích hoạt đầu tiên
            if now_wall < (first_act - TOLERANCE):
                logger.error(f"PHÁT HIỆN THỜI GIAN NHỎ HƠN NGÀY KÍCH HOẠT ĐẦU TIÊN: {now_wall:.1f} < {first_act:.1f}")
                state["status"] = STATUS_ROLLBACK
                self._save_state_to_all(state)
                return state

            # Kiểm tra 3: Phát hiện lùi giờ trong cùng phiên chạy qua bộ đếm đơn điệu (monotonic)
            mono_delta = now_mono - self._last_monotonic
            if mono_delta > 0:
                wall_delta = now_wall - last_valid
                # Nếu monotonic đã tăng ít nhất 30 giây nhưng wall clock lại giật lùi
                if mono_delta >= 30.0 and wall_delta < -10.0:
                    logger.error(f"PHÁT HIỆN LÙI ĐỒNG HỒ TRONG PHIÊN CHẠY (Monotonic={mono_delta:.1f}s, Wall={wall_delta:.1f}s)")
                    state["status"] = STATUS_ROLLBACK
                    self._save_state_to_all(state)
                    return state

            # Cập nhật mốc đơn điệu
            self._last_monotonic = now_mono

            # -------------------------------------------------------------
            # KIỂM TRA HẾT HẠN SỬ DỤNG (Chỉ áp dụng cho gói có thời hạn)
            # -------------------------------------------------------------
            if not is_permanent and expires_at is not None and now_wall >= expires_at:
                if state.get("status") != STATUS_EXPIRED:
                    logger.info(f"Giấy phép {state.get('license_id')} đã hết hạn vào {expires_at}")
                    state["status"] = STATUS_EXPIRED
                    # Đánh dấu vào danh sách used_licenses để không cho kích hoạt lại key này
                    lid = state.get("license_id")
                    if lid:
                        if "used_licenses" not in state:
                            state["used_licenses"] = {}
                        state["used_licenses"][lid] = {
                            "expired": True,
                            "expires_at": expires_at,
                            "plan": state.get("plan"),
                        }
                    self._save_state_to_all(state)
                return state

            # Nếu còn hạn và hợp lệ: cập nhật last_valid_time tiến dần về phía trước
            if now_wall > last_valid:
                state["last_valid_time"] = now_wall

            state["status"] = STATUS_ACTIVE
            self._save_state_to_all(state)
            return state

    def _watchdog_loop(self) -> None:
        """Vòng lặp chạy ngầm kiểm tra giấy phép mỗi 20 giây."""
        while not self._stop_watchdog.is_set():
            try:
                self._check_and_update_state()
            except Exception as e:
                logger.debug(f"Lỗi kiểm tra watchdog: {e}")
            self._stop_watchdog.wait(20.0)

    def is_active(self) -> bool:
        """Kiểm tra giấy phép hiện tại có đang hoạt động hợp lệ hay không."""
        st = self._check_and_update_state()
        return st.get("status") == STATUS_ACTIVE

    def get_status_info(self) -> dict:
        """Trả về toàn bộ thông tin trạng thái chi tiết để giao diện hiển thị cho người dùng."""
        st = self._check_and_update_state()
        curr_time = self._get_current_time()
        status_code = st.get("status", STATUS_UNACTIVATED)
        plan_code = st.get("plan")
        is_permanent = (plan_code == "KEY-PERM")

        expires_at = st.get("expires_at")
        rem_sec = 0.0

        if is_permanent and status_code == STATUS_ACTIVE:
            rem_str = "Vĩnh viễn (Không giới hạn)"
            exp_readable = "Vĩnh viễn (Trọn đời)"
            rem_sec = -1.0
        elif expires_at and curr_time < expires_at:
            rem_sec = max(0.0, expires_at - curr_time)

            # Định dạng thời gian còn lại (ngày, giờ, phút)
            days = int(rem_sec // 86400)
            hours = int((rem_sec % 86400) // 3600)
            mins = int((rem_sec % 3600) // 60)
            secs = int(rem_sec % 60)

            if days > 0:
                rem_str = f"{days} ngày {hours} giờ {mins} phút"
            elif hours > 0:
                rem_str = f"{hours} giờ {mins} phút {secs} giây"
            elif mins > 0:
                rem_str = f"{mins} phút {secs} giây"
            elif rem_sec > 0:
                rem_str = f"{secs} giây"
            else:
                rem_str = "0 phút (Đã hết hạn)"

            exp_readable = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expires_at))
        else:
            if status_code == STATUS_EXPIRED:
                rem_str = "0 phút (Đã hết hạn)"
            elif status_code == STATUS_UNACTIVATED:
                rem_str = "Chưa kích hoạt"
            else:
                rem_str = "Bị khóa"
            exp_readable = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expires_at)) if expires_at else "Chưa có"

        first_act_readable = ""
        if st.get("first_activated_at"):
            first_act_readable = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st["first_activated_at"]))

        return {
            "machine_id": self.machine_id,
            "status": status_code,
            "is_active": (status_code == STATUS_ACTIVE),
            "is_locked": (status_code != STATUS_ACTIVE),
            "status_message": STATUS_MESSAGES.get(status_code, "Trạng thái không xác định."),
            "license_id": st.get("license_id"),
            "plan": st.get("plan"),
            "duration_hours": st.get("duration_hours"),
            "first_activated_at": st.get("first_activated_at"),
            "first_activated_readable": first_act_readable,
            "expires_at": expires_at,
            "expires_readable": exp_readable,
            "remaining_seconds": int(rem_sec),
            "remaining_formatted": rem_str,
        }

    # ==========================================================================
    # 6. KÍCH HOẠT GIẤY PHÉP BẰNG KEY MỚI
    # ==========================================================================
    def activate(self, raw_key_string: str) -> tuple[bool, str, dict]:
        """Kích hoạt bản quyền bằng chuỗi key do nhà phát triển cấp.

        Trả về: (thành công: bool, thông báo: str, thông tin_chi_tiết: dict)
        """
        raw = re.sub(r"\s+", "", (raw_key_string or ""))
        if not raw:
            return False, "Vui lòng nhập chuỗi key bản quyền.", {}

        # 1. Kiểm tra cấu trúc key
        if not raw.startswith("TTTS-LIC1-"):
            return False, "Định dạng key không đúng (phải bắt đầu bằng 'TTTS-LIC1-').", {}

        token = raw[len("TTTS-LIC1-"):]
        if "." not in token:
            return False, "Key bản quyền bị thiếu phần chữ ký số xác thực.", {}

        payload_b64, sig_b64 = token.split(".", 1)

        def _pad_b64(s: str) -> bytes:
            missing = len(s) % 4
            if missing:
                s += "=" * (4 - missing)
            return base64.urlsafe_b64decode(s.encode("ascii"))

        try:
            canonical_bytes = _pad_b64(payload_b64)
            signature_bytes = _pad_b64(sig_b64)
        except Exception:
            return False, "Dữ liệu mã hoá Base64 trong key bị hỏng hoặc không giải mã được.", {}

        # 2. Xác minh chữ ký số Ed25519 với khóa công khai
        if self._ed25519_public_key is None:
            return False, "Lỗi nội bộ: Không thể khởi tạo bộ xác minh chữ ký số Ed25519.", {}

        try:
            self._ed25519_public_key.verify(signature_bytes, canonical_bytes)
        except Exception:
            return False, "Chữ ký số Ed25519 KHÔNG HỢP LỆ! Key đã bị sửa đổi nội dung hoặc không do nhà phát triển ký.", {}

        # 3. Đọc dữ liệu JSON payload
        try:
            payload = json.loads(canonical_bytes.decode("utf-8"))
        except Exception as e:
            return False, f"Dữ liệu JSON trong giấy phép bị lỗi cấu trúc: {e}", {}

        target_mid = (payload.get("mid") or "").strip().upper()
        current_mid = self.machine_id.strip().upper()

        # 4. Kiểm tra mã máy (Hardware Lock)
        if target_mid != current_mid:
            return (
                False,
                f"Key này được cấp riêng cho máy [{target_mid}], không khớp với máy của bạn [{current_mid}].",
                {"expected_mid": current_mid, "license_mid": target_mid},
            )

        # 5. Kiểm tra thời hạn cấp phép (1D, 7D, 30D, 6M, PERM)
        plan_code = (payload.get("plan") or "").strip().upper()
        if plan_code not in VALID_PLANS:
            return False, f"Gói bản quyền '{plan_code}' không hợp lệ. Hỗ trợ: KEY-1D, KEY-7D, KEY-30D, KEY-6M, KEY-PERM.", {}

        plan_info = VALID_PLANS[plan_code]
        lic_id = payload.get("lid") or ""

        with self.lock:
            state = self._state
            used_licenses = state.get("used_licenses", {})

            # 6. Kiểm tra xem key này đã từng được sử dụng trước đây hay chưa
            if lic_id and lic_id in used_licenses:
                past_info = used_licenses[lic_id]
                if past_info.get("expired"):
                    return (
                        False,
                        f"Key này ({lic_id}) đã từng được kích hoạt và đã hết hạn trên máy này. Không được phép tái sử dụng key cũ.",
                        {},
                    )

            # Nếu key đang là key hiện tại và vẫn còn hạn, giữ nguyên mốc kích hoạt ban đầu
            now_wall = self._get_current_time()
            if state.get("license_id") == lic_id and state.get("first_activated_at"):
                first_activated_at = state["first_activated_at"]
                expires_at = state.get("expires_at")
                duration_hours = state.get("duration_hours")
            else:
                # Key mới hoàn toàn: thời hạn tính chính xác từ thời điểm kích hoạt thành công đầu tiên
                first_activated_at = now_wall
                if plan_info["type"] == "fixed_seconds":
                    duration_seconds = plan_info["seconds"]
                    duration_hours = plan_info["hours"]
                    expires_at = first_activated_at + duration_seconds
                elif plan_info["type"] == "calendar_6m":
                    expires_at = calculate_6_months_expiration(first_activated_at)
                    duration_hours = int(round((expires_at - first_activated_at) / 3600))
                elif plan_info["type"] == "permanent":
                    expires_at = None
                    duration_hours = None
                else:
                    expires_at = None
                    duration_hours = None

            # Cập nhật trạng thái mới
            state["license_id"] = lic_id
            state["plan"] = plan_code
            state["duration_hours"] = duration_hours
            state["first_activated_at"] = first_activated_at
            state["expires_at"] = expires_at
            state["last_valid_time"] = now_wall
            state["status"] = STATUS_ACTIVE
            state["key_string"] = raw

            if "used_licenses" not in state:
                state["used_licenses"] = {}
            state["used_licenses"][lic_id] = {
                "first_activated_at": first_activated_at,
                "expires_at": expires_at,
                "plan": plan_code,
                "expired": False,
            }

            self._last_monotonic = time.monotonic()
            self._save_state_to_all(state)

        logger.info(f"Kích hoạt thành công key {plan_code} cho máy {current_mid}. Hết hạn vào: {expires_at}")
        return True, f"Kích hoạt thành công gói {plan_info['name']}! Ứng dụng đã được mở khóa đầy đủ chức năng.", self.get_status_info()


# Khởi tạo một singleton instance duy nhất cho toàn bộ ứng dụng
license_manager = LicenseManager()
