import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from watchstreet.config import Settings
from watchstreet.container import build_container
from watchstreet.migrate import upgrade_to_head
from watchstreet.models import Base
from watchstreet.services.demo import seed_demo
from watchstreet.web.app import create_app


@pytest.fixture
def container(tmp_path):
    """Runs on SQLite by default; set WATCHSTREET_TEST_DATABASE_URL to test another backend.

    The schema always comes from the Alembic migrations (``build_container`` upgrades to head).
    A shared external database is reset first so every test starts empty.
    """
    external = os.environ.get("WATCHSTREET_TEST_DATABASE_URL")
    url = external or f"sqlite:///{tmp_path / 'test.db'}"
    settings = Settings(
        database_url=url,
        market_provider="demo",
        agent_runner="offline",
        docs_dir=str(tmp_path / "docs"),
    )
    built = build_container(settings)
    if external:
        Base.metadata.drop_all(built.engine)
        with built.engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        upgrade_to_head(built.engine)
        with built.session_factory() as session:
            seed_demo(session, built.market)
            session.commit()
    yield built
    built.engine.dispose()


@pytest.fixture
def session(container):
    with container.session_factory() as s:
        yield s
        s.rollback()


@pytest.fixture
def client(container) -> TestClient:
    with TestClient(create_app(container)) as c:
        yield c
