"""In-app dashboard and summary-report views.

These two views are what the app shows instead of making the user open
exported files: :class:`DashboardView` renders the KPI tiles and every
Matplotlib chart directly inside the window, and :class:`ReportView` renders
the full analytics summary as sortable-looking tables. Both are fed by a
single :class:`DashboardData` snapshot so the numbers on the tiles, the marks
on the charts, and the rows in the tables can never disagree.

The heavy lifting — running analytics and building the figures — happens in
:func:`build_dashboard_data`, which touches no Tk widgets and is therefore
safe to call from the GUI's background worker thread. Rendering, which does
touch widgets, runs on the main thread.

Nothing heavyweight is imported at module scope: pandas, matplotlib and the
database layer are pulled in inside the functions that need them, so opening
the window stays fast.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from tkinter import BOTH, LEFT, RIGHT, Canvas, TclError, Y, ttk
from typing import TYPE_CHECKING, Any, NamedTuple

from log_analyzer.gui.palette import Palette

if TYPE_CHECKING:  # imported for typing only — keeps matplotlib off the startup path
    from log_analyzer.visualization.figures import Chart

# Tables show a capped number of rows and say so, rather than growing a nested
# scrollbar inside an already-scrolling page.
MAX_TABLE_ROWS = 12

# Inches (at the figure's own 100 dpi) that every embedded chart is resized to,
# so the dashboard's chart rows are all the same height.
CHART_CARD_SIZE_IN = (5.6, 3.1)


# ----------------------------------------------------------------------
# Data snapshot
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class DashboardData:
    """One analytics snapshot: the summary numbers plus the figures drawn from them."""

    summary: dict[str, Any]
    charts: list[Chart] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def is_empty(self) -> bool:
        return not self.summary.get("total_log_count")


class Kpi(NamedTuple):
    """One headline tile. ``tone`` is "", "Good", "Warn" or "Bad"."""

    caption: str
    value: str
    sub: str = ""
    tone: str = ""


class ReportSection(NamedTuple):
    """One report table: a title, its (heading, width, anchor) columns, and its rows."""

    title: str
    columns: Sequence[tuple[str, int, str]]
    rows: Sequence[Sequence[Any]]


def build_dashboard_data(top_n: int = 10) -> DashboardData:
    """Run analytics and build every chart figure for the dashboard.

    Pure computation — no Tk calls — so the GUI runs this on a worker thread
    and keeps the window responsive. The figures come back as plain Matplotlib
    ``Figure`` objects that the views attach to Tk canvases afterwards.
    """
    from log_analyzer.analytics import LogAnalytics
    from log_analyzer.visualization import DARK_THEME, FigureBuilder

    analytics = LogAnalytics()
    summary = analytics.generate_summary(top_n=top_n)
    charts = [] if not summary["total_log_count"] else FigureBuilder(analytics, DARK_THEME).build_all(top_n)
    return DashboardData(summary=summary, charts=charts)


# ----------------------------------------------------------------------
# Styles
# ----------------------------------------------------------------------


def init_dashboard_styles(style: ttk.Style) -> None:
    """Register the ttk styles the dashboard and report views use.

    Called once by the main window after it selects the "clam" theme, which
    (unlike the native themes) honours explicit colour configuration.
    """
    style.configure("Dash.TNotebook", background=Palette.bg, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure(
        "Dash.TNotebook.Tab",
        background=Palette.bg,
        foreground=Palette.text_muted,
        bordercolor=Palette.bg,
        lightcolor=Palette.bg,
        darkcolor=Palette.bg,
        padding=(18, 9),
        font=("Segoe UI", 10),
    )
    style.map(
        "Dash.TNotebook.Tab",
        background=[("selected", Palette.surface), ("active", Palette.border)],
        foreground=[("selected", Palette.text)],
        lightcolor=[("selected", Palette.surface)],
        expand=[("selected", (0, 0, 0, 0))],
    )

    style.configure("Tile.TFrame", background=Palette.surface_alt)
    style.configure("TileCaption.TLabel", background=Palette.surface_alt, foreground=Palette.text_dim,
                    font=("Segoe UI Semibold", 8))
    style.configure("TileValue.TLabel", background=Palette.surface_alt, foreground=Palette.text,
                    font=("Segoe UI Semibold", 20))
    style.configure("TileSub.TLabel", background=Palette.surface_alt, foreground=Palette.text_muted,
                    font=("Segoe UI", 9))
    for suffix, colour in (("Good", Palette.success), ("Warn", Palette.warning), ("Bad", Palette.error)):
        style.configure(f"TileValue{suffix}.TLabel", background=Palette.surface_alt, foreground=colour,
                        font=("Segoe UI Semibold", 20))

    style.configure("CardTitle.TLabel", background=Palette.surface, foreground=Palette.text,
                    font=("Segoe UI Semibold", 11))
    style.configure("CardNote.TLabel", background=Palette.surface, foreground=Palette.text_dim,
                    font=("Segoe UI", 8))
    style.configure("Placeholder.TLabel", background=Palette.bg, foreground=Palette.text_muted,
                    font=("Segoe UI", 11))
    style.configure("SnapshotMeta.TLabel", background=Palette.bg, foreground=Palette.text_dim,
                    font=("Consolas", 9))

    # A borderless Treeview: clam draws a light 3D frame by default, which
    # reads as a bright box on a dark panel.
    style.layout("Dash.Treeview", [("Dash.Treeview.treearea", {"sticky": "nswe"})])
    style.configure(
        "Dash.Treeview",
        background=Palette.surface,
        fieldbackground=Palette.surface,
        foreground=Palette.text,
        borderwidth=0,
        rowheight=24,
        font=("Segoe UI", 9),
    )
    style.configure(
        "Dash.Treeview.Heading",
        background=Palette.surface,
        foreground=Palette.text_dim,
        relief="flat",
        borderwidth=0,
        font=("Segoe UI Semibold", 8),
    )
    style.map("Dash.Treeview.Heading", background=[("active", Palette.border)])
    style.map(
        "Dash.Treeview",
        background=[("selected", Palette.accent_press)],
        foreground=[("selected", "#ffffff")],
    )


# ----------------------------------------------------------------------
# Reusable widgets
# ----------------------------------------------------------------------


def _wheel_step(event: Any) -> int:
    """One scroll step for a wheel event: Windows/macOS report delta, X11 sends Button-4/5."""
    if getattr(event, "num", None) in (4, 5):
        return -1 if event.num == 4 else 1
    return -1 if event.delta > 0 else 1


class ScrollableFrame(ttk.Frame):
    """A vertically scrolling area whose ``body`` holds the actual content.

    Tk has no scrollable frame, so this is the standard Canvas-plus-inner-frame
    construction, with the inner frame pinned to the canvas width so children
    can lay themselves out responsively.
    """

    def __init__(self, parent: ttk.Widget, background: str = Palette.bg) -> None:
        super().__init__(parent, style="TFrame")

        self.canvas = Canvas(self, bg=background, highlightthickness=0, borderwidth=0, takefocus=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.body = ttk.Frame(self.canvas, style="TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # bind_all is the only way to catch the wheel over a child widget (a
        # Matplotlib canvas grabs its own events), so every scroller listens
        # and the handler routes the event to whichever one the pointer is over.
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.canvas.bind_all("<Button-4>", self._on_wheel, add="+")
        self.canvas.bind_all("<Button-5>", self._on_wheel, add="+")

    def _on_body_configure(self, _event: Any) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: Any) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _on_wheel(self, event: Any) -> None:
        if self._pointer_is_inside(event):
            self.canvas.yview_scroll(_wheel_step(event), "units")

    def _pointer_is_inside(self, event: Any) -> bool:
        """True when the pointer is over this scroller's canvas or any of its children."""
        try:
            widget = self.canvas.winfo_containing(event.x_root, event.y_root)
        except (KeyError, TclError):  # a widget being torn down mid-event
            return False
        if widget is None or not self.canvas.winfo_ismapped():
            return False
        canvas_path = str(self.canvas)
        widget_path = str(widget)
        return widget_path == canvas_path or widget_path.startswith(f"{canvas_path}.")

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0.0)


class CardGrid(ttk.Frame):
    """A responsive grid of equal-width cards that re-flows as the window resizes.

    Column count is derived from the available width and ``min_card_width``, so
    a narrow window stacks cards in one column and a wide one shows three or
    four, without any fixed breakpoints.
    """

    _MAX_COLUMNS = 6

    def __init__(self, parent: ttk.Widget, min_card_width: int, gap: int = 6) -> None:
        super().__init__(parent, style="TFrame")
        self._min_card_width = max(1, min_card_width)
        self._gap = gap
        self._cards: list[ttk.Widget] = []
        self._columns = 0
        self.bind("<Configure>", lambda event: self._layout(event.width))

    def add(self, card: ttk.Widget) -> None:
        self._cards.append(card)

    def clear(self) -> None:
        for card in self._cards:
            card.destroy()
        self._cards.clear()
        self._columns = 0

    def relayout(self) -> None:
        """Force a fresh layout — call after adding cards, before the first resize event."""
        self._columns = 0
        self._layout(self.winfo_width())

    def _layout(self, width: int) -> None:
        columns = max(1, min(self._MAX_COLUMNS, width // self._min_card_width))
        if columns == self._columns or not self._cards:
            return
        self._columns = columns
        for index, card in enumerate(self._cards):
            card.grid(
                row=index // columns,
                column=index % columns,
                sticky="nsew",
                padx=self._gap,
                pady=self._gap,
            )
        # Only the columns in use join the uniform group: leaving a retired
        # column in it keeps it claiming an equal share of the width, which
        # squeezes the visible cards down to nothing.
        for column in range(self._MAX_COLUMNS):
            if column < columns:
                self.columnconfigure(column, weight=1, uniform="card")
            else:
                self.columnconfigure(column, weight=0, uniform="")


def make_card(parent: ttk.Widget, title: str | None = None) -> ttk.Frame:
    """A titled surface panel — the container every chart and table sits in."""
    card = ttk.Frame(parent, style="Card.TFrame", padding=(14, 12))
    if title:
        ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
    return card


def make_tile(parent: ttk.Widget, kpi: Kpi) -> ttk.Frame:
    """A single KPI tile: small caption, large value, optional sub-line.

    The tone only colours the number — the caption always spells out what the
    number is, so colour never carries meaning on its own.
    """
    tile = ttk.Frame(parent, style="Tile.TFrame", padding=(14, 12))
    ttk.Label(tile, text=kpi.caption.upper(), style="TileCaption.TLabel").pack(anchor="w")
    ttk.Label(tile, text=kpi.value, style=f"TileValue{kpi.tone}.TLabel").pack(anchor="w", pady=(4, 0))
    ttk.Label(tile, text=kpi.sub or " ", style="TileSub.TLabel").pack(anchor="w")
    return tile


def make_table(
    parent: ttk.Widget,
    columns: Sequence[tuple[str, int, str]],
    rows: Sequence[Sequence[Any]],
) -> ttk.Treeview:
    """A read-only table sized to its content — no nested scrollbar.

    ``columns`` is a sequence of (heading, width, anchor) triples.
    """
    keys = [f"c{index}" for index in range(len(columns))]
    table = ttk.Treeview(
        parent,
        columns=keys,
        show="headings",
        style="Dash.Treeview",
        height=max(1, len(rows)),
        selectmode="none",
    )
    for key, (heading, width, anchor) in zip(keys, columns, strict=True):
        table.heading(key, text=heading.upper(), anchor=anchor)
        table.column(key, width=width, anchor=anchor, stretch=True)

    table.tag_configure("odd", background=Palette.surface_alt)
    for index, row in enumerate(rows):
        table.insert("", "end", values=tuple(row), tags=("odd",) if index % 2 else ())
    return table


def _cap(rows: Sequence[Any]) -> tuple[Sequence[Any], str]:
    """Trim a row list to MAX_TABLE_ROWS and describe what was left out."""
    if len(rows) <= MAX_TABLE_ROWS:
        return rows, ""
    return rows[:MAX_TABLE_ROWS], f"Showing {MAX_TABLE_ROWS} of {len(rows)}"


def _num(value: Any) -> str:
    """Format a count with thousands separators; pass anything else through."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return str(value)
    return f"{value:,}" if isinstance(value, int) else f"{value:,.2f}"


def _rate_tone(percentage: float, warn_above: float = 1.0, bad_above: float = 5.0) -> str:
    if percentage > bad_above:
        return "Bad"
    if percentage > warn_above:
        return "Warn"
    return "Good"


# ----------------------------------------------------------------------
# Snapshot -> view model
#
# These two functions turn an analytics summary into the exact tiles and
# tables the views draw. They are plain data in, plain data out — no widgets —
# so the content of the dashboard can be tested without a display.
# ----------------------------------------------------------------------


def kpi_tiles(summary: dict[str, Any]) -> list[Kpi]:
    """The headline numbers, in reading order.

    Metrics the dataset cannot support are left out entirely rather than shown
    as a zero: a log file with no request-scoped lines has no p95 latency and
    no HTTP error rate, and a tile reading "0 ms" would be a claim, not a blank.
    """
    level_counts = summary["level_counts"]
    errors = level_counts.get("ERROR", 0) + level_counts.get("CRITICAL", 0)
    error_pct = summary["error_percentage"]
    malformed = summary["malformed_summary"]
    duplicates = summary["duplicate_summary"]

    tiles = [
        Kpi("Total log entries", _num(summary["total_log_count"]),
            f"across {_num(len(summary['daily_trend']))} days"),
        Kpi("Error rate", f"{error_pct}%", f"{_num(errors)} error/critical lines", _rate_tone(error_pct)),
        Kpi("Throughput", _num(summary["average_logs_per_hour"]), "logs per hour (mean)"),
    ]

    peaks = summary["peak_logging_hours"]
    if peaks:
        tiles.append(
            Kpi("Peak hour", f"{peaks[0]['hour']:02d}:00", f"{_num(peaks[0]['count'])} logs in that hour")
        )

    warnings = level_counts.get("WARNING", 0)
    tiles.append(Kpi("Warnings", _num(warnings), "WARNING-level lines", "Warn" if warnings else "Good"))

    response = summary["response_time_stats"]
    if response:
        tiles.append(
            Kpi("p95 latency", f"{response['p95_ms']:,.0f} ms", f"median {response['median_ms']:,.0f} ms")
        )

    if summary["status_code_distribution"]:
        http_rate = summary["http_error_rate"]
        tiles.append(Kpi("HTTP error rate", f"{http_rate}%", "4xx and 5xx responses", _rate_tone(http_rate)))

    malformed_rate = malformed["malformed_rate_pct"]
    tiles.append(
        Kpi(
            "Malformed lines",
            _num(malformed["malformed_lines_detected"]),
            f"{malformed_rate}% of lines ingested",
            _rate_tone(malformed_rate),
        )
    )
    tiles.append(
        Kpi("Duplicates skipped", _num(duplicates["duplicate_lines_detected"]), "identical lines re-ingested")
    )
    return tiles


def report_sections(summary: dict[str, Any]) -> Iterator[ReportSection]:
    """Every report table, in presentation order. Empty ones are skipped by the caller."""
    total = summary["total_log_count"] or 1

    yield ReportSection(
        "Log level breakdown",
        [("Level", 110, "w"), ("Count", 90, "e"), ("Share", 80, "e")],
        [
            [level, _num(count), f"{count / total * 100:.1f}%"]
            for level, count in summary["level_counts"].items()
        ],
    )

    yield ReportSection(
        "Top error messages",
        [("Count", 70, "e"), ("Message", 320, "w")],
        [[_num(r["count"]), r["message"]] for r in summary["most_common_error_messages"]],
    )

    yield ReportSection(
        "Most active users",
        [("User", 200, "w"), ("Log entries", 100, "e")],
        [[r["user"], _num(r["count"])] for r in summary["most_active_users"]],
    )

    yield ReportSection(
        "Most frequent events",
        [("Count", 70, "e"), ("Message", 320, "w")],
        [[_num(r["count"]), r["message"]] for r in summary["top_frequent_events"]],
    )

    yield ReportSection(
        "Peak logging hours",
        [("Hour", 90, "w"), ("Log entries", 100, "e")],
        [[f"{r['hour']:02d}:00", _num(r["count"])] for r in summary["peak_logging_hours"]],
    )

    daily = list(summary["daily_trend"].items())
    yield ReportSection(
        "Daily volume (most recent)",
        [("Date", 140, "w"), ("Log entries", 100, "e")],
        [[day, _num(count)] for day, count in reversed(daily)],
    )

    yield ReportSection(
        "Monthly volume",
        [("Month", 140, "w"), ("Log entries", 100, "e")],
        [[month, _num(count)] for month, count in summary["monthly_trend"].items()],
    )

    yield ReportSection(
        "HTTP status codes",
        [("Class", 100, "w"), ("Requests", 100, "e")],
        [[cls, _num(count)] for cls, count in summary["status_code_distribution"].items()],
    )

    response = summary["response_time_stats"]
    yield ReportSection(
        "Response time percentiles",
        [("Metric", 140, "w"), ("Milliseconds", 120, "e")],
        [
            [label, _num(response[key])]
            for label, key in (
                ("Mean", "mean_ms"),
                ("Median", "median_ms"),
                ("p90", "p90_ms"),
                ("p95", "p95_ms"),
                ("p99", "p99_ms"),
                ("Fastest", "min_ms"),
                ("Slowest", "max_ms"),
            )
            if key in response
        ],
    )

    yield ReportSection(
        "Busiest endpoints",
        [("Endpoint", 240, "w"), ("Requests", 90, "e")],
        [[r["endpoint"], _num(r["count"])] for r in summary["top_endpoints"]],
    )

    yield ReportSection(
        "Slowest endpoints",
        [("Endpoint", 200, "w"), ("Mean ms", 90, "e"), ("Samples", 80, "e")],
        [
            [r["endpoint"], _num(r["avg_response_time_ms"]), _num(r["sample_count"])]
            for r in summary["slowest_endpoints"]
        ],
    )

    yield ReportSection(
        "Exception types",
        [("Exception", 240, "w"), ("Occurrences", 100, "e")],
        [[r["exception_type"], _num(r["count"])] for r in summary["exception_type_breakdown"]],
    )

    stats = summary["statistical_summary"]
    rows: list[list[Any]] = []
    if stats:
        rows = [
            [label, _num(stats[key])]
            for label, key in (
                ("Mean logs/day", "mean_logs_per_day"),
                ("Median logs/day", "median_logs_per_day"),
                ("Std deviation", "std_dev_logs_per_day"),
                ("Variance", "variance_logs_per_day"),
                ("Quietest day", "min_logs_per_day"),
                ("Busiest day", "max_logs_per_day"),
                ("Skewness", "skewness"),
                ("Kurtosis", "kurtosis"),
            )
            if key in stats
        ]
        outliers = stats.get("outlier_days") or []
        rows.append(["Outlier days (>2σ)", ", ".join(outliers) if outliers else "none"])
    yield ReportSection("Daily volume statistics", [("Metric", 180, "w"), ("Value", 140, "e")], rows)

    duplicates = summary["duplicate_summary"]
    malformed = summary["malformed_summary"]
    yield ReportSection(
        "Ingestion data quality",
        [("Metric", 220, "w"), ("Value", 120, "e")],
        [
            ["Lines processed (all runs)", _num(malformed["total_lines_processed"])],
            ["Unique lines inserted", _num(duplicates["unique_lines_inserted"])],
            ["Duplicate lines skipped", _num(duplicates["duplicate_lines_detected"])],
            ["Malformed lines skipped", _num(malformed["malformed_lines_detected"])],
            ["Malformed rate", f"{malformed['malformed_rate_pct']}%"],
        ],
    )


# ----------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------


class _SnapshotView(ttk.Frame):
    """Shared scaffolding for the two snapshot views: scrolling body + empty state."""

    empty_message = "No data yet."

    def __init__(self, parent: ttk.Widget, scale: float = 1.0) -> None:
        super().__init__(parent, style="TFrame")
        self.scale = scale
        self.scroll = ScrollableFrame(self)
        self.scroll.pack(fill=BOTH, expand=True)
        self.show_message(self.empty_message)

    # -- content lifecycle ---------------------------------------------

    def _reset(self) -> None:
        for child in self.scroll.body.winfo_children():
            child.destroy()

    def show_message(self, message: str) -> None:
        """Replace all content with a single centred block of guidance."""
        self._reset()
        ttk.Label(
            self.scroll.body, text=message, style="Placeholder.TLabel", justify="center", wraplength=520
        ).pack(pady=60, padx=24)

    def render(self, data: DashboardData) -> None:
        """Draw one snapshot, or explain why there is nothing to draw."""
        if data.is_empty:
            self.show_message(self.empty_message)
            return
        self._reset()
        self._populate(data)
        self.scroll.scroll_to_top()

    def _populate(self, data: DashboardData) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _snapshot_header(self, data: DashboardData, subtitle: str) -> None:
        header = ttk.Frame(self.scroll.body, style="TFrame")
        header.pack(fill="x", padx=6, pady=(10, 2))
        ttk.Label(header, text=subtitle, style="TLabel").pack(side=LEFT)
        ttk.Label(
            header,
            text=f"snapshot {data.generated_at:%Y-%m-%d %H:%M:%S}",
            style="SnapshotMeta.TLabel",
        ).pack(side=RIGHT)


class DashboardView(_SnapshotView):
    """KPI tiles plus every chart, rendered live inside the window."""

    empty_message = (
        "The dashboard is empty.\n\n"
        "Ingest a .log file (Ctrl+I), then refresh the dashboard (Ctrl+R)\n"
        "to see charts and key metrics here."
    )

    def __init__(self, parent: ttk.Widget, scale: float = 1.0) -> None:
        # Matplotlib canvases must be kept alive explicitly: dropping the last
        # reference tears down the backend object while its Tk widget lives on.
        self._canvases: list[Any] = []
        super().__init__(parent, scale)

    def _reset(self) -> None:
        for canvas in self._canvases:
            canvas.get_tk_widget().destroy()
            canvas.figure.clf()
        self._canvases.clear()
        super()._reset()

    def _populate(self, data: DashboardData) -> None:
        summary = data.summary
        total = summary["total_log_count"]
        self._snapshot_header(data, f"{_num(total)} log entries analysed")

        tiles = CardGrid(self.scroll.body, min_card_width=round(210 * self.scale))
        tiles.pack(fill="x", padx=6, pady=(6, 4))
        for kpi in kpi_tiles(summary):
            tiles.add(make_tile(tiles, kpi))
        tiles.relayout()

        charts = CardGrid(self.scroll.body, min_card_width=round(380 * self.scale))
        charts.pack(fill=BOTH, expand=True, padx=6, pady=(4, 12))
        for chart in data.charts:
            charts.add(self._chart_card(charts, chart))
        charts.relayout()

    def _chart_card(self, parent: ttk.Widget, chart: Chart) -> ttk.Frame:
        """Embed one Matplotlib figure in a card.

        Every embedded figure is normalised to the same size first. The Tk
        backend derives the widget's requested size from the figure, and the
        grid row is as tall as its tallest card — so without this, the export
        figure sizes (which vary per chart) would give the dashboard ragged
        rows. Once shown, the figure follows the widget as the window resizes.
        """
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        chart.figure.set_size_inches(CHART_CARD_SIZE_IN)

        card = make_card(parent)
        canvas = FigureCanvasTkAgg(chart.figure, master=card)
        widget = canvas.get_tk_widget()
        widget.configure(background=Palette.surface, highlightthickness=0, borderwidth=0)
        widget.pack(fill=BOTH, expand=True)
        canvas.draw_idle()
        self._canvases.append(canvas)
        return card


class ReportView(_SnapshotView):
    """The full analytics summary as in-app tables — the report, without the export."""

    empty_message = (
        "No summary report yet.\n\n"
        "Ingest a .log file (Ctrl+I), then refresh the dashboard (Ctrl+R)\n"
        "to see the full breakdown here."
    )

    def _populate(self, data: DashboardData) -> None:
        summary = data.summary
        self._snapshot_header(data, "Full analytics breakdown")

        grid = CardGrid(self.scroll.body, min_card_width=round(360 * self.scale))
        grid.pack(fill=BOTH, expand=True, padx=6, pady=(6, 12))
        for section in report_sections(summary):
            if section.rows:
                grid.add(self._table_card(grid, section))
        grid.relayout()

    def _table_card(self, parent: ttk.Widget, section: ReportSection) -> ttk.Frame:
        card = make_card(parent, section.title)
        shown, note = _cap(section.rows)
        make_table(card, section.columns, shown).pack(fill=BOTH, expand=True)
        if note:
            ttk.Label(card, text=note, style="CardNote.TLabel").pack(anchor="e", pady=(6, 0))
        return card
