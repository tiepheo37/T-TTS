"""tools/capture_sprint_5_screenshots.py — Chụp ảnh giao diện minh họa Sprint 5 (Phase 9)
"""

import os
import shutil
import sys
import tempfile
import time
import math
import struct
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.ffmpeg_bootstrap import initialize_ffmpeg
initialize_ffmpeg()

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from gui.dialog_voice_analyzer import VoiceQualityAnalyzerDialog
from gui.pages.page_audio_studio import PageAudioStudio
from gui.pages.page_broadcast import PageBroadcast

def create_sample_wav(path: Path):
    sr = 48000
    duration_sec = 2.5
    total = int(sr * duration_sec)
    samples = []
    # 0.3s lead silence
    for _ in range(int(0.3 * sr)):
        samples.append(0)
    # Tone
    tone_len = total - int(0.6 * sr)
    for i in range(tone_len):
        v = 0.25 * math.sin(2.0 * math.pi * 440.0 * (i / sr))
        samples.append(int(v * 32767.0))
    # 0.3s trail silence
    for _ in range(int(0.3 * sr)):
        samples.append(0)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))

def main():
    app = QApplication.instance() or QApplication([])

    docs_dir = PROJECT_ROOT / "docs" / "screenshots"
    docs_dir.mkdir(parents=True, exist_ok=True)

    artifact_dir = Path(r"C:\Users\Minh Dang\.gemini\antigravity\brain\d6a22ea3-cf3a-46e7-8bfd-850b7f7adf9d")

    temp_wav = PROJECT_ROOT / "data" / "temp_analyzer_demo.wav"
    temp_wav.parent.mkdir(parents=True, exist_ok=True)
    create_sample_wav(temp_wav)

    # 1. VoiceQualityAnalyzerDialog
    print("Capturing VoiceQualityAnalyzerDialog...")
    dlg = VoiceQualityAnalyzerDialog(temp_wav)
    dlg.show()
    if hasattr(dlg, "worker") and dlg.worker.isRunning():
        dlg.worker.wait(3000)
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()

    shot1 = docs_dir / "sprint_5_voice_quality_analyzer_dialog.png"
    pix1 = dlg.grab()
    pix1.save(str(shot1))
    if artifact_dir.exists():
        shutil.copy2(shot1, artifact_dir / shot1.name)
    dlg.close()

    # 2. PageAudioStudio with btn_analyze
    print("Capturing PageAudioStudio...")
    studio = PageAudioStudio()
    studio.resize(1100, 700)
    studio.show()
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()

    shot2 = docs_dir / "sprint_5_audio_studio_analyzer_toolbar.png"
    pix2 = studio.grab()
    pix2.save(str(shot2))
    if artifact_dir.exists():
        shutil.copy2(shot2, artifact_dir / shot2.name)
    studio.close()

    # 3. PageBroadcast with Smart Mix button
    print("Capturing PageBroadcast...")
    bc = PageBroadcast()
    bc.resize(1100, 700)
    bc.show()
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()

    shot3 = docs_dir / "sprint_5_broadcast_smart_mix.png"
    pix3 = bc.grab()
    pix3.save(str(shot3))
    if artifact_dir.exists():
        shutil.copy2(shot3, artifact_dir / shot3.name)
    bc.close()

    if temp_wav.exists():
        temp_wav.unlink()

    print("All screenshots captured and copied successfully!")

if __name__ == "__main__":
    main()
