"""Unit tests for log_analyzer.analytics.log_analytics, run against SQLite (no live Postgres needed)."""

from __future__ import annotations

from log_analyzer.analytics import LogAnalytics


def test_total_log_count(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    assert analytics.total_log_count() == 5


def test_level_counts(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    counts = analytics.level_counts()
    assert counts["ERROR"] == 2
    assert counts["INFO"] == 2
    assert counts["WARNING"] == 1


def test_error_percentage(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    assert analytics.error_percentage() == 40.0  # 2 ERROR / 5 total * 100


def test_most_active_users(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    top = analytics.most_active_users(top_n=5)
    assert top[0]["user"] == "alice"
    assert top[0]["count"] == 3


def test_most_common_error_messages(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    top_errors = analytics.most_common_error_messages(top_n=5)
    assert top_errors[0]["message"] == "Failed to authenticate user"
    assert top_errors[0]["count"] == 2


def test_daily_trend_buckets_by_date(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    daily = analytics.daily_trend()
    assert daily["2026-01-01"] == 3
    assert daily["2026-01-02"] == 2


def test_duplicate_and_malformed_summary(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    dup = analytics.duplicate_summary()
    mal = analytics.malformed_summary()

    assert dup["duplicate_lines_detected"] == 3
    assert mal["malformed_lines_detected"] == 2
    assert mal["total_lines_processed"] == 10


def test_statistical_summary_has_expected_keys(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    stats = analytics.statistical_summary()

    assert "mean_logs_per_day" in stats
    assert "std_dev_logs_per_day" in stats
    assert "skewness" in stats
    assert "outlier_days" in stats


def test_generate_summary_is_json_shaped(sqlite_engine_with_data):
    """generate_summary()'s output must be built entirely from native Python types."""
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    summary = analytics.generate_summary()

    assert isinstance(summary["total_log_count"], int)
    assert isinstance(summary["error_percentage"], float)
    assert isinstance(summary["level_counts"], dict)
    assert isinstance(summary["most_active_users"], list)
