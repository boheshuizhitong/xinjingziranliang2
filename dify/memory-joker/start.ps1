# ============================================================
# AI Memory Joker · One-click startup (Windows PowerShell)
# ============================================================
# 1. Installs Python deps for PowerContext
# 2. Launches PowerContext memory server on http://localhost:8000
# ============================================================

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  AI Memory Joker · PowerContext Server" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$Here\powercontext"

# Check python
$py = $null
foreach ($candidate in @("python3", "python")) {
    try {
        $v = & $candidate --version 2>&1
        if ($LASTEXITCODE -eq 0) { $py = $candidate; break }
    } catch {}
}

if (-not $py) {
    Write-Host "[ERROR] Python 3 not found. Please install Python 3.10+" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Using $py" -ForegroundColor Green

# Install deps
Write-Host "[…] Installing dependencies ..." -ForegroundColor Yellow
& $py -m pip install -q fastapi uvicorn pydantic 2>&1 | Out-Null

# Kill any existing server on port 8000
try {
    $listener = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
    if ($listener) {
        $pid = $listener.OwningProcess
        Write-Host "[!] Port 8000 occupied by PID $pid, killing ..." -ForegroundColor Yellow
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
} catch {}

# Start server
Write-Host ""
Write-Host "🚀 Starting PowerContext on http://0.0.0.0:8000" -ForegroundColor Green
Write-Host "   Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

& $py server.py
