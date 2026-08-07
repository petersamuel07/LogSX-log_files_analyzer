"""Database bootstrap: create the database itself, then all tables/indexes.

SQLAlchemy's create_engine/metadata.create_all can create tables inside a
database, but it cannot create the database itself — a connection has to
already be pointed at *some* existing database to run any SQL. We connect
to PostgreSQL's always-present "postgres" maintenance database with raw
psycopg2 to issue CREATE DATABASE, then hand off to SQLAlchemy for the schema.
"""

from __future__ import annotations

import logging

import psycopg2
from psycopg2 import sql as pg_sql

from log_analyzer.config import get_settings
from log_analyzer.database.connection import get_engine, session_scope
from log_analyzer.models import Base, LogLevel
from log_analyzer.parser.log_parser import VALID_LEVELS

logger = logging.getLogger(__name__)


def create_database_if_not_exists() -> None:
    """Connect to the 'postgres' maintenance DB and CREATE DATABASE if missing."""
    settings = get_settings()
    conn = psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        dbname="postgres",
    )
    # DDL statements like CREATE DATABASE cannot run inside a transaction block.
    conn.autocommit = True
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.db_name,))
            already_exists = cursor.fetchone() is not None

            if already_exists:
                logger.info("Database %r already exists, skipping creation.", settings.db_name)
            else:
                cursor.execute(
                    pg_sql.SQL("CREATE DATABASE {}").format(pg_sql.Identifier(settings.db_name))
                )
                logger.info("Created database %r.", settings.db_name)
    finally:
        conn.close()


def create_tables() -> None:
    """Create every table/index declared by the ORM models, if not already present."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("Ensured all tables and indexes exist.")


def seed_log_levels() -> None:
    """Pre-populate the log_levels lookup table with the five fixed severities.

    Seeding upfront (rather than get-or-create during ingestion) keeps the
    lookup table free of race conditions when ingestion runs concurrently,
    and guarantees the FK target always exists.
    """
    with session_scope() as session:
        existing = {row.name for row in session.query(LogLevel).all()}
        missing = VALID_LEVELS - existing
        for level_name in sorted(missing):
            session.add(LogLevel(name=level_name))
        if missing:
            logger.info("Seeded log_levels with: %s", ", ".join(sorted(missing)))


def initialize_database() -> None:
    """Full bootstrap: create DB, create tables, seed lookup data. Idempotent."""
    create_database_if_not_exists()
    create_tables()
    seed_log_levels()
