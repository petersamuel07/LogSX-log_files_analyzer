"""Audit table recording the outcome of each ingestion run, one row per source file.

Backs the "duplicate log detection" and "missing/malformed log detection"
analytics features without having to re-parse files at report time.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from log_analyzer.models.base import Base


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_file: Mapped[str] = mapped_column(String(500), nullable=False)
    run_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    total_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    malformed_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"IngestionRun(id={self.id}, source_file={self.source_file!r})"
