"""Centralized application configuration loaded from environment variables."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

if getattr(sys, "frozen", False):
    # Running as a PyInstaller-built .exe: __file__ resolves inside a temp
    # extraction directory (sys._MEIPASS) that's wiped after the process
    # exits, so .env/data/outputs must live next to the executable instead.
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    # Project root = three levels up from this file (src/log_analyzer/config/settings.py -> repo root)
    PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    """Immutable application settings, populated once from environment variables."""

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    log_level: str
    log_input_dir: Path
    reports_output_dir: Path
    charts_output_dir: Path

    @property
    def database_url(self) -> str:
        """SQLAlchemy connection URL for the target application database."""
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def admin_database_url(self) -> str:
        """Connection URL to the default 'postgres' maintenance database.

        Used only to issue CREATE DATABASE, since a connection cannot create
        the database it is currently connected to.
        """
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/postgres"
        )


def _resolve_path(raw: str) -> Path:
    """Resolve a config path relative to the project root, not the CWD."""
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache Settings from the .env file (or real environment variables).

    Cached with lru_cache so the .env file is parsed once per process, and every
    module that calls get_settings() shares the same immutable configuration.
    """
    load_dotenv(PROJECT_ROOT / ".env")

    return Settings(
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_name=os.getenv("DB_NAME", "log_analyzer"),
        db_user=os.getenv("DB_USER", "postgres"),
        db_password=os.getenv("DB_PASSWORD", ""),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        log_input_dir=_resolve_path(os.getenv("LOG_INPUT_DIR", "data/logs")),
        reports_output_dir=_resolve_path(os.getenv("REPORTS_OUTPUT_DIR", "outputs/reports")),
        charts_output_dir=_resolve_path(os.getenv("CHARTS_OUTPUT_DIR", "outputs/charts")),
    )
