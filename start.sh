#!/bin/bash
# Receipts launcher (Mac / Linux)
cd "$(dirname "$0")"

# already running? just open the browser
if curl -s -m 2 http://localhost:8765/api/health >/dev/null 2>&1; then
  xdg-open http://localhost:8765 2>/dev/null || open http://localhost:8765 2>/dev/null
  exit 0
fi

if ! command -v python3 >/dev/null; then
  command -v notify-send >/dev/null && notify-send "Receipts" "Python 3 is required — install it from python.org"
  echo "Python 3 is required. Install it from https://python.org and run this again."
  exit 1
fi

if [ ! -d ".venv" ]; then
  command -v notify-send >/dev/null && notify-send "Receipts" "First run — setting up (about a minute)…"
  echo "First run — setting things up (one minute)…"
  python3 -m venv .venv
fi
# keep dependencies in sync with requirements.txt (fast when nothing changed)
./.venv/bin/pip install -q -r requirements.txt

exec ./.venv/bin/python app.py
