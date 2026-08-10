"""Repo-root shim for the LogSX CLI — see src/log_analyzer/cli.py for the real thing.

Kept so `python main.py <command>` keeps working straight out of a fresh clone,
before the package is installed. Once installed (`pip install -e .`), the
equivalent entry points are `logsx <command>` and `python -m log_analyzer <command>`.
"""

import sys

from log_analyzer.cli import main

if __name__ == "__main__":
    sys.exit(main())
