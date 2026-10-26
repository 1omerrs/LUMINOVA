import os

os.environ.setdefault("APP_ENV", "test")
os.environ["MAIL_WEBHOOK_URL"] = ""
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://luminova:luminova@127.0.0.1:5433/luminova_test",
)

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import get_settings

ADMIN_DSN = "postgresql://luminova:luminova@127.0.0.1:5433/luminova"
TEST_DSN = "postgresql://luminova:luminova@127.0.0.1:5433/luminova_test"


@pytest.fixture(autouse=True)
def reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def database():
    try:
        with psycopg.connect(ADMIN_DSN, autocommit=True) as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                ("luminova_test",),
            ).fetchone()
            if exists is None:
                connection.execute("CREATE DATABASE luminova_test")
    except psycopg.Error:
        pytest.fail("PostgreSQL erişilemiyor. Kök dizinde `docker compose up -d` çalıştır.")

    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    yield TEST_DSN


@pytest.fixture
def client(database: str):
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
