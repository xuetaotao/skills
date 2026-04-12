#!/bin/bash

# Media Downloader - One-click runner

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="$SCRIPT_DIR/.venv"

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "Virtual environment not found. Creating one..."
    cd "$SCRIPT_DIR"
    python3 -m venv .venv
    source "$VENV_PATH/bin/activate"
    pip install -r requirements.txt
else
    source "$VENV_PATH/bin/activate"
fi

# Run the launcher GUI by default
cd "$SCRIPT_DIR"
python -m src gui
