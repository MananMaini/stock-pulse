#!/bin/bash
# One-click launcher for StockPulse (macOS: double-click this file)
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Setting up (first run only)..."
  python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi
(sleep 3 && open http://127.0.0.1:8000) &
./.venv/bin/python app.py
