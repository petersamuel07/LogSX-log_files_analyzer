"""Unit tests for log_analyzer.analytics.log_analytics, run against SQLite (no live Postgres needed)."""

from __future__ import annotations

from log_analyzer.analytics import LogAnalytics


def test_total_log_count(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    assert analytics.total_log_count() == 6


def test_level_counts(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    counts = analytics.level_counts()
    assert counts["INFO"] == 3
    assert counts["ERROR"] == 2
    assert counts["WARNING"] == 1


def test_error_percentage(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    assert analytics.error_percentage() == round(2 / 6 * 100, 2)


def test_most_active_users_excludes_unauthenticated_entries(sqlite_engine_with_data):
    """The background entry has no user; value_counts() must not count it as a phantom user."""
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    top = analytics.most_active_users(top_n=5)
    assert top[0]["user"] == "alice"
    assert top[0]["count"] == 3
    assert sum(r["count"] for r in top) == 5  # 6 total rows minus 1 unauthenticated background row


def test_most_common_error_messages(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    top_errors = analytics.most_common_error_messages(top_n=5)
    assert top_errors[0]["message"] == "Failed to authenticate user"
    assert top_errors[0]["count"] == 2


def test_daily_trend_buckets_by_date(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    daily = analytics.daily_trend()
    assert daily["2026-01-01"] == 3
    assert daily["2026-01-02"] == 3


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


def test_response_time_stats_excludes_non_http_entries(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    stats = analytics.response_time_stats()

    assert stats["sample_count"] == 5  # 6 rows minus the 1 background row with no response time
    assert stats["min_ms"] == 15.0
    assert stats["max_ms"] == 950.0


def test_status_code_distribution(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    distribution = analytics.status_code_distribution()

    assert distribution["2xx"] == 2  # two 200s
    assert distribution["4xx"] == 1  # one 429
    assert distribution["5xx"] == 2  # two 500s


def test_http_error_rate(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    # 3 of 5 HTTP-context entries are >= 400 (one 429, two 500s)
    assert analytics.http_error_rate() == 60.0


def test_top_endpoints(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    top = analytics.top_endpoints(top_n=5)

    assert top[0]["endpoint"] == "/api/v1/login"
    assert top[0]["count"] == 3


def test_slowest_endpoints_with_low_min_samples(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    slowest = analytics.slowest_endpoints(top_n=5, min_samples=1)

    assert slowest[0]["endpoint"] == "/api/v1/login"
    assert slowest[0]["avg_response_time_ms"] > slowest[1]["avg_response_time_ms"]


def test_exception_type_breakdown(sqlite_engine_with_data):
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    breakdown = analytics.exception_type_breakdown()

    assert breakdown[0]["exception_type"] == "ValueError"
    assert breakdown[0]["count"] == 2


def test_generate_summary_is_json_shaped(sqlite_engine_with_data):
    """generate_summary()'s output must be built entirely from native Python types."""
    analytics = LogAnalytics(engine=sqlite_engine_with_data)
    summary = analytics.generate_summary()

    assert isinstance(summary["total_log_count"], int)
    assert isinstance(summary["error_percentage"], float)
    assert isinstance(summary["level_counts"], dict)
    assert isinstance(summary["most_active_users"], list)
    assert isinstance(summary["response_time_stats"], dict)
    assert isinstance(summary["status_code_distribution"], dict)
    assert isinstance(summary["exception_type_breakdown"], list)
