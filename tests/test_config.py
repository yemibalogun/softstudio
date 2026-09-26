"""
The database URL always names the driver the project actually installs.

SQLAlchemy's default driver for a bare "postgresql://" URL is not stable
across versions: 2.0 resolves it to psycopg2, 2.1 to psycopg 3.
requirements.txt ships psycopg2-binary, so a bare URL means the app
starts or fails depending on which SQLAlchemy a fresh install happens to
pull in. app/config.py pins the driver in the URL instead.
"""
import importlib

import pytest

import app.config as config_module


@pytest.mark.parametrize(
    "given",
    [
        "postgresql://user:pw@host:5432/db",
        "postgres://user:pw@host:5432/db",  # the alias SQLAlchemy dropped
    ],
)
def test_postgres_urls_name_the_psycopg2_driver(given):
    assert config_module._db_url("SOME_KEY", given) == "postgresql+psycopg2://user:pw@host:5432/db"


def test_an_explicit_driver_is_left_alone():
    """A deployment that asks for a specific driver keeps it."""
    for url in [
        "postgresql+psycopg2://user:pw@host/db",
        "postgresql+psycopg://user:pw@host/db",
        "sqlite:///local.db",
    ]:
        assert config_module._db_url("SOME_KEY", url) == url


def test_the_environment_wins_over_the_default(monkeypatch):
    monkeypatch.setenv("DB_URL_UNDER_TEST", "postgresql://env:pw@envhost/envdb")
    assert config_module._db_url("DB_URL_UNDER_TEST", "postgresql://fallback@h/d") == (
        "postgresql+psycopg2://env:pw@envhost/envdb"
    )


def test_every_config_class_resolves_to_an_importable_driver(monkeypatch):
    """
    Guards the actual failure this fixed: CI crashed with
    ModuleNotFoundError: No module named 'psycopg' during `flask db upgrade`.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:pw@h:5432/d")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://u:pw@h:5432/d_test")
    importlib.reload(config_module)
    try:
        from sqlalchemy.engine import make_url
        for name in ("BaseConfig", "DevelopmentConfig", "TestingConfig"):
            url = make_url(getattr(config_module, name).SQLALCHEMY_DATABASE_URI)
            assert url.get_driver_name() == "psycopg2", f"{name} resolved to {url.get_driver_name()}"
            url.get_dialect()  # imports the DBAPI module; raises if it is missing
    finally:
        monkeypatch.undo()
        importlib.reload(config_module)
