# 行情复盘汇总一键运行脚本（Windows / PowerShell）
# 复用 yupen 的虚拟环境（内含 akshare / pandas 等依赖）
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$yupenVenvPython = Join-Path $scriptDir "..\..\yupen\.venv\Scripts\python.exe"

if (-not (Test-Path $yupenVenvPython)) {
    Write-Host "未找到 yupen 虚拟环境：$yupenVenvPython"
    Write-Host "请先在 yupen 目录执行 run_windows.ps1 初始化环境。"
    exit 1
}

& $yupenVenvPython (Join-Path $scriptDir "main.py")
