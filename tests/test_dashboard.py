"""Unit tests for the dashboard's view model.

`kpi_tiles` and `report_sections` decide everything the dashboard and summary
report actually say, and both are plain functions over an analytics summary —
so what the user sees is tested here without opening a window.
"""

from __future__ import annotations

import pytest

from log_analyzer.analytics import LogAnalytics
from log_analyzer.gui.dashboard import DashboardData, kpi_tiles, report_sections


@pytest.fixture()
def summary(sqlite_engine_with_data):
    return LogAnalytics(engine=sqlite_engine_with_data).generate_summary()


def test_dashboard_data_reports_an_empty_snapshot():
    assert DashboardData(summary={"total_log_count": 0}).is_empty
    assert not DashboardData(summary={"total_log_count": 1}).is_empty


def test_kpi_tiles_lead_with_the_headline_counts(summary):
    tiles = {tile.caption: tile for tile in kpi_tiles(summary)}

    assert tiles["Total log entries"].value == "6"
    assert tiles["Error rate"].value == f"{summary['error_percentage']}%"
    assert tiles["Peak hour"].value.endswith(":00")


def test_kpi_tone_escalates_with_the_error_rate(summary):
    def tone_for(percentage: float) -> str:
        loud = {**summary, "error_percentage": percentage}
        return next(tile.tone for tile in kpi_tiles(loud) if tile.caption == "Error rate")

    assert tone_for(0.4) == "Good"
    assert tone_for(3.0) == "Warn"
    assert tone_for(30.0) == "Bad"


def test_http_tiles_are_dropped_when_there_is_no_http_data(summary):
    without_http = {**summary, "status_code_distribution": {}, "response_time_stats": {}}
    captions = [tile.caption for tile in kpi_tiles(without_http)]

    assert "HTTP error rate" not in captions
    assert "p95 latency" not in captions
    assert "Total log entries" in captions


def test_report_sections_cover_the_whole_summary(summary):
    sections = {section.title: section for section in report_sections(summary)}

    assert "Log level breakdown" in sections
    assert "Top error messages" in sections
    assert "Ingestion data quality" in sections
    for section in sections.values():
        assert all(len(row) == len(section.columns) for row in section.rows), (
            f"{section.title}: every row must have one cell per column"
        )


def test_daily_volume_section_lists_the_most_recent_day_first(summary):
    section = next(s for s in report_sections(summary) if s.title.startswith("Daily volume"))
    dates = [row[0] for row in section.rows]

    assert dates == sorted(dates, reverse=True)


def test_report_sections_survive_an_empty_dataset():
    """Rendering must not blow up between "database created" and "first file ingested"."""
    blank = {
        "total_log_count": 0,
        "level_counts": {},
        "error_percentage": 0.0,
        "most_common_error_messages": [],
        "most_active_users": [],
        "peak_logging_hours": [],
        "hourly_distribution": {},
        "daily_trend": {},
        "monthly_trend": {},
        "top_frequent_events": [],
        "average_logs_per_hour": 0.0,
        "response_time_stats": {},
        "status_code_distribution": {},
        "http_error_rate": 0.0,
        "top_endpoints": [],
        "slowest_endpoints": [],
        "exception_type_breakdown": [],
        "duplicate_summary": {"duplicate_lines_detected": 0, "unique_lines_inserted": 0},
        "malformed_summary": {
            "malformed_lines_detected": 0,
            "total_lines_processed": 0,
            "malformed_rate_pct": 0.0,
        },
        "statistical_summary": {},
    }

    assert kpi_tiles(blank)
    assert [section for section in report_sections(blank) if section.rows]
