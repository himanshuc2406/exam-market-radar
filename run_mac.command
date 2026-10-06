#!/bin/bash
set -e

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install it from https://www.python.org/downloads/macos/"
  echo "Then run this file again."
  read -r -p "Press Enter to close..."
  exit 1
fi

MAC_VENV=".venv-mac"
if [ ! -x "$MAC_VENV/bin/python" ]; then
  echo "Creating the Mac environment..."
  python3 -m venv "$MAC_VENV"
  "$MAC_VENV/bin/python" -m pip install --upgrade pip
fi

if ! "$MAC_VENV/bin/python" -c "import flask, dotenv, requests, youtube_transcript_api, openpyxl, reportlab" >/dev/null 2>&1; then
  echo "Installing or updating dependencies..."
  "$MAC_VENV/bin/python" -m pip install -r requirements.txt
fi

echo
echo "============================================"
echo "  Exam Market Radar -> http://127.0.0.1:5002"
echo "  Press Control+C here to stop"
echo "============================================"
echo

(sleep 2; open "http://127.0.0.1:5002") &
exec "$MAC_VENV/bin/python" app.py
