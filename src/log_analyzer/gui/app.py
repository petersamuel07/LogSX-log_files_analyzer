"""Tkinter desktop GUI for LogSX — Log Files Analyzer.

Wraps the same services/analytics/visualization/reports classes the CLI
(log_analyzer.cli) uses — this is a thin presentation layer, not a second copy of any
business logic. Long-running operations (DB init, ingestion, analytics) run
on a background thread so the window never freezes, with output streamed
into a scrollable console via a thread-safe `root.after()` callback.

The look is built on ttk's "clam" theme, which (unlike the native "vista"
theme) honours explicit colour configuration on every widget, so the palette
below applies consistently on Windows, macOS, and Linux.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import (
    BOTH,
    DISABLED,
    END,
    LEFT,
    NORMAL,
    RIGHT,
    X,
    Y,
    Menu,
    StringVar,
    TclError,
    Tk,
    filedialog,
    messagebox,
    ttk,
)
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from log_analyzer.config import get_settings, setup_logging
from log_analyzer.utils import asset_path, format_analytics_summary, format_ingestion_summary

logger = logging.getLogger(__name__)

APP_NAME = "LogSX"
APP_TAGLINE = "Log Files Analyzer"


def _enable_dpi_awareness() -> float:
    """Opt into per-monitor DPI awareness on Windows and return the display scale.

    Without this, Windows renders a Tk window at 96 DPI and bitmap-stretches it
    on a scaled display, which makes every label look blurry. Must be called
    before the first Tk() is created. Returns the scale factor (1.0 = 100%),
    which the caller feeds into Tk's own scaling so point-sized fonts and the
    initial window geometry come out at the right physical size.
    """
    if sys.platform != "win32":
        return 1.0
    try:
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE. Raises OSError if awareness was
        # already set (e.g. via a manifest), which is fine — we still want the scale.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except (AttributeError, OSError):
        return 1.0


def _claim_taskbar_identity() -> None:
    """Tell Windows this process is LogSX, not its Python host.

    Without an explicit AppUserModelID, a Tk app launched from `python gui.py`
    inherits the interpreter's identity, so the taskbar shows the Python icon
    and groups LogSX windows under it — the window icon set below is ignored
    there. Frozen builds get this from the exe itself, but setting it costs
    nothing and makes running from source look the same.
    """
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("logsx.log-files-analyzer")
    except (AttributeError, OSError):
        pass


def _load_brand_image(filename: str, height: int) -> Any | None:
    """Load a brand PNG scaled to `height` pixels, or None when unavailable.

    The caller must hold a reference to the returned image: Tkinter keeps only
    a weak association, and a garbage-collected image renders as a blank gap.

    Artwork is treated as optional throughout — a checkout without `assets/`,
    a build that forgot to bundle it, or a Pillow-less environment all still
    get a fully working window, just an unbranded one.
    """
    path = asset_path(filename)
    if path is None:
        logger.debug("Brand asset %s not found; rendering without it.", filename)
        return None
    try:
        from PIL import Image, ImageTk
    except ImportError:
        logger.debug("Pillow unavailable; rendering without brand artwork.")
        return None
    try:
        with Image.open(path) as raw:
            art = raw.convert("RGBA")
        width = max(1, round(art.width * height / art.height))
        return ImageTk.PhotoImage(art.resize((width, height), Image.LANCZOS))
    except (OSError, ValueError) as exc:
        logger.debug("Could not load brand asset %s: %s", path, exc)
        return None


class Palette:
    """Single source of truth for every colour used in the window."""

    bg = "#12141a"          # window background
    surface = "#1a1d26"     # cards / panels
    border = "#2b3040"
    header = "#0d0f14"

    text = "#e8eaf0"
    text_muted = "#8b93a7"
    text_dim = "#5f6779"

    accent = "#4f8cff"
    accent_hover = "#6b9dff"
    accent_press = "#3c73dd"

    success = "#3ecf8e"
    warning = "#f5a623"
    error = "#ff6b6b"

    console_bg = "#0e1015"


class LogSXGUI:
    """Main application window."""

    def __init__(self) -> None:
        setup_logging(get_settings().log_level)

        scale = _enable_dpi_awareness()
        _claim_taskbar_identity()

        self.root = Tk()
        self.root.tk.call("tk", "scaling", scale * 96.0 / 72.0)
        self.root.title(f"{APP_NAME} — {APP_TAGLINE}")
        self.root.geometry(f"{round(1060 * scale)}x{round(680 * scale)}")
        self.root.minsize(round(880 * scale), round(560 * scale))
        self.root.configure(bg=Palette.bg)

        self.selected_file: Path | None = None
        self._action_buttons: list[ttk.Button] = []
        self._busy = False
        self._scale = scale
        # Tk images must outlive the widgets showing them (see _load_brand_image).
        self._brand_images: list[Any] = []

        self._apply_window_icon()
        self._init_styles()
        self._build_menu()
        self._build_widgets()
        self._bind_shortcuts()

        self._log(f"{APP_NAME} ready.", tag="heading")
        self._log("Select a .log file with Browse (Ctrl+O), or generate a sample to get started.")

    # ------------------------------------------------------------------
    # Branding
    # ------------------------------------------------------------------

    def _apply_window_icon(self) -> None:
        """Put the LogSX mark on the title bar, taskbar, and Alt-Tab switcher.

        Prefers the multi-resolution .ico so Windows picks a crisp size for each
        of those surfaces instead of rescaling one bitmap. Tk builds on Linux
        and macOS reject .ico outright, so those fall back to the PNG mark.
        """
        icon = asset_path("icon.ico")
        if icon is not None:
            try:
                self.root.iconbitmap(default=str(icon))
                return
            except TclError:
                logger.debug("This Tk build rejected the .ico; falling back to PNG.")

        # The dark-ink mark would vanish against a dark title bar, so use the
        # light-ink one — it reads on both, unlike black on black.
        image = _load_brand_image("mark-on-dark-128.png", 128)
        if image is not None:
            self._brand_images.append(image)
            self.root.iconphoto(True, image)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _init_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("TFrame", background=Palette.bg)
        style.configure("Card.TFrame", background=Palette.surface)
        style.configure("Header.TFrame", background=Palette.header)
        style.configure("Status.TFrame", background=Palette.header)

        style.configure("TLabel", background=Palette.bg, foreground=Palette.text, font=("Segoe UI", 10))
        style.configure("Brand.TLabel", background=Palette.header, foreground=Palette.text,
                        font=("Segoe UI Semibold", 19))
        style.configure("BrandMark.TLabel", background=Palette.header)
        style.configure("BrandSub.TLabel", background=Palette.header, foreground=Palette.text_muted,
                        font=("Segoe UI", 10))
        style.configure("HeaderMeta.TLabel", background=Palette.header, foreground=Palette.text_dim,
                        font=("Consolas", 9))
        style.configure("Card.TLabel", background=Palette.surface, foreground=Palette.text, font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=Palette.surface, foreground=Palette.text_dim,
                        font=("Segoe UI Semibold", 8))
        style.configure("File.TLabel", background=Palette.surface, foreground=Palette.text_muted,
                        font=("Consolas", 9))
        style.configure("Status.TLabel", background=Palette.header, foreground=Palette.text_muted,
                        font=("Segoe UI", 9))

        # Secondary (default) action button.
        style.configure(
            "Action.TButton",
            background=Palette.surface,
            foreground=Palette.text,
            bordercolor=Palette.border,
            lightcolor=Palette.surface,
            darkcolor=Palette.surface,
            focuscolor=Palette.accent,
            font=("Segoe UI", 10),
            padding=(12, 8),
            relief="flat",
            anchor="w",
        )
        style.map(
            "Action.TButton",
            background=[("disabled", Palette.surface), ("pressed", Palette.header), ("active", Palette.border)],
            foreground=[("disabled", Palette.text_dim)],
            bordercolor=[("active", Palette.accent)],
        )

        # Primary (accent) action button.
        style.configure(
            "Primary.TButton",
            background=Palette.accent,
            foreground="#ffffff",
            bordercolor=Palette.accent,
            lightcolor=Palette.accent,
            darkcolor=Palette.accent,
            font=("Segoe UI Semibold", 10),
            padding=(12, 8),
            relief="flat",
            anchor="w",
        )
        style.map(
            "Primary.TButton",
            background=[("disabled", Palette.border), ("pressed", Palette.accent_press), ("active", Palette.accent_hover)],
            foreground=[("disabled", Palette.text_dim)],
        )

        style.configure(
            "Ghost.TButton",
            background=Palette.surface,
            foreground=Palette.text_muted,
            bordercolor=Palette.surface,
            lightcolor=Palette.surface,
            darkcolor=Palette.surface,
            font=("Segoe UI", 9),
            padding=(8, 4),
            relief="flat",
        )
        style.map(
            "Ghost.TButton",
            background=[("active", Palette.border), ("pressed", Palette.header)],
            foreground=[("active", Palette.text), ("disabled", Palette.text_dim)],
        )

        style.configure(
            "Thin.Horizontal.TProgressbar",
            background=Palette.accent,
            troughcolor=Palette.header,
            bordercolor=Palette.header,
            lightcolor=Palette.accent,
            darkcolor=Palette.accent,
            thickness=3,
        )

        style.configure("Sep.TSeparator", background=Palette.border)

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = Menu(self.root)

        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Log File...", accelerator="Ctrl+O", command=self._on_browse)
        file_menu.add_command(label="Generate Sample Log", accelerator="Ctrl+G", command=self._on_generate_sample)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        run_menu = Menu(menubar, tearoff=0)
        run_menu.add_command(label="Initialize Database", command=self._on_init_db)
        run_menu.add_command(label="Ingest Selected File", accelerator="Ctrl+I", command=self._on_ingest)
        run_menu.add_command(label="Run Analytics", accelerator="Ctrl+R", command=self._on_analyze)
        run_menu.add_command(label="Generate Charts", command=self._on_charts)
        run_menu.add_command(label="Export Reports", command=self._on_report)
        menubar.add_cascade(label="Run", menu=run_menu)

        view_menu = Menu(menubar, tearoff=0)
        view_menu.add_command(label="Open Charts Folder", command=self._on_open_charts_folder)
        view_menu.add_command(label="Open Reports Folder", command=self._on_open_reports_folder)
        view_menu.add_separator()
        view_menu.add_command(label="Clear Console", accelerator="Ctrl+L", command=self._on_clear_output)
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = Menu(menubar, tearoff=0)
        help_menu.add_command(label=f"About {APP_NAME}", command=self._on_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.configure(menu=menubar)

    def _build_widgets(self) -> None:
        self._build_header()

        body = ttk.Frame(self.root, style="TFrame")
        body.pack(fill=BOTH, expand=True, padx=14, pady=12)

        self._build_sidebar(body)
        self._build_console(body)
        self._build_statusbar()

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame")
        header.pack(fill=X)

        inner = ttk.Frame(header, style="Header.TFrame")
        inner.pack(fill=X, padx=16, pady=12)

        brand = ttk.Frame(inner, style="Header.TFrame")
        brand.pack(side=LEFT)

        # Icon only, not the full lockup: the lockup carries its own "LogSX /
        # LOG FILES ANALYZER" wordmark, which the two labels beside it already say.
        mark = _load_brand_image("mark-on-dark-128.png", round(30 * self._scale))
        if mark is not None:
            self._brand_images.append(mark)
            ttk.Label(brand, image=mark, style="BrandMark.TLabel").pack(side=LEFT, padx=(0, 10))

        ttk.Label(brand, text=APP_NAME, style="Brand.TLabel").pack(side=LEFT)
        ttk.Label(brand, text=f"  {APP_TAGLINE}", style="BrandSub.TLabel").pack(side=LEFT, pady=(6, 0))

        settings = get_settings()
        target = f"{settings.db_user}@{settings.db_host}:{settings.db_port}/{settings.db_name}"
        ttk.Label(inner, text=target, style="HeaderMeta.TLabel").pack(side=RIGHT, pady=(6, 0))

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        sidebar = ttk.Frame(parent, style="Card.TFrame", width=round(290 * self._scale))
        sidebar.pack(side=LEFT, fill=Y, padx=(0, 12))
        sidebar.pack_propagate(False)

        # --- Selected file ---------------------------------------------
        self._section_label(sidebar, "INPUT FILE", first=True)

        file_box = ttk.Frame(sidebar, style="Card.TFrame")
        file_box.pack(fill=X, padx=14, pady=(0, 4))

        self.file_var = StringVar(value="No file selected")
        self.file_label = ttk.Label(file_box, textvariable=self.file_var, style="File.TLabel",
                                    wraplength=round(250 * self._scale), justify=LEFT)
        self.file_label.pack(fill=X, anchor="w")

        self._add_button(sidebar, "Browse for a .log file", self._on_browse, primary=True)
        self._add_button(sidebar, "Generate Sample Log", self._on_generate_sample)

        # --- Pipeline --------------------------------------------------
        self._section_label(sidebar, "PIPELINE")
        self._add_button(sidebar, "Initialize Database", self._on_init_db)
        self._add_button(sidebar, "Ingest Selected File", self._on_ingest)
        self._add_button(sidebar, "Run Analytics", self._on_analyze)

        # --- Outputs ---------------------------------------------------
        self._section_label(sidebar, "OUTPUTS")
        self._add_button(sidebar, "Generate Charts", self._on_charts)
        self._add_button(sidebar, "Export Reports", self._on_report)

        folders = ttk.Frame(sidebar, style="Card.TFrame")
        folders.pack(fill=X, padx=14, pady=(6, 14))
        ttk.Button(folders, text="Charts folder", style="Ghost.TButton",
                   command=self._on_open_charts_folder).pack(side=LEFT, expand=True, fill=X, padx=(0, 3))
        ttk.Button(folders, text="Reports folder", style="Ghost.TButton",
                   command=self._on_open_reports_folder).pack(side=LEFT, expand=True, fill=X, padx=(3, 0))

    def _build_console(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(side=LEFT, fill=BOTH, expand=True)

        bar = ttk.Frame(card, style="Card.TFrame")
        bar.pack(fill=X, padx=14, pady=(12, 6))
        ttk.Label(bar, text="CONSOLE", style="Section.TLabel").pack(side=LEFT)
        ttk.Button(bar, text="Clear", style="Ghost.TButton", command=self._on_clear_output).pack(side=RIGHT)

        self.output = ScrolledText(
            card,
            state=DISABLED,
            font=("Consolas", 10),
            wrap="word",
            bg=Palette.console_bg,
            fg=Palette.text,
            insertbackground=Palette.text,
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
            selectbackground=Palette.accent_press,
        )
        self.output.pack(fill=BOTH, expand=True, padx=14, pady=(0, 14))

        # ScrolledText builds a classic tk.Scrollbar, which ignores ttk styling —
        # colour it directly so it doesn't sit as a light grey bar on a dark panel.
        self.output.vbar.configure(
            bg=Palette.surface,
            activebackground=Palette.border,
            troughcolor=Palette.console_bg,
            highlightthickness=0,
            borderwidth=0,
            width=12,
        )

        self.output.tag_configure("info", foreground=Palette.text)
        self.output.tag_configure("muted", foreground=Palette.text_muted)
        self.output.tag_configure("heading", foreground=Palette.accent, font=("Consolas", 10, "bold"))
        self.output.tag_configure("success", foreground=Palette.success)
        self.output.tag_configure("warning", foreground=Palette.warning)
        self.output.tag_configure("error", foreground=Palette.error)
        self.output.tag_configure("time", foreground=Palette.text_dim)

    def _build_statusbar(self) -> None:
        self.progress = ttk.Progressbar(self.root, style="Thin.Horizontal.TProgressbar", mode="indeterminate")
        self.progress.pack(fill=X)

        bar = ttk.Frame(self.root, style="Status.TFrame")
        bar.pack(fill=X)

        self.status_var = StringVar(value="Idle")
        ttk.Label(bar, textvariable=self.status_var, style="Status.TLabel").pack(side=LEFT, padx=14, pady=6)

        self.hint_var = StringVar(value="Ctrl+O open · Ctrl+I ingest · Ctrl+R analytics · Ctrl+L clear")
        ttk.Label(bar, textvariable=self.hint_var, style="Status.TLabel").pack(side=RIGHT, padx=14, pady=6)

    def _section_label(self, parent: ttk.Frame, text: str, first: bool = False) -> None:
        ttk.Label(parent, text=text, style="Section.TLabel").pack(
            fill=X, padx=14, pady=(14 if first else 16, 6), anchor="w"
        )

    def _add_button(
        self, parent: ttk.Frame, text: str, command: Callable[[], None], primary: bool = False
    ) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command, style="Primary.TButton" if primary else "Action.TButton")
        button.pack(fill=X, padx=14, pady=3)
        self._action_buttons.append(button)
        return button

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _e: self._guarded(self._on_browse))
        self.root.bind("<Control-g>", lambda _e: self._guarded(self._on_generate_sample))
        self.root.bind("<Control-i>", lambda _e: self._guarded(self._on_ingest))
        self.root.bind("<Control-r>", lambda _e: self._guarded(self._on_analyze))
        self.root.bind("<Control-l>", lambda _e: self._on_clear_output())

    def _guarded(self, action: Callable[[], None]) -> None:
        """Ignore a shortcut while a background job is running."""
        if not self._busy:
            action()

    # ------------------------------------------------------------------
    # Thread-safe output + background execution
    # ------------------------------------------------------------------

    def _log(self, message: str, tag: str = "info") -> None:
        """Schedule a message append on the main thread — safe to call from a worker thread."""
        self.root.after(0, self._append_output, message, tag)

    def _append_output(self, message: str, tag: str = "info") -> None:
        self.output.configure(state=NORMAL)
        self.output.insert(END, f"{datetime.now():%H:%M:%S}  ", "time")
        self.output.insert(END, message + "\n", tag)
        self.output.see(END)
        self.output.configure(state=DISABLED)

    def _set_busy(self, busy: bool, status: str = "") -> None:
        self._busy = busy
        state = DISABLED if busy else NORMAL
        for button in self._action_buttons:
            button.configure(state=state)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
        self.status_var.set(status or ("Working..." if busy else "Idle"))

    def _run_async(self, description: str, target: Callable[[], None]) -> None:
        """Run `target` on a background thread, keeping the window responsive."""
        self.root.after(0, self._set_busy, True, f"{description}...")
        self._log(description, tag="heading")

        def worker() -> None:
            started = datetime.now()
            try:
                target()
                elapsed = (datetime.now() - started).total_seconds()
                self._log(f"Done — {description.lower()} ({elapsed:.1f}s)", tag="success")
            except Exception as exc:  # noqa: BLE001 - surfacing any failure to the GUI is the point
                logger.exception("GUI action failed: %s", description)
                self._log(f"Failed — {description.lower()}: {exc}", tag="error")
                self._log(traceback.format_exc(), tag="muted")
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
            self._set_selected_file(Path(path))

    def _set_selected_file(self, path: Path) -> None:
        self.selected_file = path
        size_mb = path.stat().st_size / (1024 * 1024) if path.exists() else 0.0
        self.file_var.set(f"{path.name}\n{size_mb:.2f} MB · {path.parent}")
        self._log(f"Selected: {path}", tag="muted")

    def _on_init_db(self) -> None:
        def task() -> None:
            from log_analyzer.database import initialize_database

            initialize_database()
            self._log("Database ready: tables, indexes, and log levels created.")

        self._run_async("Initializing database", task)

    def _on_generate_sample(self) -> None:
        def task() -> None:
            from log_analyzer.utils import generate_sample_logs

            settings = get_settings()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = settings.log_input_dir / f"gui_sample_{timestamp}.log"
            path = generate_sample_logs(output_path, num_lines=3000)
            self._log(f"Generated sample log file: {path}")
            self.root.after(0, self._set_selected_file, path)

        self._run_async("Generating sample log file (3000 lines)", task)

    def _on_ingest(self) -> None:
        if self.selected_file is None:
            messagebox.showwarning("No file selected", "Use 'Browse for a .log file' or 'Generate Sample Log' first.")
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
            self._log(f"Cannot auto-open folders on this OS. Path: {path}", tag="warning")

    def _on_clear_output(self) -> None:
        self.output.configure(state=NORMAL)
        self.output.delete("1.0", END)
        self.output.configure(state=DISABLED)

    def _on_about(self) -> None:
        from log_analyzer import __version__

        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME} — {APP_TAGLINE}\nVersion {__version__}\n\n"
            "ETL and analytics pipeline for application log files, backed by PostgreSQL.\n"
            "This window drives the same services as the command line (logsx).",
        )

    def run(self) -> None:
        self.root.mainloop()


# Kept as an alias so existing imports of the old class name keep working.
LogAnalyzerGUI = LogSXGUI


def main() -> None:
    LogSXGUI().run()


if __name__ == "__main__":
    main()
