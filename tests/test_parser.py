"""Unit tests for log_analyzer.parser.log_parser."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from log_analyzer.parser.log_parser import LogParser

VALID_HTTP_LINE = (
    "2026-08-07 14:32:10,512 [INFO] [pid:4821] [thread:MainThread] "
    "logger=app.controllers.auth_controller module=auth_service func=login "
    "trace_id=7f3c1a92e1b4 user_id=1042 session_id=sess_88ad3f ip=203.0.113.42 "
    "method=POST endpoint=/api/v1/login status=200 response_time_ms=142 "
    "- User login successful"
)

VALID_BACKGROUND_LINE = (
    "2026-08-07 03:00:00,001 [INFO] [pid:4821] [thread:Scheduler-1] "
    "logger=app.jobs.cleanup_job module=notification_service func=run_job "
    "trace_id=- user_id=- session_id=- ip=- method=- endpoint=- status=- response_time_ms=- "
    "- Nightly cleanup job started"
)

MALFORMED_LINE = "this is not a valid log line"


def test_parse_valid_http_line():
    parser = LogParser()
    entry = parser.parse_line(VALID_HTTP_LINE)

    assert entry is not None
    assert entry.level == "INFO"
    assert entry.pid == 4821
    assert entry.thread == "MainThread"
    assert entry.logger == "app.controllers.auth_controller"
    assert entry.module == "auth_service"
    assert entry.function == "login"
    assert entry.trace_id == "7f3c1a92e1b4"
    assert entry.user_id == "1042"
    assert entry.session_id == "sess_88ad3f"
    assert entry.ip_address == "203.0.113.42"
    assert entry.http_method == "POST"
    assert entry.http_endpoint == "/api/v1/login"
    assert entry.status_code == 200
    assert entry.response_time_ms == 142
    assert entry.message == "User login successful"
    assert entry.timestamp == datetime(2026, 8, 7, 14, 32, 10, 512000)


def test_parse_valid_background_line_has_none_optional_fields():
    parser = LogParser()
    entry = parser.parse_line(VALID_BACKGROUND_LINE)

    assert entry is not None
    assert entry.trace_id is None
    assert entry.user_id is None
    assert entry.session_id is None
    assert entry.ip_address is None
    assert entry.http_method is None
    assert entry.http_endpoint is None
    assert entry.status_code is None
    assert entry.response_time_ms is None


def test_parse_malformed_line_returns_none_and_counts():
    parser = LogParser()
    result = parser.parse_line(MALFORMED_LINE)

    assert result is None
    assert parser.stats.malformed_lines == 1
    assert parser.stats.valid_lines == 0


def test_parse_blank_line_is_ignored_not_counted():
    parser = LogParser()
    result = parser.parse_line("   \n")

    assert result is None
    assert parser.stats.total_lines == 0  # blank lines never increment stats


def test_unknown_level_is_malformed():
    parser = LogParser()
    line = VALID_HTTP_LINE.replace("[INFO]", "[TRACE]")
    result = parser.parse_line(line)

    assert result is None
    assert parser.stats.malformed_lines == 1


def test_non_numeric_status_is_malformed():
    parser = LogParser()
    line = VALID_HTTP_LINE.replace("status=200", "status=abc")
    result = parser.parse_line(line)

    assert result is None
    assert parser.stats.malformed_lines == 1


def test_hash_is_deterministic_for_identical_content():
    parser = LogParser()
    entry1 = parser.parse_line(VALID_HTTP_LINE)
    entry2 = parser.parse_line(VALID_HTTP_LINE)

    assert entry1.log_hash == entry2.log_hash


def test_hash_differs_for_different_messages():
    parser = LogParser()
    entry1 = parser.parse_line(VALID_HTTP_LINE)
    entry2 = parser.parse_line(VALID_HTTP_LINE.replace("User login successful", "User logout"))

    assert entry1.log_hash != entry2.log_hash


def test_parse_file_streams_valid_entries(tmp_path: Path):
    log_file = tmp_path / "test.log"
    log_file.write_text(f"{VALID_HTTP_LINE}\n{MALFORMED_LINE}\n{VALID_BACKGROUND_LINE}\n", encoding="utf-8")

    parser = LogParser()
    entries = list(parser.parse_file(log_file))

    assert len(entries) == 2
    assert parser.stats.total_lines == 3
    assert parser.stats.valid_lines == 2
    assert parser.stats.malformed_lines == 1


def test_parse_file_attaches_stack_trace_to_preceding_error(tmp_path: Path):
    error_line = VALID_HTTP_LINE.replace("[INFO]", "[ERROR]").replace(
        "User login successful", "Unhandled exception during login"
    )
    content = (
        f"{error_line}\n"
        'Traceback (most recent call last):\n'
        '  File "auth_controller.py", line 44, in authenticate\n'
        "    verify_password(user, password)\n"
        "ValueError: invalid credentials\n"
        f"{VALID_BACKGROUND_LINE}\n"
    )
    log_file = tmp_path / "error.log"
    log_file.write_text(content, encoding="utf-8")

    parser = LogParser()
    entries = list(parser.parse_file(log_file))

    assert len(entries) == 2
    error_entry, background_entry = entries

    assert error_entry.level == "ERROR"
    assert error_entry.exception_type == "ValueError"
    assert "Traceback" in error_entry.stack_trace
    assert "ValueError: invalid credentials" in error_entry.stack_trace

    assert background_entry.exception_type is None
    assert background_entry.stack_trace is None
    # stack trace lines belong to the error entry, not counted as separately malformed
    assert parser.stats.malformed_lines == 0


def test_continuation_line_with_no_pending_entry_is_malformed(tmp_path: Path):
    """A non-matching line with nothing valid before it has nowhere to attach."""
    log_file = tmp_path / "orphan.log"
    log_file.write_text("some orphan continuation line\n", encoding="utf-8")

    parser = LogParser()
    entries = list(parser.parse_file(log_file))

    assert entries == []
    assert parser.stats.malformed_lines == 1
