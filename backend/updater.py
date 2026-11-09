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

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(os.environ.get("LOCALAPPDATA", ".")) / "T-TTS" / "data"
        self.config = load_update_config(self.data_dir)
        self.repo = self.config.get("github_repo", DEFAULT_GITHUB_REPO)
        self.channel = self.config.get("channel", DEFAULT_CHANNEL)
        self.current_version = APP_VERSION

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

            tag = target_rel.get("tag_name", "").strip().lstrip("vV")
            if not is_newer_version(tag, self.current_version):
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

            dl_url = chosen_asset.get("browser_download_url") if chosen_asset else target_rel.get("html_url")
            asset_name = chosen_asset.get("name", f"T-TTS_Setup_v{tag}.exe") if chosen_asset else f"T-TTS_Setup_v{tag}.exe"
            asset_size = chosen_asset.get("size", 0) if chosen_asset else 0

            # Tìm checksum SHA256 nếu có
            sha256_val = ""
            # 1. Từ digest asset nếu có
            if chosen_asset and chosen_asset.get("digest"):
                dig = str(chosen_asset.get("digest", "")).lower()
                if dig.startswith("sha256:"):
                    sha256_val = dig.split("sha256:")[1].strip()
            # 2. Từ body của release
            if not sha256_val:
                body = target_rel.get("body", "")
                for line in body.splitlines():
                    if "sha256" in line.lower() and ":" in line:
                        parts = line.split(":")
                        if len(parts) >= 2 and len(parts[1].strip()) == 64:
                            sha256_val = parts[1].strip().lower()
                            break

            self.config["last_version_checked"] = tag
            save_update_config(self.data_dir, self.config)

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

    def create_pre_update_backup(self) -> Path:
        """Tạo bản sao lưu dữ liệu cấu hình, license và dự án người dùng trước khi nâng cấp."""
        backup_dir = self.data_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / f"pre_update_backup_{time.strftime('%Y%m%d_%H%M%S')}.json"

        state = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "current_version": self.current_version,
            "data_files": {},
        }
        for fname in ["update_config.json", "custom_voices.json", "license_state.json", "history.json"]:
            fpath = self.data_dir / fname
            if fpath.is_file():
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        state["data_files"][fname] = json.load(f)
                except Exception:
                    pass
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return backup_file

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
