-- LogSX — Log Files Analyzer — PostgreSQL schema
-- Mirrors src/log_analyzer/models/*.py exactly. The Python application creates
-- this schema automatically via SQLAlchemy (see database/init_db.py); this file
-- exists so the schema can be reviewed, run manually in pgAdmin, or version
-- controlled independently of the ORM.

-- Run this first, from psql/pgAdmin connected to the default "postgres" database
-- (CREATE DATABASE cannot run inside a transaction block or from within the
-- database being created):
--
--     CREATE DATABASE log_analyzer;
--
-- Then connect to log_analyzer and run everything below.

-- ============================================================
-- Lookup tables
-- ============================================================

CREATE TABLE IF NOT EXISTS log_levels (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    id       SERIAL PRIMARY KEY,
    username VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS modules (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS loggers (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS ix_users_username ON users (username);
CREATE INDEX IF NOT EXISTS ix_modules_name ON modules (name);
CREATE INDEX IF NOT EXISTS ix_loggers_name ON loggers (name);
CREATE INDEX IF NOT EXISTS ix_log_levels_name ON log_levels (name);

-- ============================================================
-- Fact table — modeled on a realistic production application log line
-- ============================================================

CREATE TABLE IF NOT EXISTS log_entries (
    id          SERIAL PRIMARY KEY,
    log_hash    CHAR(64) NOT NULL UNIQUE,       -- SHA-256 of the raw primary log line
    "timestamp" TIMESTAMP NOT NULL,

    -- Process / origin
    pid           INTEGER NOT NULL,
    thread_name   VARCHAR(100) NOT NULL,
    function_name VARCHAR(150) NOT NULL,

    -- Distributed tracing / request context — nullable: not every log line is request-scoped
    trace_id         VARCHAR(64),
    session_id       VARCHAR(64),
    ip_address       VARCHAR(45),                -- 45 = max IPv6 text length
    http_method      VARCHAR(10),
    http_endpoint    VARCHAR(255),
    status_code      INTEGER,
    response_time_ms INTEGER,

    -- Error detail — nullable: only present on exception-raising ERROR/CRITICAL entries
    exception_type VARCHAR(255),
    stack_trace    TEXT,

    message    TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    user_id   INTEGER REFERENCES users (id),           -- nullable: unauthenticated/background logs
    level_id  INTEGER NOT NULL REFERENCES log_levels (id),
    module_id INTEGER NOT NULL REFERENCES modules (id),
    logger_id INTEGER NOT NULL REFERENCES loggers (id)
);

CREATE INDEX IF NOT EXISTS ix_log_entries_log_hash ON log_entries (log_hash);
CREATE INDEX IF NOT EXISTS ix_log_entries_timestamp ON log_entries ("timestamp");
CREATE INDEX IF NOT EXISTS ix_log_entries_user_id ON log_entries (user_id);
CREATE INDEX IF NOT EXISTS ix_log_entries_level_id ON log_entries (level_id);
CREATE INDEX IF NOT EXISTS ix_log_entries_module_id ON log_entries (module_id);
CREATE INDEX IF NOT EXISTS ix_log_entries_logger_id ON log_entries (logger_id);
CREATE INDEX IF NOT EXISTS ix_log_entries_trace_id ON log_entries (trace_id);
CREATE INDEX IF NOT EXISTS ix_log_entries_http_endpoint ON log_entries (http_endpoint);
CREATE INDEX IF NOT EXISTS ix_log_entries_status_code ON log_entries (status_code);

-- Composite index for the most common analytics query shape: filtering/grouping
-- by level within a timestamp range (e.g. "ERROR counts per day").
CREATE INDEX IF NOT EXISTS ix_log_entries_timestamp_level
    ON log_entries ("timestamp", level_id);

-- ============================================================
-- Audit table — one row per ingestion run, backs duplicate/malformed analytics
-- ============================================================

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id              SERIAL PRIMARY KEY,
    source_file     VARCHAR(500) NOT NULL,
    run_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    total_lines     INTEGER NOT NULL DEFAULT 0,
    valid_lines     INTEGER NOT NULL DEFAULT 0,
    malformed_lines INTEGER NOT NULL DEFAULT 0,
    inserted_lines  INTEGER NOT NULL DEFAULT 0,
    duplicate_lines INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- Seed data: the five fixed log severities
-- ============================================================

INSERT INTO log_levels (name)
VALUES ('DEBUG'), ('INFO'), ('WARNING'), ('ERROR'), ('CRITICAL')
ON CONFLICT (name) DO NOTHING;
