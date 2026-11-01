# SDD 上下文管理系统 —— 一键启动（Windows PowerShell）
# 用法：
#   .\start.ps1                 # 建 venv、装依赖、启动 PowerContext、导入资料、运行验证
#   .\start.ps1 -SkipVerify     # 只启动服务与导入，不跑验证
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location -LiteralPath $root

if (-not (Test-Path -LiteralPath "$root\.venv\Scripts\python.exe")) {
    Write-Host "[1/4] 创建虚拟环境..."
    python -m venv "$root\.venv"
}
$py = "$root\.venv\Scripts\python.exe"

Write-Host "[2/4] 安装依赖..."
& $py -m pip install -r "$root\requirements.txt" | Out-Null

Write-Host "[3/4] 启动 PowerContext 兼容服务器（端口 8010）..."
$pc = Start-Process -FilePath $py -ArgumentList "$root\pc_server\server.py" `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3
Write-Host "      PowerContext PID=$($pc.Id)  http://127.0.0.1:8010"

Write-Host "[4/4] 导入工程资料到 seekdb..."
& $py -m context_module --import --clear

if ($args -contains "-SkipVerify") {
    Write-Host "已跳过验证。手动运行验证：python samples\verify.py --reset"
} else {
    Write-Host "运行验收验证样例（如已配置 MINIMAX_API_KEY 则含 MiniMax 修改步骤）..."
    & $py samples\verify.py --reset
}
