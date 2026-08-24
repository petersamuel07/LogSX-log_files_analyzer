"""Matplotlib figure builders for log analytics.

These builders are deliberately pyplot-free: every chart is created as a bare
``matplotlib.figure.Figure``, never through ``plt.subplots()``. That matters
for two reasons.

* pyplot keeps a global registry of open figures, which leaks memory in a
  long-running GUI that re-renders its dashboard on every refresh, and it
  binds the process to one global backend.
* A bare Figure can be handed to *either* consumer — ``ChartGenerator`` saves
  it as a PNG through the Agg backend, while the GUI dashboard hands the very
  same object to ``FigureCanvasTkAgg`` and draws it inside the window. One set
  of chart definitions, two surfaces.

Figures use the constrained layout engine so labels re-flow correctly when the
user resizes the dashboard, rather than needing a manual ``tight_layout()``
call on every resize event.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from log_analyzer.analytics import LogAnalytics
from log_analyzer.visualization.theme import LIGHT_THEME, ChartTheme

logger = logging.getLogger(__name__)

LEVEL_ORDER = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
STATUS_CLASS_ORDER = ["2xx", "3xx", "4xx", "5xx"]


@dataclass(frozen=True)
class Chart:
    """One rendered figure plus the metadata both consumers need.

    ``key`` is the stable identifier: the PNG filename stem on disk and the
    widget key in the dashboard, so a chart keeps the same identity wherever
    it is shown.
    """

    key: str
    title: str
    figure: Figure


class FigureBuilder:
    """Builds the standard chart set from a LogAnalytics instance.

    Every method returns a :class:`Chart`, or ``None`` when the underlying
    dataset has nothing to plot (HTTP charts on a log file with no
    request-scoped lines, for example) — callers skip those rather than
    showing an empty frame.
    """

    def __init__(self, analytics: LogAnalytics, theme: ChartTheme = LIGHT_THEME) -> None:
        self.analytics = analytics
        self.theme = theme

    # ------------------------------------------------------------------
    # Shared chrome
    # ------------------------------------------------------------------

    def _new(self, figsize: tuple[float, float]) -> tuple[Figure, Axes]:
        theme = self.theme
        fig = Figure(figsize=figsize, dpi=100, layout="constrained", facecolor=theme.surface)
        # Constrained layout sizes the axes from the tick labels' *vertical*
        # extent but not the horizontal overhang of the first and last x tick,
        # so the outermost label loses its final digit on a narrow figure. A
        # slightly wider pad buys back the room it needs.
        fig.get_layout_engine().set(w_pad=0.10, h_pad=0.05)
        ax = fig.add_subplot(111)
        ax.set_facecolor(theme.surface)
        ax.tick_params(colors=theme.ink_secondary, labelsize=9)
        return fig, ax

    def _finalize(self, fig: Figure, ax: Axes, key: str, title: str) -> Chart:
        """Apply the shared chart chrome: title, recessive grid, no top/right spines."""
        theme = self.theme
        # The title sits on the *figure*, not the axes: on the horizontal bar
        # charts the axes start well to the right of long category labels, so
        # an axes-anchored title runs off the edge of a narrow dashboard card.
        fig.suptitle(title, x=0.012, ha="left", fontsize=12, fontweight="bold", color=theme.ink_primary)
        ax.grid(axis="y", color=theme.gridline, linewidth=0.8, alpha=0.8)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(theme.baseline)
        ax.xaxis.label.set_color(theme.ink_secondary)
        ax.yaxis.label.set_color(theme.ink_secondary)
        return Chart(key=key, title=title, figure=fig)

    # ------------------------------------------------------------------
    # Charts
    # ------------------------------------------------------------------

    def level_distribution(self) -> Chart:
        counts = self.analytics.level_counts()
        levels = [lvl for lvl in LEVEL_ORDER if lvl in counts]
        values = [counts[lvl] for lvl in levels]
        colors = [self.theme.level_colors[lvl] for lvl in levels]

        fig, ax = self._new((7, 4.5))
        bars = ax.bar(levels, values, color=colors, width=0.6)
        ax.bar_label(bars, padding=3, color=self.theme.ink_secondary, fontsize=9)
        ax.set_ylabel("Log count")
        return self._finalize(fig, ax, "level_distribution", "Log Level Distribution")

    def daily_trend(self) -> Chart:
        daily = self.analytics.daily_trend()
        dates = list(daily.keys())
        values = list(daily.values())

        fig, ax = self._new((9, 4.5))
        ax.plot(
            dates,
            values,
            color=self.theme.sequential,
            linewidth=2,
            solid_capstyle="round",
            marker="o",
            markersize=4,
        )
        ax.set_ylabel("Log count")
        ax.xaxis.set_major_locator(MaxNLocator(nbins=10))
        for label in ax.get_xticklabels():
            label.set_rotation(45)
            label.set_horizontalalignment("right")
        return self._finalize(fig, ax, "daily_trend", "Daily Log Volume Trend")

    def hourly_activity(self) -> Chart:
        hourly = self.analytics.hourly_distribution()
        hours = list(range(24))
        values = [hourly.get(h, 0) for h in hours]

        fig, ax = self._new((9, 4.5))
        ax.bar(hours, values, color=self.theme.sequential, width=0.7)
        ax.set_xlabel("Hour of day")
        ax.set_ylabel("Log count")
        ax.set_xticks(hours)
        return self._finalize(fig, ax, "hourly_activity", "Peak Logging Hours")

    def top_errors(self, top_n: int = 10) -> Chart:
        records = list(reversed(self.analytics.most_common_error_messages(top_n)))
        labels = [r["message"][:40] for r in records]
        values = [r["count"] for r in records]

        fig, ax = self._new((8, 5))
        ax.barh(labels, values, color=self.theme.error, height=0.6)
        ax.set_xlabel("Occurrences")
        return self._finalize(fig, ax, "top_errors", f"Top {len(records)} Error Messages")

    def top_users(self, top_n: int = 10) -> Chart:
        records = list(reversed(self.analytics.most_active_users(top_n)))
        labels = [r["user"] for r in records]
        values = [r["count"] for r in records]

        fig, ax = self._new((7, 5))
        ax.barh(labels, values, color=self.theme.sequential, height=0.6)
        ax.set_xlabel("Log count")
        return self._finalize(fig, ax, "top_users", f"Top {len(records)} Most Active Users")

    def status_code_distribution(self) -> Chart | None:
        """2xx/3xx/4xx/5xx breakdown. None if no log lines carry HTTP context."""
        distribution = self.analytics.status_code_distribution()
        if not distribution:
            logger.info("No HTTP status codes present — skipping status_code_distribution chart.")
            return None

        classes = [c for c in STATUS_CLASS_ORDER if c in distribution]
        values = [distribution[c] for c in classes]
        colors = [self.theme.status_colors[c] for c in classes]

        fig, ax = self._new((6, 4.5))
        bars = ax.bar(classes, values, color=colors, width=0.5)
        ax.bar_label(bars, padding=3, color=self.theme.ink_secondary, fontsize=9)
        ax.set_ylabel("Request count")
        return self._finalize(fig, ax, "status_code_distribution", "HTTP Status Code Distribution")

    def response_time_distribution(self) -> Chart | None:
        """Histogram of response times. None if no log lines carry a response time."""
        response_times = self.analytics.df["response_time_ms"].dropna()
        if response_times.empty:
            logger.info("No response times present — skipping response_time_distribution chart.")
            return None

        fig, ax = self._new((8, 4.5))
        ax.hist(response_times, bins=30, color=self.theme.sequential, edgecolor=self.theme.surface, linewidth=0.5)
        ax.set_xlabel("Response time (ms)")
        ax.set_ylabel("Request count")
        return self._finalize(fig, ax, "response_time_distribution", "Response Time Distribution")

    def top_endpoints(self, top_n: int = 10) -> Chart | None:
        """Most frequently hit HTTP endpoints. None if no log lines carry HTTP context."""
        records = list(reversed(self.analytics.top_endpoints(top_n)))
        if not records:
            logger.info("No HTTP endpoints present — skipping top_endpoints chart.")
            return None

        labels = [r["endpoint"] for r in records]
        values = [r["count"] for r in records]

        fig, ax = self._new((7, 5))
        ax.barh(labels, values, color=self.theme.sequential, height=0.6)
        ax.set_xlabel("Request count")
        return self._finalize(fig, ax, "top_endpoints", f"Top {len(records)} HTTP Endpoints")

    def slowest_endpoints(self, top_n: int = 10) -> Chart | None:
        """Endpoints ranked by mean latency. None if no endpoint has enough samples."""
        records = list(reversed(self.analytics.slowest_endpoints(top_n)))
        if not records:
            logger.info("No endpoint has enough latency samples — skipping slowest_endpoints chart.")
            return None

        labels = [r["endpoint"] for r in records]
        values = [r["avg_response_time_ms"] for r in records]

        fig, ax = self._new((7, 5))
        ax.barh(labels, values, color=self.theme.sequential, height=0.6)
        ax.set_xlabel("Mean response time (ms)")
        return self._finalize(fig, ax, "slowest_endpoints", f"Slowest {len(records)} Endpoints")

    def exception_breakdown(self, top_n: int = 10) -> Chart | None:
        """Most common exception types. None if no entry recorded one."""
        records = list(reversed(self.analytics.exception_type_breakdown(top_n)))
        if not records:
            logger.info("No exception types present — skipping exception_breakdown chart.")
            return None

        labels = [r["exception_type"] for r in records]
        values = [r["count"] for r in records]

        fig, ax = self._new((7, 5))
        ax.barh(labels, values, color=self.theme.error, height=0.6)
        ax.set_xlabel("Occurrences")
        return self._finalize(fig, ax, "exception_breakdown", f"Top {len(records)} Exception Types")

    # ------------------------------------------------------------------
    # The full set
    # ------------------------------------------------------------------

    def build_all(self, top_n: int = 10) -> list[Chart]:
        """Build every chart the current dataset supports, in presentation order."""
        charts = [
            self.level_distribution(),
            self.daily_trend(),
            self.hourly_activity(),
            self.top_errors(top_n),
            self.top_users(top_n),
            self.status_code_distribution(),
            self.response_time_distribution(),
            self.top_endpoints(top_n),
            self.slowest_endpoints(top_n),
            self.exception_breakdown(top_n),
        ]
        return [chart for chart in charts if chart is not None]
