#!/bin/bash

# WeChat Article Downloader - One-click runner

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="$SCRIPT_DIR/.venv"

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "Virtual environment not found. Creating one..."
    cd "$SCRIPT_DIR"
    python3 -m venv .venv
    source "$VENV_PATH/bin/activate"
    pip install -r requirements.txt
    playwright install chromium
else
    source "$VENV_PATH/bin/activate"
fi

# Check if URL is provided
if [ -z "$1" ]; then
    echo "Usage: ./run.sh <wechat_article_url>"
    echo "Example: ./run.sh https://mp.weixin.qq.com/s/xxxxx"
    exit 1
fi

# Run the downloader
cd "$SCRIPT_DIR"
python -m src "$1"
