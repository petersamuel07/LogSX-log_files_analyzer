"""Orchestrates reading .log files -> parsing -> validating -> de-duplicated DB writes.

This is the ETL "Load" stage: it turns a stream of ParsedLogEntry objects from
the parser into normalized rows across users/modules/log_levels/log_entries,
batching inserts for performance and relying on the log_hash UNIQUE constraint
(via PostgreSQL's ON CONFLICT DO NOTHING) so re-running ingestion on the same
file twice is always safe.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from tqdm import tqdm

from log_analyzer.database.connection import session_scope
from log_analyzer.models import IngestionRun, LogEntry, LogLevel, Module, User
from log_analyzer.parser.log_parser import LogParser, ParsedLogEntry

logger = logging.getLogger(__name__)


class IngestionService:
    """Batch-loads one or more .log files into PostgreSQL."""

    def __init__(self, batch_size: int = 1000) -> None:
        self.batch_size = batch_size
        self._level_cache: dict[str, int] = {}
        self._user_cache: dict[str, int] = {}
        self._module_cache: dict[str, int] = {}

    def _load_lookup_caches(self, session: Session) -> None:
        """Warm in-memory caches so repeated usernames/modules don't hit the DB per row."""
        self._level_cache = {row.name: row.id for row in session.query(LogLevel).all()}
        self._user_cache = {row.username: row.id for row in session.query(User).all()}
        self._module_cache = {row.name: row.id for row in session.query(Module).all()}

    def _get_or_create_user(self, session: Session, username: str) -> int:
        if username in self._user_cache:
            return self._user_cache[username]
        user = session.query(User).filter_by(username=username).one_or_none()
        if user is None:
            user = User(username=username)
            session.add(user)
            session.flush()  # assigns user.id without committing the whole transaction
        self._user_cache[username] = user.id
        return user.id

    def _get_or_create_module(self, session: Session, module_name: str) -> int:
        if module_name in self._module_cache:
            return self._module_cache[module_name]
        module = session.query(Module).filter_by(name=module_name).one_or_none()
        if module is None:
            module = Module(name=module_name)
            session.add(module)
            session.flush()
        self._module_cache[module_name] = module.id
        return module.id

    def _flush_batch(self, session: Session, batch: list[ParsedLogEntry]) -> tuple[int, int]:
        """Insert a batch, skipping rows whose log_hash already exists.

        Returns (inserted_count, duplicate_count). PostgreSQL's ON CONFLICT DO
        NOTHING also correctly skips duplicate hashes appearing more than once
        *within the same batch*, not just ones already committed from a prior run.
        """
        if not batch:
            return 0, 0

        rows = []
        for entry in batch:
            level_id = self._level_cache.get(entry.level)
            if level_id is None:
                # Should never happen: parser only accepts VALID_LEVELS, which
                # database.init_db.seed_log_levels() pre-populates in full.
                raise ValueError(f"Unseeded log level {entry.level!r} — run initialize_database() first.")

            rows.append(
                {
                    "log_hash": entry.log_hash,
                    "timestamp": entry.timestamp,
                    "message": entry.message,
                    "user_id": self._get_or_create_user(session, entry.user),
                    "level_id": level_id,
                    "module_id": self._get_or_create_module(session, entry.module),
                }
            )

        stmt = pg_insert(LogEntry).values(rows).on_conflict_do_nothing(index_elements=["log_hash"])
        result = session.execute(stmt)
        session.flush()

        inserted = result.rowcount if result.rowcount and result.rowcount > 0 else 0
        duplicates = len(rows) - inserted
        return inserted, duplicates

    def ingest_file(self, file_path: Path) -> dict:
        """Parse and load a single .log file. Returns a summary stats dict."""
        file_path = Path(file_path)
        logger.info("Starting ingestion of %s", file_path)

        parser = LogParser()
        inserted_total = 0
        duplicate_total = 0
        batch: list[ParsedLogEntry] = []

        with session_scope() as session:
            self._load_lookup_caches(session)

            for entry in tqdm(parser.parse_file(file_path), desc=f"Ingesting {file_path.name}", unit="line"):
                batch.append(entry)
                if len(batch) >= self.batch_size:
                    inserted, duplicates = self._flush_batch(session, batch)
                    inserted_total += inserted
                    duplicate_total += duplicates
                    batch.clear()

            inserted, duplicates = self._flush_batch(session, batch)
            inserted_total += inserted
            duplicate_total += duplicates

            run = IngestionRun(
                source_file=str(file_path),
                total_lines=parser.stats.total_lines,
                valid_lines=parser.stats.valid_lines,
                malformed_lines=parser.stats.malformed_lines,
                inserted_lines=inserted_total,
                duplicate_lines=duplicate_total,
            )
            session.add(run)

        summary = {
            "source_file": str(file_path),
            "total_lines": parser.stats.total_lines,
            "valid_lines": parser.stats.valid_lines,
            "malformed_lines": parser.stats.malformed_lines,
            "inserted_lines": inserted_total,
            "duplicate_lines": duplicate_total,
        }
        logger.info("Finished ingesting %s: %s", file_path.name, summary)
        return summary

    def ingest_directory(self, directory: Path, pattern: str = "*.log") -> list[dict]:
        """Ingest every file matching `pattern` in `directory` (non-recursive)."""
        directory = Path(directory)
        files = sorted(directory.glob(pattern))
        if not files:
            logger.warning("No files matching %r found in %s", pattern, directory)
            return []

        summaries = []
        for file_path in files:
            try:
                summaries.append(self.ingest_file(file_path))
            except Exception:
                logger.exception("Failed to ingest %s — continuing with remaining files.", file_path)
        return summaries
