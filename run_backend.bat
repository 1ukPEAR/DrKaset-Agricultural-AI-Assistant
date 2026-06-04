@echo off
setlocal

cd /d "%~dp0backend"

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] Python virtual environment not found: backend\venv
  echo Please create it and install requirements first.
  pause
  exit /b 1
)

echo Starting DrKaset backend on http://127.0.0.1:8000
echo Press Ctrl+C to stop.
echo.

"venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

pause
