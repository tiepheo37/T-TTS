import os
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src_dir = ROOT / "release_test" / "T-TTS_v3.0_Desktop"
zip_path = ROOT / "dist" / "T-TTS_v3.0_Desktop_Portable.zip"

print(f"Creating Portable ZIP archive from: {src_dir}")
t0 = time.time()
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            fpath = Path(root) / f
            arcname = fpath.relative_to(src_dir.parent)
            zf.write(fpath, arcname)

size_mb = zip_path.stat().st_size / (1024 * 1024)
print(f"Portable ZIP archive successfully created: {zip_path.name} ({size_mb:.2f} MB) in {time.time()-t0:.1f}s")
