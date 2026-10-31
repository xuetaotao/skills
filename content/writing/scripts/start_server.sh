#!/usr/bin/env bash
# Linux / macOS：启动写作工作台 http://127.0.0.1:8331（命令行：python -m backend prompt / new / list / save / check / titles）
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  command -v python3 >/dev/null || { echo "Python 3 was not found on PATH, so .venv could not be created."; exit 1; }
  echo "No .venv in this project. Creating one and installing requirements.txt ..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
PY=.venv/bin/python
"$PY" -c "import fastapi, uvicorn" 2>/dev/null || { echo "Missing Python packages in $PY. Install them with: $PY -m pip install -r requirements.txt"; exit 1; }
( for _ in $(seq 30); do curl -fs http://127.0.0.1:8331/api/meta >/dev/null 2>&1 && { (xdg-open http://127.0.0.1:8331 || open http://127.0.0.1:8331) >/dev/null 2>&1; break; }; sleep 0.5; done ) &
exec "$PY" -m uvicorn backend.server:app --port 8331 --host 127.0.0.1
