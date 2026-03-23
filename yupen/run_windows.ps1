$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    python -m venv .venv
}

& $venvPython -m pip install -r requirements.txt

Set-Location (Join-Path $projectRoot "src")
& $venvPython main.py
