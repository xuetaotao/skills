#!/bin/bash
# 行情复盘汇总一键运行脚本
# 复用 yupen 的虚拟环境（内含 akshare / pandas 等依赖）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
YUPEN_VENV_PYTHON="$SCRIPT_DIR/../../yupen/.venv/bin/python3"

if [ ! -x "$YUPEN_VENV_PYTHON" ]; then
    echo "未找到 yupen 虚拟环境：$YUPEN_VENV_PYTHON"
    echo "请先在 yupen 目录执行 run.sh 初始化环境。"
    exit 1
fi

"$YUPEN_VENV_PYTHON" "$SCRIPT_DIR/main.py"
