"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from log_analyzer.models import Base, IngestionRun, LogEntry, LogLevel, Module, User


@pytest.fixture()
def sqlite_engine_with_data():
    """An in-memory SQLite engine pre-populated with a small, deterministic log dataset.

    LogAnalytics' queries are plain ANSI SQL (no PostgreSQL-only syntax), so
    it can be exercised against SQLite here without a live PostgreSQL
    connection — keeping these tests fast and fully CI-portable.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        levels = {name: LogLevel(name=name) for name in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]}
        users = {name: User(username=name) for name in ["alice", "bob"]}
        modules = {name: Module(name=name) for name in ["auth_service", "api_gateway"]}
        session.add_all([*levels.values(), *users.values(), *modules.values()])
        session.flush()

        base_time = datetime(2026, 1, 1, 9, 0, 0)
        rows = [
            ("INFO", "alice", "auth_service", "User login successful", base_time),
            ("INFO", "bob", "api_gateway", "Health check passed", base_time + timedelta(hours=1)),
            ("ERROR", "alice", "auth_service", "Failed to authenticate user", base_time + timedelta(hours=2)),
            ("ERROR", "alice", "auth_service", "Failed to authenticate user", base_time + timedelta(days=1)),
            ("WARNING", "bob", "api_gateway", "Slow query detected", base_time + timedelta(days=1, hours=3)),
        ]
        for i, (level, user, module, message, timestamp) in enumerate(rows):
            session.add(
                LogEntry(
                    log_hash=f"hash-{i}",
                    timestamp=timestamp,
                    message=message,
                    user_id=users[user].id,
                    level_id=levels[level].id,
                    module_id=modules[module].id,
                )
            )
        session.add(
            IngestionRun(
                source_file="test.log",
                total_lines=10,
                valid_lines=5,
                malformed_lines=2,
                inserted_lines=5,
                duplicate_lines=3,
            )
        )
        session.commit()

    return engine
