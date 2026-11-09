@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
REM Chạy Voice Studio - Quân đội Nhân dân Việt Nam

cd /d "%~dp0"

echo ============================================================
echo   VOICE STUDIO - CHUYỂN VĂN BẢN THÀNH GIỌNG NÓI TIẾNG VIỆT
echo ============================================================

REM Kiểm tra Python 3.12 / Standalone Python
set PYTHON_EXE=python
if exist "python312\python\python.exe" (
    set PYTHON_EXE=python312\python\python.exe
    echo [OK] Phát hiện Python 3.12 tích hợp sẵn tại python312\python\python.exe
)

REM Kiểm tra version Python hệ thống nếu không dùng standalone
if "%PYTHON_EXE%"=="python" (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
    echo Version Python hệ thống: %PY_VER%
    echo %PY_VER% | findstr /R "^3\.14" >nul
    if %errorlevel%==0 (
        echo [CẢNH BÁO] Hệ thống đang chạy Python 3.14+ (kaldi-native-fbank chưa có wheel sẵn).
        echo Yêu cầu sử dụng Python 3.10 - 3.13 (khuyến nghị Python 3.12).
    )
)

REM Tạo venv nếu chưa có
if not exist "venv" (
    echo Đang tạo môi trường ảo (venv)...
    "%PYTHON_EXE%" -m venv venv
)

REM Kích hoạt venv
call venv\Scripts\activate.bat

python -c "import flask, vieneu" >nul 2>&1
if %errorlevel% neq 0 (
    echo Đang cập nhật thư viện từ requirements.txt...
    pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org
) else (
    echo [OK] Môi trường thư viện đã sẵn sàng (Skip pip install)!
)

echo.
echo Kiểm tra các thư viện cốt lõi...
python -c "import flask, vieneu; print('[OK] Cả Flask và VieNeu-TTS đều hoạt động chuẩn xác!')"
if %errorlevel% neq 0 (
    echo [LỖI] Chưa nạp được Flask hoặc VieNeu. Kiểm tra lại thông báo ở trên.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   ỨNG DỤNG ĐÃ SẴN SÀNG!
echo   Mở trình duyệt truy cập: http://127.0.0.1:8001
echo   Tài liệu Local API:      http://127.0.0.1:8001/docs
echo ============================================================
echo.

python -m backend.app
pause
