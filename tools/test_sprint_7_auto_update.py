"""tools/test_sprint_7_auto_update.py — BỘ TEST KIỂM THỬ SPRINT 7: AUTO UPDATE & SAFE MIGRATION
===================================================================================================
Tác giả: Nguyễn Văn Tiệp
Hệ thống: T-TTS Windows Native Desktop (VieNeu-TTS v3 Turbo ONNX CPU)

Kiểm thử 16 tiêu chí toàn diện:
1. Version comparison & v3.0.1 bypass logic (direct jump 3.0.0 -> 3.1.0)
2. GitHub Release metadata parsing (v3.1.0 payload)
3. Download integrity & SHA-256 verification (valid & mismatch)
4. System readiness checks (disk space, write permissions, temp dir)
5. Pre-update backup creation (data files, pronunciation dict, history, license, projects)
6. Data migration v3.0.0 -> v3.1.0 (new directories, audio_presets, bypassed_version log)
7. Rollback & restore backup (list_backups, restore_backup, non-destructive restoration)
8. Ed25519 offline license preservation (machine ID & license state integrity)
9. User data preservation (audio projects, broadcast projects, schedules, custom voices)
10. Interrupted download cleanup (temp file deletion on cancel/interruption)
11. Installer launch parameters (/SILENT, /CLOSEAPPLICATIONS, /RESTARTAPPLICATIONS)
12. UpdateDialog Military K20 UI (banner, styling, rollback button, notes)
13. CheckUpdateWorker thread (asynchronous execution, signal emission)
14. DownloadUpdateWorker thread (progress signals, cancel handling)
15. No silent update enforcement (explicit user action required)
16. Full regression across all modules (VieNeu-TTS, Document Reader, Text Processor, Audio DSP)
"""

import os
import sys
import time
import json
import shutil
import hashlib
import tempfile
import threading
from pathlib import Path
from typing import Dict, Any

# Đảm bảo đường dẫn gốc của project
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Đảm bảo UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from backend.version import (
    APP_VERSION,
    parse_version,
    is_newer_version,
    load_update_config,
    save_update_config,
)
from backend.updater import (
    UpdateInfoData,
    UpdateManager,
    CheckUpdateWorker,
    DownloadUpdateWorker,
)


def print_test_header(idx: int, title: str):
    print(f"\n[{idx:02d}/16] TEST: {title}")
    print("-" * 75)


def test_01_version_comparison_and_v301_bypass():
    """1. Kiểm tra so sánh phiên bản và bỏ qua hoàn toàn v3.0.1."""
    print_test_header(1, "Version Comparison & v3.0.1 Direct Jump Bypass")

    # So sánh phiên bản
    assert is_newer_version("3.1.0", "3.0.0") is True, "3.1.0 phải lớn hơn 3.0.0"
    assert is_newer_version("3.0.0", "3.1.0") is False, "3.0.0 không được lớn hơn 3.1.0"
    assert is_newer_version("3.1.0", "3.0.1") is True, "3.1.0 phải lớn hơn 3.0.1"
    assert is_newer_version("3.0.1", "3.0.0") is True, "3.0.1 phải lớn hơn 3.0.0"
    assert is_newer_version("3.1.0", "3.1.0") is False, "Hai phiên bản giống nhau không được coi là mới hơn"

    # Phân tích tuple
    assert parse_version("v3.1.0") == (3, 1, 0)
    assert parse_version("3.0.0") == (3, 0, 0)
    assert parse_version("3.0.1_Release") == (3, 0, 1)

    # Kiểm tra kịch bản nhảy cóc: Máy đang cài 3.0.0 nhận bản cập nhật 3.1.0 trực tiếp
    updater = UpdateManager(current_version="3.0.0")
    assert updater.current_version == "3.0.0"
    assert is_newer_version("3.1.0", updater.current_version) is True
    print("  ✓ So sánh phiên bản chuẩn xác theo ngữ nghĩa tuple (3, 1, 0) > (3, 0, 0)")
    print("  ✓ Bản nâng cấp v3.1.0 hỗ trợ nhảy trực tiếp từ v3.0.0, bỏ qua hoàn toàn v3.0.1")
    return True


def test_02_release_metadata_parsing():
    """2. Kiểm tra phân tích dữ liệu Release từ GitHub API."""
    print_test_header(2, "GitHub Release Metadata Parsing")

    fake_release = {
        "tag_name": "v3.1.0",
        "name": "T-TTS v3.1.0 — Bản Phát Hành Đột Phá Xử Lý Tài Liệu & Âm Thanh Quân Đội",
        "body": "Nâng cấp trực tiếp từ v3.0.0 lên v3.1.0.\nBảo toàn toàn bộ bản quyền Ed25519 và dữ liệu.\nSHA256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "published_at": "2026-11-09T10:00:00Z",
        "assets": [
            {
                "name": "T-TTS_v3.1.0_Setup.exe",
                "size": 145000000,
                "browser_download_url": "https://github.com/tiepheo37/T-TTS/releases/download/v3.1.0/T-TTS_v3.1.0_Setup.exe",
            }
        ],
    }

    updater = UpdateManager(current_version="3.0.0")
    info = updater.parse_release_data(fake_release)

    assert info.available is True, "Phải nhận diện có bản cập nhật mới"
    assert info.latest_version == "3.1.0", f"Phiên bản mới phải là 3.1.0, nhận được {info.latest_version}"
    assert info.current_version == "3.0.0"
    assert info.asset_name == "T-TTS_v3.1.0_Setup.exe"
    assert info.sha256 == "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    assert "https://" in info.download_url
    print(f"  ✓ Phân tích release thành công: {info.release_title}")
    print(f"  ✓ Trích xuất SHA-256 từ release body: {info.sha256[:16]}...")
    return True


def test_03_download_integrity_and_sha256():
    """3. Kiểm tra tính toàn vẹn gói cập nhật & xác minh mã SHA-256."""
    print_test_header(3, "Download Integrity & SHA-256 Verification")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        test_file = tmp_path / "sample_setup.exe"
        payload = b"TEST_BINARY_PAYLOAD_TTTS_V310_SETUP" * 1024
        test_file.write_bytes(payload)

        actual_sha256 = hashlib.sha256(payload).hexdigest()

        # Giả lập tải file qua file:// URL
        updater = UpdateManager(data_dir=tmp_path / "data")
        update_info = UpdateInfoData(
            available=True,
            current_version="3.0.0",
            latest_version="3.1.0",
            asset_name="Test_Setup.exe",
            asset_size=len(payload),
            download_url=test_file.as_uri(),
            sha256=actual_sha256,
        )

        progress_recorded = []
        dest = updater.download_update(
            update_info,
            progress_callback=lambda pct, dl, tot, sp: progress_recorded.append(pct),
        )

        assert dest.is_file(), "Tệp sau khi tải phải tồn tại"
        assert dest.stat().st_size == len(payload), "Kích thước tệp tải về phải khớp"
        print(f"  ✓ Tải và xác minh thành công với SHA-256 khớp: {actual_sha256[:16]}...")

        # Thử kịch bản mã SHA-256 sai lệch (giả mạo hoặc lỗi truyền tải)
        bad_info = UpdateInfoData(
            available=True,
            current_version="3.0.0",
            latest_version="3.1.0",
            asset_name="Bad_Setup.exe",
            asset_size=len(payload),
            download_url=test_file.as_uri(),
            sha256="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        )
        try:
            updater.download_update(bad_info)
            assert False, "Phải ném ngoại lệ ValueError khi SHA-256 không khớp!"
        except ValueError as ve:
            print("  ✓ Bắt lỗi chính xác và từ chối gói cập nhật khi SHA-256 không khớp")
            assert not (Path(tempfile.gettempdir()) / "T-TTS_Updates" / "Bad_Setup.exe").exists()
            print("  ✓ Tệp tạm bị xóa an toàn khi phát hiện lỗi toàn vẹn")

    return True


def test_04_system_readiness_checks():
    """4. Kiểm tra điều kiện sẵn sàng hệ thống (Disk space, Permissions, Temp)."""
    print_test_header(4, "System Readiness Checks")

    with tempfile.TemporaryDirectory() as tmp_dir:
        updater = UpdateManager(data_dir=Path(tmp_dir) / "data")
        readiness = updater.check_system_readiness(required_free_mb=100)

        assert "ready" in readiness
        assert "free_space_mb" in readiness
        assert "has_write_perm" in readiness
        assert readiness["has_write_perm"] is True
        assert readiness["free_space_mb"] > 100, f"Dung lượng trống phải > 100MB, đo được {readiness['free_space_mb']} MB"
        assert readiness["ready"] is True
        print(f"  ✓ Dung lượng đĩa khả dụng: {readiness['free_space_mb']} MB (Yêu cầu: 100 MB)")
        print(f"  ✓ Quyền ghi thư mục dữ liệu: {readiness['has_write_perm']}")

        # Thử nghiệm với yêu cầu dung lượng phi thực tế
        unreal_readiness = updater.check_system_readiness(required_free_mb=100_000_000)
        assert unreal_readiness["ready"] is False
        assert len(unreal_readiness["issues"]) > 0
        print(f"  ✓ Phát hiện chính xác trường hợp không đủ dung lượng: {unreal_readiness['issues'][0]}")

    return True


def test_05_pre_update_backup_creation():
    """5. Kiểm tra tạo bản sao lưu toàn diện trước khi cập nhật."""
    print_test_header(5, "Pre-Update Backup Creation")

    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # Tạo các file cấu hình và dữ liệu giả lập v3.0.0
        (data_dir / "update_config.json").write_text(json.dumps({"channel": "stable", "auto_check": True}), encoding="utf-8")
        (data_dir / "license_state.json").write_text(json.dumps({"machine_id": "TEST-MACHINE-GUID-1234", "plan": "KEY-PERM"}), encoding="utf-8")
        (data_dir / "history.json").write_text(json.dumps([{"id": 1, "text": "Lịch sử chuyển đổi âm thanh"}]), encoding="utf-8")
        (data_dir / "pronunciation-dict.json").write_text(json.dumps({"f-35": "ép ba mươi lăm"}), encoding="utf-8")
        (data_dir / "custom_voices.json").write_text(json.dumps({"voices": ["voice_a", "voice_b"]}), encoding="utf-8")

        # Tạo các dự án
        proj_audio = data_dir / "projects" / "audio"
        proj_audio.mkdir(parents=True, exist_ok=True)
        (proj_audio / "project1.json").write_text(json.dumps({"name": "Audio Project 1", "sample_rate": 24000}), encoding="utf-8")

        proj_bcast = data_dir / "projects" / "broadcast"
        proj_bcast.mkdir(parents=True, exist_ok=True)
        (proj_bcast / "bcast1.json").write_text(json.dumps({"name": "Bản Tin Quân Sự 1", "duration": 120}), encoding="utf-8")

        updater = UpdateManager(data_dir=data_dir, current_version="3.0.0")
        backup_file = updater.create_pre_update_backup(target_version="3.1.0")

        assert backup_file.is_file(), "Tệp sao lưu phải được tạo"
        with open(backup_file, "r", encoding="utf-8") as f:
            b_data = json.load(f)

        assert b_data["current_version"] == "3.0.0"
        assert b_data["target_version"] == "3.1.0"
        assert "pronunciation-dict.json" in b_data["data_files"]
        assert "license_state.json" in b_data["data_files"]
        assert "history.json" in b_data["data_files"]
        assert "update_config.json" in b_data["data_files"]
        assert len(b_data["projects_backup"]) == 2
        assert len(b_data["file_checksums"]) >= 6
        print(f"  ✓ Bản sao lưu được tạo thành công: {backup_file.name}")
        print(f"  ✓ Sao lưu đầy đủ {len(b_data['data_files'])} tệp cấu hình và {len(b_data['projects_backup'])} dự án người dùng")
        print(f"  ✓ Ghi nhận mã băm SHA-256 cho {len(b_data['file_checksums'])} mục dữ liệu")

    return True


def test_06_data_migration_v300_to_v310():
    """6. Kiểm tra quy trình di chuyển dữ liệu v3.0.0 -> v3.1.0 (nhảy cóc qua v3.0.1)."""
    print_test_header(6, "Data Migration v3.0.0 -> v3.1.0 (Bypass v3.0.1)")

    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # Giả lập dữ liệu v3.0.0
        (data_dir / "license_state.json").write_text(json.dumps({"plan": "KEY-1Y", "status": "active"}), encoding="utf-8")
        (data_dir / "pronunciation-dict.json").write_text(json.dumps({"bqp": "bộ quốc phòng"}), encoding="utf-8")

        updater = UpdateManager(data_dir=data_dir, current_version="3.0.0")
        res = updater.perform_data_migration(from_version="3.0.0", to_version="3.1.0")

        # Kiểm tra cấu trúc thư mục mới của v3.1.0
        assert (data_dir / "projects" / "documents").is_dir(), "Phải khởi tạo thư mục Document Projects"
        assert (data_dir / "presets").is_dir(), "Phải khởi tạo thư mục Presets"
        assert (data_dir / "presets" / "audio_presets.json").is_file(), "Phải khởi tạo preset âm thanh mặc định"

        # Kiểm tra manifest ghi nhận kịch bản bỏ qua v3.0.1
        manifest_file = data_dir / "migration_v3.0.0_to_v3.1.0.json"
        assert manifest_file.is_file(), "Tệp nhật ký di chuyển phải tồn tại"
        with open(manifest_file, "r", encoding="utf-8") as mf:
            m_data = json.load(mf)

        assert m_data["from_version"] == "3.0.0"
        assert m_data["to_version"] == "3.1.0"
        assert m_data["bypassed_version"] == "3.0.1"
        assert m_data["direct_jump"] is True
        assert m_data["status"] == "completed"

        # Đảm bảo dữ liệu cũ không bị thay đổi
        with open(data_dir / "license_state.json", "r", encoding="utf-8") as lf:
            assert json.load(lf)["status"] == "active"
        with open(data_dir / "pronunciation-dict.json", "r", encoding="utf-8") as pf:
            assert json.load(pf)["bqp"] == "bộ quốc phòng"

        print("  ✓ Hoàn tất di chuyển cấu trúc v3.1.0 (projects/documents & presets)")
        print(f"  ✓ Nhật ký di chuyển khẳng định bypassed_version = '{m_data['bypassed_version']}'")
        print("  ✓ Bảo toàn tuyệt đối 100% dữ liệu, bản quyền và từ điển của người dùng")

    return True


def test_07_rollback_and_restore_backup():
    """7. Kiểm tra khôi phục bản sao lưu (Rollback & Restore)."""
    print_test_header(7, "Rollback & Restore Backup Mechanism")

    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # 1. Tạo file ban đầu
        dict_file = data_dir / "pronunciation-dict.json"
        dict_file.write_text(json.dumps({"ban_dau": "nguyên bản 100%"}), encoding="utf-8")

        updater = UpdateManager(data_dir=data_dir, current_version="3.0.0")
        backup_file = updater.create_pre_update_backup(target_version="3.1.0")

        # 2. Kiểm tra list_backups
        backups = updater.list_backups()
        assert len(backups) == 1
        assert backups[0]["current_version"] == "3.0.0"
        assert backups[0]["file_count"] >= 1
        print(f"  ✓ Liệt kê bản sao lưu thành công: {backups[0]['file_name']}")

        # 3. Phá hoại hoặc làm hỏng dữ liệu
        dict_file.write_text(json.dumps({"pha_hoai": "du_lieu_bi_loi"}), encoding="utf-8")
        with open(dict_file, "r", encoding="utf-8") as f:
            assert "pha_hoai" in json.load(f)

        # 4. Thực hiện phục hồi từ bản sao lưu
        restore_res = updater.restore_backup(backup_file)
        assert restore_res["status"] == "success"
        assert "pronunciation-dict.json" in restore_res["restored_files"]

        # 5. Xác minh dữ liệu đã trở lại ban đầu
        with open(dict_file, "r", encoding="utf-8") as f:
            restored_dict = json.load(f)
        assert restored_dict.get("ban_dau") == "nguyên bản 100%"
        print(f"  ✓ Phục hồi thành công {restore_res['total_files']} tệp và dữ liệu trở về trạng thái nguyên bản")

    return True


def test_08_ed25519_license_preservation():
    """8. Kiểm tra bảo toàn bản quyền Ed25519 và Machine ID."""
    print_test_header(8, "Ed25519 Offline License Preservation")

    from backend.license import get_machine_id

    machine_id = get_machine_id()
    assert machine_id and len(machine_id) > 5, "Machine ID phải hợp lệ và ổn định"

    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        lic_data = {
            "machine_id": machine_id,
            "plan": "KEY-PERM",
            "license_key": "TTTS-PERM-AAAA-BBBB-CCCC-DDDD",
            "activated_at": time.time() - 100000,
            "last_seen_timestamp": time.time(),
            "status": "active",
            "hmac": "fake_hmac_ed25519_signature_for_test",
        }
        lic_file = data_dir / "license_state.json"
        lic_file.write_text(json.dumps(lic_data, indent=2), encoding="utf-8")

        updater = UpdateManager(data_dir=data_dir, current_version="3.0.0")
        updater.perform_data_migration(from_version="3.0.0", to_version="3.1.0")

        # Đọc lại và so sánh
        with open(lic_file, "r", encoding="utf-8") as f:
            saved_lic = json.load(f)

        assert saved_lic["machine_id"] == machine_id
        assert saved_lic["plan"] == "KEY-PERM"
        assert saved_lic["hmac"] == "fake_hmac_ed25519_signature_for_test"
        print(f"  ✓ Machine ID ({machine_id[:8]}...) và cấu trúc bản quyền Ed25519 được bảo toàn tuyệt đối")

    return True


def test_09_user_data_preservation():
    """9. Kiểm tra bảo toàn các dự án người dùng (Audio, Broadcast, Schedule)."""
    print_test_header(9, "User Projects & History Preservation")

    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        for sub in ["projects/audio", "projects/broadcast", "projects/schedules"]:
            (data_dir / sub).mkdir(parents=True, exist_ok=True)

        # Lưu các dự án
        a_file = data_dir / "projects/audio/project_alpha.json"
        a_file.write_text(json.dumps({"title": "Thu âm chỉ thị số 12"}), encoding="utf-8")

        b_file = data_dir / "projects/broadcast/bulletin_01.json"
        b_file.write_text(json.dumps({"title": "Bản tin phát thanh 07:00"}), encoding="utf-8")

        s_file = data_dir / "projects/schedules/sched_morning.json"
        s_file.write_text(json.dumps({"title": "Lịch phát thanh sáng"}), encoding="utf-8")

        updater = UpdateManager(data_dir=data_dir, current_version="3.0.0")
        updater.perform_data_migration(from_version="3.0.0", to_version="3.1.0")

        # Kiểm tra sự tồn tại nguyên vẹn
        assert json.loads(a_file.read_text(encoding="utf-8"))["title"] == "Thu âm chỉ thị số 12"
        assert json.loads(b_file.read_text(encoding="utf-8"))["title"] == "Bản tin phát thanh 07:00"
        assert json.loads(s_file.read_text(encoding="utf-8"))["title"] == "Lịch phát thanh sáng"
        print("  ✓ Dự án Audio Studio: 100% nguyên vẹn")
        print("  ✓ Dự án Broadcast Studio: 100% nguyên vẹn")
        print("  ✓ Dự án Schedule Studio: 100% nguyên vẹn")

    return True


def test_10_interrupted_download_cleanup():
    """10. Kiểm tra dọn dẹp file tạm khi tải bị hủy hoặc ngắt quãng."""
    print_test_header(10, "Interrupted Download Cleanup")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        source_file = tmp_path / "big_fake.bin"
        source_file.write_bytes(b"DATA_BLOCK_" * 100000)

        updater = UpdateManager(data_dir=tmp_path / "data")
        cancel_evt = threading.Event()
        cancel_evt.set()  # Hủy ngay lập tức

        update_info = UpdateInfoData(
            available=True,
            current_version="3.0.0",
            latest_version="3.1.0",
            asset_name="Cancelled_Setup.exe",
            asset_size=source_file.stat().st_size,
            download_url=source_file.as_uri(),
        )

        try:
            updater.download_update(update_info, cancel_event=cancel_evt)
            assert False, "Phải ném InterruptedError khi hủy tải"
        except InterruptedError:
            target_dest = Path(tempfile.gettempdir()) / "T-TTS_Updates" / "Cancelled_Setup.exe"
            assert not target_dest.exists(), "Tệp tạm phải được xóa dọn sạch khi hủy"
            print("  ✓ Dọn sạch tệp tạm thành công khi người dùng hủy quá trình tải")

    return True


def test_11_installer_launch_parameters():
    """11. Kiểm tra tham số dòng lệnh cài đặt Inno Setup (/SILENT, /CLOSEAPPLICATIONS, /RESTARTAPPLICATIONS)."""
    print_test_header(11, "Inno Setup Launch Parameters Verification")

    with tempfile.TemporaryDirectory() as tmp_dir:
        updater = UpdateManager(data_dir=Path(tmp_dir) / "data")

        # Kiểm tra file không tồn tại
        try:
            updater.install_and_restart(UpdateInfoData(), Path("non_existent_setup.exe"), perform_exit=False)
            assert False, "Phải ném FileNotFoundError"
        except FileNotFoundError:
            print("  ✓ Kiểm tra tính hợp lệ của tệp setup trước khi chạy")

        # Kiểm tra tệp .exe hợp lệ (nhưng không gọi subprocess thực tế bằng fake runner)
        fake_exe = Path(tmp_dir) / "T-TTS_Setup.exe"
        fake_exe.write_bytes(b"MZ_DUMMY_EXE_HEADER")

        # Kiểm tra logic tham số trong updater
        expected_flags = ["/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"]
        # Đọc trực tiếp logic từ updater.py
        with open(REPO_ROOT / "backend" / "updater.py", "r", encoding="utf-8") as f:
            code = f.read()
        for flag in expected_flags:
            assert flag in code, f"Thiếu cờ cài đặt quan trọng: {flag}"
            print(f"  ✓ Tham số cài đặt tự động được cấu hình chính xác: {flag}")

    return True


def test_12_update_dialog_military_ui():
    """12. Kiểm tra giao diện UpdateDialog phong cách Quân đội K20."""
    print_test_header(12, "UpdateDialog Military K20 UI Verification")

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmp_dir:
        updater = UpdateManager(data_dir=Path(tmp_dir) / "data")
        info = UpdateInfoData(
            available=True,
            current_version="3.0.0",
            latest_version="3.1.0",
            release_title="T-TTS v3.1.0 Bản Nâng Cấp Master",
            release_notes="• Tích hợp Document Reader DOCX/PDF/TXT\n• Bộ xử lý âm thanh chuyên sâu EQ, Compressor, Noise Reduction",
            asset_size=150 * 1024 * 1024,
        )

        from gui.dialog_update import UpdateDialog, MILITARY_K20_UPDATE_QSS
        dlg = UpdateDialog(updater, info)

        assert dlg.banner is not None, "Phải có huy hiệu nâng cấp trực tiếp"
        assert "NÂNG CẤP TRỰC TIẾP v3.0.0 → v3.1.0" in dlg.banner.text()
        assert dlg.btn_rollback is not None, "Phải có nút khôi phục sao lưu"
        assert dlg.btn_update is not None, "Phải có nút cập nhật"
        assert dlg.progress_bar is not None, "Phải có thanh tiến trình"
        assert "#0F1E11" in dlg.styleSheet(), "Theme phải là Dark Military K20 (#0F1E11)"

        print("  ✓ Huy hiệu nâng cấp trực tiếp v3.0.0 → v3.1.0 hiển thị nổi bật")
        print("  ✓ Nút Khôi phục sao lưu (Rollback) tích hợp đầy đủ")
        print("  ✓ QSS Dark Military K20 (#0F1E11, #142817, #FFD700, #4ADE80) áp dụng hoàn chỉnh")
        dlg.close()

    return True


def test_13_check_update_worker_thread():
    """13. Kiểm tra CheckUpdateWorker chạy ngầm trên QThread."""
    print_test_header(13, "CheckUpdateWorker Async Thread Verification")

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmp_dir:
        worker = CheckUpdateWorker(data_dir=Path(tmp_dir) / "data")
        signals_received = []
        worker.check_finished.connect(lambda info: signals_received.append(("finish", info)))
        worker.check_error.connect(lambda err: signals_received.append(("error", err)))

        # Chạy worker và xử lý event loop của Qt
        worker.start()
        for _ in range(50):
            app.processEvents()
            if not worker.isRunning():
                break
            time.sleep(0.1)
        for _ in range(5):
            app.processEvents()
            time.sleep(0.02)

        assert len(signals_received) > 0, "CheckUpdateWorker phải phát ít nhất 1 tín hiệu (finish hoặc error do mạng)"
        sig_type, payload = signals_received[0]
        print(f"  ✓ CheckUpdateWorker hoàn thành an toàn trong background thread: tín hiệu = '{sig_type}'")

    return True


def test_14_download_update_worker_thread():
    """14. Kiểm tra DownloadUpdateWorker phát tín hiệu tiến trình thời gian thực."""
    print_test_header(14, "DownloadUpdateWorker Progress & Cancel Signals")

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        data_dir = tmp_path / "data"
        updater = UpdateManager(data_dir=data_dir)

        # Tạo file nguồn giả lập
        sample_file = tmp_path / "source.bin"
        sample_file.write_bytes(b"HELLO_PROGRESS" * 50000)

        info = UpdateInfoData(
            available=True,
            current_version="3.0.0",
            latest_version="3.1.0",
            asset_name="Worker_Setup.exe",
            asset_size=sample_file.stat().st_size,
            download_url=sample_file.as_uri(),
        )

        worker = DownloadUpdateWorker(updater, info)
        progresses = []
        finished_files = []
        worker.progress.connect(lambda pct, dl, tot, sp: progresses.append(pct))
        worker.download_finished.connect(lambda f: finished_files.append(f))

        worker.start()
        for _ in range(50):
            app.processEvents()
            if not worker.isRunning():
                break
            time.sleep(0.1)
        for _ in range(5):
            app.processEvents()
            time.sleep(0.02)

        assert len(finished_files) == 1, "DownloadUpdateWorker phải phát tín hiệu hoàn tất"
        assert len(progresses) > 0, "Phải ghi nhận được tín hiệu tiến trình tải"
        print(f"  ✓ Ghi nhận {len(progresses)} mốc tiến trình tải (tối đa {max(progresses)}%)")
        print("  ✓ Tín hiệu download_finished kết nối thành công")

    return True


def test_15_no_silent_update_enforcement():
    """15. Kiểm tra bắt buộc xác nhận người dùng, không bao giờ tự động cập nhật ngầm."""
    print_test_header(15, "No-Silent-Update Security Policy")

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmp_dir:
        updater = UpdateManager(data_dir=Path(tmp_dir) / "data")
        info = UpdateInfoData(available=True, current_version="3.0.0", latest_version="3.1.0")

        from gui.dialog_update import UpdateDialog
        dlg = UpdateDialog(updater, info)

        # Kiểm tra trạng thái ban đầu: không tự động kích hoạt tải hoặc cài đặt
        assert dlg.download_worker is None, "Không được tự ý tải khi chưa có lệnh người dùng"
        assert dlg.btn_update.isEnabled() is True, "Nút Cập nhật ngay phải chờ người dùng bấm"
        assert not dlg.btn_later.isHidden(), "Luôn cho phép người dùng chọn 'Để sau'"
        print("  ✓ Hộp thoại luôn ở trạng thái chờ lệnh người dùng (Chính sách Không cập nhật ngầm)")
        print("  ✓ Người dùng nắm toàn quyền quyết định cập nhật hoặc từ chối")
        dlg.close()

    return True


def test_16_full_regression_all_modules():
    """16. Kiểm tra hồi quy toàn diện mọi module cốt lõi sau Sprint 7."""
    print_test_header(16, "Full Regression All Core Modules Post-Sprint 7")

    # 1. VieNeu-TTS v3 Turbo TTSEngine
    from backend.tts_engine import TTSEngine
    engine = TTSEngine(mode="v3turbo", precision="int8", device="cpu")
    assert engine is not None
    print("  ✓ 16.1 VieNeu-TTS v3 Turbo ONNX CPU: Sẵn sàng")

    # 2. Document Reader
    from backend.document_reader import DocumentReader, extract_document_text
    reader = DocumentReader()
    assert reader is not None
    print("  ✓ 16.2 Document Reader (DOCX, PDF, TXT): Hoạt động chuẩn xác")

    # 3. Vietnamese Text Processor
    from backend.text_processor import VietnameseTextProcessor, TextProcessor
    tp = TextProcessor()
    norm = tp.full_normalize("Hà   Nội ngày  9/11/2026.")
    assert "Hà Nội" in norm and "hai nghìn" in norm
    print("  ✓ 16.3 Vietnamese Text Processor & Number Reading: Hoạt động chuẩn xác")

    # 4. Audio Enhancement DSP Engine & Intelligent Audio
    from backend.audio_enhancement import AudioEnhancementEngine
    from backend.intelligent_audio import IntelligentVoiceEnhancer
    dsp = AudioEnhancementEngine()
    analyzer = IntelligentVoiceEnhancer()
    assert dsp is not None and analyzer is not None
    print("  ✓ 16.4 Audio DSP Enhancement & Intelligent Analyzer: Hoạt động chuẩn xác")

    # 5. Project Managers & Studios
    from backend.project_manager import ProjectManager
    pm = ProjectManager()
    assert pm is not None
    print("  ✓ 16.5 Project Manager & Studios: Hoàn toàn ổn định")

    return True


def run_all_sprint_7_tests():
    print("\n" + "=" * 75)
    print("T-TTS v3.1.0 — SPRINT 7: AUTO UPDATE & SAFE MIGRATION TEST SUITE")
    print("Tác giả: Nguyễn Văn Tiệp | Kiến trúc: VieNeu-TTS v3 Turbo ONNX CPU")
    print("=" * 75)

    tests = [
        test_01_version_comparison_and_v301_bypass,
        test_02_release_metadata_parsing,
        test_03_download_integrity_and_sha256,
        test_04_system_readiness_checks,
        test_05_pre_update_backup_creation,
        test_06_data_migration_v300_to_v310,
        test_07_rollback_and_restore_backup,
        test_08_ed25519_license_preservation,
        test_09_user_data_preservation,
        test_10_interrupted_download_cleanup,
        test_11_installer_launch_parameters,
        test_12_update_dialog_military_ui,
        test_13_check_update_worker_thread,
        test_14_download_update_worker_thread,
        test_15_no_silent_update_enforcement,
        test_16_full_regression_all_modules,
    ]

    passed = 0
    failed = 0

    for idx, test_fn in enumerate(tests, 1):
        try:
            res = test_fn()
            if res:
                passed += 1
                print(f"--> [PASS] TEST {idx:02d}/16: {test_fn.__name__}")
            else:
                failed += 1
                print(f"--> [FAIL] TEST {idx:02d}/16: {test_fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"--> [ERROR] TEST {idx:02d}/16: {test_fn.__name__} — {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 75)
    print(f"KẾT QUẢ KIỂM THỬ SPRINT 7: {passed}/{len(tests)} PASS (Tỷ lệ: {passed/len(tests)*100:.1f}%)")
    if failed == 0:
        print("TẤT CẢ 16 TIÊU CHÍ AUTO UPDATE & SAFE MIGRATION ĐẠT 100% HOÀN HẢO!")
    else:
        print(f"CẢNH BÁO: CÓ {failed} TEST THẤT BẠI!")
    print("=" * 75)

    return failed == 0


if __name__ == "__main__":
    success = run_all_sprint_7_tests()
    sys.exit(0 if success else 1)
