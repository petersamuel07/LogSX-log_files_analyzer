"""CSV/JSON report exporters — turns a LogAnalytics summary dict into files on disk."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class ReportExporter:
    """Writes an analytics summary to JSON (full detail) and CSV (per-metric tables)."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_summary_json(self, summary: dict[str, Any], filename: str = "analytics_summary.json") -> Path:
        """Write the complete nested summary as a single JSON file."""
        path = self.output_dir / filename
        with path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, default=str)
        logger.info("Wrote JSON report: %s", path)
        return path

    def _export_dict_as_csv(self, data: dict, columns: tuple[str, str], filename: str) -> Path:
        df = pd.DataFrame(list(data.items()), columns=list(columns))
        path = self.output_dir / filename
        df.to_csv(path, index=False)
        logger.info("Wrote CSV report: %s", path)
        return path

    def _export_records_as_csv(self, records: list[dict], filename: str) -> Path:
        df = pd.DataFrame(records)
        path = self.output_dir / filename
        df.to_csv(path, index=False)
        logger.info("Wrote CSV report: %s", path)
        return path

    def export_all(self, summary: dict[str, Any]) -> dict[str, Path]:
        """Export the full report set: one JSON summary plus one CSV per tabular metric.

        Returns a dict mapping report name -> written file path, so the CLI can
        print exactly what was produced.
        """
        outputs: dict[str, Path] = {}

        outputs["summary_json"] = self.export_summary_json(summary)

        outputs["level_counts_csv"] = self._export_dict_as_csv(
            summary["level_counts"], ("level", "count"), "level_counts.csv"
        )
        outputs["daily_trend_csv"] = self._export_dict_as_csv(
            summary["daily_trend"], ("date", "count"), "daily_trend.csv"
        )
        outputs["monthly_trend_csv"] = self._export_dict_as_csv(
            summary["monthly_trend"], ("month", "count"), "monthly_trend.csv"
        )
        outputs["top_errors_csv"] = self._export_records_as_csv(
            summary["most_common_error_messages"], "top_error_messages.csv"
        )
        outputs["top_users_csv"] = self._export_records_as_csv(
            summary["most_active_users"], "most_active_users.csv"
        )
        outputs["top_events_csv"] = self._export_records_as_csv(
            summary["top_frequent_events"], "top_frequent_events.csv"
        )

        logger.info("Exported %d report files to %s", len(outputs), self.output_dir)
        return outputs
