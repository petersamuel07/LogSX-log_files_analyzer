"""Centralized logging configuration shared by every module in the package."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from log_analyzer.config.settings import PROJECT_ROOT

LOG_FILE = PROJECT_ROOT / "logs" / "log_analyzer.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger with a console handler and a rotating file handler.

    Called once, at application startup (CLI entry point / test fixtures).
    Every module then does ``logger = logging.getLogger(__name__)`` and inherits
    this configuration automatically instead of configuring logging itself.
    """
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Rotate at 5 MB, keep 3 backups, so the log file never grows unbounded
    # during large batch-ingestion runs.
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # SQLAlchemy's own logger is very verbose at INFO; keep it at WARNING
    # unless the user explicitly asks for DEBUG-level app logging.
    if level.upper() != "DEBUG":
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
