$ErrorActionPreference = "Stop"

$originalDir = (Get-Location).Path
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

try {
    Set-Location $projectRoot

    if (-not (Test-Path $venvPython)) {
        python3 -m venv .venv
    }

    & $venvPython -m pip install -r requirements.txt

    Set-Location (Join-Path $projectRoot "src")
    & $venvPython main.py
}
finally {
    Set-Location $originalDir
}

