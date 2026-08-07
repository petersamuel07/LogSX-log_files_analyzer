"""Pandas/NumPy/SciPy analytics computed over the log_entries table.

LogAnalytics loads the fully joined dataset (log_entries + users + log_levels
+ modules + loggers) into a single Pandas DataFrame once per instance, then
every analytic method is a cheap in-memory Pandas/NumPy/SciPy operation on
that DataFrame rather than a fresh SQL round-trip.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from sqlalchemy import Engine

from log_analyzer.database.connection import get_engine

logger = logging.getLogger(__name__)

_JOINED_QUERY = """
    SELECT
        le.id,
        le."timestamp" AS timestamp,
        le.message,
        le.pid,
        le.thread_name,
        le.function_name,
        le.trace_id,
        le.session_id,
        le.ip_address,
        le.http_method,
        le.http_endpoint,
        le.status_code,
        le.response_time_ms,
        le.exception_type,
        le.stack_trace,
        ll.name AS level,
        u.username AS user,
        m.name AS module,
        lg.name AS logger
    FROM log_entries le
    JOIN log_levels ll ON le.level_id = ll.id
    LEFT JOIN users u ON le.user_id = u.id
    JOIN modules m ON le.module_id = m.id
    JOIN loggers lg ON le.logger_id = lg.id
"""


def _series_to_records(series: pd.Series, key_name: str, value_name: str = "count") -> list[dict[str, Any]]:
    """Convert a value_counts()-style Series into JSON-serializable records.

    Pandas/NumPy scalar types (numpy.int64, Timestamp, ...) are not natively
    JSON-serializable, so every value is cast to a plain Python type here —
    this is the single place that boundary conversion happens.
    """
    return [
        {key_name: str(index), value_name: int(value)}
        for index, value in series.items()
    ]


class LogAnalytics:
    """Computes the full analytics feature set over the log_entries table."""

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self._df: pd.DataFrame | None = None

    @property
    def df(self) -> pd.DataFrame:
        """The joined log dataset, loaded from PostgreSQL on first access and cached."""
        if self._df is None:
            self._df = pd.read_sql(_JOINED_QUERY, self.engine, parse_dates=["timestamp"])
            logger.info("Loaded %d log entries into DataFrame for analysis.", len(self._df))
        return self._df

    # ------------------------------------------------------------------
    # Basic counts
    # ------------------------------------------------------------------

    def total_log_count(self) -> int:
        return int(len(self.df))

    def level_counts(self) -> dict[str, int]:
        """INFO/WARNING/ERROR/etc. counts."""
        return self.df["level"].value_counts().astype(int).to_dict()

    def error_percentage(self) -> float:
        """Percentage of all logs at ERROR severity (CRITICAL excluded — reported separately)."""
        total = self.total_log_count()
        if total == 0:
            return 0.0
        error_count = int((self.df["level"] == "ERROR").sum())
        return round(error_count / total * 100, 2)

    # ------------------------------------------------------------------
    # Top-N breakdowns
    # ------------------------------------------------------------------

    def most_common_error_messages(self, top_n: int = 10) -> list[dict[str, Any]]:
        error_df = self.df[self.df["level"].isin(["ERROR", "CRITICAL"])]
        counts = error_df["message"].value_counts().head(top_n)
        return _series_to_records(counts, key_name="message")

    def most_active_users(self, top_n: int = 10) -> list[dict[str, Any]]:
        counts = self.df["user"].value_counts().head(top_n)
        return _series_to_records(counts, key_name="user")

    def top_frequent_events(self, top_n: int = 10) -> list[dict[str, Any]]:
        counts = self.df["message"].value_counts().head(top_n)
        return _series_to_records(counts, key_name="message")

    # ------------------------------------------------------------------
    # Time-based trends
    # ------------------------------------------------------------------

    def hourly_distribution(self) -> dict[int, int]:
        """Log volume for each hour of the day (0-23), summed across all dates."""
        counts = self.df["timestamp"].dt.hour.value_counts().sort_index()
        return {int(hour): int(count) for hour, count in counts.items()}

    def peak_logging_hours(self, top_n: int = 5) -> list[dict[str, Any]]:
        hourly = pd.Series(self.hourly_distribution()).sort_values(ascending=False).head(top_n)
        return [{"hour": int(hour), "count": int(count)} for hour, count in hourly.items()]

    def daily_trend(self) -> dict[str, int]:
        counts = self.df["timestamp"].dt.date.value_counts().sort_index()
        return {str(day): int(count) for day, count in counts.items()}

    def monthly_trend(self) -> dict[str, int]:
        periods = self.df["timestamp"].dt.to_period("M")
        counts = periods.value_counts().sort_index()
        return {str(period): int(count) for period, count in counts.items()}

    def average_logs_per_hour(self) -> float:
        """Average throughput: total logs / number of hours spanned by the dataset.

        Uses the actual min/max timestamp range rather than a fixed 24-hour
        window, so it reflects real throughput regardless of how many days
        of logs are loaded.
        """
        if self.df.empty:
            return 0.0
        span = self.df["timestamp"].max() - self.df["timestamp"].min()
        hours = max(span.total_seconds() / 3600, 1.0)  # avoid div-by-zero on single-instant datasets
        return round(self.total_log_count() / hours, 2)

    # ------------------------------------------------------------------
    # HTTP / request-context metrics (only present on request-scoped log lines)
    # ------------------------------------------------------------------

    def response_time_stats(self) -> dict[str, Any]:
        """Latency percentiles (NumPy) over every log line with a recorded response time.

        Background/system logs have no response_time_ms (they're not tied to
        an HTTP request), so this is computed only over the request-scoped subset.
        """
        response_times = self.df["response_time_ms"].dropna()
        if response_times.empty:
            return {}

        values = response_times.to_numpy(dtype=float)
        return {
            "sample_count": int(len(values)),
            "mean_ms": round(float(np.mean(values)), 2),
            "median_ms": round(float(np.median(values)), 2),
            "p90_ms": round(float(np.percentile(values, 90)), 2),
            "p95_ms": round(float(np.percentile(values, 95)), 2),
            "p99_ms": round(float(np.percentile(values, 99)), 2),
            "min_ms": round(float(np.min(values)), 2),
            "max_ms": round(float(np.max(values)), 2),
        }

    def status_code_distribution(self) -> dict[str, int]:
        """HTTP status codes bucketed into 2xx/3xx/4xx/5xx classes."""
        statuses = self.df["status_code"].dropna()
        if statuses.empty:
            return {}
        class_labels = {200: "2xx", 300: "3xx", 400: "4xx", 500: "5xx"}
        classes = (statuses.astype(int) // 100 * 100).map(class_labels)
        counts = classes.value_counts()
        return {str(label): int(count) for label, count in counts.items()}

    def http_error_rate(self) -> float:
        """Percentage of HTTP requests returning 4xx/5xx — distinct from the log-level error_percentage()."""
        statuses = self.df["status_code"].dropna()
        if statuses.empty:
            return 0.0
        error_count = int((statuses >= 400).sum())
        return round(error_count / len(statuses) * 100, 2)

    def top_endpoints(self, top_n: int = 10) -> list[dict[str, Any]]:
        """Most frequently hit HTTP endpoints."""
        endpoints = self.df["http_endpoint"].dropna()
        counts = endpoints.value_counts().head(top_n)
        return _series_to_records(counts, key_name="endpoint")

    def slowest_endpoints(self, top_n: int = 10, min_samples: int = 5) -> list[dict[str, Any]]:
        """Endpoints with the highest average response time (min_samples avoids noise from rare routes)."""
        http_df = self.df.dropna(subset=["http_endpoint", "response_time_ms"])
        if http_df.empty:
            return []

        grouped = http_df.groupby("http_endpoint")["response_time_ms"].agg(["mean", "count"])
        grouped = grouped[grouped["count"] >= min_samples].sort_values("mean", ascending=False).head(top_n)
        return [
            {
                "endpoint": str(endpoint),
                "avg_response_time_ms": round(float(row["mean"]), 2),
                "sample_count": int(row["count"]),
            }
            for endpoint, row in grouped.iterrows()
        ]

    def exception_type_breakdown(self, top_n: int = 10) -> list[dict[str, Any]]:
        """Most common exception types among ERROR/CRITICAL entries that carried a stack trace."""
        exceptions = self.df["exception_type"].dropna()
        counts = exceptions.value_counts().head(top_n)
        return _series_to_records(counts, key_name="exception_type")

    # ------------------------------------------------------------------
    # Ingestion-run-backed quality metrics (duplicate / malformed detection)
    # ------------------------------------------------------------------

    def duplicate_summary(self) -> dict[str, Any]:
        """Duplicate lines skipped during ingestion, aggregated across all runs."""
        with self.engine.connect() as conn:
            runs = pd.read_sql("SELECT * FROM ingestion_runs", conn)
        total_duplicates = int(runs["duplicate_lines"].sum()) if not runs.empty else 0
        total_inserted = int(runs["inserted_lines"].sum()) if not runs.empty else 0
        return {"duplicate_lines_detected": total_duplicates, "unique_lines_inserted": total_inserted}

    def malformed_summary(self) -> dict[str, Any]:
        """Malformed/unparseable lines skipped during ingestion, aggregated across all runs."""
        with self.engine.connect() as conn:
            runs = pd.read_sql("SELECT * FROM ingestion_runs", conn)
        if runs.empty:
            return {"malformed_lines_detected": 0, "total_lines_processed": 0, "malformed_rate_pct": 0.0}
        total_malformed = int(runs["malformed_lines"].sum())
        total_processed = int(runs["total_lines"].sum())
        rate = round(total_malformed / total_processed * 100, 2) if total_processed else 0.0
        return {
            "malformed_lines_detected": total_malformed,
            "total_lines_processed": total_processed,
            "malformed_rate_pct": rate,
        }

    # ------------------------------------------------------------------
    # NumPy / SciPy statistical summary
    # ------------------------------------------------------------------

    def statistical_summary(self) -> dict[str, Any]:
        """Descriptive + shape statistics over the daily log-volume distribution.

        Uses NumPy for the core descriptive stats and SciPy for skewness,
        kurtosis, and z-score-based outlier-day detection — days whose log
        volume deviates more than 2 standard deviations from the mean.
        """
        daily = self.daily_trend()
        if not daily:
            return {}

        counts = np.array(list(daily.values()), dtype=float)
        days = list(daily.keys())

        result: dict[str, Any] = {
            "mean_logs_per_day": round(float(np.mean(counts)), 2),
            "median_logs_per_day": round(float(np.median(counts)), 2),
            "min_logs_per_day": int(np.min(counts)),
            "max_logs_per_day": int(np.max(counts)),
        }

        if len(counts) > 1:
            std = float(np.std(counts, ddof=1))
            result["std_dev_logs_per_day"] = round(std, 2)
            result["variance_logs_per_day"] = round(float(np.var(counts, ddof=1)), 2)
        else:
            std = 0.0
            result["std_dev_logs_per_day"] = 0.0
            result["variance_logs_per_day"] = 0.0

        if len(counts) > 2:
            result["skewness"] = round(float(scipy_stats.skew(counts)), 3)
            result["kurtosis"] = round(float(scipy_stats.kurtosis(counts)), 3)
        else:
            result["skewness"] = 0.0
            result["kurtosis"] = 0.0

        if std > 0:
            z_scores = scipy_stats.zscore(counts)
            outlier_days = [days[i] for i, z in enumerate(z_scores) if abs(z) > 2]
        else:
            outlier_days = []
        result["outlier_days"] = outlier_days

        return result

    # ------------------------------------------------------------------
    # Everything combined — the single source of truth for reports/exports
    # ------------------------------------------------------------------

    def generate_summary(self, top_n: int = 10) -> dict[str, Any]:
        """Build the complete analytics summary consumed by the CSV/JSON exporters."""
        return {
            "total_log_count": self.total_log_count(),
            "level_counts": self.level_counts(),
            "error_percentage": self.error_percentage(),
            "most_common_error_messages": self.most_common_error_messages(top_n),
            "most_active_users": self.most_active_users(top_n),
            "peak_logging_hours": self.peak_logging_hours(5),
            "hourly_distribution": self.hourly_distribution(),
            "daily_trend": self.daily_trend(),
            "monthly_trend": self.monthly_trend(),
            "top_frequent_events": self.top_frequent_events(top_n),
            "average_logs_per_hour": self.average_logs_per_hour(),
            "response_time_stats": self.response_time_stats(),
            "status_code_distribution": self.status_code_distribution(),
            "http_error_rate": self.http_error_rate(),
            "top_endpoints": self.top_endpoints(top_n),
            "slowest_endpoints": self.slowest_endpoints(top_n),
            "exception_type_breakdown": self.exception_type_breakdown(top_n),
            "duplicate_summary": self.duplicate_summary(),
            "malformed_summary": self.malformed_summary(),
            "statistical_summary": self.statistical_summary(),
        }
