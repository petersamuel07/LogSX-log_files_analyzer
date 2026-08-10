"""Process entry point for the desktop GUI, shared by every way of starting it.

Both the repo-root ``gui.py`` shim (which PyInstaller builds the .exe from)
and the installed ``logsx-gui`` console script call :func:`main` here, so the
windowed-build stream fix below applies no matter how the GUI was started.
"""

from __future__ import annotations

import os
import sys


def ensure_std_streams() -> None:
    """Give the process real stdout/stderr streams if it was started without them.

    A PyInstaller --windowed build has no console, so sys.stdout/stderr are
    None rather than a real stream. Anything that writes to them directly
    (tqdm's progress bar; our own console log handler) crashes with
    "AttributeError: 'NoneType' object has no attribute 'write'" the first
    time it tries. Redirecting to a discard sink makes those writes harmless
    no-ops instead — there's no console for a progress bar to show up in anyway.
    """
    # These sinks intentionally stay open for the life of the process and are
    # never closed, so a context manager is the wrong shape here (ruff SIM115).
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115


def main() -> int:
    ensure_std_streams()

    # Imported after the stream fix so nothing captures a None stream on the
    # way in (logging's StreamHandler and tqdm both latch onto whatever
    # sys.stdout/stderr is at the moment they're constructed).
    from log_analyzer.gui.app import LogSXGUI

    LogSXGUI().run()
    return 0
