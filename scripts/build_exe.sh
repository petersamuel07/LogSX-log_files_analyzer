#!/usr/bin/env bash
# Builds a standalone Windows LFA.exe from gui.py via PyInstaller.
# The resulting dist/LFA.exe needs no Python install to run — just
# PostgreSQL reachable and a .env file placed next to the .exe.
#
# Usage:
#   ./scripts/build_exe.sh

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -f "venv/Scripts/python.exe" ] && [ ! -f "venv/bin/python" ]; then
    echo "Error: venv/ not found. Run ./scripts/setup.sh first." >&2
    exit 1
fi

VENV_PYTHON="venv/Scripts/python.exe"
[ -f "$VENV_PYTHON" ] || VENV_PYTHON="venv/bin/python"

echo "==> Installing build tooling (PyInstaller)"
"$VENV_PYTHON" -m pip install -r requirements-dev.txt --quiet

echo "==> Building LFA.exe from gui.py"
"$VENV_PYTHON" -m PyInstaller --onefile --windowed --name LFA --specpath packaging gui.py

echo ""
echo "==> Build complete: dist/LFA.exe"
echo ""
echo "Before running it:"
echo "  1. Copy .env next to dist/LFA.exe (frozen mode looks for it beside the .exe, not in the source tree)."
echo "  2. Make sure PostgreSQL is reachable with the credentials in that .env."
echo "  3. Double-click dist/LFA.exe, or run it from a terminal: ./dist/LFA.exe"
echo ""
echo "data/, outputs/, and logs/ will be created next to the .exe on first run."
