#!/bin/bash
set -euo pipefail

ORIGINAL_DIR="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
    cd "$ORIGINAL_DIR" || true
}
trap cleanup EXIT

cd "$SCRIPT_DIR"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"

if [ ! -x "$VENV_PYTHON" ]; then
    python3 -m venv .venv
fi

"$VENV_PYTHON" -m pip install -r requirements.txt

# 使用 -m 方式运行，确保包内相对导入正常
"$VENV_PYTHON" -m src
