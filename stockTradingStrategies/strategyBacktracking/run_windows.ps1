$ErrorActionPreference = "Stop"

$originalDir = (Get-Location).Path
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

try {
    Set-Location $projectRoot

    if (-not (Test-Path $venvPython)) {
        python -m venv .venv
    }

    & $venvPython -m pip install -r requirements.txt

    # 使用 -m 方式运行，确保包内相对导入正常
    & $venvPython -m src
}
finally {
    Set-Location $originalDir
}
