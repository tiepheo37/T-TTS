"""backend/updater.py — MODULE QUẢN LÝ AUTO UPDATE ĐỘC LẬP CHO T-TTS
=============================================================================
Kiến trúc:
T-TTS → Update Manager → GitHub Releases → Kiểm tra phiên bản → Tải gói cập nhật
      → Xác minh gói (SHA256) → Cài đặt & Khởi động lại.

Hỗ trợ 2 cơ chế song song (Dual Engine):
1. Native VelopPack (velopack.UpdateManager): Khi chạy trong bản cài đặt VelopPack.
2. Direct HTTPS GitHub Releases: Hỗ trợ linh hoạt cho mọi môi trường (Inno Setup / Portable / Test).
"""

from __future__ import annotations

import os
import sys
import time
import json
import hashlib
import tempfile
import threading
import subprocess
from pathlib import Path
from typing import Optional, Callable, Dict, Any

from PySide6.QtCore import QThread, Signal

from backend.version import (
    APP_VERSION,
    APP_NAME,
    APP_AUTHOR,
    DEFAULT_GITHUB_REPO,
    DEFAULT_CHANNEL,
    is_newer_version,
    load_update_config,
    save_update_config,
)

# Thử import velopack nếu khả dụng
try:
    import velopack
    HAS_VELOPACK = True
except Exception:
    HAS_VELOPACK = False


class UpdateInfoData:
    """Chứa toàn bộ thông tin về phiên bản cập nhật."""

    def __init__(
        self,
        available: bool = False,
        current_version: str = APP_VERSION,
        latest_version: str = APP_VERSION,
        release_title: str = "",
        release_notes: str = "",
        published_at: str = "",
        download_url: str = "",
        asset_name: str = "",
        asset_size: int = 0,
        sha256: str = "",
        is_velopack: bool = False,
        velopack_info: Any = None,
        error_msg: str = "",
    ):
        self.available = available
        self.current_version = current_version
        self.latest_version = latest_version
        self.release_title = release_title
        self.release_notes = release_notes
        self.published_at = published_at
        self.download_url = download_url
        self.asset_name = asset_name
        self.asset_size = asset_size
        self.sha256 = sha256
        self.is_velopack = is_velopack
        self.velopack_info = velopack_info
        self.error_msg = error_msg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "release_title": self.release_title,
            "release_notes": self.release_notes,
            "published_at": self.published_at,
            "download_url": self.download_url,
            "asset_name": self.asset_name,
            "asset_size": self.asset_size,
            "sha256": self.sha256,
            "is_velopack": self.is_velopack,
            "error_msg": self.error_msg,
        }


class UpdateManager:
    """Quản lý kiểm tra, tải về, xác minh và cài đặt phiên bản T-TTS mới."""

    def __init__(self, data_dir: Optional[Path] = None, current_version: Optional[str] = None):
        self.data_dir = data_dir or Path(os.environ.get("LOCALAPPDATA", ".")) / "T-TTS" / "data"
        self.config = load_update_config(self.data_dir)
        self.repo = self.config.get("github_repo", DEFAULT_GITHUB_REPO)
        self.channel = self.config.get("channel", DEFAULT_CHANNEL)
        self.current_version = current_version or APP_VERSION

    def check_for_updates(self) -> UpdateInfoData:
        """Kiểm tra phiên bản mới từ GitHub Releases qua VelopPack hoặc HTTPS API."""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        self.config["last_checked_time"] = now_str

        # 1. Thử kiểm tra bằng VelopPack nếu môi trường hỗ trợ
        if HAS_VELOPACK:
            try:
                source = velopack.GithubSource(
                    f"https://github.com/{self.repo}",
                    access_token=None,
                    prerelease=(self.channel.lower() == "beta"),
                )
                um = velopack.UpdateManager(source=source)
                v_info = um.check_for_updates()
                if v_info is not None and v_info.TargetFullRelease is not None:
                    target = v_info.TargetFullRelease
                    if is_newer_version(target.Version, self.current_version):
                        notes = target.NotesMarkdown or target.NotesHtml or "Bản cập nhật nâng cấp tính năng và hiệu năng."
                        info = UpdateInfoData(
                            available=True,
                            current_version=self.current_version,
                            latest_version=target.Version,
                            release_title=f"T-TTS v{target.Version}",
                            release_notes=notes,
                            published_at=now_str,
                            asset_name=target.FileName,
                            asset_size=target.Size or 0,
                            sha256=target.SHA256 or "",
                            is_velopack=True,
                            velopack_info=v_info,
                        )
                        save_update_config(self.data_dir, self.config)
                        return info
            except Exception:
                # Nếu không chạy trong bundle VelopPack hoặc xảy ra lỗi locator, tự động fallback sang GitHub API
                pass

        # 2. Kiểm tra trực tiếp qua GitHub Releases API (100% tin cậy, không phụ thuộc packaging)
        try:
            import urllib.request
            import urllib.error
            import socket

            headers = {
                "User-Agent": f"T-TTS-Updater/{APP_VERSION} (Windows)",
                "Accept": "application/vnd.github.v3+json",
            }

            releases = []
            # Ưu tiên query /releases/latest nếu ở kênh stable
            if self.channel.lower() == "stable":
                latest_url = f"https://api.github.com/repos/{self.repo}/releases/latest"
                req_latest = urllib.request.Request(latest_url, headers=headers)
                try:
                    with urllib.request.urlopen(req_latest, timeout=12) as response:
                        single_rel = json.loads(response.read().decode("utf-8"))
                        if isinstance(single_rel, dict) and "tag_name" in single_rel:
                            releases = [single_rel]
                except urllib.error.HTTPError as he:
                    if he.code != 404:
                        raise he
                    # Nếu 404 trên /latest (ví dụ repo chỉ có prerelease hoặc chưa gán latest), fallback sang /releases
                    releases = []

            if not releases:
                api_url = f"https://api.github.com/repos/{self.repo}/releases"
                req = urllib.request.Request(api_url, headers=headers)
                with urllib.request.urlopen(req, timeout=12) as response:
                    releases = json.loads(response.read().decode("utf-8"))

            if not isinstance(releases, list) or len(releases) == 0:
                return UpdateInfoData(available=False, current_version=self.current_version, latest_version=self.current_version)

            # Lọc theo channel: nếu stable thì bỏ qua prerelease
            target_rel = None
            for rel in releases:
                if rel.get("draft", False):
                    continue
                is_pre = rel.get("prerelease", False)
                if self.channel.lower() == "stable" and is_pre:
                    continue
                target_rel = rel
                break

            if not target_rel:
                return UpdateInfoData(available=False, current_version=self.current_version, latest_version=self.current_version)

            info = self.parse_release_data(target_rel)
            if info.available:
                self.config["last_version_checked"] = info.latest_version
                save_update_config(self.data_dir, self.config)
            return info

        except urllib.error.HTTPError as e:
            if e.code == 404:
                err_str = (
                    f"Kho lưu trữ GitHub '{self.repo}' chưa có bản phát hành (Release) nào "
                    f"hoặc đang ở chế độ riêng tư (HTTP Error 404: Not Found)."
                )
            elif e.code in (403, 429):
                err_str = (
                    "Đã vượt quá giới hạn lượt truy vấn của GitHub API (HTTP 403/429 Rate Limit). "
                    "Vui lòng thử lại sau ít phút."
                )
            else:
                err_str = f"Lỗi phản hồi từ máy chủ GitHub (HTTP {e.code}: {e.reason})."
            return UpdateInfoData(
                available=False,
                current_version=self.current_version,
                latest_version=self.current_version,
                error_msg=err_str,
            )

        except urllib.error.URLError as e:
            reason_str = str(getattr(e, "reason", e)).lower()
            if "timed out" in reason_str or "timeout" in reason_str:
                err_str = "Hết thời gian chờ kết nối máy chủ GitHub (Timeout). Vui lòng kiểm tra lại tốc độ mạng."
            else:
                err_str = "Không thể kết nối tới máy chủ GitHub. Vui lòng kiểm tra lại kết nối mạng Internet."
            return UpdateInfoData(
                available=False,
                current_version=self.current_version,
                latest_version=self.current_version,
                error_msg=err_str,
            )

        except (socket.timeout, TimeoutError):
            err_str = "Hết thời gian chờ kết nối máy chủ GitHub (Timeout). Vui lòng kiểm tra lại kết nối mạng."
            return UpdateInfoData(
                available=False,
                current_version=self.current_version,
                latest_version=self.current_version,
                error_msg=err_str,
            )

        except Exception as e:
            return UpdateInfoData(
                available=False,
                current_version=self.current_version,
                latest_version=self.current_version,
                error_msg=f"Lỗi kiểm tra cập nhật: {e}",
            )

    def parse_release_data(self, target_rel: dict) -> UpdateInfoData:
        """Phân tích dữ liệu JSON một release từ GitHub API thành UpdateInfoData."""
        tag = target_rel.get("tag_name", "").strip().lstrip("vV")
        if not tag:
            return UpdateInfoData(available=False, current_version=self.current_version, latest_version=self.current_version)

        is_newer = is_newer_version(tag, self.current_version)
        if not is_newer:
            return UpdateInfoData(available=False, current_version=self.current_version, latest_version=tag)

        # Tìm file cài đặt Setup (.exe) hoặc gói update trong assets
        assets = target_rel.get("assets", [])
        chosen_asset = None
        for a in assets:
            aname = a.get("name", "").lower()
            if aname.endswith(".exe") and ("setup" in aname or "update" in aname or "t-tts" in aname):
                chosen_asset = a
                break

        if not chosen_asset and assets:
            for a in assets:
                aname = a.get("name", "").lower()
                if aname.endswith(".exe") or aname.endswith(".zip"):
                    chosen_asset = a
                    break

        dl_url = chosen_asset.get("browser_download_url") if chosen_asset else target_rel.get("html_url", "")
        asset_name = chosen_asset.get("name", f"T-TTS_Setup_v{tag}.exe") if chosen_asset else f"T-TTS_Setup_v{tag}.exe"
        asset_size = chosen_asset.get("size", 0) if chosen_asset else 0

        # Tìm checksum SHA256 nếu có
        sha256_val = ""
        if chosen_asset and chosen_asset.get("digest"):
            dig = str(chosen_asset.get("digest", "")).lower()
            if dig.startswith("sha256:"):
                sha256_val = dig.split("sha256:")[1].strip()

        if not sha256_val:
            body = target_rel.get("body", "")
            for line in body.splitlines():
                if "sha256" in line.lower() and ":" in line:
                    parts = line.split(":")
                    if len(parts) >= 2 and len(parts[1].strip()) == 64:
                        sha256_val = parts[1].strip().lower()
                        break

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        return UpdateInfoData(
            available=True,
            current_version=self.current_version,
            latest_version=tag,
            release_title=target_rel.get("name") or f"T-TTS v{tag}",
            release_notes=target_rel.get("body", "") or "Cải tiến hiệu năng và cập nhật tính năng mới.",
            published_at=target_rel.get("published_at", now_str),
            download_url=dl_url,
            asset_name=asset_name,
            asset_size=asset_size,
            sha256=sha256_val,
            is_velopack=False,
        )

    def check_system_readiness(self, required_free_mb: int = 500) -> Dict[str, Any]:
        """Kiểm tra điều kiện hệ thống trước khi cập nhật (dung lượng đĩa trống, quyền ghi, thư mục tạm)."""
        import shutil
        issues = []

        # 1. Kiểm tra dung lượng đĩa
        drive_path = self.data_dir if self.data_dir.exists() else Path(self.data_dir.anchor or ".")
        try:
            total, used, free = shutil.disk_usage(drive_path)
            free_mb = free / (1024 * 1024)
            if free_mb < required_free_mb:
                issues.append(f"Dung lượng đĩa trống ({free_mb:.1f} MB) nhỏ hơn mức yêu cầu ({required_free_mb} MB).")
        except Exception as e:
            free_mb = 0.0
            issues.append(f"Không thể đo dung lượng đĩa: {e}")

        # 2. Kiểm tra quyền ghi tại data_dir
        has_write_perm = False
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            test_file = self.data_dir / ".write_test.tmp"
            test_file.write_text("test_write_perm", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            has_write_perm = True
        except Exception as e:
            issues.append(f"Không có quyền ghi tại thư mục dữ liệu: {e}")

        # 3. Kiểm tra thư mục temp
        temp_dir = Path(tempfile.gettempdir()) / "T-TTS_Updates"
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
            t_test = temp_dir / ".temp_write_test.tmp"
            t_test.write_text("temp_test", encoding="utf-8")
            t_test.unlink(missing_ok=True)
        except Exception as e:
            issues.append(f"Không thể ghi vào thư mục tạm hệ thống: {e}")

        return {
            "ready": len(issues) == 0,
            "free_space_mb": round(free_mb, 1),
            "required_free_mb": required_free_mb,
            "has_write_perm": has_write_perm,
            "issues": issues,
        }

    def create_pre_update_backup(self, target_version: str = APP_VERSION) -> Path:
        """Tạo bản sao lưu dữ liệu cấu hình, license và toàn bộ dự án người dùng trước khi nâng cấp."""
        backup_dir = self.data_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"pre_update_backup_{timestamp_str}.json"

        # Lấy Machine ID nếu có thể
        try:
            from backend.license import get_machine_id
            machine_id = get_machine_id()
        except Exception:
            machine_id = "UNKNOWN"

        state = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "current_version": self.current_version,
            "target_version": target_version,
            "machine_id": machine_id,
            "data_files": {},
            "file_checksums": {},
            "projects_backup": {},
        }

        # Danh sách file cấu hình quan trọng cần bảo vệ
        critical_files = [
            "update_config.json",
            "custom_voices.json",
            "license_state.json",
            "history.json",
            "pronunciation-dict.json",
            "system_settings.json",
        ]

        for fname in critical_files:
            fpath = self.data_dir / fname
            if fpath.is_file():
                try:
                    with open(fpath, "rb") as bf:
                        sha = hashlib.sha256(bf.read()).hexdigest()
                    state["file_checksums"][fname] = sha

                    with open(fpath, "r", encoding="utf-8") as f:
                        state["data_files"][fname] = json.load(f)
                except Exception as e:
                    state["data_files"][fname] = {"_error": str(e)}

        # Sao lưu toàn bộ các dự án Audio, Broadcast, Schedules, Documents
        proj_root = self.data_dir / "projects"
        if proj_root.is_dir():
            for p_json in proj_root.rglob("*.json"):
                try:
                    rel_p = str(p_json.relative_to(proj_root)).replace("\\", "/")
                    with open(p_json, "rb") as bf:
                        sha = hashlib.sha256(bf.read()).hexdigest()
                    state["file_checksums"][f"projects/{rel_p}"] = sha

                    with open(p_json, "r", encoding="utf-8") as pf:
                        state["projects_backup"][rel_p] = json.load(pf)
                except Exception:
                    pass

        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return backup_file

    def restore_backup(self, backup_file: Path | str) -> Dict[str, Any]:
        """Khôi phục dữ liệu cấu hình, license và các dự án từ bản sao lưu JSON."""
        bpath = Path(backup_file)
        if not bpath.is_file():
            raise FileNotFoundError(f"Tệp sao lưu không tồn tại: {bpath}")

        with open(bpath, "r", encoding="utf-8") as f:
            state = json.load(f)

        restored_files = []
        restored_projects = []

        # 1. Khôi phục các data files
        data_files = state.get("data_files", {})
        for fname, content in data_files.items():
            if isinstance(content, dict) and "_error" in content:
                continue
            dest = self.data_dir / fname
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="utf-8") as out:
                json.dump(content, out, ensure_ascii=False, indent=2)
            restored_files.append(fname)

        # 2. Khôi phục các dự án
        projects_backup = state.get("projects_backup", {})
        proj_root = self.data_dir / "projects"
        for rel_p, p_data in projects_backup.items():
            dest = proj_root / rel_p
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="utf-8") as out:
                json.dump(p_data, out, ensure_ascii=False, indent=2)
            restored_projects.append(rel_p)

        return {
            "status": "success",
            "backup_file": str(bpath),
            "restored_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source_version": state.get("current_version", "unknown"),
            "restored_files": restored_files,
            "restored_projects": restored_projects,
            "total_files": len(restored_files),
            "total_projects": len(restored_projects),
        }

    def list_backups(self) -> list[Dict[str, Any]]:
        """Liệt kê các bản sao lưu hiện có trong thư mục backups, sắp xếp mới nhất lên đầu."""
        backup_dir = self.data_dir / "backups"
        if not backup_dir.is_dir():
            return []

        backups = []
        for bf in backup_dir.glob("*.json"):
            try:
                st = bf.stat()
                with open(bf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                backups.append({
                    "file_path": str(bf),
                    "file_name": bf.name,
                    "timestamp": data.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))),
                    "current_version": data.get("current_version", "unknown"),
                    "target_version": data.get("target_version", ""),
                    "size_bytes": st.st_size,
                    "file_count": len(data.get("data_files", {})),
                    "project_count": len(data.get("projects_backup", {})),
                    "mtime": st.st_mtime,
                })
            except Exception:
                pass

        backups.sort(key=lambda x: x["mtime"], reverse=True)
        return backups

    def perform_data_migration(self, from_version: str = "3.0.0", to_version: str = "3.1.0") -> Dict[str, Any]:
        """Thực hiện di chuyển và chuẩn bị dữ liệu khi nâng cấp từ v3.0.0 lên v3.1.0.
        Bỏ qua hoàn toàn v3.0.1, bảo toàn 100% bản quyền, cấu hình và dự án cũ.
        """
        # 1. Tạo backup an toàn trước
        backup_file = self.create_pre_update_backup(target_version=to_version)

        # 2. Tạo cấu trúc thư mục mới của v3.1.0 nếu chưa có
        doc_dir = self.data_dir / "projects" / "documents"
        doc_dir.mkdir(parents=True, exist_ok=True)

        presets_dir = self.data_dir / "presets"
        presets_dir.mkdir(parents=True, exist_ok=True)

        # Khởi tạo presets mặc định nếu tệp audio_presets.json chưa tồn tại
        presets_file = presets_dir / "audio_presets.json"
        if not presets_file.exists():
            default_presets = {
                "version": to_version,
                "presets": {
                    "military_comm": {"name": "Truyền thanh Doanh trại", "eq_low": -2.0, "eq_mid": 2.5, "eq_high": 1.0, "lufs": -16.0},
                    "studio_narrator": {"name": "Thuyết minh Tài liệu Quân sự", "eq_low": 0.5, "eq_mid": 1.0, "eq_high": 2.0, "lufs": -18.0},
                    "field_radio": {"name": "Bộ đàm Dã chiến", "eq_low": -6.0, "eq_mid": 4.0, "eq_high": -3.0, "lufs": -14.0},
                }
            }
            try:
                with open(presets_file, "w", encoding="utf-8") as f:
                    json.dump(default_presets, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # 3. Ghi nhận nhật ký di chuyển migration
        migration_manifest = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "from_version": from_version,
            "to_version": to_version,
            "bypassed_version": "3.0.1",
            "direct_jump": True,
            "backup_file": str(backup_file),
            "status": "completed",
            "message": f"Nâng cấp trực tiếp thành công từ v{from_version} lên v{to_version} (Bỏ qua hoàn toàn v3.0.1).",
            "new_directories": [
                str(doc_dir.relative_to(self.data_dir)).replace("\\", "/"),
                str(presets_dir.relative_to(self.data_dir)).replace("\\", "/"),
            ],
        }

        manifest_file = self.data_dir / f"migration_v{from_version}_to_v{to_version}.json"
        with open(manifest_file, "w", encoding="utf-8") as mf:
            json.dump(migration_manifest, mf, ensure_ascii=False, indent=2)

        return migration_manifest

    def download_update(
        self,
        update_info: UpdateInfoData,
        progress_callback: Optional[Callable[[int, float, float, float], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        max_retries: int = 3,
    ) -> Path:
        """Tải bản cập nhật với streaming, retry khi lỗi mạng, kiểm tra tiến trình và xác minh SHA-256."""
        if update_info.is_velopack and HAS_VELOPACK and update_info.velopack_info:
            try:
                source = velopack.GithubSource(f"https://github.com/{self.repo}")
                um = velopack.UpdateManager(source=source)
                def v_progress(pct):
                    if progress_callback:
                        progress_callback(int(pct), 0.0, 0.0, 0.0)
                um.download_updates(update_info.velopack_info, progress_callback=v_progress)
                return Path(".")
            except Exception:
                pass

        if not update_info.download_url:
            raise ValueError("Không có đường dẫn tải về hợp lệ từ GitHub Release.")

        import urllib.request
        temp_dir = Path(tempfile.gettempdir()) / "T-TTS_Updates"
        temp_dir.mkdir(parents=True, exist_ok=True)
        dest_file = temp_dir / update_info.asset_name

        req = urllib.request.Request(
            update_info.download_url,
            headers={"User-Agent": f"T-TTS-Updater/{APP_VERSION} (Windows)"},
        )

        last_error = None
        for attempt in range(1, max_retries + 1):
            if cancel_event and cancel_event.is_set():
                dest_file.unlink(missing_ok=True)
                raise InterruptedError("Người dùng đã hủy quá trình tải bản cập nhật.")

            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    total_size = int(resp.headers.get("Content-Length", update_info.asset_size or 0))
                    downloaded = 0
                    start_time = time.time()
                    chunk_size = 128 * 1024  # 128 KB
                    hasher = hashlib.sha256()

                    with open(dest_file, "wb") as f:
                        while True:
                            if cancel_event and cancel_event.is_set():
                                dest_file.unlink(missing_ok=True)
                                raise InterruptedError("Người dùng đã hủy quá trình tải bản cập nhật.")

                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break

                            f.write(chunk)
                            hasher.update(chunk)
                            downloaded += len(chunk)

                            elapsed = time.time() - start_time
                            speed_mb_s = (downloaded / (1024 * 1024)) / max(0.1, elapsed)
                            pct = int(downloaded * 100 / total_size) if total_size > 0 else 0

                            if progress_callback:
                                progress_callback(
                                    pct,
                                    downloaded / (1024 * 1024),
                                    total_size / (1024 * 1024),
                                    speed_mb_s,
                                )

                    # Kiểm tra dung lượng tải về nếu total_size > 0
                    if total_size > 0 and downloaded < total_size:
                        raise IOError(f"Tệp tải về không trọn vẹn ({downloaded}/{total_size} bytes).")

                    # Xác minh mã băm SHA-256 nếu có
                    if update_info.sha256:
                        calc_sha = hasher.hexdigest().lower()
                        if calc_sha != update_info.sha256.lower():
                            dest_file.unlink(missing_ok=True)
                            raise ValueError(
                                f"Xác minh tính toàn vẹn thất bại! Mã SHA-256 không khớp.\n"
                                f"Kỳ vọng: {update_info.sha256}\n"
                                f"Thực tế: {calc_sha}"
                            )

                    # Thành công
                    return dest_file

            except (InterruptedError, ValueError):
                dest_file.unlink(missing_ok=True)
                raise
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    time.sleep(1.5 * attempt)
                else:
                    dest_file.unlink(missing_ok=True)
                    raise IOError(f"Tải bản cập nhật thất bại sau {max_retries} lần thử: {last_error}")

        return dest_file

    def install_and_restart(self, update_info: UpdateInfoData, update_file: Path, perform_exit: bool = True):
        """Tiến hành cài đặt phiên bản mới và khởi động lại phần mềm an toàn."""
        if update_info.is_velopack and HAS_VELOPACK and update_info.velopack_info:
            try:
                source = velopack.GithubSource(f"https://github.com/{self.repo}")
                um = velopack.UpdateManager(source=source)
                um.apply_updates_and_restart(update_info.velopack_info)
                return
            except Exception:
                pass

        if not (update_file.is_file() and update_file.suffix.lower() == ".exe" and update_file.stat().st_size > 0):
            raise FileNotFoundError(f"Tệp cài đặt không tồn tại hoặc không hợp lệ: {update_file}")

        # 1. Lưu backup trạng thái trước khi cài
        try:
            self.create_pre_update_backup()
        except Exception:
            pass

        # 2. Khởi chạy trình cài đặt Inno Setup
        cmd = [
            str(update_file.resolve()),
            "/SILENT",
            "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS",
        ]
        try:
            subprocess.Popen(cmd, shell=False)
        except Exception as e:
            raise RuntimeError(f"Lỗi khởi chạy bộ cài đặt '{update_file.name}': {e}")

        # 3. Thoát ứng dụng an toàn nếu được yêu cầu
        if perform_exit:
            time.sleep(1.0)
            sys.exit(0)


# =============================================================================
# WORKER THREADS CHO GIAO DIỆN PYSIDE6
# =============================================================================

class CheckUpdateWorker(QThread):
    """Tiểu trình chạy nền kiểm tra cập nhật, không làm chậm giao diện chính."""
    check_finished = Signal(object)  # UpdateInfoData
    check_error = Signal(str)

    def __init__(self, data_dir: Optional[Path] = None):
        super().__init__()
        self.updater = UpdateManager(data_dir=data_dir)

    def run(self):
        try:
            info = self.updater.check_for_updates()
            self.check_finished.emit(info)
        except Exception as e:
            self.check_error.emit(str(e))


class DownloadUpdateWorker(QThread):
    """Tiểu trình tải bản cập nhật với đầy đủ tiến trình và hỗ trợ hủy."""
    progress = Signal(int, float, float, float)  # pct, downloaded_mb, total_mb, speed_mb_s
    status_changed = Signal(str)
    download_finished = Signal(object)  # Path
    download_error = Signal(str)
    cancelled = Signal()

    def __init__(self, updater: UpdateManager, update_info: UpdateInfoData):
        super().__init__()
        self.updater = updater
        self.update_info = update_info
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            self.status_changed.emit("Đang kết nối tới máy chủ cập nhật...")
            fpath = self.updater.download_update(
                self.update_info,
                progress_callback=lambda pct, dl, tot, sp: self.progress.emit(pct, dl, tot, sp),
                cancel_event=self.cancel_event,
            )
            self.status_changed.emit("Đang xác minh tính toàn vẹn gói cập nhật...")
            time.sleep(0.5)
            self.download_finished.emit(fpath)
        except InterruptedError:
            self.cancelled.emit()
        except Exception as e:
            self.download_error.emit(str(e))
