@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python，请先安装 Python 3.10+
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo 正在创建虚拟环境并安装依赖…
  python -m venv .venv
  call ".venv\Scripts\activate.bat"
  python -m pip install -r requirements.txt
) else (
  call ".venv\Scripts\activate.bat"
)

set PORT=8765
echo 启动流量新闻台 http://127.0.0.1:%PORT%
start "" "http://127.0.0.1:%PORT%/"
python -m uvicorn app:app --host 127.0.0.1 --port %PORT%
pause
