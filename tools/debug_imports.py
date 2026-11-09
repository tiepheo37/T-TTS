import sys, traceback
from pathlib import Path
sys.path.insert(0, r"D:\cac loai app\voice-studio-app")

try:
    print("Step 1: QApplication")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    print("Step 2: tts_service")
    from backend.service import tts_service

    print("Step 3: scheduler_engine")
    from backend.scheduler_engine import scheduler_engine

    print("Step 4: MainWindow")
    from gui.main_window import MainWindow

    print("Step 5: initialize_model")
    if not tts_service.engine.ready:
        tts_service.initialize_model()
    print("Model initialized!")
except Exception:
    traceback.print_exc()
