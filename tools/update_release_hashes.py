import hashlib
import json
import os
from pathlib import Path

BASE_DIR = Path(r"D:\cac loai app\voice-studio-app")
DIST_DIR = BASE_DIR / "dist"

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

installer_path = DIST_DIR / "T-TTS_Setup_v3.0_Offline.exe"
portable_path = DIST_DIR / "T-TTS_v3.0_Desktop_Portable.zip"

print("Calculating hashes...")
h_inst = sha256_file(installer_path)
h_port = sha256_file(portable_path)

print(f"Installer: {h_inst}")
print(f"Portable:  {h_port}")

# Copy installer to T-TTS_Setup_v3.0.0.Offline.exe as well for convenience
import shutil
shutil.copy2(installer_path, DIST_DIR / "T-TTS_Setup_v3.0.0.Offline.exe")

checksums_content = f"{h_inst} *T-TTS_Setup_v3.0_Offline.exe\n{h_inst} *T-TTS_Setup_v3.0.0.Offline.exe\n{h_port} *T-TTS_v3.0_Desktop_Portable.zip\n"
(DIST_DIR / "checksums.txt").write_text(checksums_content, encoding="utf-8")

metadata = {
    "version": "3.0.0",
    "github_repo": "tiepheo37/T-TTS",
    "author": "Nguyễn Văn Tiệp",
    "files": [
        {
            "name": "T-TTS_Setup_v3.0_Offline.exe",
            "size_bytes": installer_path.stat().st_size,
            "sha256": h_inst,
        },
        {
            "name": "T-TTS_Setup_v3.0.0.Offline.exe",
            "size_bytes": (DIST_DIR / "T-TTS_Setup_v3.0.0.Offline.exe").stat().st_size,
            "sha256": h_inst,
        },
        {
            "name": "T-TTS_v3.0_Desktop_Portable.zip",
            "size_bytes": portable_path.stat().st_size,
            "sha256": h_port,
        }
    ]
}

(DIST_DIR / "release_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
print("Updated checksums.txt and release_metadata.json successfully.")
