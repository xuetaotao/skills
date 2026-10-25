#!/usr/bin/env bash
# Linux / macOS：启动网页图片下载器图形界面（命令行：python -m backend <网址>）
set -euo pipefail
cd "$(dirname "$0")/.."
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" -m frontend
