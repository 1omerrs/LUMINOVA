import pytest
from pydantic import ValidationError

from app.core.config import get_settings


def test_local_defaults_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert ":5433/" in settings.database_url
    assert settings.database_url.endswith("/luminova")


def test_production_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()


def test_production_rejects_localhost_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://luminova:different-secret@db.internal:5432/luminova",
    )
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()


def test_rejects_non_psycopg_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql://luminova:luminova@127.0.0.1:5432/luminova")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()
