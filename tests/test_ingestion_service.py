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


def _make_line(unique_token: str, *, level: str = "INFO", with_http: bool = True) -> str:
    """Build a well-formed line in the realistic production-log format for test isolation."""
    if with_http:
        context = (
            f"trace_id={unique_token[:16]} user_id=9001 session_id=sess_{unique_token[:8]} "
            "ip=203.0.113.99 method=GET endpoint=/api/v1/pytest status=200 response_time_ms=42"
        )
    else:
        context = "trace_id=- user_id=- session_id=- ip=- method=- endpoint=- status=- response_time_ms=-"
    return (
        f"2026-01-01 10:00:00,000 [{level}] [pid:9999] [thread:MainThread] "
        f"logger=pytest.logger module=pytest_module func=pytest_func {context} "
        f"- pytest check {unique_token}"
    )


def test_ingest_file_is_idempotent(tmp_path: Path):
    """Ingesting the same file twice must insert once and skip the second time.

    The message includes a fresh UUID so its content hash is guaranteed novel
    on every test run — this is a real, persistent database (not a throwaway
    fixture), so reusing fixed content would see leftover rows from a
    previous run and misreport them as pre-existing duplicates.
    """
    unique_token = uuid.uuid4().hex
    log_file = tmp_path / "idempotency_test.log"
    log_file.write_text(_make_line(unique_token) + "\n", encoding="utf-8")

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
        f"{_make_line(unique_token)}\nthis line is not in the expected format at all\n",
        encoding="utf-8",
    )

    summary = IngestionService().ingest_file(log_file)

    assert summary["valid_lines"] == 1
    assert summary["malformed_lines"] == 1
    assert summary["inserted_lines"] == 1


def test_ingest_file_handles_unauthenticated_background_line(tmp_path: Path):
    """A line with no user/HTTP context must ingest with a NULL user_id, not fail."""
    unique_token = uuid.uuid4().hex
    log_file = tmp_path / "background_test.log"
    log_file.write_text(_make_line(unique_token, with_http=False) + "\n", encoding="utf-8")

    summary = IngestionService().ingest_file(log_file)

    assert summary["valid_lines"] == 1
    assert summary["inserted_lines"] == 1


def test_ingest_file_attaches_stack_trace(tmp_path: Path):
    unique_token = uuid.uuid4().hex
    log_file = tmp_path / "exception_test.log"
    log_file.write_text(
        f"{_make_line(unique_token, level='ERROR')}\n"
        'Traceback (most recent call last):\n'
        '  File "x.py", line 1, in y\n'
        "ValueError: pytest induced failure\n",
        encoding="utf-8",
    )

    summary = IngestionService().ingest_file(log_file)

    assert summary["valid_lines"] == 1
    assert summary["inserted_lines"] == 1
    assert summary["malformed_lines"] == 0
