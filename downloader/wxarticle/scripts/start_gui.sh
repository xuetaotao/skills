#!/usr/bin/env bash
# Linux / macOS：启动公众号文章下载图形界面（命令行：python -m backend <链接> ...）
set -euo pipefail
cd "$(dirname "$0")/.."
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" -m frontend
