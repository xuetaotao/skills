#!/usr/bin/env bash
# Linux / macOS：启动网页图片下载器图形界面（命令行：python -m backend <网址>）
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  command -v python3 >/dev/null || { echo "Python 3 was not found on PATH, so .venv could not be created."; exit 1; }
  echo "No .venv in this project. Creating one and installing requirements.txt ..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
PY=.venv/bin/python
"$PY" -c "import requests, bs4, PyQt5" 2>/dev/null || { echo "Missing Python packages in $PY. Install them with: $PY -m pip install -r requirements.txt"; exit 1; }
exec "$PY" -m frontend
