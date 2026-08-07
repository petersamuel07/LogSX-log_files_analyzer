"""Regex-based parsing and validation of realistic production application log lines.

Expected primary line format (matches what
src/log_analyzer/utils/sample_generator.py writes to disk)::

    2026-08-07 14:32:10,512 [INFO] [pid:4821] [thread:MainThread] logger=app.controllers.auth_controller
    module=auth_service func=login trace_id=7f3c1a92e1b4 user_id=1042 session_id=sess_88ad3f
    ip=203.0.113.42 method=POST endpoint=/api/v1/login status=200 response_time_ms=142
    - User login successful

(shown wrapped for readability — it is one line in the actual file.)

Fields that don't apply to every log line — trace_id, user_id, session_id, ip,
method, endpoint, status, response_time_ms — use a literal ``-`` placeholder
when absent (the same convention Apache/Nginx access logs use), matching a
background job or an unauthenticated request that has no HTTP/user context.

ERROR/CRITICAL entries may be followed by a multi-line exception + stack
trace. Those lines don't match the primary pattern themselves; parse_file()
treats any non-matching line as a continuation of the log entry immediately
above it — the same strategy real multiline log shippers (e.g. Filebeat) use.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S,%f"

LOG_LINE_PATTERN = re.compile(
    r"""
    ^(?P<timestamp>\d{4}-\d{2}-\d{2}\ \d{2}:\d{2}:\d{2},\d{3})\s+
    \[(?P<level>[A-Z]+)\]\s+
    \[pid:(?P<pid>\d+)\]\s+
    \[thread:(?P<thread>[^\]]+)\]\s+
    logger=(?P<logger>\S+)\s+
    module=(?P<module>\S+)\s+
    func=(?P<function>\S+)\s+
    trace_id=(?P<trace_id>\S+)\s+
    user_id=(?P<user_id>\S+)\s+
    session_id=(?P<session_id>\S+)\s+
    ip=(?P<ip>\S+)\s+
    method=(?P<method>\S+)\s+
    endpoint=(?P<endpoint>\S+)\s+
    status=(?P<status>\S+)\s+
    response_time_ms=(?P<response_time_ms>\S+)\s+
    -\s+
    (?P<message>.+)$
    """,
    re.VERBOSE,
)

# Matches the conventional final line of a Python traceback, e.g.
# "ValueError: invalid credentials" — used to derive exception_type from a
# multi-line stack trace. Scans all continuation lines and keeps the LAST
# match, since that's where Python puts the exception that was actually raised.
_EXCEPTION_LINE_PATTERN = re.compile(r"^(?P<exc_type>[\w.]+(?:Error|Exception|Fault)):\s")


def _parse_optional(token: str) -> str | None:
    """Convert the '-' absent-value placeholder to None."""
    return None if token == "-" else token


def _extract_exception_type(continuation_lines: list[str]) -> str | None:
    exception_type = None
    for line in continuation_lines:
        match = _EXCEPTION_LINE_PATTERN.match(line)
        if match:
            exception_type = match.group("exc_type")
    return exception_type


@dataclass(frozen=True)
class ParsedLogEntry:
    """A single successfully parsed and validated log line (plus any attached stack trace)."""

    timestamp: datetime
    level: str
    pid: int
    thread: str
    logger: str
    module: str
    function: str
    trace_id: str | None
    user_id: str | None
    session_id: str | None
    ip_address: str | None
    http_method: str | None
    http_endpoint: str | None
    status_code: int | None
    response_time_ms: int | None
    message: str
    raw_line: str
    log_hash: str
    exception_type: str | None = None
    stack_trace: str | None = None

    @staticmethod
    def build_hash(raw_line: str) -> str:
        """Deterministic dedup key: SHA-256 of the raw primary log line.

        Hashing the whole line (rather than a hand-picked subset of fields)
        means any real difference between two lines makes them distinct
        entries, while two byte-identical log statements always dedup
        correctly — including the exact-duplicate lines the sample generator
        intentionally injects for testing.
        """
        return hashlib.sha256(raw_line.encode("utf-8")).hexdigest()


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

    def _build_entry(
        self, match: re.Match, source: str, line_number: int, raw_line: str
    ) -> ParsedLogEntry | None:
        """Turn a successful regex match into a ParsedLogEntry, validating level/timestamp/numerics.

        Only touches valid_lines/malformed_lines — callers are responsible for
        incrementing total_lines, since parse_line() and parse_file() count
        differently (parse_file must count blank-continuation-eligible lines
        before it knows whether they'll become a new entry or a continuation).
        """
        fields = match.groupdict()

        level = fields["level"].upper()
        if level not in VALID_LEVELS:
            self.stats.malformed_lines += 1
            logger.warning("Unknown log level %r at %s:%d -> %r", level, source, line_number, raw_line[:200])
            return None

        try:
            timestamp = datetime.strptime(fields["timestamp"], TIMESTAMP_FORMAT)
        except ValueError:
            self.stats.malformed_lines += 1
            logger.warning("Unparseable timestamp %r at %s:%d", fields["timestamp"], source, line_number)
            return None

        try:
            status_code = int(fields["status"]) if fields["status"] != "-" else None
            response_time_ms = int(fields["response_time_ms"]) if fields["response_time_ms"] != "-" else None
        except ValueError:
            self.stats.malformed_lines += 1
            logger.warning(
                "Non-numeric status/response_time at %s:%d -> %r", source, line_number, raw_line[:200]
            )
            return None

        self.stats.valid_lines += 1
        return ParsedLogEntry(
            timestamp=timestamp,
            level=level,
            pid=int(fields["pid"]),
            thread=fields["thread"],
            logger=fields["logger"],
            module=fields["module"],
            function=fields["function"],
            trace_id=_parse_optional(fields["trace_id"]),
            user_id=_parse_optional(fields["user_id"]),
            session_id=_parse_optional(fields["session_id"]),
            ip_address=_parse_optional(fields["ip"]),
            http_method=_parse_optional(fields["method"]),
            http_endpoint=_parse_optional(fields["endpoint"]),
            status_code=status_code,
            response_time_ms=response_time_ms,
            message=fields["message"].strip(),
            raw_line=raw_line,
            log_hash=ParsedLogEntry.build_hash(raw_line),
        )

    def parse_line(self, line: str, source: str = "<string>", line_number: int = 0) -> ParsedLogEntry | None:
        """Parse a single self-contained line — no stack-trace continuation support.

        Useful for quick one-off checks and unit tests. Full-file ingestion,
        which needs to attach stack traces to the entry they follow, should
        use parse_file() instead.
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

        return self._build_entry(match, source, line_number, stripped)

    def parse_file(self, file_path: Path) -> Iterator[ParsedLogEntry]:
        """Stream-parse a .log file, attaching stack-trace continuation lines to their entry.

        A line that doesn't match the primary pattern is treated as a
        continuation of the most recently matched entry only when that entry
        is ERROR/CRITICAL — the only levels that realistically emit a stack
        trace — mirroring how real multiline log shippers group exception
        output with the log line above it. A non-matching line following a
        DEBUG/INFO/WARNING entry is genuinely malformed, not a continuation,
        and is flagged as such rather than silently absorbed.
        """
        file_path = Path(file_path)
        logger.info("Parsing log file: %s", file_path)

        pending: ParsedLogEntry | None = None
        continuation: list[str] = []

        def finalize() -> ParsedLogEntry | None:
            nonlocal pending, continuation
            if pending is None:
                return None
            finished = pending
            if continuation:
                finished = replace(
                    finished,
                    stack_trace="\n".join(continuation),
                    exception_type=_extract_exception_type(continuation),
                )
            pending, continuation = None, []
            return finished

        with file_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, raw in enumerate(handle, start=1):
                stripped = raw.rstrip("\r\n")
                if not stripped.strip():
                    continue

                self.stats.total_lines += 1
                match = LOG_LINE_PATTERN.match(stripped)
                if match:
                    finished = finalize()
                    if finished is not None:
                        yield finished
                    pending = self._build_entry(match, file_path.name, line_number, stripped)
                elif pending is not None and pending.level in ("ERROR", "CRITICAL"):
                    continuation.append(stripped)
                else:
                    self.stats.malformed_lines += 1
                    logger.warning(
                        "Malformed log line at %s:%d -> %r", file_path.name, line_number, stripped[:200]
                    )

            finished = finalize()
            if finished is not None:
                yield finished
