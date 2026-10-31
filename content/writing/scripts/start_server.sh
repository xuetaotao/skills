#!/usr/bin/env bash
# Linux / macOS锛氬惎鍔ㄥ叕浼楀彿鏁版嵁鍒嗘瀽缃戠珯 http://127.0.0.1:8331锛堝懡浠よ锛歱ython -m backend scrape / analyze ...锛?
set -euo pipefail
cd "$(dirname "$0")/.."
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
( for _ in $(seq 30); do curl -fs http://127.0.0.1:8331/api/meta >/dev/null 2>&1 && { (xdg-open http://127.0.0.1:8331 || open http://127.0.0.1:8331) >/dev/null 2>&1; break; }; sleep 0.5; done ) &
exec "$PY" -m uvicorn backend.server:app --port 8331 --host 127.0.0.1
