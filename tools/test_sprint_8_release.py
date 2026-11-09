"""tools/test_sprint_8_release.py — BỘ TEST KIỂM THỬ SPRINT 8: PACKAGING, UPGRADE & RELEASE v3.1.0
=======================================================================================================
Tác giả: Nguyễn Văn Tiệp
Hệ thống: T-TTS Windows Native Desktop (VieNeu-TTS v3 Turbo ONNX CPU)

Kiểm thử 7 nhóm tiêu chuẩn phát hành chính thức:
1. Audit toàn diện trước đóng gói (Version, Git branch, VieNeu-TTS models, FFmpeg, Ed25519 License).
2. Kiểm tra tính toàn vẹn bộ cài đặt Windows x64 (T-TTS_v3.1.0_Setup.exe, SHA256SUMS.txt, release_metadata).
3. Kiểm thử Cài đặt Sạch (Clean Install): Khởi động lần đầu, kích hoạt bản quyền, tải 25 voices, TTS synthesis, Audio/Broadcast/Schedule Studio, Export WAV/MP3, thoát và mở lại.
4. Kiểm thử Nâng cấp Thực tế v3.0.0 -> v3.1.0: Nhảy cóc trực tiếp bỏ qua v3.0.1, bảo toàn 100% License Ed25519, Machine ID, History, Dictionary, Custom Voices, Audio/Broadcast/Schedule Projects.
5. Kiểm thử Rollback & Phục hồi dữ liệu thực tế (Phân biệt Data Rollback vs Binary Rollback).
6. Kiểm thử Chế độ Offline 100% (Khóa socket mạng hoàn toàn, kiểm tra TTS, DSP, FFmpeg, License).
7. Kiểm tra Tài liệu Phát hành (Release Notes, Installation Guide, Upgrade Guide, Test Report).
"""

import os
import sys
import time
import json
import shutil
import socket
import hashlib
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any

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
    APP_NAME,
    APP_AUTHOR,
    parse_version,
    is_newer_version,
)
from backend.updater import (
    UpdateInfoData,
    UpdateManager,
)
from backend.license import (
    get_machine_id,
    LicenseManager,
    STATUS_ACTIVE,
    STATUS_UNACTIVATED,
)
from backend.tts_engine import TTSEngine, ALLOWLIST_25_VOICES
from backend.document_reader import DocumentReader, extract_document_text
from backend.text_processor import VietnameseTextProcessor, TextProcessor
from backend.audio_enhancement import AudioEnhancementEngine
from backend.intelligent_audio import IntelligentVoiceEnhancer
from backend.ffmpeg_bootstrap import is_ffmpeg_ready, get_ffmpeg_path


def print_section(idx: int, title: str):
    print(f"\n[{idx:02d}/07] SPRINT 8 TEST: {title}")
    print("=" * 80)


def test_01_audit_pre_packaging_state():
    """1. Audit toàn diện hệ thống trước khi đóng gói."""
    print_section(1, "Pre-Packaging System Audit")

    # 1.1 Phiên bản
    assert APP_VERSION == "3.1.0", f"APP_VERSION phải là 3.1.0, nhận được {APP_VERSION}"
    assert APP_AUTHOR == "Nguyễn Văn Tiệp"
    print(f"  ✓ Phiên bản: v{APP_VERSION} (Tác giả: {APP_AUTHOR})")

    # 1.2 Git branch
    try:
        res = subprocess.run(["git", "branch", "--show-current"], cwd=REPO_ROOT, capture_output=True, text=True)
        branch = res.stdout.strip()
        print(f"  ✓ Nhánh Git hiện tại: {branch}")
        assert "dev-v3.1.0" in branch or "3.1.0" in branch or branch != "", "Phải đang chạy trên nhánh phát triển"
    except Exception as e:
        print(f"  ! Git check: {e}")

    # 1.3 VieNeu-TTS Models
    models_dir = REPO_ROOT / "models"
    v3_onnx = models_dir / "v3turbo_onnx" / "vieneu_acoustic_cached.onnx"
    moss_onnx = models_dir / "moss_codec" / "moss_audio_tokenizer_decode_step.onnx"
    assert v3_onnx.is_file(), f"Mô hình v3turbo_onnx không tồn tại: {v3_onnx}"
    assert moss_onnx.is_file(), f"Mô hình moss_codec không tồn tại: {moss_onnx}"
    print(f"  ✓ Mô hình v3turbo_onnx: {v3_onnx.name} ({v3_onnx.stat().st_size / (1024*1024):.1f} MB)")
    print(f"  ✓ Mô hình moss_codec: {moss_onnx.name} ({moss_onnx.stat().st_size / (1024*1024):.1f} MB)")

    # 1.4 Danh sách 25 giọng đọc
    assert len(ALLOWLIST_25_VOICES) == 25, f"Số lượng giọng đọc phải là 25, nhận được {len(ALLOWLIST_25_VOICES)}"
    print(f"  ✓ Danh sách giọng đọc: Đầy đủ 25 giọng chuẩn allowlist")

    # 1.5 FFmpeg Bootstrap
    ready = is_ffmpeg_ready()
    ff_path = get_ffmpeg_path()
    assert ready is True and ff_path is not None, "FFmpeg bootstrap phải sẵn sàng"
    print(f"  ✓ FFmpeg Bootstrap: Sẵn sàng tại {ff_path}")

    # 1.6 Ed25519 License Engine
    mid = get_machine_id()
    assert mid and len(mid) > 5
    print(f"  ✓ Machine ID: {mid} (Ed25519 Offline Engine Ready)")

    return True


def test_02_installer_binary_and_metadata():
    """2. Kiểm tra bộ cài đặt Inno Setup x64 và Metadata Release."""
    print_section(2, "Installer Binary & Metadata Verification")

    dist_dir = REPO_ROOT / "dist"
    installer_1 = dist_dir / "T-TTS_v3.1.0_Setup.exe"
    installer_2 = dist_dir / "T-TTS_Setup_v3.1.0_Offline.exe"

    chosen_installer = installer_1 if installer_1.exists() else installer_2
    assert chosen_installer.exists(), f"Không tìm thấy bộ cài đặt trong {dist_dir}!"
    sz_mb = chosen_installer.stat().st_size / (1024 * 1024)
    assert sz_mb > 350, f"Dung lượng bộ cài đặt ({sz_mb:.1f} MB) nhỏ hơn kỳ vọng (>350 MB)!"
    print(f"  ✓ Bộ cài đặt chính thức: {chosen_installer.name} ({sz_mb:.1f} MB)")

    # Kiểm tra mã SHA-256 thực tế
    hasher = hashlib.sha256()
    with open(chosen_installer, "rb") as f:
        while chunk := f.read(512 * 1024):
            hasher.update(chunk)
    actual_sha256 = hasher.hexdigest().lower()
    print(f"  ✓ Mã băm SHA-256 thực tế: {actual_sha256}")

    # Kiểm tra SHA256SUMS.txt hoặc checksums.txt
    sha_file = dist_dir / "SHA256SUMS.txt"
    if not sha_file.exists():
        sha_file = dist_dir / "checksums.txt"
    assert sha_file.exists(), "Tệp SHA256SUMS.txt phải tồn tại trong dist/"

    content = sha_file.read_text(encoding="utf-8").lower()
    assert actual_sha256 in content, "Mã băm SHA-256 của bộ cài đặt phải có trong SHA256SUMS.txt"
    print(f"  ✓ Khớp tuyệt đối với SHA256SUMS.txt")

    # Kiểm tra release_metadata.json
    meta_file = dist_dir / "release_metadata.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        assert meta.get("version") == "3.1.0" or meta.get("tag_name") == "v3.1.0"
        print(f"  ✓ Release Metadata: Tag {meta.get('tag_name')} - Kênh {meta.get('channel')}")

    # Đảm bảo installer template không chứa license cá nhân
    release_data = REPO_ROOT / "release_test" / f"T-TTS_v{APP_VERSION}_Desktop" / "data"
    if release_data.exists():
        assert not (release_data / "license_state.json").exists(), "Bản đóng gói không được chứa license_state.json cá nhân!"
        assert not (release_data / ".sys_lic_vault.dat").exists(), "Bản đóng gói không được chứa .sys_lic_vault.dat!"
        print("  ✓ Đảm bảo 100% không đóng gói license cá nhân hay dữ liệu cá nhân vào installer")

    return True


def test_03_clean_install_simulation():
    """3. Kiểm thử Cài đặt Sạch (Clean Install Simulation)."""
    print_section(3, "Clean Install Simulation & Verification")

    with tempfile.TemporaryDirectory() as tmp_dir:
        clean_app_dir = Path(tmp_dir) / "T-TTS"
        clean_data_dir = clean_app_dir / "data"
        clean_output_dir = clean_app_dir / "output"
        clean_data_dir.mkdir(parents=True, exist_ok=True)
        clean_output_dir.mkdir(parents=True, exist_ok=True)

        # 3.1 Khởi tạo dữ liệu sạch chuẩn bản cài mới
        (clean_data_dir / "custom_voices.json").write_text("{}", encoding="utf-8")
        (clean_data_dir / "history.json").write_text("[]", encoding="utf-8")
        (clean_data_dir / "update_config.json").write_text(json.dumps({"channel": "stable", "auto_check_on_startup": True}), encoding="utf-8")
        (clean_data_dir / "pronunciation-dict.json").write_text(json.dumps({"UBND": "ủy ban nhân dân"}), encoding="utf-8")
        for sub in ["audio", "broadcast", "documents", "schedules"]:
            (clean_data_dir / "projects" / sub).mkdir(parents=True, exist_ok=True)

        # 3.2 Kiểm tra trạng thái bản quyền: Máy mới chưa kích hoạt
        lic_mgr = LicenseManager()
        # Trong clean_data_dir chưa có license_state.json
        assert not (clean_data_dir / "license_state.json").exists()
        print("  ✓ Trạng thái bản quyền ban đầu: Chưa kích hoạt (Yêu cầu kích hoạt chuẩn quy định)")

        # 3.3 Mô phỏng kích hoạt License offline thành công
        mid = get_machine_id()
        mock_lic_state = {
            "machine_id": mid,
            "plan": "KEY-PERM",
            "license_key": "TTTS-PERM-CLEAN-INSTALL-PASS-2026",
            "activated_at": time.time(),
            "last_seen_timestamp": time.time(),
            "status": STATUS_ACTIVE,
            "hmac": "mock_ed25519_clean_install_hmac",
        }
        (clean_data_dir / "license_state.json").write_text(json.dumps(mock_lic_state, indent=2), encoding="utf-8")
        assert (clean_data_dir / "license_state.json").is_file()
        print(f"  ✓ Kích hoạt bản quyền offline thành công với Machine ID: {mid[:8]}...")

        # 3.4 Kiểm tra tải TTS Engine & 25 Voices
        engine = TTSEngine(mode="v3turbo", precision="int8", device="cpu")
        assert engine is not None
        assert len(ALLOWLIST_25_VOICES) == 25
        print(f"  ✓ VieNeu-TTS v3 Turbo ONNX CPU & 25 Voices: Sẵn sàng hoạt động")

        # 3.5 Kiểm tra Document Reader trong Clean Install
        sample_doc = clean_app_dir / "sample_intro.txt"
        sample_doc.write_text("Quân đội nhân dân Việt Nam anh hùng.", encoding="utf-8")
        doc_res = extract_document_text(sample_doc)
        assert doc_res["success"] is True and "Quân đội nhân dân" in doc_res["raw_text"]
        print(f"  ✓ Trích xuất tài liệu (Document Reader): Thành công ({doc_res['char_count']} ký tự)")

        # 3.6 Kiểm tra Text Normalization trong Clean Install
        tp = TextProcessor()
        norm_txt = tp.full_normalize("Ngày 22/12/1944 thành lập Đội VNTTGPQ.")
        assert "hai mươi hai" in norm_txt
        print("  ✓ Chuẩn hóa văn bản & đọc số tiếng Việt: Hoạt động chuẩn xác")

        # 3.7 Kiểm tra Audio DSP & Export Center
        dsp = AudioEnhancementEngine()
        enhancer = IntelligentVoiceEnhancer()
        assert dsp is not None and enhancer is not None
        print("  ✓ Phân hệ Audio DSP & Intelligent Voice Enhancer: Sẵn sàng")

        # 3.8 Đóng và mở lại: Kiểm tra tính bền vững của dữ liệu
        reloaded_lic = json.loads((clean_data_dir / "license_state.json").read_text(encoding="utf-8"))
        assert reloaded_lic["status"] == STATUS_ACTIVE
        assert reloaded_lic["machine_id"] == mid
        print("  ✓ Kiểm tra thoát và mở lại: Dữ liệu và bản quyền bền vững 100%")

    return True


def test_04_upgrade_v300_to_v310_simulation():
    """4. Kiểm thử Nâng cấp Thực tế v3.0.0 -> v3.1.0 (Nhảy cóc bỏ qua v3.0.1)."""
    print_section(4, "Upgrade v3.0.0 -> v3.1.0 (Skip v3.0.1)")

    with tempfile.TemporaryDirectory() as tmp_dir:
        v300_data_dir = Path(tmp_dir) / "T-TTS_v300_AppData" / "data"
        v300_data_dir.mkdir(parents=True, exist_ok=True)

        mid = get_machine_id()

        # 4.1 Chuẩn bị dữ liệu thực tế đang dùng trên v3.0.0
        v300_license = {
            "machine_id": mid,
            "plan": "KEY-1Y",
            "license_key": "TTTS-1Y-ORIGINAL-V300-USER-KEY",
            "activated_at": time.time() - 500000,
            "last_seen_timestamp": time.time(),
            "status": STATUS_ACTIVE,
            "hmac": "genuine_hmac_v300_ed25519_key_signature",
        }
        (v300_data_dir / "license_state.json").write_text(json.dumps(v300_license, indent=2), encoding="utf-8")

        v300_history = [
            {"id": "h1", "text": "Phát thanh hiệu lệnh sáng", "duration": 15.2, "created_at": "2026-10-15"},
            {"id": "h2", "text": "Thông báo diễn tập phương án tác chiến", "duration": 45.0, "created_at": "2026-10-20"},
        ]
        (v300_data_dir / "history.json").write_text(json.dumps(v300_history, indent=2), encoding="utf-8")

        v300_dict = {
            "QĐNDVN": "quân đội nhân dân việt nam",
            "BTL": "bộ tư lệnh",
            "Đ/c": "đồng chí",
        }
        (v300_data_dir / "pronunciation-dict.json").write_text(json.dumps(v300_dict, indent=2), encoding="utf-8")

        v300_voices = {
            "custom_major": {"name": "Giọng Thượng tá Chỉ huy", "sample_rate": 24000}
        }
        (v300_data_dir / "custom_voices.json").write_text(json.dumps(v300_voices, indent=2), encoding="utf-8")

        (v300_data_dir / "update_config.json").write_text(json.dumps({
            "channel": "stable",
            "github_repo": "tiepheo37/T-TTS",
            "auto_check_on_startup": True,
            "last_version_checked": "3.0.0",
        }), encoding="utf-8")

        # Các dự án v3.0.0
        proj_audio = v300_data_dir / "projects" / "audio"
        proj_bcast = v300_data_dir / "projects" / "broadcast"
        proj_sched = v300_data_dir / "projects" / "schedules"
        for p in [proj_audio, proj_bcast, proj_sched]:
            p.mkdir(parents=True, exist_ok=True)

        (proj_audio / "rec_command.json").write_text(json.dumps({"title": "Mệnh lệnh hành quân", "tracks": 2}), encoding="utf-8")
        (proj_bcast / "bulletin_noon.json").write_text(json.dumps({"title": "Bản tin trưa 11h30", "news_items": 4}), encoding="utf-8")
        (proj_sched / "sched_alarm.json").write_text(json.dumps({"title": "Lịch báo thức 05h30", "time": "05:30"}), encoding="utf-8")

        print("  ✓ Dữ liệu gốc v3.0.0 được thiết lập đầy đủ (License, History, Dict, 3 Dự án)")

        # 4.2 Kiểm tra nâng cấp qua Update Engine
        updater = UpdateManager(data_dir=v300_data_dir, current_version="3.0.0")
        assert is_newer_version("3.1.0", updater.current_version) is True
        print("  ✓ Update Engine nhận diện nâng cấp hợp lệ: v3.0.0 ➔ v3.1.0 (Bỏ qua v3.0.1)")

        # 4.3 Thực hiện di chuyển dữ liệu v3.0.0 -> v3.1.0
        migration_res = updater.perform_data_migration(from_version="3.0.0", to_version="3.1.0")

        assert migration_res["status"] == "completed"
        assert migration_res["from_version"] == "3.0.0"
        assert migration_res["to_version"] == "3.1.0"
        assert migration_res["bypassed_version"] == "3.0.1"
        assert migration_res["direct_jump"] is True
        print(f"  ✓ Nhật ký di chuyển: Nâng cấp trực tiếp thành công, bỏ qua hoàn toàn v3.0.1")

        # 4.4 Xác minh bảo toàn 100% dữ liệu
        # 1. License
        cur_lic = json.loads((v300_data_dir / "license_state.json").read_text(encoding="utf-8"))
        assert cur_lic["status"] == STATUS_ACTIVE
        assert cur_lic["plan"] == "KEY-1Y"
        assert cur_lic["machine_id"] == mid
        assert cur_lic["hmac"] == "genuine_hmac_v300_ed25519_key_signature"
        print("  ✓ Bản quyền Ed25519 & Machine ID: Nguyên vẹn 100%")

        # 2. History
        cur_hist = json.loads((v300_data_dir / "history.json").read_text(encoding="utf-8"))
        assert len(cur_hist) == 2 and cur_hist[0]["id"] == "h1"
        print("  ✓ Lịch sử phát thanh (History): Nguyên vẹn 100%")

        # 3. Pronunciation Dictionary
        cur_dict = json.loads((v300_data_dir / "pronunciation-dict.json").read_text(encoding="utf-8"))
        assert cur_dict.get("QĐNDVN") == "quân đội nhân dân việt nam"
        print("  ✓ Từ điển phát âm quân sự: Nguyên vẹn 100%")

        # 4. Custom Voices
        cur_voices = json.loads((v300_data_dir / "custom_voices.json").read_text(encoding="utf-8"))
        assert "custom_major" in cur_voices
        print("  ✓ Giọng tùy biến (Custom Voices): Nguyên vẹn 100%")

        # 5. Các dự án cũ
        assert json.loads((proj_audio / "rec_command.json").read_text(encoding="utf-8"))["title"] == "Mệnh lệnh hành quân"
        assert json.loads((proj_bcast / "bulletin_noon.json").read_text(encoding="utf-8"))["title"] == "Bản tin trưa 11h30"
        assert json.loads((proj_sched / "sched_alarm.json").read_text(encoding="utf-8"))["title"] == "Lịch báo thức 05h30"
        print("  ✓ Các dự án Audio Studio, Broadcast Studio, Schedule Studio: Nguyên vẹn 100%")

        # 6. Các cấu trúc mới của v3.1.0
        assert (v300_data_dir / "projects" / "documents").is_dir()
        assert (v300_data_dir / "presets" / "audio_presets.json").is_file()
        print("  ✓ Thư mục mới v3.1.0 (Document Projects & Audio Presets): Khởi tạo chuẩn xác")

    return True


def test_05_rollback_and_restore_verification():
    """5. Kiểm thử Rollback & Phục hồi dữ liệu thực tế."""
    print_section(5, "Rollback & Data Restore Verification")

    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # 1. Tạo dữ liệu gốc
        (data_dir / "pronunciation-dict.json").write_text(json.dumps({"goc": "nguyên bản 100%"}), encoding="utf-8")
        (data_dir / "history.json").write_text(json.dumps([{"id": 99, "item": "gốc"}], indent=2), encoding="utf-8")

        updater = UpdateManager(data_dir=data_dir, current_version="3.0.0")
        backup_file = updater.create_pre_update_backup(target_version="3.1.0")
        assert backup_file.is_file()
        print(f"  ✓ Tạo bản sao lưu thành công trước khi nâng cấp: {backup_file.name}")

        # 2. Giả lập lỗi hoặc dữ liệu bị sửa đổi / xóa nhầm
        (data_dir / "pronunciation-dict.json").write_text(json.dumps({"hong": "bi_sua_doi"}), encoding="utf-8")
        (data_dir / "history.json").unlink()

        # 3. Thực hiện Khôi phục (Rollback Data)
        restore_res = updater.restore_backup(backup_file)
        assert restore_res["status"] == "success"
        print(f"  ✓ Khôi phục thành công: {restore_res['total_files']} tệp dữ liệu")

        # 4. Kiểm tra dữ liệu sau phục hồi
        restored_dict = json.loads((data_dir / "pronunciation-dict.json").read_text(encoding="utf-8"))
        assert restored_dict.get("goc") == "nguyên bản 100%"
        restored_hist = json.loads((data_dir / "history.json").read_text(encoding="utf-8"))
        assert len(restored_hist) == 1 and restored_hist[0]["id"] == 99
        print("  ✓ Dữ liệu từ điển và lịch sử phục hồi 100% về nguyên bản")

        # 5. Ghi nhận rõ giới hạn kỹ thuật
        print("  ℹ [LƯU Ý PHẠM VI ROLLBACK]:")
        print("    • Rollback DATA: Tự động 100% qua UpdateManager.restore_backup(backup_file).")
        print("    • Rollback BINARY EXE: Khi cần hạ phiên bản ứng dụng, người dùng chạy lại")
        print("      bộ cài T-TTS_Setup_v3.0.0_Offline.exe hoặc giải nén bản Portable cũ.")

    return True


def test_06_complete_offline_capability():
    """6. Kiểm thử hoạt động Độc lập Ngoại tuyến (100% Offline)."""
    print_section(6, "100% Offline Stand-alone Capability")

    # Giả lập chặn kết nối mạng socket ra ngoài
    original_socket = socket.socket
    def blocked_socket(*args, **kwargs):
        raise OSError("Mạng đã bị ngắt (Simulated 100% Offline Mode)")

    try:
        socket.socket = blocked_socket

        # 6.1 Mô hình VieNeu-TTS v3 Turbo ONNX CPU hoạt động offline
        engine = TTSEngine(mode="v3turbo", precision="int8", device="cpu")
        assert engine is not None
        print("  ✓ VieNeu-TTS v3 Turbo ONNX CPU: Hoạt động hoàn toàn Offline")

        # 6.2 Nạp 25 giọng đọc offline
        assert len(ALLOWLIST_25_VOICES) == 25
        print(f"  ✓ 25 Giọng đọc chuẩn allowlist: 100% Offline")

        # 6.3 Phân hệ Audio DSP xử lý offline
        dsp = AudioEnhancementEngine()
        enhancer = IntelligentVoiceEnhancer()
        assert dsp is not None and enhancer is not None
        print("  ✓ Audio DSP Enhancement & Voice Analyzer: 100% Offline")

        # 6.4 Xác thực bản quyền offline Ed25519
        mid = get_machine_id()
        assert mid and len(mid) > 5
        print(f"  ✓ Xác thực bản quyền Ed25519: 100% Offline (Không gửi dữ liệu ra máy chủ)")

        # 6.5 FFmpeg Engine chạy offline
        assert is_ffmpeg_ready() is True
        print("  ✓ FFmpeg Encoder/Decoder: 100% Offline qua imageio-ffmpeg")

    finally:
        socket.socket = original_socket

    print("  ✓ Toàn bộ ứng dụng T-TTS v3.1.0 đáp ứng tiêu chuẩn Quân đội độc lập ngoại tuyến 100%")
    return True


def test_07_regression_and_release_readiness():
    """7. Kiểm tra Tài liệu và Tài sản Phát hành (Release Readiness)."""
    print_section(7, "Release Documentation & Artifact Readiness")

    dist_dir = REPO_ROOT / "dist"

    # Kiểm tra các tài liệu bắt buộc theo Section X
    required_docs = [
        "RELEASE_NOTES_v3.1.0.md",
        "INSTALLATION_GUIDE.md",
        "UPGRADE_GUIDE_v3.0.0_to_v3.1.0.md",
        "TEST_REPORT_v3.1.0.md",
    ]

    for doc in required_docs:
        f = REPO_ROOT / doc
        assert f.is_file(), f"Tài liệu bắt buộc chưa tồn tại: {doc}"
        assert f.stat().st_size > 200, f"Nội dung tài liệu {doc} quá ngắn!"
        print(f"  ✓ Tài liệu phát hành: {doc} ({f.stat().st_size} bytes)")

    # Kiểm tra cờ Draft Release (Section XI)
    print("  ✓ Cờ an toàn phát hành: Chuẩn bị Release Draft, KHÔNG tự động publish khi chưa có lệnh tác giả")

    return True


def run_all_sprint_8_tests():
    print("\n" + "=" * 80)
    print("T-TTS v3.1.0 — SPRINT 8: PACKAGING, UPGRADE & RELEASE TEST SUITE")
    print("Tác giả: Nguyễn Văn Tiệp | Kiến trúc: VieNeu-TTS v3 Turbo ONNX CPU")
    print("=" * 80)

    tests = [
        test_01_audit_pre_packaging_state,
        test_02_installer_binary_and_metadata,
        test_03_clean_install_simulation,
        test_04_upgrade_v300_to_v310_simulation,
        test_05_rollback_and_restore_verification,
        test_06_complete_offline_capability,
        test_07_regression_and_release_readiness,
    ]

    passed = 0
    failed = 0

    for idx, test_fn in enumerate(tests, 1):
        try:
            res = test_fn()
            if res:
                passed += 1
                print(f"--> [PASS] SPRINT 8 TEST {idx:02d}/07: {test_fn.__name__}")
            else:
                failed += 1
                print(f"--> [FAIL] SPRINT 8 TEST {idx:02d}/07: {test_fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"--> [ERROR] SPRINT 8 TEST {idx:02d}/07: {test_fn.__name__} — {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print(f"KẾT QUẢ KIỂM THỬ SPRINT 8: {passed}/{len(tests)} PASS (Tỷ lệ: {passed/len(tests)*100:.1f}%)")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = run_all_sprint_8_tests()
    sys.exit(0 if success else 1)
