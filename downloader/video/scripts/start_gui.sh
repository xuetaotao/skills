#!/usr/bin/env bash
# Linux / macOS：启动音视频下载器图形界面（命令行：python -m backend video <网址>）
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  command -v python3 >/dev/null || { echo "Python 3 was not found on PATH, so .venv could not be created."; exit 1; }
  echo "No .venv in this project. Creating one and installing requirements.txt ..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
PY=.venv/bin/python
"$PY" -c "import yt_dlp, requests, Cryptodome, PyQt5" 2>/dev/null || { echo "Missing Python packages in $PY. Install them with: $PY -m pip install -r requirements.txt"; exit 1; }
command -v ffmpeg >/dev/null || echo "提示：没有找到 ffmpeg，合并音视频、转 mp3、转封装 mp4 将不可用"
exec "$PY" -m frontend
