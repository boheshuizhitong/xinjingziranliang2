# Windows 一键启动 seekdb (Docker) + 后端 + 前端
# 前提: 已安装 Docker Desktop 并登录
# 用法: 在 PowerShell 中执行 .\start-all.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== [1/3] 启动 seekdb (Docker) ===" -ForegroundColor Cyan
$seekdbRunning = docker ps --format "{{.Names}}" | Select-String -Pattern "^seekdb$" -Quiet
if (-not $seekdbRunning) {
    docker run -d --name seekdb -p 2881:2881 oceanbase/seekdb 2>$null `
        -or docker start seekdb 2>$null `
        -or docker run -d --name seekdb -p 2881:2881 ghcr.io/oceanbase/seekdb
    Write-Host "seekdb 已启动, 等待就绪..."
    Start-Sleep -Seconds 5
} else {
    Write-Host "seekdb 已在运行"
}

Write-Host "=== [2/3] 安装后端依赖 ===" -ForegroundColor Cyan
Push-Location (Join-Path $PSScriptRoot "backend")
if (-not (Test-Path "node_modules")) { npm install }
Write-Host "启动后端 (端口 5174)..."
$backendProc = Start-Process -FilePath "node" -ArgumentList "server.js" -PassThru -NoNewWindow
Pop-Location

Write-Host "等待后端就绪..."
Start-Sleep -Seconds 3

Write-Host "=== [3/3] 安装前端依赖 ===" -ForegroundColor Cyan
Push-Location (Join-Path $PSScriptRoot "frontend")
if (-not (Test-Path "node_modules")) { npm install }
Write-Host "启动前端 (Vite dev server, 端口 5173)..."
$frontendProc = Start-Process -FilePath "npm" -ArgumentList "run","dev" -PassThru -NoNewWindow
Pop-Location

Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host " 前端: http://localhost:5173" -ForegroundColor Green
Write-Host " 后端: http://localhost:5174/api/health" -ForegroundColor Green
Write-Host " seekdb: 127.0.0.1:2881 (root, 空密码)" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host "按 Ctrl+C 停止所有服务"

try {
    while ($true) { Start-Sleep -Seconds 60 }
} finally {
    Write-Host "正在停止服务..."
    Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $frontendProc.Id -Force -ErrorAction SilentlyContinue
}
