import sys
from pathlib import Path

BASE = Path(r"D:\cac loai app\voice-studio-app")
sys.path.insert(0, str(BASE))

from backend.updater import UpdateManager

mgr = UpdateManager()
print(f"Update Source Repo: {mgr.repo}")

# Test 1: v3.0.0 (current)
info = mgr.check_for_updates()
print(f"[Test 1: Normal check v3.0.0]")
print(f"  - Available: {info.available}")
print(f"  - Current: {info.current_version}")
print(f"  - Latest: {info.latest_version}")
print(f"  - Error msg: {info.error_msg or 'None (Thành công 100%)'}")

# Test 2: Simulated older client checking for update
mgr.current_version = "2.0.0"
info2 = mgr.check_for_updates()
print(f"[Test 2: Older client v2.0.0 check]")
print(f"  - Available: {info2.available}")
print(f"  - Current: {info2.current_version}")
print(f"  - Latest: {info2.latest_version}")
print(f"  - Asset name: {info2.asset_name}")
print(f"  - Asset size: {round(info2.asset_size / (1024*1024), 2)} MB")
print(f"  - Download URL: {info2.download_url}")
