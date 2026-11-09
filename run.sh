#!/usr/bin/env bash
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

cd "$(dirname "$0")"

echo "============================================================"
echo "  VOICE STUDIO - CHUYỂN VĂN BẢN THÀNH GIỌNG NÓI TIẾNG VIỆT"
echo "============================================================"

if [ ! -d "venv" ]; then
    echo "Đang tạo môi trường ảo (venv)..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Đang cài đặt thư viện..."
pip install -r requirements.txt

echo "Kiểm tra import..."
python3 -c "import flask, vieneu; print('[OK] Import thành công!')"

echo "Mở trình duyệt: http://127.0.0.1:8001"
echo "API Docs:      http://127.0.0.1:8001/docs"
python3 -m backend.app
