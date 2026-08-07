"""Unit tests for log_analyzer.config.settings."""

from __future__ import annotations

from pathlib import Path

from log_analyzer.config import settings as settings_module
from log_analyzer.config.settings import Settings


def _make_settings(**overrides) -> Settings:
    defaults = dict(
        db_host="localhost",
        db_port=5432,
        db_name="testdb",
        db_user="user",
        db_password="pass",
        log_level="INFO",
        log_input_dir=Path("data/logs"),
        reports_output_dir=Path("outputs/reports"),
        charts_output_dir=Path("outputs/charts"),
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_database_url_format():
    settings = _make_settings()
    assert settings.database_url == "postgresql+psycopg2://user:pass@localhost:5432/testdb"


def test_admin_database_url_points_to_postgres_maintenance_db():
    settings = _make_settings()
    assert settings.admin_database_url.endswith("/postgres")
    assert settings.admin_database_url != settings.database_url


def test_get_settings_reads_env_vars(monkeypatch):
    settings_module.get_settings.cache_clear()

    monkeypatch.setenv("DB_HOST", "testhost")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "custom_db")
    monkeypatch.setenv("DB_USER", "custom_user")
    monkeypatch.setenv("DB_PASSWORD", "custom_pass")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    try:
        settings = settings_module.get_settings()
        assert settings.db_host == "testhost"
        assert settings.db_port == 5433
        assert settings.db_name == "custom_db"
        assert settings.log_level == "DEBUG"
    finally:
        settings_module.get_settings.cache_clear()


def test_get_settings_is_cached(monkeypatch):
    settings_module.get_settings.cache_clear()
    try:
        first = settings_module.get_settings()
        second = settings_module.get_settings()
        assert first is second  # lru_cache returns the identical instance
    finally:
        settings_module.get_settings.cache_clear()
