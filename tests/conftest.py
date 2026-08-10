"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from log_analyzer.models import Base, IngestionRun, LogEntry, Logger, LogLevel, Module, User


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
        loggers = {
            name: Logger(name=name)
            for name in ["app.controllers.auth_controller", "app.gateways.api_gateway"]
        }
        session.add_all([*levels.values(), *users.values(), *modules.values(), *loggers.values()])
        session.flush()

        base_time = datetime(2026, 1, 1, 9, 0, 0)
        # (level, user, module, logger, message, timestamp, status_code, response_time_ms, exception_type, endpoint)
        rows = [
            ("INFO", "alice", "auth_service", "app.controllers.auth_controller",
             "User login successful", base_time, 200, 120, None, "/api/v1/login"),
            ("INFO", "bob", "api_gateway", "app.gateways.api_gateway",
             "Health check passed", base_time + timedelta(hours=1), 200, 15, None, "/api/v1/health"),
            ("ERROR", "alice", "auth_service", "app.controllers.auth_controller",
             "Failed to authenticate user", base_time + timedelta(hours=2), 500, 900, "ValueError", "/api/v1/login"),
            ("ERROR", "alice", "auth_service", "app.controllers.auth_controller",
             "Failed to authenticate user", base_time + timedelta(days=1), 500, 950, "ValueError", "/api/v1/login"),
            ("WARNING", "bob", "api_gateway", "app.gateways.api_gateway",
             "Slow query detected", base_time + timedelta(days=1, hours=3), 429, 600, None, "/api/v1/health"),
            # one background/non-HTTP entry: no user, no status, no response time, no endpoint
            ("INFO", None, "auth_service", "app.controllers.auth_controller",
             "Nightly cleanup job started", base_time + timedelta(days=1, hours=5), None, None, None, None),
        ]
        for i, row in enumerate(rows):
            (level, user, module, logger_name, message,
             timestamp, status, resp_ms, exc_type, endpoint) = row
            session.add(
                LogEntry(
                    log_hash=f"hash-{i}",
                    timestamp=timestamp,
                    pid=1000 + i,
                    thread_name="MainThread",
                    function_name="handle",
                    http_endpoint=endpoint,
                    status_code=status,
                    response_time_ms=resp_ms,
                    exception_type=exc_type,
                    stack_trace="Traceback...\nValueError: bad" if exc_type else None,
                    message=message,
                    user_id=users[user].id if user else None,
                    level_id=levels[level].id,
                    module_id=modules[module].id,
                    logger_id=loggers[logger_name].id,
                )
            )
        session.add(
            IngestionRun(
                source_file="test.log",
                total_lines=10,
                valid_lines=6,
                malformed_lines=2,
                inserted_lines=6,
                duplicate_lines=3,
            )
        )
        session.commit()

    return engine
