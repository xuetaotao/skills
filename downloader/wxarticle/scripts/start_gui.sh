#!/usr/bin/env bash
# Linux / macOS：启动公众号文章下载图形界面（命令行：python -m backend <链接> ...）
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  command -v python3 >/dev/null || { echo "Python 3 was not found on PATH, so .venv could not be created."; exit 1; }
  echo "No .venv in this project. Creating one and installing requirements.txt ..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python -m playwright install chromium
fi
PY=.venv/bin/python
"$PY" -c "import playwright, PyQt5" 2>/dev/null || { echo "Missing Python packages in $PY. Install them with: $PY -m pip install -r requirements.txt && $PY -m playwright install chromium"; exit 1; }
exec "$PY" -m frontend
