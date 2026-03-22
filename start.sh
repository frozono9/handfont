#!/usr/bin/env bash
# HandFont — start the web app
set -e

echo "────────────────────────────────────"
echo "  HandFont — Handwriting Font Maker"
echo "────────────────────────────────────"

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Please install Python 3.10+."
  exit 1
fi

# Install dependencies if needed
if ! python3 -c "import flask" 2>/dev/null; then
  echo "Installing dependencies..."
  pip install -r requirements.txt --break-system-packages
fi

# Create template dir
mkdir -p templates

echo ""
echo "Starting server on http://localhost:5000"
echo "Press Ctrl+C to stop."
echo ""

python3 app.py
