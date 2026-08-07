"""Synthetic .log file generator used to exercise the pipeline without real logs.

Produces lines in the realistic production-log format LogParser expects
(process/thread, logger/module/function, trace/user/session/IP, HTTP
method/endpoint/status/response-time, and occasional exception + stack
traces), plus a controlled fraction of intentional duplicates and malformed
lines so the dedup and malformed-detection analytics have something real to
report on.

Log entries are generated as "blocks" — a primary line plus any stack-trace
continuation lines that belong to it — and sorted as whole blocks by
timestamp, so a multi-line exception never gets separated from the log line
it belongs to.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from pathlib import Path

from tqdm import tqdm

logger = logging.getLogger(__name__)

USER_IDS = ["1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008"]

MODULES = [
    "auth_service",
    "payment_gateway",
    "order_service",
    "inventory_service",
    "notification_service",
    "api_gateway",
]

LOGGERS_BY_MODULE = {
    "auth_service": ["app.services.auth_service", "app.controllers.auth_controller"],
    "payment_gateway": ["app.services.payment_service", "app.gateways.payment_gateway"],
    "order_service": ["app.services.order_service", "app.controllers.order_controller"],
    "inventory_service": ["app.services.inventory_service"],
    "notification_service": ["app.services.notification_service", "app.jobs.notification_job"],
    "api_gateway": ["app.gateways.api_gateway", "app.middleware.request_logger"],
}

FUNCTIONS_BY_MODULE = {
    "auth_service": ["login", "logout", "validate_token", "refresh_session", "authenticate"],
    "payment_gateway": ["process_payment", "refund", "validate_card", "capture_payment"],
    "order_service": ["create_order", "update_order", "cancel_order", "get_order_status"],
    "inventory_service": ["check_stock", "reserve_item", "update_inventory", "restock"],
    "notification_service": ["send_email", "send_sms", "push_notification", "run_job"],
    "api_gateway": ["route_request", "authenticate_request", "rate_limit_check", "log_request"],
}

HTTP_ENDPOINTS_BY_MODULE = {
    "auth_service": ["/api/v1/login", "/api/v1/logout", "/api/v1/refresh"],
    "payment_gateway": ["/api/v1/payments", "/api/v1/payments/refund"],
    "order_service": ["/api/v1/orders", "/api/v1/orders/{id}"],
    "inventory_service": ["/api/v1/inventory", "/api/v1/inventory/{sku}"],
    "notification_service": ["/api/v1/notifications"],
    "api_gateway": ["/api/v1/health", "/api/v1/status"],
}

HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]
THREADS = ["MainThread", "Thread-1", "Thread-2", "Thread-3", "Thread-7", "Thread-12", "Worker-1", "Worker-2", "Scheduler-1"]
PIDS = [4821, 4822, 5011, 5012]

# Status codes plausible for each log level — a WARNING is far more likely to
# carry a 4xx than a 5xx, an ERROR the reverse, DEBUG/INFO mostly succeed.
STATUS_CHOICES_BY_LEVEL = {
    "DEBUG": ([200, 204], [80, 20]),
    "INFO": ([200, 201, 204, 304], [65, 15, 12, 8]),
    "WARNING": ([400, 401, 403, 404, 429], [25, 25, 15, 20, 15]),
    "ERROR": ([500, 502, 503, 400], [45, 20, 20, 15]),
    "CRITICAL": ([500, 503], [60, 40]),
}

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

# (exception_type, message, stack frames). exception_type must end in
# Error/Exception/Fault to match LogParser's _EXCEPTION_LINE_PATTERN.
EXCEPTION_TEMPLATES = [
    ("ValueError", "invalid credentials", ['File "auth_controller.py", line 44, in authenticate', "verify_password(user, password)"]),
    ("ConnectionError", "could not connect to database", ['File "db.py", line 12, in connect', "conn = psycopg2.connect(**params)"]),
    ("TimeoutError", "external API call timed out", ['File "payment_gateway.py", line 88, in charge_card', "response = requests.post(url, timeout=5)"]),
    ("KeyError", "'user_id'", ['File "order_service.py", line 33, in create_order', 'user_id = payload["user_id"]']),
    ("PermissionError", "insufficient privileges", ['File "auth_controller.py", line 60, in authorize', "check_permission(user, resource)"]),
]


def _random_timestamp(day: datetime, rng: random.Random) -> datetime:
    hour = rng.choices(range(24), weights=HOUR_WEIGHTS, k=1)[0]
    minute = rng.randrange(60)
    second = rng.randrange(60)
    millisecond = rng.randrange(1000)
    return day.replace(hour=hour, minute=minute, second=second, microsecond=millisecond * 1000)


_HEX_DIGITS = "0123456789abcdef"


def _random_hex(rng: random.Random, length: int) -> str:
    """Seeded stand-in for uuid4().hex.

    uuid4() draws from OS randomness and ignores random.Random's seed, which
    would silently break the seed-based reproducibility generate_sample_logs()
    promises.
    """
    return "".join(rng.choices(_HEX_DIGITS, k=length))


def _random_ip(rng: random.Random) -> str:
    subnet = rng.choice(["10.0.0.", "192.168.1.", "203.0.113."])
    return f"{subnet}{rng.randint(1, 254)}"


def _random_status(rng: random.Random, level: str) -> int:
    codes, weights = STATUS_CHOICES_BY_LEVEL[level]
    return rng.choices(codes, weights=weights, k=1)[0]


def _random_response_time_ms(rng: random.Random, status: int) -> int:
    if status >= 500:
        return rng.randint(400, 5000)
    if status >= 400:
        return rng.randint(20, 600)
    return rng.randint(8, 450)


def _random_stack_trace_lines(rng: random.Random) -> list[str]:
    exc_type, message, frames = rng.choice(EXCEPTION_TEMPLATES)
    lines = ["Traceback (most recent call last):"]
    lines.extend(f"  {frame}" for frame in frames)
    lines.append(f"{exc_type}: {message}")
    return lines


def _tok(value: object) -> str:
    """Render a field as its '-' placeholder when absent, matching LogParser's convention."""
    return "-" if value is None else str(value)


def _random_primary_line(rng: random.Random, day: datetime) -> tuple[str, str, str]:
    """Build one primary log line. Returns (line, level, timestamp_sort_key)."""
    level = rng.choices(list(LEVEL_WEIGHTS), weights=list(LEVEL_WEIGHTS.values()), k=1)[0]
    module = rng.choice(MODULES)
    logger_name = rng.choice(LOGGERS_BY_MODULE[module])
    function = rng.choice(FUNCTIONS_BY_MODULE[module])
    pid = rng.choice(PIDS)
    thread = rng.choice(THREADS)

    timestamp = _random_timestamp(day, rng)
    ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]

    # ~65% of log lines happen within an HTTP request; the rest are background
    # jobs / startup / system logs with no request context at all.
    is_http = rng.random() < 0.65
    if is_http:
        trace_id = _random_hex(rng, 16)
        has_user = rng.random() < 0.75  # some endpoints are public/unauthenticated
        user_id = rng.choice(USER_IDS) if has_user else None
        session_id = f"sess_{_random_hex(rng, 8)}" if has_user else None
        ip_address = _random_ip(rng)
        method = rng.choice(HTTP_METHODS)
        endpoint = rng.choice(HTTP_ENDPOINTS_BY_MODULE[module])
        status = _random_status(rng, level)
        response_time_ms = _random_response_time_ms(rng, status)
    else:
        trace_id = user_id = session_id = ip_address = method = endpoint = None
        status = response_time_ms = None

    template = rng.choice(MESSAGES_BY_LEVEL[level])
    message = template.format(n=rng.randint(1, 9999))

    line = (
        f"{ts_str} [{level}] [pid:{pid}] [thread:{thread}] "
        f"logger={logger_name} module={module} func={function} "
        f"trace_id={_tok(trace_id)} user_id={_tok(user_id)} session_id={_tok(session_id)} "
        f"ip={_tok(ip_address)} method={_tok(method)} endpoint={_tok(endpoint)} "
        f"status={_tok(status)} response_time_ms={_tok(response_time_ms)} - {message}"
    )
    return line, level, ts_str


def _random_malformed_line(rng: random.Random) -> str:
    variants = [
        "database connection pool exhausted, retrying in background",
        # missing the [pid:...] segment entirely
        "2026-08-07 10:00:00,000 [INFO] [thread:MainThread] logger=app.services.auth_service"
        " module=auth_service func=login trace_id=- user_id=- session_id=- ip=- method=- endpoint=-"
        " status=- response_time_ms=- - missing pid field",
        # timestamp uses a dot instead of the required comma before milliseconds
        "2026-08-07 10:00:00.000 [INFO] [pid:4821] [thread:MainThread] logger=app.services.auth_service"
        " module=auth_service func=login trace_id=- user_id=- session_id=- ip=- method=- endpoint=-"
        " status=- response_time_ms=- - wrong timestamp separator",
        # unrecognized log level
        "2026-08-07 10:00:00,000 [TRACE] [pid:4821] [thread:MainThread] logger=app.services.auth_service"
        " module=auth_service func=login trace_id=- user_id=- session_id=- ip=- method=- endpoint=-"
        " status=- response_time_ms=- - unsupported level",
        # non-numeric status code
        f"2026-08-07 10:00:00,000 [ERROR] [pid:4821] [thread:MainThread] logger=app.services.auth_service"
        f" module=auth_service func=login trace_id=- user_id={rng.choice(USER_IDS)} session_id=- ip=-"
        f" method=GET endpoint=/api/v1/login status=abc response_time_ms=- - non-numeric status",
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
        num_lines: approximate number of primary log lines to write (stack
            traces, duplicates, and malformed lines are added on top).
        days_back: spread generated timestamps across the last N days, so
            daily/monthly trend analytics have multiple buckets to show.
        duplicate_rate: fraction of primary lines that get an exact duplicate
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

    # Each block is (sort_key, [lines]) — a primary line plus any stack-trace
    # continuation lines that must stay immediately after it once sorted.
    blocks: list[tuple[str, list[str]]] = []

    for _ in tqdm(range(num_lines), desc=f"Generating {output_path.name}", unit="line"):
        day = today - timedelta(days=rng.randint(0, days_back))
        primary_line, level, ts_key = _random_primary_line(rng, day)

        block_lines = [primary_line]
        if level in ("ERROR", "CRITICAL") and rng.random() < 0.5:
            block_lines.extend(_random_stack_trace_lines(rng))
        blocks.append((ts_key, block_lines))

        if rng.random() < duplicate_rate:
            blocks.append((ts_key, [primary_line]))  # exact duplicate -> same content hash

    malformed_count = int(num_lines * malformed_rate)
    for _ in range(malformed_count):
        blocks.append(("", [_random_malformed_line(rng)]))

    blocks.sort(key=lambda block: block[0])

    with output_path.open("w", encoding="utf-8") as handle:
        for _, block_lines in blocks:
            for line in block_lines:
                handle.write(line + "\n")

    logger.info(
        "Generated sample log file %s (%d base lines, ~%d malformed injected)",
        output_path,
        num_lines,
        malformed_count,
    )
    return output_path
