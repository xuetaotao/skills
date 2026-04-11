# WeChat Article Downloader - One-click runner (Windows)

$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$VENV_PATH = Join-Path $SCRIPT_DIR ".venv"
$VENV_PYTHON = Join-Path $VENV_PATH "Scripts\python.exe"

# Check if virtual environment exists
if (-not (Test-Path $VENV_PYTHON)) {
    Write-Host "Virtual environment not found. Creating one..."
    Set-Location $SCRIPT_DIR
    python -m venv .venv
    & $VENV_PYTHON -m pip install -r requirements.txt
    & $VENV_PYTHON -m playwright install chromium
} else {
    & $VENV_PYTHON -m pip install -r requirements.txt
}

# Check if URL is provided
if (-not $args[0]) {
    Write-Host "Usage: .\run_windows.ps1 <wechat_article_url>"
    Write-Host "Example: .\run_windows.ps1 https://mp.weixin.qq.com/s/xxxxx"
    exit 1
}

# Run the downloader
Set-Location $SCRIPT_DIR
& $VENV_PYTHON -m src $args[0]
