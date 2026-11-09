@echo off
chcp 65001 >nul
title T-TTS — Đóng gói Bản Phát Hành Auto Update
echo ================================================================================
echo    T-TTS v3.0 — HỆ THỐNG TRỢ LÝ GIỌNG NÓI QUÂN ĐỘI
echo    Tác giả: Nguyễn Văn Tiệp
echo    Quy trình đóng gói tự động chuẩn GitHub Releases / VelopPack
echo ================================================================================
echo.

python312\python\python.exe tools\build_update_release.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LỖI] Quá trình build thất bại! Vui lòng kiểm tra thông báo lỗi bên trên.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ================================================================================
echo [THÀNH CÔNG] Bản phát hành và metadata đã sẵn sàng trong thư mục dist/
echo ================================================================================
pause
