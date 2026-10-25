@echo off
REM Update financial reports, quotes, valuation history and dividends for the watchlist and their industry peers
REM Usage: update_data.bat            (whole watchlist)
REM        update_data.bat 600900     (only these stocks and their peers)
cd /d "%~dp0.."
call :find_python
call :check_deps || (pause & exit /b 1)
"%PY%" -m backend.update %*
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
"%PY%" -c "import akshare, pandas, requests, xlrd" >nul 2>&1
if errorlevel 1 (
  echo.
  echo Missing Python packages in: %PY%
  echo Install them with:
  echo     "%PY%" -m pip install -r requirements.txt
  echo.
  exit /b 1
)
exit /b 0
