# 学伴 StudyMate 一键启动（Windows / PowerShell）
# 用法：右键“使用 PowerShell 运行”，或在本目录执行  .\start.ps1
# 启动内容：① PowerContext 兼容服务(pc_server, 端口8010) ② 主应用(端口8080)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " 学伴 StudyMate 启动中" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

# ---- 1. Python 检查 ----
$py = $null
foreach ($cand in @("python", "py -3", "python3")) {
    try { $null = & $cand --version 2>$null; $py = $cand; break } catch {}
}
if (-not $py) { Write-Host "[X] 未找到 Python，请先安装 Python 3.11+ 并加入 PATH" -ForegroundColor Red; exit 1 }
Write-Host "[1/4] Python: $((& $py --version 2>&1))"

# ---- 2. 依赖安装（可选 venv）----
if (-not (Test-Path "$root\.venv")) {
    Write-Host "[2/4] 首次运行，创建虚拟环境并安装依赖（约几分钟）…"
    & $py -m venv "$root\.venv"
    & "$root\.venv\Scripts\python.exe" -m pip install --upgrade pip -q
    & "$root\.venv\Scripts\python.exe" -m pip install -r "$root\requirements.txt" -q
    if ($LASTEXITCODE -ne 0) { Write-Host "[X] 依赖安装失败" -ForegroundColor Red; exit 1 }
}
$vpy = "$root\.venv\Scripts\python.exe"
Write-Host "[2/4] Python 环境就绪: $vpy"

# ---- 3. 启动 PowerContext（若已配置 POWERCONTEXT_URL 则跳过）----
if ($env:POWERCONTEXT_URL) {
    Write-Host "[3/4] 使用外部 PowerContext: $env:POWERCONTEXT_URL"
} else {
    Write-Host "[3/4] 启动 PowerContext 兼容服务 (端口 8010)…"
    $env:POWERCONTEXT_PORT = "8010"
    Start-Process -FilePath $vpy -ArgumentList "$root\pc_server\server.py" `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput "$root\data\pc_server.log" `
        -RedirectStandardError "$root\data\pc_server.err.log"
    Start-Sleep -Seconds 3
    try {
        $h = Invoke-WebRequest -Uri "http://127.0.0.1:8010/health/live" -UseBasicParsing -TimeoutSec 5
        Write-Host "      PowerContext 就绪: $($h.StatusCode)" -ForegroundColor Green
    } catch {
        Write-Host "      [警告] PowerContext 未就绪，请查看 data\pc_server.err.log" -ForegroundColor Yellow
    }
}

# ---- 4. 启动主应用 ----
Write-Host "[4/4] 启动主应用 (端口 8080)…"
Write-Host ""
Write-Host "  ➜ 打开浏览器访问:  http://127.0.0.1:8080" -ForegroundColor Green
Write-Host "  ➜ 停止服务: 关闭本窗口（PowerContext 用 taskkill /f /pid <pid> 或重启电脑）" -ForegroundColor Yellow
& $vpy -m uvicorn app.main:app --host 127.0.0.1 --port 8080
