$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"
$pythonExe = Join-Path $backendDir "venv\Scripts\python.exe"
$hostAddr = "127.0.0.1"
$port = 8000

if (-not (Test-Path -LiteralPath $pythonExe)) {
    Write-Error "Python virtual environment not found: $pythonExe"
}

$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Host "Backend already listening on http://$hostAddr`:$port (PID: $($listener[0].OwningProcess))"
    exit 0
}

Write-Host "Starting DrKaset backend on http://$hostAddr`:$port"
Write-Host "Working directory: $backendDir"

Push-Location $backendDir
try {
    & $pythonExe -m uvicorn main:app --host $hostAddr --port $port
}
finally {
    Pop-Location
}
