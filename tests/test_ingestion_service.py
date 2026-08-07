"""Integration tests for IngestionService against a real PostgreSQL database.

These use ON CONFLICT DO NOTHING, a PostgreSQL-specific construct SQLite
cannot emulate, so they need the database configured in .env to be reachable.
If it isn't, the whole module is skipped rather than failing, so the rest of
the suite stays runnable without a live PostgreSQL instance.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from log_analyzer.database import get_engine, initialize_database
from log_analyzer.services import IngestionService


def _postgres_available() -> bool:
    try:
        with get_engine().connect():
            return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="PostgreSQL not reachable")


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema():
    initialize_database()


def test_ingest_file_is_idempotent(tmp_path: Path):
    """Ingesting the same file twice must insert once and skip the second time.

    The message includes a fresh UUID so its content hash is guaranteed novel
    on every test run — this is a real, persistent database (not a throwaway
    fixture), so reusing fixed content would see leftover rows from a
    previous run and misreport them as pre-existing duplicates.
    """
    unique_token = uuid.uuid4().hex
    log_file = tmp_path / "idempotency_test.log"
    log_file.write_text(
        f"2026-01-01 10:00:00,000 [INFO] user=pytest_idempotency_user module=pytest_module"
        f" - pytest idempotency check {unique_token}\n",
        encoding="utf-8",
    )

    service = IngestionService()
    first = service.ingest_file(log_file)
    second = service.ingest_file(log_file)

    assert first["inserted_lines"] == 1
    assert first["duplicate_lines"] == 0
    assert second["inserted_lines"] == 0
    assert second["duplicate_lines"] == 1


def test_ingest_file_skips_malformed_lines(tmp_path: Path):
    unique_token = uuid.uuid4().hex
    log_file = tmp_path / "malformed_test.log"
    log_file.write_text(
        f"2026-01-01 10:00:00,000 [INFO] user=pytest_malformed_user module=pytest_module"
        f" - a perfectly valid line {unique_token}\n"
        "this line is not in the expected format at all\n",
        encoding="utf-8",
    )

    summary = IngestionService().ingest_file(log_file)

    assert summary["valid_lines"] == 1
    assert summary["malformed_lines"] == 1
    assert summary["inserted_lines"] == 1
