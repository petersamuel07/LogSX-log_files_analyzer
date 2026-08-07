"""CLI entry point for the Log File Analyzer.

How to use
----------
1. Create/activate a virtual environment and install dependencies:

       python -m venv venv
       .\\venv\\Scripts\\Activate.ps1        (Windows PowerShell)
       pip install -r requirements.txt
       pip install -e .

2. Copy .env.example to .env and set your real PostgreSQL credentials.

3. Typical workflow:

       python main.py init-db
       python main.py generate-sample --num-lines 5000
       python main.py pipeline data/sample/sample_5000.log

   Or run each stage independently:

       python main.py ingest data/logs                # file or directory
       python main.py analyze
       python main.py report
       python main.py charts

Run `python main.py -h` or `python main.py <command> -h` for full option lists.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from log_analyzer.config import get_settings, setup_logging

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="log-analyzer",
        description="Parse, store, and analyze application log files backed by PostgreSQL.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override LOG_LEVEL from .env for this run.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create the database, tables, indexes, and seed log levels.")

    gen = subparsers.add_parser("generate-sample", help="Generate a synthetic .log file for testing.")
    gen.add_argument("--output", type=Path, default=None, help="Output path (default: data/sample/sample_<n>.log)")
    gen.add_argument("--num-lines", type=int, default=5000)
    gen.add_argument("--days-back", type=int, default=30)
    gen.add_argument("--seed", type=int, default=None)

    ingest = subparsers.add_parser("ingest", help="Parse and load .log file(s) into PostgreSQL.")
    ingest.add_argument("path", type=Path, help="A .log file or a directory of .log files.")
    ingest.add_argument("--pattern", default="*.log", help="Glob pattern when path is a directory.")
    ingest.add_argument("--batch-size", type=int, default=1000)

    analyze = subparsers.add_parser("analyze", help="Print the full analytics summary to the console.")
    analyze.add_argument("--top-n", type=int, default=10)

    report = subparsers.add_parser("report", help="Export CSV/JSON analytics reports.")
    report.add_argument("--top-n", type=int, default=10)

    subparsers.add_parser("charts", help="Generate all Matplotlib charts.")

    pipeline = subparsers.add_parser("pipeline", help="Run ingest -> analyze -> report -> charts in one pass.")
    pipeline.add_argument("path", type=Path, help="A .log file or a directory of .log files to ingest first.")
    pipeline.add_argument("--pattern", default="*.log")
    pipeline.add_argument("--batch-size", type=int, default=1000)
    pipeline.add_argument("--top-n", type=int, default=10)

    return parser


def _print_ingestion_summary(summary: dict[str, Any]) -> None:
    print(f"\n{summary['source_file']}")
    print(f"  total lines:      {summary['total_lines']}")
    print(f"  valid lines:      {summary['valid_lines']}")
    print(f"  malformed lines:  {summary['malformed_lines']}")
    print(f"  inserted:         {summary['inserted_lines']}")
    print(f"  duplicates:       {summary['duplicate_lines']}")


def _print_analytics_summary(summary: dict[str, Any]) -> None:
    print("\n=== Log Analytics Summary ===")
    print(f"Total logs:        {summary['total_log_count']}")
    print(f"Error percentage:  {summary['error_percentage']}%")
    print(f"Avg logs/hour:     {summary['average_logs_per_hour']}")

    print("\nLevel counts:")
    for level, count in summary["level_counts"].items():
        print(f"  {level:10s} {count}")

    print("\nTop error messages:")
    for rec in summary["most_common_error_messages"][:5]:
        print(f"  {rec['count']:5d}  {rec['message']}")

    print("\nMost active users:")
    for rec in summary["most_active_users"][:5]:
        print(f"  {rec['count']:5d}  {rec['user']}")

    print("\nPeak logging hours:")
    for rec in summary["peak_logging_hours"]:
        print(f"  hour {rec['hour']:02d}:00  -> {rec['count']} logs")

    stats = summary["statistical_summary"]
    if stats:
        print("\nStatistical summary (daily volume):")
        print(
            f"  mean={stats['mean_logs_per_day']}  median={stats['median_logs_per_day']}  "
            f"std={stats['std_dev_logs_per_day']}  skew={stats['skewness']}  kurtosis={stats['kurtosis']}"
        )
        if stats["outlier_days"]:
            print(f"  outlier days: {', '.join(stats['outlier_days'])}")

    dup = summary["duplicate_summary"]
    mal = summary["malformed_summary"]
    print(f"\nDuplicates skipped (all runs):  {dup['duplicate_lines_detected']}")
    print(f"Malformed lines (all runs):     {mal['malformed_lines_detected']} ({mal['malformed_rate_pct']}%)")


def cmd_init_db(args: argparse.Namespace) -> None:
    from log_analyzer.database import initialize_database

    initialize_database()
    print("Database initialized.")


def cmd_generate_sample(args: argparse.Namespace) -> None:
    from log_analyzer.utils import generate_sample_logs

    settings = get_settings()
    output = args.output or (settings.log_input_dir.parent / "sample" / f"sample_{args.num_lines}.log")
    path = generate_sample_logs(
        output, num_lines=args.num_lines, days_back=args.days_back, seed=args.seed
    )
    print(f"Generated sample log file: {path}")


def cmd_ingest(args: argparse.Namespace) -> None:
    from log_analyzer.services import IngestionService

    service = IngestionService(batch_size=args.batch_size)
    if args.path.is_dir():
        for summary in service.ingest_directory(args.path, pattern=args.pattern):
            _print_ingestion_summary(summary)
    else:
        _print_ingestion_summary(service.ingest_file(args.path))


def cmd_analyze(args: argparse.Namespace) -> None:
    from log_analyzer.analytics import LogAnalytics

    analytics = LogAnalytics()
    _print_analytics_summary(analytics.generate_summary(top_n=args.top_n))


def cmd_report(args: argparse.Namespace) -> None:
    from log_analyzer.analytics import LogAnalytics
    from log_analyzer.reports import ReportExporter

    settings = get_settings()
    analytics = LogAnalytics()
    summary = analytics.generate_summary(top_n=args.top_n)
    outputs = ReportExporter(settings.reports_output_dir).export_all(summary)

    print("\nReports written:")
    for name, path in outputs.items():
        print(f"  {name:20s} {path}")


def cmd_charts(args: argparse.Namespace) -> None:
    from log_analyzer.analytics import LogAnalytics
    from log_analyzer.visualization import ChartGenerator

    settings = get_settings()
    analytics = LogAnalytics()
    paths = ChartGenerator(analytics, settings.charts_output_dir).generate_all()

    print("\nCharts written:")
    for path in paths:
        print(f"  {path}")


def cmd_pipeline(args: argparse.Namespace) -> None:
    from log_analyzer.analytics import LogAnalytics
    from log_analyzer.reports import ReportExporter
    from log_analyzer.services import IngestionService
    from log_analyzer.visualization import ChartGenerator

    settings = get_settings()

    print("=== Step 1/4: Ingesting logs ===")
    service = IngestionService(batch_size=args.batch_size)
    if args.path.is_dir():
        for summary in service.ingest_directory(args.path, pattern=args.pattern):
            _print_ingestion_summary(summary)
    else:
        _print_ingestion_summary(service.ingest_file(args.path))

    print("\n=== Step 2/4: Computing analytics ===")
    analytics = LogAnalytics()
    summary = analytics.generate_summary(top_n=args.top_n)
    _print_analytics_summary(summary)

    print("\n=== Step 3/4: Exporting reports ===")
    for name, path in ReportExporter(settings.reports_output_dir).export_all(summary).items():
        print(f"  {name:20s} {path}")

    print("\n=== Step 4/4: Generating charts ===")
    for path in ChartGenerator(analytics, settings.charts_output_dir).generate_all():
        print(f"  {path}")

    print("\nPipeline complete.")


_COMMAND_HANDLERS = {
    "init-db": cmd_init_db,
    "generate-sample": cmd_generate_sample,
    "ingest": cmd_ingest,
    "analyze": cmd_analyze,
    "report": cmd_report,
    "charts": cmd_charts,
    "pipeline": cmd_pipeline,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging(args.log_level or settings.log_level)

    try:
        _COMMAND_HANDLERS[args.command](args)
    except Exception as exc:
        logger.exception("Command %r failed", args.command)
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
