"""tools/capture_sprint_6_screenshots.py — Chụp ảnh giao diện minh họa Sprint 6 Full Integration
"""

import os
import shutil
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.ffmpeg_bootstrap import initialize_ffmpeg
initialize_ffmpeg()

from PySide6.QtWidgets import QApplication
from gui.pages.page_synthesize import PageSynthesize
from gui.pages.page_batch import PageBatch
from gui.pages.page_audio_studio import PageAudioStudio
from gui.pages.page_schedule import PageSchedule, DocumentToTTSDialog

def main():
    app = QApplication.instance() or QApplication([])

    docs_dir = PROJECT_ROOT / "docs" / "screenshots"
    docs_dir.mkdir(parents=True, exist_ok=True)

    artifact_dir = Path(r"C:\Users\Minh Dang\.gemini\antigravity\brain\d6a22ea3-cf3a-46e7-8bfd-850b7f7adf9d")

    # 1. Synthesize Studio with Inter-module Buttons
    print("Capturing PageSynthesize...")
    synth = PageSynthesize()
    synth.resize(1150, 750)
    synth.player_card.setVisible(True)
    synth.lbl_result_info.setText("<b>Tệp âm thanh:</b> demo_speech.wav | <b>Độ dài:</b> 00:04.2 | <b>Tốc độ:</b> 1.00x")
    synth.show()
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()

    shot1 = docs_dir / "sprint_6_synthesize_integration.png"
    synth.grab().save(str(shot1))
    if artifact_dir.exists():
        shutil.copy2(shot1, artifact_dir / shot1.name)
    synth.close()

    # 2. Batch TTS with PDF/DOCX and Text Normalization Checkbox
    print("Capturing PageBatch...")
    batch = PageBatch()
    batch.resize(1150, 750)
    batch.show()
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()

    shot2 = docs_dir / "sprint_6_batch_document_normalization.png"
    batch.grab().save(str(shot2))
    if artifact_dir.exists():
        shutil.copy2(shot2, artifact_dir / shot2.name)
    batch.close()

    # 3. Audio Studio with Send to Broadcast & Schedule
    print("Capturing PageAudioStudio...")
    studio = PageAudioStudio()
    studio.resize(1150, 750)
    studio.show()
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()

    shot3 = docs_dir / "sprint_6_audio_studio_integration_toolbar.png"
    studio.grab().save(str(shot3))
    if artifact_dir.exists():
        shutil.copy2(shot3, artifact_dir / shot3.name)
    studio.close()

    # 4. Schedule Studio with Document-to-TTS Dialog
    print("Capturing Schedule Studio Document-to-TTS...")
    doc_dlg = DocumentToTTSDialog()
    doc_dlg.show()
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()

    shot4 = docs_dir / "sprint_6_schedule_document_tts_dialog.png"
    doc_dlg.grab().save(str(shot4))
    if artifact_dir.exists():
        shutil.copy2(shot4, artifact_dir / shot4.name)
    doc_dlg.close()

    print("All Sprint 6 screenshots captured and copied successfully!")

if __name__ == "__main__":
    main()
