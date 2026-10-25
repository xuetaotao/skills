@echo off
REM Start the Financial Report Tracker local server (http://127.0.0.1:8323)
REM Data for your watchlist and their industry peers is refreshed in the background every time the server starts.
REM Set FIN_AUTO_REFRESH=0 to disable that.
cd /d "%~dp0.."
call :find_python
call :check_deps || (pause & exit /b 1)
REM Open the browser in the background once the server responds (gives up after ~15s)
start "" /b powershell -NoProfile -Command "for ($i = 0; $i -lt 30; $i++) { try { Invoke-WebRequest http://127.0.0.1:8323/api/status -UseBasicParsing -TimeoutSec 1 | Out-Null; Start-Process 'http://127.0.0.1:8323'; break } catch { Start-Sleep -Milliseconds 500 } }"
"%PY%" -m uvicorn backend.server:app --port 8323 --host 127.0.0.1
pause
exit /b

:find_python
REM Priority: project .venv > WorkBuddy managed env > python on PATH
set "PY=python"
set "WB_PY=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if exist "%WB_PY%" set "PY=%WB_PY%"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
exit /b

:check_deps
"%PY%" -c "import fastapi, uvicorn, akshare, pandas, requests, xlrd" >nul 2>&1
if errorlevel 1 (
  echo.
  echo Missing Python packages in: %PY%
  echo Install them with:
  echo     "%PY%" -m pip install -r requirements.txt
  echo.
  exit /b 1
)
exit /b 0
