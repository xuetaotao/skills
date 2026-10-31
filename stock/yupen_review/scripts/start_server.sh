#!/usr/bin/env bash
# Linux / macOS：启动本地网站 http://127.0.0.1:8325（启动时自动更新数据，REVIEW_AUTO_REFRESH=0 可关闭）
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  command -v python3 >/dev/null || { echo "Python 3 was not found on PATH, so .venv could not be created."; exit 1; }
  echo "No .venv in this project. Creating one and installing requirements.txt ..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
PY=.venv/bin/python
"$PY" -c "import fastapi, uvicorn, akshare, pandas, requests" 2>/dev/null || { echo "Missing Python packages in $PY. Install them with: $PY -m pip install -r requirements.txt"; exit 1; }
exec "$PY" -m uvicorn backend.server:app --port 8325 --host 127.0.0.1
