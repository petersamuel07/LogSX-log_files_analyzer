"""Unit tests for log_analyzer.parser.log_parser."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from log_analyzer.parser.log_parser import LogParser

VALID_LINE = "2026-08-07 14:32:10,512 [INFO] user=alice module=auth_service - User login successful"
MALFORMED_LINE = "this is not a valid log line"


def test_parse_valid_line():
    parser = LogParser()
    entry = parser.parse_line(VALID_LINE)

    assert entry is not None
    assert entry.level == "INFO"
    assert entry.user == "alice"
    assert entry.module == "auth_service"
    assert entry.message == "User login successful"
    assert entry.timestamp == datetime(2026, 8, 7, 14, 32, 10, 512000)


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
    line = "2026-08-07 14:32:10,512 [TRACE] user=alice module=auth_service - some message"
    result = parser.parse_line(line)

    assert result is None
    assert parser.stats.malformed_lines == 1


def test_hash_is_deterministic_for_identical_content():
    parser = LogParser()
    entry1 = parser.parse_line(VALID_LINE)
    entry2 = parser.parse_line(VALID_LINE)

    assert entry1.log_hash == entry2.log_hash


def test_hash_differs_for_different_messages():
    parser = LogParser()
    entry1 = parser.parse_line(VALID_LINE)
    entry2 = parser.parse_line(VALID_LINE.replace("User login successful", "User logout"))

    assert entry1.log_hash != entry2.log_hash


def test_parse_file_streams_valid_entries(tmp_path: Path):
    log_file = tmp_path / "test.log"
    log_file.write_text(f"{VALID_LINE}\n{MALFORMED_LINE}\n{VALID_LINE}\n", encoding="utf-8")

    parser = LogParser()
    entries = list(parser.parse_file(log_file))

    assert len(entries) == 2
    assert parser.stats.total_lines == 3
    assert parser.stats.valid_lines == 2
    assert parser.stats.malformed_lines == 1
