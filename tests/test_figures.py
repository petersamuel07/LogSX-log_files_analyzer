"""Unit tests for log_analyzer.visualization.figures.

These build real Matplotlib figures against the in-memory SQLite fixture. No
display is needed: the builders never touch pyplot or a GUI backend, which is
exactly the property that lets the same figures be saved as PNGs by the CLI
and embedded in the GUI dashboard.
"""

from __future__ import annotations

import pytest

from log_analyzer.analytics import LogAnalytics
from log_analyzer.visualization import DARK_THEME, LIGHT_THEME, ChartGenerator, FigureBuilder


@pytest.fixture()
def builder(sqlite_engine_with_data):
    return FigureBuilder(LogAnalytics(engine=sqlite_engine_with_data))


def test_build_all_returns_a_chart_per_supported_metric(builder):
    charts = builder.build_all()
    keys = [chart.key for chart in charts]

    assert keys[:5] == [
        "level_distribution",
        "daily_trend",
        "hourly_activity",
        "top_errors",
        "top_users",
    ]
    assert len(keys) == len(set(keys)), "chart keys must be unique — they name the PNG files"


def test_every_chart_carries_a_title_and_a_figure(builder):
    for chart in builder.build_all():
        assert chart.title
        # The title lives on the figure (not the axes) so long category labels
        # can't push it off the edge of a narrow dashboard card.
        assert chart.figure._suptitle.get_text() == chart.title


def test_http_charts_are_skipped_without_request_data(sqlite_engine_with_data):
    """A log file of pure background lines has no endpoints, statuses, or latencies to plot."""
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    for column in ("http_endpoint", "status_code", "response_time_ms"):
        analytics.df[column] = None
    builder = FigureBuilder(analytics)

    assert builder.status_code_distribution() is None
    assert builder.response_time_distribution() is None
    assert builder.top_endpoints() is None
    assert builder.slowest_endpoints() is None
    assert {chart.key for chart in builder.build_all()} == {
        "level_distribution",
        "daily_trend",
        "hourly_activity",
        "top_errors",
        "top_users",
        "exception_breakdown",
    }


def test_theme_drives_the_figure_surface(sqlite_engine_with_data):
    """The dashboard's dark figures and the exported light ones come from one builder."""
    analytics = LogAnalytics(engine=sqlite_engine_with_data)

    light = FigureBuilder(analytics, LIGHT_THEME).level_distribution().figure
    dark = FigureBuilder(analytics, DARK_THEME).level_distribution().figure

    assert light.get_facecolor() != dark.get_facecolor()


def test_chart_generator_writes_one_png_per_chart(sqlite_engine_with_data, tmp_path):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    paths = ChartGenerator(analytics, tmp_path).generate_all()

    assert paths, "expected at least one chart to be written"
    assert {path.name for path in paths} == {path.name for path in tmp_path.glob("*.png")}
    assert all(path.stat().st_size > 0 for path in paths)
