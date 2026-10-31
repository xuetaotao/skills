@echo off
REM Start the ETF Screener local server (http://127.0.0.1:8324)
REM ETF lists, shares and prices are refreshed in the background every time the server starts,
REM and a snapshot for the day is saved. Set ETF_AUTO_REFRESH=0 to disable that.
cd /d "%~dp0.."
call :find_python || (pause & exit /b 1)
call :check_deps || (pause & exit /b 1)
REM Open the browser in the background once the server responds (gives up after ~15s)
start "" /b powershell -NoProfile -Command "for ($i = 0; $i -lt 30; $i++) { try { Invoke-WebRequest http://127.0.0.1:8324/api/status -UseBasicParsing -TimeoutSec 1 | Out-Null; Start-Process 'http://127.0.0.1:8324'; break } catch { Start-Sleep -Milliseconds 500 } }"
"%PY%" -m uvicorn backend.server:app --port 8324 --host 127.0.0.1
pause
exit /b
:find_python
REM Use this project's .venv. Create it with PATH python when it is missing.
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
  exit /b 0
)
where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo Python was not found on PATH, so .venv could not be created.
  echo Install Python and add it to PATH, then run this script again.
  echo.
  exit /b 1
)
echo No .venv in this project. Creating one and installing requirements.txt ...
python -m venv .venv
if errorlevel 1 exit /b 1
set "PY=.venv\Scripts\python.exe"
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
exit /b 0

:check_deps
"%PY%" -c "import fastapi, uvicorn, akshare, pandas, requests, openpyxl" >nul 2>&1
if errorlevel 1 (
  echo.
  echo Missing Python packages in: %PY%
  echo Install them with:
  echo     "%PY%" -m pip install -r requirements.txt
  echo.
  exit /b 1
)
exit /b 0