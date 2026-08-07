"""Test harness: dedicated fleetpulse_test database, real Postgres, clean tables per test."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import Base

TEST_DB = "fleetpulse_test"


def _test_url() -> str:
    base = get_settings().database_url
    return base.rsplit("/", 1)[0] + f"/{TEST_DB}"


def _ensure_test_database() -> None:
    admin = create_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    _ensure_test_database()
    eng = create_engine(_test_url(), pool_pre_ping=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine: Engine) -> Generator[Session, None, None]:
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = maker()
    yield session
    session.close()
    # Truncate everything between tests, newest tables included automatically.
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
