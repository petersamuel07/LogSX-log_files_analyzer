"""Repo-root shim for the LogSX desktop GUI — see src/log_analyzer/gui/ for the real thing.

Kept so `python gui.py` works out of a fresh clone, and because this is the
script PyInstaller builds LogSX.exe from (see packaging/LogSX.spec). Once the
package is installed, `logsx-gui` is the equivalent entry point.
"""

import sys

from log_analyzer.gui.launcher import main

if __name__ == "__main__":
    sys.exit(main())
