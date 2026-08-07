"""Desktop GUI entry point for the Log File Analyzer.

Run with:
    python gui.py

A simple Tkinter window wrapping the same services the CLI (main.py) uses:
initialize the database, generate a sample log, ingest a file, run
analytics, generate charts, and export reports — all with live output in
a scrollable panel. See main.py for the CLI equivalent.
"""

from log_analyzer.gui import LogAnalyzerGUI

if __name__ == "__main__":
    LogAnalyzerGUI().run()
