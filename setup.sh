#!/usr/bin/env bash
# One-shot setup: creates the virtual environment, installs all dependencies,
# installs this package in editable mode, and creates .env from the template
# if it doesn't already exist. Safe to re-run — every step is idempotent.
#
# Usage:
#   ./setup.sh
#
# Override the Python interpreter if "python" doesn't point to Python 3.13+:
#   PYTHON_BIN=python3.13 ./setup.sh

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"

echo "==> Log File Analyzer setup"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Error: '$PYTHON_BIN' not found on PATH. Install Python 3.13+ first, or set PYTHON_BIN." >&2
    exit 1
fi
echo "==> Using $("$PYTHON_BIN" --version)"

if [ ! -d "venv" ]; then
    echo "==> Creating virtual environment (venv/)"
    "$PYTHON_BIN" -m venv venv
else
    echo "==> venv/ already exists, skipping creation"
fi

# The venv's python lives under Scripts/ on Windows, bin/ on macOS/Linux.
if [ -f "venv/Scripts/python.exe" ]; then
    VENV_PYTHON="venv/Scripts/python.exe"
    ACTIVATE_HINT='.\venv\Scripts\Activate.ps1   (PowerShell)   or   source venv/Scripts/activate   (Git Bash)'
elif [ -f "venv/bin/python" ]; then
    VENV_PYTHON="venv/bin/python"
    ACTIVATE_HINT='source venv/bin/activate'
else
    echo "Error: could not locate the venv's python executable." >&2
    exit 1
fi

echo "==> Upgrading pip"
"$VENV_PYTHON" -m pip install --upgrade pip --quiet

echo "==> Installing dependencies from requirements.txt"
"$VENV_PYTHON" -m pip install -r requirements.txt

echo "==> Installing the log_analyzer package in editable mode"
"$VENV_PYTHON" -m pip install -e . --quiet

if [ ! -f ".env" ]; then
    echo "==> Creating .env from .env.example"
    cp .env.example .env
    echo "    NOTE: edit .env with your real PostgreSQL credentials before running the app."
else
    echo "==> .env already exists, leaving it untouched"
fi

cat <<EOF

==> Setup complete.

Next steps:
  1. Make sure .env has your real PostgreSQL credentials.
  2. Activate the virtual environment:
       $ACTIVATE_HINT
  3. Initialize the database:
       python main.py init-db
  4. Try the pipeline end to end:
       python main.py generate-sample --num-lines 5000 --seed 42
       python main.py pipeline data/logs/sample_5000.log
  5. Or launch the GUI instead of the CLI:
       python gui.py
EOF
