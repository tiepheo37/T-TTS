import sys, traceback
from pathlib import Path
sys.path.insert(0, r"D:\cac loai app\voice-studio-app")
try:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from gui.main_window import MainWindow
    mw = MainWindow()
    print("MainWindow created successfully!")
except Exception:
    traceback.print_exc()
