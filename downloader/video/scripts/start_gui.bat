@echo off
REM Start the video/audio downloader GUI (command line: python -m backend video <url>)
cd /d "%~dp0.."
call :find_python || (pause & exit /b 1)
call :check_deps || (pause & exit /b 1)
where ffmpeg >nul 2>&1 || echo Note: ffmpeg was not found on PATH. Merging video+audio, mp3 conversion and mp4 remuxing will be unavailable.
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
exit /b 0

:check_deps
"%PY%" -c "import yt_dlp, requests, Cryptodome, PyQt5" >nul 2>&1
if errorlevel 1 (
  echo.
  echo Missing Python packages in: %PY%
  echo Install them with:
  echo     python -m venv .venv
  echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo.
  exit /b 1
)
exit /b 0
