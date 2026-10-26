import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migrations_reach_head(database: str) -> None:
    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    with psycopg.connect(database) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        comment = connection.execute(
            """
            SELECT obj_description(namespace.oid, 'pg_namespace')
            FROM pg_namespace AS namespace
            WHERE namespace.nspname = 'public'
            """
        ).fetchone()

    assert version is not None
    assert version[0] == head == "0033_verification_codes"
    assert comment is not None
    assert comment[0] is not None
    assert "company_id" in comment[0]
