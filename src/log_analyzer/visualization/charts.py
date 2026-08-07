"""Matplotlib chart generation for log analytics.

Colors follow a validated, colorblind-safe palette: a single sequential blue
for magnitude-only charts (daily trend, hourly activity, top users), and the
reserved status colors (good/warning/serious/critical) for the log-level
distribution chart, since DEBUG->CRITICAL is genuinely a severity/status scale
rather than an arbitrary categorical grouping.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive backend — safe for headless/CLI use

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

from log_analyzer.analytics import LogAnalytics

logger = logging.getLogger(__name__)

# --- Palette (see dataviz skill references/palette.md — light-mode chart chrome) ---
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

SEQUENTIAL_BLUE = "#2a78d6"
ERROR_ORANGE = "#ec835a"

LEVEL_COLORS = {
    "DEBUG": INK_MUTED,
    "INFO": SEQUENTIAL_BLUE,
    "WARNING": "#fab219",
    "ERROR": ERROR_ORANGE,
    "CRITICAL": "#d03b3b",
}
LEVEL_ORDER = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Status-class colors reuse the reserved good/warning/critical palette roles,
# since 2xx/4xx/5xx genuinely are a status scale, not an arbitrary category.
STATUS_CLASS_COLORS = {"2xx": "#0ca30c", "3xx": SEQUENTIAL_BLUE, "4xx": "#fab219", "5xx": "#d03b3b"}
STATUS_CLASS_ORDER = ["2xx", "3xx", "4xx", "5xx"]

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": BASELINE,
        "axes.labelcolor": INK_SECONDARY,
        "text.color": INK_PRIMARY,
        "xtick.color": INK_SECONDARY,
        "ytick.color": INK_SECONDARY,
        "grid.color": GRIDLINE,
        "font.family": "sans-serif",
        "font.size": 10,
    }
)


class ChartGenerator:
    """Generates the standard chart set from a LogAnalytics instance and saves PNGs."""

    def __init__(self, analytics: LogAnalytics, output_dir: Path) -> None:
        self.analytics = analytics
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _finalize(self, fig, ax, filename: str, title: str) -> Path:
        """Shared chart chrome: title, recessive gridlines, no top/right spines."""
        ax.set_title(title, fontsize=12, fontweight="bold", color=INK_PRIMARY, loc="left", pad=12)
        ax.grid(axis="y", linewidth=0.8, alpha=0.8)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(BASELINE)

        fig.tight_layout()
        path = self.output_dir / filename
        fig.savefig(path, dpi=150, facecolor=SURFACE)
        plt.close(fig)
        logger.info("Saved chart: %s", path)
        return path

    def plot_level_distribution(self) -> Path:
        counts = self.analytics.level_counts()
        levels = [lvl for lvl in LEVEL_ORDER if lvl in counts]
        values = [counts[lvl] for lvl in levels]
        colors = [LEVEL_COLORS[lvl] for lvl in levels]

        fig, ax = plt.subplots(figsize=(7, 4.5))
        bars = ax.bar(levels, values, color=colors, width=0.6)
        ax.bar_label(bars, padding=3, color=INK_SECONDARY, fontsize=9)
        ax.set_ylabel("Log count")
        return self._finalize(fig, ax, "level_distribution.png", "Log Level Distribution")

    def plot_daily_trend(self) -> Path:
        daily = self.analytics.daily_trend()
        dates = list(daily.keys())
        values = list(daily.values())

        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.plot(dates, values, color=SEQUENTIAL_BLUE, linewidth=2, solid_capstyle="round", marker="o", markersize=4)
        ax.set_ylabel("Log count")
        ax.xaxis.set_major_locator(MaxNLocator(nbins=10))
        fig.autofmt_xdate(rotation=45)
        return self._finalize(fig, ax, "daily_trend.png", "Daily Log Volume Trend")

    def plot_hourly_activity(self) -> Path:
        hourly = self.analytics.hourly_distribution()
        hours = list(range(24))
        values = [hourly.get(h, 0) for h in hours]

        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.bar(hours, values, color=SEQUENTIAL_BLUE, width=0.7)
        ax.set_xlabel("Hour of day")
        ax.set_ylabel("Log count")
        ax.set_xticks(hours)
        return self._finalize(fig, ax, "hourly_activity.png", "Peak Logging Hours")

    def plot_top_errors(self, top_n: int = 10) -> Path:
        records = list(reversed(self.analytics.most_common_error_messages(top_n)))
        labels = [r["message"][:40] for r in records]
        values = [r["count"] for r in records]

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.barh(labels, values, color=ERROR_ORANGE, height=0.6)
        ax.set_xlabel("Occurrences")
        return self._finalize(fig, ax, "top_errors.png", f"Top {len(records)} Error Messages")

    def plot_top_users(self, top_n: int = 10) -> Path:
        records = list(reversed(self.analytics.most_active_users(top_n)))
        labels = [r["user"] for r in records]
        values = [r["count"] for r in records]

        fig, ax = plt.subplots(figsize=(7, 5))
        ax.barh(labels, values, color=SEQUENTIAL_BLUE, height=0.6)
        ax.set_xlabel("Log count")
        return self._finalize(fig, ax, "top_users.png", f"Top {len(records)} Most Active Users")

    def plot_status_code_distribution(self) -> Path | None:
        """2xx/3xx/4xx/5xx breakdown. Returns None if no log lines carry HTTP context."""
        distribution = self.analytics.status_code_distribution()
        if not distribution:
            logger.info("No HTTP status codes present — skipping status_code_distribution chart.")
            return None

        classes = [c for c in STATUS_CLASS_ORDER if c in distribution]
        values = [distribution[c] for c in classes]
        colors = [STATUS_CLASS_COLORS[c] for c in classes]

        fig, ax = plt.subplots(figsize=(6, 4.5))
        bars = ax.bar(classes, values, color=colors, width=0.5)
        ax.bar_label(bars, padding=3, color=INK_SECONDARY, fontsize=9)
        ax.set_ylabel("Request count")
        return self._finalize(fig, ax, "status_code_distribution.png", "HTTP Status Code Distribution")

    def plot_response_time_distribution(self) -> Path | None:
        """Histogram of response times. Returns None if no log lines carry a response time."""
        response_times = self.analytics.df["response_time_ms"].dropna()
        if response_times.empty:
            logger.info("No response times present — skipping response_time_distribution chart.")
            return None

        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.hist(response_times, bins=30, color=SEQUENTIAL_BLUE, edgecolor=SURFACE, linewidth=0.5)
        ax.set_xlabel("Response time (ms)")
        ax.set_ylabel("Request count")
        return self._finalize(fig, ax, "response_time_distribution.png", "Response Time Distribution")

    def plot_top_endpoints(self, top_n: int = 10) -> Path | None:
        """Most frequently hit HTTP endpoints. Returns None if no log lines carry HTTP context."""
        records = list(reversed(self.analytics.top_endpoints(top_n)))
        if not records:
            logger.info("No HTTP endpoints present — skipping top_endpoints chart.")
            return None

        labels = [r["endpoint"] for r in records]
        values = [r["count"] for r in records]

        fig, ax = plt.subplots(figsize=(7, 5))
        ax.barh(labels, values, color=SEQUENTIAL_BLUE, height=0.6)
        ax.set_xlabel("Request count")
        return self._finalize(fig, ax, "top_endpoints.png", f"Top {len(records)} HTTP Endpoints")

    def generate_all(self) -> list[Path]:
        """Generate and save every chart. Skips HTTP-specific charts if no request-scoped data exists."""
        charts = [
            self.plot_level_distribution(),
            self.plot_daily_trend(),
            self.plot_hourly_activity(),
            self.plot_top_errors(),
            self.plot_top_users(),
            self.plot_status_code_distribution(),
            self.plot_response_time_distribution(),
            self.plot_top_endpoints(),
        ]
        return [path for path in charts if path is not None]
