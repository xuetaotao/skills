@echo off
REM Incremental update of all data series (safe to run daily)
cd /d "%~dp0"
"C:\Users\xuetaotao\.workbuddy\binaries\python\envs\default\Scripts\python.exe" -m app.update
pause
