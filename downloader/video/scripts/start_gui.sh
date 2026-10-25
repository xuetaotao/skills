#!/usr/bin/env bash
# Linux / macOS：启动音视频下载器图形界面（命令行：python -m backend video <网址>）
set -euo pipefail
cd "$(dirname "$0")/.."
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
command -v ffmpeg >/dev/null || echo "提示：没有找到 ffmpeg，合并音视频、转 mp3、转封装 mp4 将不可用"
exec "$PY" -m frontend
