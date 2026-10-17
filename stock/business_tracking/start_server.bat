@echo off
REM Start the Cycle Observatory local server (http://127.0.0.1:8321)
cd /d "%~dp0"
"C:\Users\xuetaotao\.workbuddy\binaries\python\envs\default\Scripts\python.exe" -m uvicorn app.server:app --port 8321 --host 127.0.0.1
pause
