#!/usr/bin/env bash
# Linux / macOS：启动本地网站 http://127.0.0.1:8325（启动时自动更新数据，REVIEW_AUTO_REFRESH=0 可关闭）
set -euo pipefail
cd "$(dirname "$0")/.."
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" -m uvicorn backend.server:app --port 8325 --host 127.0.0.1
