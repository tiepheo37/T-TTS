@echo off
chcp 65001 >nul
title T-TTS v3.0 — CÔNG CỤ CẤP BẢN QUYỀN OFFLINE
cd /d "%~dp0"

echo Đang khởi động Ứng dụng Cấp Key T-TTS v3.0...

if exist "tools\T-TTS_KeyGenerator.exe" (
    start "" "tools\T-TTS_KeyGenerator.exe"
    exit /b 0
)

set PYTHON_EXE=python
if exist "python312\python\python.exe" (
    set PYTHON_EXE=python312\python\python.exe
)

start "" "%PYTHON_EXE%" "tools\key_generator_gui.py"
exit /b 0
