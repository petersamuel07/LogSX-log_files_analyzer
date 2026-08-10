"""The central fact table: one row per parsed, validated, de-duplicated log line.

Modeled on a realistic production application log line: process/thread info,
logger/module/function origin, distributed-tracing fields (trace_id), request
context (user/session/IP/HTTP method+endpoint/status/response time), and an
optional exception + stack trace. Not every log line has every field — a
background job has no HTTP context, and an unauthenticated request has no
user — so those columns are nullable rather than forcing empty-string values.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from log_analyzer.models.base import Base

if TYPE_CHECKING:
    from log_analyzer.models.log_level import LogLevel
    from log_analyzer.models.logger import Logger
    from log_analyzer.models.module import Module
    from log_analyzer.models.user import User


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(primary_key=True)

    # SHA-256 of the raw primary log line (everything up to, but not including,
    # any stack-trace continuation lines). A UNIQUE constraint on this column is
    # what makes re-ingesting the same file, or overlapping files, a safe no-op.
    log_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    # --- Process / origin ---
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    thread_name: Mapped[str] = mapped_column(String(100), nullable=False)
    function_name: Mapped[str] = mapped_column(String(150), nullable=False)

    # --- Distributed tracing / request context (nullable: not every log line is request-scoped) ---
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # 45 = max IPv6 length
    http_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    http_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Error detail (nullable: only present on exception-raising ERROR/CRITICAL entries) ---
    exception_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)

    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # user_id is nullable: unauthenticated requests and background jobs have no user.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("log_levels.id"), nullable=False, index=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"), nullable=False, index=True)
    logger_id: Mapped[int] = mapped_column(ForeignKey("loggers.id"), nullable=False, index=True)

    user: Mapped[User | None] = relationship(back_populates="log_entries")
    level: Mapped[LogLevel] = relationship(back_populates="log_entries")
    module: Mapped[Module] = relationship(back_populates="log_entries")
    logger: Mapped[Logger] = relationship(back_populates="log_entries")

    __table_args__ = (
        # Composite index accelerates the most common analytics query shape:
        # "counts/trends of a given level over a timestamp range".
        Index("ix_log_entries_timestamp_level", "timestamp", "level_id"),
    )

    def __repr__(self) -> str:
        return f"LogEntry(id={self.id}, timestamp={self.timestamp}, level_id={self.level_id})"
