"""Unit tests for log_analyzer.utils.sample_generator."""

from __future__ import annotations

from pathlib import Path

from log_analyzer.parser.log_parser import LogParser
from log_analyzer.utils.sample_generator import generate_sample_logs


def test_generate_sample_logs_creates_file(tmp_path: Path):
    output = tmp_path / "sample.log"
    result_path = generate_sample_logs(output, num_lines=200, seed=1)

    assert result_path == output
    assert output.exists()
    assert output.stat().st_size > 0


def test_generate_sample_logs_is_reproducible_with_seed(tmp_path: Path):
    out1 = generate_sample_logs(tmp_path / "a.log", num_lines=100, seed=42)
    out2 = generate_sample_logs(tmp_path / "b.log", num_lines=100, seed=42)

    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")


def test_generated_logs_are_parseable_when_malformed_rate_is_zero(tmp_path: Path):
    output = generate_sample_logs(tmp_path / "sample.log", num_lines=500, seed=5, malformed_rate=0.0)

    parser = LogParser()
    list(parser.parse_file(output))

    assert parser.stats.malformed_lines == 0
    assert parser.stats.valid_lines > 0


def test_generate_sample_logs_injects_malformed_lines(tmp_path: Path):
    output = generate_sample_logs(tmp_path / "sample.log", num_lines=500, seed=5, malformed_rate=0.1)

    parser = LogParser()
    list(parser.parse_file(output))

    assert parser.stats.malformed_lines > 0


def test_generate_sample_logs_injects_duplicates(tmp_path: Path):
    output = generate_sample_logs(
        tmp_path / "sample.log", num_lines=500, seed=5, duplicate_rate=0.5, malformed_rate=0.0
    )

    parser = LogParser()
    entries = list(parser.parse_file(output))
    unique_hashes = {entry.log_hash for entry in entries}

    # duplicate_rate=0.5 guarantees at least some repeated hashes among 500 lines.
    assert len(unique_hashes) < len(entries)
