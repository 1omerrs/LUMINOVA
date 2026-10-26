from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engines: dict[str, Engine] = {}
_sessionmakers: dict[str, sessionmaker[Session]] = {}


def get_engine() -> Engine:
    url = get_settings().database_url
    engine = _engines.get(url)
    if engine is None:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            connect_args={"connect_timeout": 3},
        )
        _engines[url] = engine
    return engine


def get_sessionmaker() -> sessionmaker[Session]:
    url = get_settings().database_url
    factory = _sessionmakers.get(url)
    if factory is None:
        factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)
        _sessionmakers[url] = factory
    return factory


def get_db() -> Generator[Session, None, None]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
