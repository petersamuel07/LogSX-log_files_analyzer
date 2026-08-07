"""Regex-based parsing and validation of application log lines.

Expected log line format (matches what generate_sample_logs() produces and
what src/log_analyzer/utils/sample_generator.py writes to disk)::

    2026-08-07 14:32:10,512 [INFO] user=alice module=auth_service - User login successful

Field breakdown:
    timestamp : "YYYY-MM-DD HH:MM:SS,mmm"  (millisecond precision, like Python's
                 default logging.Formatter datefmt)
    level     : one of DEBUG, INFO, WARNING, ERROR, CRITICAL
    user      : the username that triggered the event
    module    : the application module/component that emitted the log
    message   : free-text event description
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S,%f"

LOG_LINE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+"
    r"\[(?P<level>[A-Z]+)\]\s+"
    r"user=(?P<user>\S+)\s+"
    r"module=(?P<module>\S+)\s+-\s+"
    r"(?P<message>.+)$"
)


@dataclass(frozen=True)
class ParsedLogEntry:
    """A single successfully parsed and validated log line."""

    timestamp: datetime
    level: str
    user: str
    module: str
    message: str
    raw_line: str
    log_hash: str

    @staticmethod
    def build_hash(timestamp: datetime, level: str, user: str, module: str, message: str) -> str:
        """Deterministic content hash used as the database dedup key.

        Two log lines with identical timestamp/level/user/module/message are
        considered the same event, even if they appear in different files or
        were re-ingested after a crash — this is what makes ingestion idempotent.
        """
        payload = f"{timestamp.isoformat()}|{level}|{user}|{module}|{message}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ParseStats:
    """Running counters for a parse pass, used for the malformed-log analytics feature."""

    total_lines: int = 0
    valid_lines: int = 0
    malformed_lines: int = 0

    def as_dict(self) -> dict:
        return {
            "total_lines": self.total_lines,
            "valid_lines": self.valid_lines,
            "malformed_lines": self.malformed_lines,
        }


class LogParser:
    """Parses raw .log files/lines into validated ParsedLogEntry records."""

    def __init__(self) -> None:
        self.stats = ParseStats()

    def parse_line(self, line: str, source: str = "<string>", line_number: int = 0) -> ParsedLogEntry | None:
        """Parse a single log line.

        Returns None (and logs a warning) if the line is blank or does not
        match the expected format — malformed lines are skipped, never fatal,
        so one bad line in a 1M-line file does not abort the whole ingestion.
        """
        stripped = line.strip()
        if not stripped:
            return None

        self.stats.total_lines += 1
        match = LOG_LINE_PATTERN.match(stripped)
        if not match:
            self.stats.malformed_lines += 1
            logger.warning("Malformed log line at %s:%d -> %r", source, line_number, stripped[:200])
            return None

        fields = match.groupdict()

        level = fields["level"].upper()
        if level not in VALID_LEVELS:
            self.stats.malformed_lines += 1
            logger.warning(
                "Unknown log level %r at %s:%d -> %r", level, source, line_number, stripped[:200]
            )
            return None

        try:
            timestamp = datetime.strptime(fields["timestamp"], TIMESTAMP_FORMAT)
        except ValueError:
            self.stats.malformed_lines += 1
            logger.warning(
                "Unparseable timestamp %r at %s:%d", fields["timestamp"], source, line_number
            )
            return None

        user = fields["user"]
        module = fields["module"]
        message = fields["message"].strip()

        self.stats.valid_lines += 1
        return ParsedLogEntry(
            timestamp=timestamp,
            level=level,
            user=user,
            module=module,
            message=message,
            raw_line=stripped,
            log_hash=ParsedLogEntry.build_hash(timestamp, level, user, module, message),
        )

    def parse_file(self, file_path: Path) -> Iterator[ParsedLogEntry]:
        """Stream-parse a .log file line by line.

        Uses a generator rather than returning a list so multi-gigabyte log
        files can be ingested without loading the entire file into memory.
        """
        file_path = Path(file_path)
        logger.info("Parsing log file: %s", file_path)
        with file_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                entry = self.parse_line(line, source=file_path.name, line_number=line_number)
                if entry is not None:
                    yield entry
