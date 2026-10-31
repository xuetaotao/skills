@echo off
REM Update financial reports, quotes, valuation history and dividends for the watchlist and their industry peers
REM Usage: update_data.bat            (whole watchlist)
REM        update_data.bat 600900     (only these stocks and their peers)
cd /d "%~dp0.."
call :find_python || (pause & exit /b 1)
call :check_deps || (pause & exit /b 1)
"%PY%" -m backend.update %*
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
