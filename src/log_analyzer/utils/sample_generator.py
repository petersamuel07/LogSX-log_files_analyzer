"""Synthetic .log file generator used to exercise the pipeline without real logs.

Produces lines in the exact format LogParser expects, plus a controlled
fraction of intentional duplicates and malformed lines so the dedup and
malformed-detection analytics have something real to report on.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from pathlib import Path

from tqdm import tqdm

logger = logging.getLogger(__name__)

USERS = ["alice", "bob", "charlie", "diana", "erin", "frank", "grace", "heidi"]

MODULES = [
    "auth_service",
    "payment_gateway",
    "order_service",
    "inventory_service",
    "notification_service",
    "api_gateway",
]

MESSAGES_BY_LEVEL = {
    "DEBUG": [
        "Cache lookup for key session_{n}",
        "Entering function process_request",
        "Query executed in {n}ms",
    ],
    "INFO": [
        "User login successful",
        "Order #{n} created",
        "Payment processed successfully",
        "Health check passed",
        "User logged out",
    ],
    "WARNING": [
        "High memory usage detected ({n}%)",
        "Retrying failed request (attempt {n})",
        "Deprecated API endpoint called",
        "Slow query detected ({n}ms)",
    ],
    "ERROR": [
        "Database connection failed",
        "Payment declined for order #{n}",
        "Null pointer exception encountered",
        "Timeout while calling external API",
        "Failed to authenticate user",
    ],
    "CRITICAL": [
        "Service unavailable - shutting down",
        "Out of memory - restarting worker",
        "Data corruption detected in table orders",
    ],
}

# Roughly mimics a business-hours traffic curve: low overnight, peaking mid-morning
# and mid-afternoon. This is what makes the "peak logging hours" analytic meaningful
# on generated data instead of a flat/uniform distribution.
HOUR_WEIGHTS = [
    1, 1, 1, 1, 1, 2,          # 00-05
    4, 8, 14, 18, 20, 18,      # 06-11
    16, 18, 20, 18, 14, 10,    # 12-17
    8, 6, 4, 3, 2, 1,          # 18-23
]

LEVEL_WEIGHTS = {"DEBUG": 15, "INFO": 55, "WARNING": 15, "ERROR": 12, "CRITICAL": 3}


def _random_timestamp(day: datetime, rng: random.Random) -> datetime:
    hour = rng.choices(range(24), weights=HOUR_WEIGHTS, k=1)[0]
    minute = rng.randrange(60)
    second = rng.randrange(60)
    millisecond = rng.randrange(1000)
    return day.replace(hour=hour, minute=minute, second=second, microsecond=millisecond * 1000)


def _random_valid_line(rng: random.Random, day: datetime) -> str:
    level = rng.choices(list(LEVEL_WEIGHTS), weights=list(LEVEL_WEIGHTS.values()), k=1)[0]
    user = rng.choice(USERS)
    module = rng.choice(MODULES)
    template = rng.choice(MESSAGES_BY_LEVEL[level])
    message = template.format(n=rng.randint(1, 9999))
    timestamp = _random_timestamp(day, rng)
    ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    return f"{ts_str} [{level}] user={user} module={module} - {message}"


def _random_malformed_line(rng: random.Random) -> str:
    variants = [
        "this line has no structure at all",
        f"[INFO] user={rng.choice(USERS)} module=api_gateway - missing timestamp",
        f"2026-13-40 25:99:99,999 [INFO] user={rng.choice(USERS)} module=api_gateway - invalid timestamp values",
        f"2026-08-07 10:00:00,000 [NOTALEVEL] user={rng.choice(USERS)} module=api_gateway - bad level",
        "",
    ]
    return rng.choice(variants)


def generate_sample_logs(
    output_path: Path,
    num_lines: int = 5000,
    days_back: int = 30,
    duplicate_rate: float = 0.03,
    malformed_rate: float = 0.02,
    seed: int | None = None,
) -> Path:
    """Generate a synthetic .log file with realistic, chronologically-sorted entries.

    Args:
        output_path: destination .log file path.
        num_lines: approximate number of lines to write (duplicates/malformed
            lines are added on top of this base count, not instead of it).
        days_back: spread generated timestamps across the last N days, so
            daily/monthly trend analytics have multiple buckets to show.
        duplicate_rate: fraction of valid lines that get an exact duplicate
            appended immediately after them (tests DB dedup logic).
        malformed_rate: fraction of extra malformed lines injected (tests
            malformed-line detection).
        seed: optional RNG seed for reproducible output (useful in tests).

    Returns:
        The resolved output path.
    """
    rng = random.Random(seed)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    today = datetime.now()
    lines: list[str] = []

    for _ in tqdm(range(num_lines), desc=f"Generating {output_path.name}", unit="line"):
        day = today - timedelta(days=rng.randint(0, days_back))
        line = _random_valid_line(rng, day)
        lines.append(line)
        if rng.random() < duplicate_rate:
            lines.append(line)  # exact duplicate, same content -> same hash

    malformed_count = int(num_lines * malformed_rate)
    for _ in range(malformed_count):
        lines.append(_random_malformed_line(rng))

    # Real log files are chronological, so sort valid lines by their timestamp
    # prefix. Malformed lines lack a usable prefix and naturally sort together,
    # which mirrors a real-world burst of bad log output from a misbehaving writer.
    lines_with_sort_key = []
    for line in lines:
        ts_key = line[:23] if len(line) >= 23 else ""
        lines_with_sort_key.append((ts_key, line))
    lines_with_sort_key.sort(key=lambda pair: pair[0])

    with output_path.open("w", encoding="utf-8") as handle:
        for _, line in lines_with_sort_key:
            handle.write(line + "\n")

    logger.info(
        "Generated sample log file %s (%d base lines, ~%d malformed injected)",
        output_path,
        num_lines,
        malformed_count,
    )
    return output_path
