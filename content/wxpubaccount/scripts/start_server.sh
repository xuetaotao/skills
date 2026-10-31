#!/usr/bin/env bash
# Linux / macOS：启动公众号数据分析网站 http://127.0.0.1:8332（命令行：python -m backend scrape / analyze ...）
set -euo pipefail
cd "$(dirname "$0")/.."
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
( for _ in $(seq 30); do curl -fs http://127.0.0.1:8332/api/status >/dev/null 2>&1 && { (xdg-open http://127.0.0.1:8332 || open http://127.0.0.1:8332) >/dev/null 2>&1; break; }; sleep 0.5; done ) &
exec "$PY" -m uvicorn backend.server:app --port 8332 --host 127.0.0.1
