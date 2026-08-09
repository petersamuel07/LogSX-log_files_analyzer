#!/usr/bin/env bash
# Builds a standalone Windows LogSX.exe from gui.py via PyInstaller.
# The resulting dist/LogSX.exe needs no Python install to run — just
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

# The exe icon and the GUI's header mark come out of assets/. They're committed,
# but regenerate them if only the master logo is present so a fresh clone that
# ran build_assets.py's inputs — but not the script — still gets a branded exe.
if [ ! -f "assets/icon.ico" ] && [ -f "assets/logo.png" ]; then
    echo "==> Generating brand assets from assets/logo.png"
    "$VENV_PYTHON" scripts/build_assets.py
fi

# --add-data uses the platform's path separator, not a fixed character.
DATA_SEP=";"
case "$(uname -s)" in
    Linux* | Darwin*) DATA_SEP=":" ;;
esac

BRAND_ARGS=()
if [ -f "assets/icon.ico" ]; then
    # Bundled read-only, so the GUI reads them from sys._MEIPASS at runtime
    # (see src/log_analyzer/utils/assets.py) rather than from beside the .exe.
    BRAND_ARGS+=(--icon "assets/icon.ico" --add-data "assets${DATA_SEP}assets")
else
    echo "Warning: assets/icon.ico not found — building with PyInstaller's default icon." >&2
fi

echo "==> Building LogSX.exe from gui.py"
"$VENV_PYTHON" -m PyInstaller --onefile --windowed --name LogSX --specpath packaging \
    "${BRAND_ARGS[@]}" gui.py

echo ""
echo "==> Build complete: dist/LogSX.exe"
echo ""
echo "Before running it:"
echo "  1. Copy .env next to dist/LogSX.exe (frozen mode looks for it beside the .exe, not in the source tree)."
echo "  2. Make sure PostgreSQL is reachable with the credentials in that .env."
echo "  3. Double-click dist/LogSX.exe, or run it from a terminal: ./dist/LogSX.exe"
echo ""
echo "data/, outputs/, and logs/ will be created next to the .exe on first run."
