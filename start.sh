#!/bin/bash
# Receipts launcher for running from source (Mac / Linux).
# Most people should install the packaged app instead — see the Releases page.
cd "$(dirname "$0")"

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

# launch.py opens Receipts in its own window; it falls back to your browser
# if this system has no web view available.
exec ./.venv/bin/python launch.py
