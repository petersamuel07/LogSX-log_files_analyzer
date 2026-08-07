"""A simple Tkinter desktop GUI for the Log File Analyzer.

Wraps the same services/analytics/visualization/reports classes the CLI
(main.py) uses — this is a thin presentation layer, not a second copy of any
business logic. Long-running operations (DB init, ingestion, analytics) run
on a background thread so the window never freezes, with output streamed
into a scrollable text panel via a thread-safe `root.after()` callback.
"""

from __future__ import annotations

import logging
import os
import threading
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, DISABLED, END, LEFT, NORMAL, X, Button, Frame, Label, StringVar, Tk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from log_analyzer.config import get_settings, setup_logging
from log_analyzer.utils import format_analytics_summary, format_ingestion_summary

logger = logging.getLogger(__name__)


class LogAnalyzerGUI:
    """Main application window."""

    def __init__(self) -> None:
        setup_logging(get_settings().log_level)

        self.root = Tk()
        self.root.title("LFA — Log File Analyzer")
        self.root.geometry("760x560")
        self.root.minsize(600, 400)

        self.selected_file: Path | None = None
        self._buttons: list[Button] = []

        self._build_widgets()
        self._log("Ready. Select a .log file, or generate a sample to get started.")

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _build_widgets(self) -> None:
        title = Label(self.root, text="LFA — Log File Analyzer", font=("Segoe UI", 16, "bold"))
        title.pack(pady=(12, 4))

        file_frame = Frame(self.root)
        file_frame.pack(fill=X, padx=12, pady=6)

        self.file_var = StringVar(value="(no file selected)")
        Label(file_frame, textvariable=self.file_var, anchor="w", fg="#52514e").pack(side=LEFT, fill=X, expand=True)
        self._add_button(file_frame, "Browse...", self._on_browse, side=LEFT).pack(side=LEFT, padx=(6, 0))

        actions_frame = Frame(self.root)
        actions_frame.pack(fill=X, padx=12, pady=6)

        self._add_button(actions_frame, "Initialize Database", self._on_init_db)
        self._add_button(actions_frame, "Generate Sample Log", self._on_generate_sample)
        self._add_button(actions_frame, "Ingest Selected File", self._on_ingest)
        self._add_button(actions_frame, "Run Analytics", self._on_analyze)
        self._add_button(actions_frame, "Generate Charts", self._on_charts)
        self._add_button(actions_frame, "Export Reports", self._on_report)

        folders_frame = Frame(self.root)
        folders_frame.pack(fill=X, padx=12, pady=(0, 6))
        self._add_button(folders_frame, "Open Charts Folder", self._on_open_charts_folder)
        self._add_button(folders_frame, "Open Reports Folder", self._on_open_reports_folder)
        self._add_button(folders_frame, "Clear Output", self._on_clear_output)

        self.status_var = StringVar(value="Idle")
        Label(self.root, textvariable=self.status_var, anchor="w", fg="#0b0b0b").pack(fill=X, padx=12)

        self.output = ScrolledText(self.root, state=DISABLED, font=("Consolas", 9), wrap="word")
        self.output.pack(fill=BOTH, expand=True, padx=12, pady=(6, 12))

    def _add_button(self, parent: Frame, text: str, command: Callable[[], None], side: str = LEFT) -> Button:
        button = Button(parent, text=text, command=command)
        button.pack(side=side, padx=4, pady=2)
        self._buttons.append(button)
        return button

    # ------------------------------------------------------------------
    # Thread-safe output + background execution
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        """Schedule a message append on the main thread — safe to call from a worker thread."""
        self.root.after(0, self._append_output, message)

    def _append_output(self, message: str) -> None:
        self.output.configure(state=NORMAL)
        self.output.insert(END, message + "\n")
        self.output.see(END)
        self.output.configure(state=DISABLED)

    def _set_busy(self, busy: bool, status: str = "") -> None:
        state = DISABLED if busy else NORMAL
        for button in self._buttons:
            button.configure(state=state)
        self.status_var.set(status or ("Working..." if busy else "Idle"))

    def _run_async(self, description: str, target: Callable[[], None]) -> None:
        """Run `target` on a background thread, keeping the window responsive."""
        self.root.after(0, self._set_busy, True, description)

        def worker() -> None:
            try:
                target()
                self._log(f"\n[done] {description}")
            except Exception as exc:  # noqa: BLE001 - surfacing any failure to the GUI is the point
                logger.exception("GUI action failed: %s", description)
                self._log(f"\n[error] {description} failed: {exc}\n{traceback.format_exc()}")
            finally:
                self.root.after(0, self._set_busy, False)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_browse(self) -> None:
        settings = get_settings()
        initial_dir = settings.log_input_dir if settings.log_input_dir.exists() else Path.cwd()
        path = filedialog.askopenfilename(
            title="Select a .log file",
            initialdir=str(initial_dir),
            filetypes=[("Log files", "*.log"), ("All files", "*.*")],
        )
        if path:
            self.selected_file = Path(path)
            self.file_var.set(str(self.selected_file))
            self._log(f"Selected file: {self.selected_file}")

    def _on_init_db(self) -> None:
        def task() -> None:
            from log_analyzer.database import initialize_database

            initialize_database()
            self._log("Database initialized: tables, indexes, and log levels are ready.")

        self._run_async("Initializing database", task)

    def _on_generate_sample(self) -> None:
        def task() -> None:
            from log_analyzer.utils import generate_sample_logs

            settings = get_settings()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = settings.log_input_dir / f"gui_sample_{timestamp}.log"
            path = generate_sample_logs(output_path, num_lines=3000)
            self._log(f"Generated sample log file: {path}")

            self.selected_file = path
            self.root.after(0, self.file_var.set, str(path))

        self._run_async("Generating sample log file (3000 lines)", task)

    def _on_ingest(self) -> None:
        if self.selected_file is None:
            messagebox.showwarning("No file selected", "Click 'Browse...' or 'Generate Sample Log' first.")
            return

        def task() -> None:
            from log_analyzer.services import IngestionService

            summary = IngestionService().ingest_file(self.selected_file)
            self._log(format_ingestion_summary(summary))

        self._run_async(f"Ingesting {self.selected_file.name}", task)

    def _on_analyze(self) -> None:
        def task() -> None:
            from log_analyzer.analytics import LogAnalytics

            summary = LogAnalytics().generate_summary()
            self._log(format_analytics_summary(summary))

        self._run_async("Running analytics", task)

    def _on_charts(self) -> None:
        def task() -> None:
            from log_analyzer.analytics import LogAnalytics
            from log_analyzer.visualization import ChartGenerator

            settings = get_settings()
            analytics = LogAnalytics()
            paths = ChartGenerator(analytics, settings.charts_output_dir).generate_all()
            self._log("Charts written:\n" + "\n".join(f"  {p}" for p in paths))

        self._run_async("Generating charts", task)

    def _on_report(self) -> None:
        def task() -> None:
            from log_analyzer.analytics import LogAnalytics
            from log_analyzer.reports import ReportExporter

            settings = get_settings()
            summary = LogAnalytics().generate_summary()
            outputs = ReportExporter(settings.reports_output_dir).export_all(summary)
            self._log("Reports written:\n" + "\n".join(f"  {name}: {path}" for name, path in outputs.items()))

        self._run_async("Exporting CSV/JSON reports", task)

    def _on_open_charts_folder(self) -> None:
        self._open_folder(get_settings().charts_output_dir)

    def _on_open_reports_folder(self) -> None:
        self._open_folder(get_settings().reports_output_dir)

    def _open_folder(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(path)  # noqa: S606 - Windows-only convenience, matches this project's target OS
        except AttributeError:
            self._log(f"Cannot auto-open folders on this OS. Path: {path}")

    def _on_clear_output(self) -> None:
        self.output.configure(state=NORMAL)
        self.output.delete("1.0", END)
        self.output.configure(state=DISABLED)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    LogAnalyzerGUI().run()


if __name__ == "__main__":
    main()
