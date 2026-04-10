#!/bin/bash
set -euo pipefail

ORIGINAL_DIR="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
    cd "$ORIGINAL_DIR" || true
}
trap cleanup EXIT

cd "$SCRIPT_DIR"

VENV_PYTHON=".venv/bin/python3"

if [ ! -x "$VENV_PYTHON" ]; then
    python3 -m venv .venv
fi

"$VENV_PYTHON" -m pip install -r requirements.txt

cd src
"$VENV_PYTHON" main.py

