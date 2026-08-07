"""Human-readable text formatting for ingestion/analytics summaries.

Shared by the CLI (main.py) and the Tkinter GUI so both present identical
output built from the same summary dicts, instead of each re-implementing
its own formatting.
"""

from __future__ import annotations

from typing import Any


def format_ingestion_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"{summary['source_file']}",
        f"  total lines:      {summary['total_lines']}",
        f"  valid lines:      {summary['valid_lines']}",
        f"  malformed lines:  {summary['malformed_lines']}",
        f"  inserted:         {summary['inserted_lines']}",
        f"  duplicates:       {summary['duplicate_lines']}",
    ]
    return "\n".join(lines)


def format_analytics_summary(summary: dict[str, Any]) -> str:
    lines = [
        "=== Log Analytics Summary ===",
        f"Total logs:        {summary['total_log_count']}",
        f"Error percentage:  {summary['error_percentage']}%",
        f"Avg logs/hour:     {summary['average_logs_per_hour']}",
        "",
        "Level counts:",
    ]
    for level, count in summary["level_counts"].items():
        lines.append(f"  {level:10s} {count}")

    lines.append("")
    lines.append("Top error messages:")
    for rec in summary["most_common_error_messages"][:5]:
        lines.append(f"  {rec['count']:5d}  {rec['message']}")

    lines.append("")
    lines.append("Most active users:")
    for rec in summary["most_active_users"][:5]:
        lines.append(f"  {rec['count']:5d}  {rec['user']}")

    lines.append("")
    lines.append("Peak logging hours:")
    for rec in summary["peak_logging_hours"]:
        lines.append(f"  hour {rec['hour']:02d}:00  -> {rec['count']} logs")

    response_stats = summary.get("response_time_stats")
    if response_stats:
        lines.append("")
        lines.append("Response time (ms):")
        lines.append(
            f"  mean={response_stats['mean_ms']}  p90={response_stats['p90_ms']}  "
            f"p95={response_stats['p95_ms']}  p99={response_stats['p99_ms']}"
        )

    status_dist = summary.get("status_code_distribution")
    if status_dist:
        lines.append("")
        lines.append("HTTP status codes:")
        lines.append("  " + "  ".join(f"{cls}={count}" for cls, count in status_dist.items()))
        lines.append(f"  HTTP error rate: {summary.get('http_error_rate', 0.0)}%")

    stats = summary["statistical_summary"]
    if stats:
        lines.append("")
        lines.append("Statistical summary (daily volume):")
        lines.append(
            f"  mean={stats['mean_logs_per_day']}  median={stats['median_logs_per_day']}  "
            f"std={stats['std_dev_logs_per_day']}  skew={stats['skewness']}  kurtosis={stats['kurtosis']}"
        )
        if stats["outlier_days"]:
            lines.append(f"  outlier days: {', '.join(stats['outlier_days'])}")

    dup = summary["duplicate_summary"]
    mal = summary["malformed_summary"]
    lines.append("")
    lines.append(f"Duplicates skipped (all runs):  {dup['duplicate_lines_detected']}")
    lines.append(f"Malformed lines (all runs):     {mal['malformed_lines_detected']} ({mal['malformed_rate_pct']}%)")

    return "\n".join(lines)
