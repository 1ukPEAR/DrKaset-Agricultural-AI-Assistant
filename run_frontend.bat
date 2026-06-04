@echo off
setlocal

cd /d "%~dp0frontend"

if not exist "package.json" (
  echo [ERROR] package.json not found in frontend folder.
  pause
  exit /b 1
)

if not exist "node_modules" (
  echo [INFO] node_modules not found. Installing dependencies...
  npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed.
    pause
    exit /b 1
  )
)

echo Starting DrKaset frontend on http://127.0.0.1:5173
echo Press Ctrl+C to stop.
echo.

npm run dev -- --host 127.0.0.1 --port 5173

pause
