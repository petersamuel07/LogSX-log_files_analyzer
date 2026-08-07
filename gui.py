"""Desktop GUI entry point for the Log File Analyzer.

Run with:
    python gui.py

A simple Tkinter window wrapping the same services the CLI (main.py) uses:
initialize the database, generate a sample log, ingest a file, run
analytics, generate charts, and export reports — all with live output in
a scrollable panel. See main.py for the CLI equivalent.
"""

import os
import sys

# A PyInstaller --windowed build has no console, so sys.stdout/stderr are
# None rather than a real stream. Anything that writes to them directly
# (tqdm's progress bar; our own console log handler) crashes with
# "AttributeError: 'NoneType' object has no attribute 'write'" the first
# time it tries. Redirecting to a discard sink makes those writes harmless
# no-ops instead — there's no console for a progress bar to show up in anyway.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from log_analyzer.gui import LogAnalyzerGUI  # noqa: E402 - must follow the stdout/stderr patch above

if __name__ == "__main__":
    LogAnalyzerGUI().run()
