# Image Downloader - One-click runner (Windows)

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
} else {
    & $VENV_PYTHON -m pip install -r requirements.txt
}

# Run the launcher GUI by default
Set-Location $SCRIPT_DIR
& $VENV_PYTHON -m src gui
