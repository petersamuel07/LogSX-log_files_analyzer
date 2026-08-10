#!/usr/bin/env bash
# One-shot setup: creates the virtual environment, installs all dependencies,
# installs this package in editable mode, and creates .env from the template
# if it doesn't already exist. Safe to re-run — every step is idempotent.
#
# Usage:
#   ./scripts/setup.sh
#
# Override the Python interpreter if "python" doesn't point to Python 3.13+:
#   PYTHON_BIN=python3.13 ./scripts/setup.sh

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON_BIN="${PYTHON_BIN:-python}"

echo "==> LogSX — Log Files Analyzer setup"

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

# requirements.txt is "-e .", so this installs the package in editable mode
# along with the runtime dependencies declared in pyproject.toml.
echo "==> Installing the log_analyzer package and its dependencies"
"$VENV_PYTHON" -m pip install -r requirements.txt

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
       logsx init-db
  4. Try the pipeline end to end:
       logsx generate-sample --num-lines 5000 --seed 42
       logsx pipeline data/sample/sample_5000.log
  5. Or launch the GUI instead of the CLI:
       logsx-gui

  (\`python main.py ...\` and \`python gui.py\` still work as before.)
EOF
