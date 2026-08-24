"""PNG export for the analytics charts.

This module is only the *file* half of visualization: it takes the figures
built by :class:`log_analyzer.visualization.figures.FigureBuilder` and writes
them to disk. The in-app dashboard renders those same figures directly into
the window instead of saving them, so the chart definitions live in one place
and neither surface re-implements them.

Exported PNGs use the light theme, since they are viewed on a white page or
pasted into a document rather than on the app's dark panels.
"""

from __future__ import annotations

import logging
from pathlib import Path

from log_analyzer.analytics import LogAnalytics
from log_analyzer.visualization.figures import Chart, FigureBuilder
from log_analyzer.visualization.theme import LIGHT_THEME, ChartTheme

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Renders the standard chart set to PNG files in ``output_dir``."""

    def __init__(self, analytics: LogAnalytics, output_dir: Path, theme: ChartTheme = LIGHT_THEME) -> None:
        self.analytics = analytics
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.builder = FigureBuilder(analytics, theme)

    def _save(self, chart: Chart | None) -> Path | None:
        """Write one chart to ``<output_dir>/<key>.png``, or do nothing if it has no data."""
        if chart is None:
            return None
        path = self.output_dir / f"{chart.key}.png"
        chart.figure.savefig(path, dpi=150, facecolor=chart.figure.get_facecolor())
        logger.info("Saved chart: %s", path)
        return path

    def plot_level_distribution(self) -> Path:
        return self._save(self.builder.level_distribution())  # type: ignore[return-value]

    def plot_daily_trend(self) -> Path:
        return self._save(self.builder.daily_trend())  # type: ignore[return-value]

    def plot_hourly_activity(self) -> Path:
        return self._save(self.builder.hourly_activity())  # type: ignore[return-value]

    def plot_top_errors(self, top_n: int = 10) -> Path:
        return self._save(self.builder.top_errors(top_n))  # type: ignore[return-value]

    def plot_top_users(self, top_n: int = 10) -> Path:
        return self._save(self.builder.top_users(top_n))  # type: ignore[return-value]

    def plot_status_code_distribution(self) -> Path | None:
        return self._save(self.builder.status_code_distribution())

    def plot_response_time_distribution(self) -> Path | None:
        return self._save(self.builder.response_time_distribution())

    def plot_top_endpoints(self, top_n: int = 10) -> Path | None:
        return self._save(self.builder.top_endpoints(top_n))

    def plot_slowest_endpoints(self, top_n: int = 10) -> Path | None:
        return self._save(self.builder.slowest_endpoints(top_n))

    def plot_exception_breakdown(self, top_n: int = 10) -> Path | None:
        return self._save(self.builder.exception_breakdown(top_n))

    def generate_all(self, top_n: int = 10) -> list[Path]:
        """Save every chart the dataset supports and return the written paths."""
        paths = [self._save(chart) for chart in self.builder.build_all(top_n)]
        return [path for path in paths if path is not None]
