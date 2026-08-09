"""Locating the packaged brand assets (logo, icon) from any run mode.

This deliberately resolves differently from `config.PROJECT_ROOT`. Config
points *beside* a frozen .exe because `.env`, `data/`, and `outputs/` are
user-editable and must survive the process. Brand assets are the opposite:
read-only, versioned with the code, and shipped *inside* the one-file bundle,
so a PyInstaller build has to read them out of the temporary extraction
directory (`sys._MEIPASS`) instead.

Every lookup is allowed to fail. The GUI is fully usable without artwork, so
callers get `None` rather than an exception when a file is missing — a build
that forgot `--add-data assets` should still start.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _resolve_assets_dir() -> Path:
    if getattr(sys, "frozen", False):
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            return Path(bundle) / "assets"
        return Path(sys.executable).resolve().parent / "assets"
    # src/log_analyzer/utils/assets.py -> repo root
    return Path(__file__).resolve().parents[3] / "assets"


ASSETS_DIR = _resolve_assets_dir()


def asset_path(name: str) -> Path | None:
    """Return the full path to a brand asset, or None if it isn't shipped.

    Args:
        name: File name relative to the assets directory, e.g. "icon.ico".
    """
    candidate = ASSETS_DIR / name
    return candidate if candidate.is_file() else None
