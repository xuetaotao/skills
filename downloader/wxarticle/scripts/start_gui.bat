@echo off
REM Start the WeChat article downloader GUI (command line: python -m backend <url> [url ...])
cd /d "%~dp0.."
call :find_python || (pause & exit /b 1)
call :check_deps || (pause & exit /b 1)
"%PY%" -m frontend
if errorlevel 1 pause
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
echo Installing Playwright Chromium ...
"%PY%" -m playwright install chromium
if errorlevel 1 exit /b 1
exit /b 0

:check_deps
"%PY%" -c "import playwright, PyQt5" >nul 2>&1
if errorlevel 1 (
  echo.
  echo Missing Python packages in: %PY%
  echo Install them with:
  echo     python -m venv .venv
  echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo     .venv\Scripts\python.exe -m playwright install chromium
  echo.
  exit /b 1
)
exit /b 0
