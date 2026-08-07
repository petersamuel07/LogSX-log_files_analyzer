"""The central fact table: one row per parsed, validated, de-duplicated log line."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from log_analyzer.models.base import Base

if TYPE_CHECKING:
    from log_analyzer.models.log_level import LogLevel
    from log_analyzer.models.module import Module
    from log_analyzer.models.user import User


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(primary_key=True)

    # SHA-256 of (timestamp, level, user, module, message). A UNIQUE constraint
    # on this column is what makes re-ingesting the same log file, or two files
    # that overlap, a safe no-op instead of duplicate rows.
    log_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("log_levels.id"), nullable=False, index=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"), nullable=False, index=True)

    user: Mapped["User"] = relationship(back_populates="log_entries")
    level: Mapped["LogLevel"] = relationship(back_populates="log_entries")
    module: Mapped["Module"] = relationship(back_populates="log_entries")

    __table_args__ = (
        # Composite index accelerates the most common analytics query shape:
        # "counts/trends of a given level over a timestamp range".
        Index("ix_log_entries_timestamp_level", "timestamp", "level_id"),
    )

    def __repr__(self) -> str:
        return f"LogEntry(id={self.id}, timestamp={self.timestamp}, level_id={self.level_id})"
