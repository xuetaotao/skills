@echo off
REM Start the video/audio downloader GUI (command line: python -m backend video <url>)
cd /d "%~dp0.."
call :find_python
call :check_deps || (pause & exit /b 1)
where ffmpeg >nul 2>&1 || echo Note: ffmpeg was not found on PATH. Merging video+audio, mp3 conversion and mp4 remuxing will be unavailable.
"%PY%" -m frontend
if errorlevel 1 pause
exit /b

:find_python
REM Priority: project .venv > WorkBuddy managed env > python on PATH
set "PY=python"
set "WB_PY=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if exist "%WB_PY%" set "PY=%WB_PY%"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
exit /b

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
