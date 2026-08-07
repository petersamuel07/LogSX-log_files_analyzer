"""CLI entry point for the Log File Analyzer.

Placeholder for Step 9 (argparse-driven CLI). For now it only proves
that the ``log_analyzer`` package is importable via the editable install.

How to use (Step 1 scaffold stage)
-----------------------------------
1. Create and activate a virtual environment:

   Windows (PowerShell):
       python -m venv venv
       .\\venv\\Scripts\\Activate.ps1

   macOS / Linux:
       python -m venv venv
       source venv/bin/activate

2. Install dependencies and the package itself in editable mode:
       pip install -r requirements.txt
       pip install -e .

3. Copy the environment template and fill in your real PostgreSQL
   credentials (the real .env is git-ignored, never commit it):
       copy .env.example .env        (Windows)
       cp .env.example .env          (macOS / Linux)

4. Run this script to confirm the scaffold is wired up correctly:
       python main.py

   Expected output:
       log_analyzer package v0.1.0 — scaffold OK

This entry point will grow into the full argparse CLI (ingest logs,
run analytics, export reports, generate charts) in a later step.
"""

import log_analyzer


def main() -> None:
    print(f"log_analyzer package v{log_analyzer.__version__} — scaffold OK")


if __name__ == "__main__":
    main()
