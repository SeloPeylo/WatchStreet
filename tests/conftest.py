import os

import pytest
from fastapi.testclient import TestClient

from watchstreet.config import Settings
from watchstreet.container import build_container
from watchstreet.intel.ingest import seed_feeds
from watchstreet.models import Base
from watchstreet.web.app import create_app


@pytest.fixture
def container(tmp_path):
    """Runs on SQLite by default; set WATCHSTREET_TEST_DATABASE_URL to test another backend."""
    url = os.environ.get("WATCHSTREET_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    settings = Settings(
        database_url=url,
        market_provider="demo",
        agent_runner="offline",
        docs_dir=str(tmp_path / "docs"),
    )
    built = build_container(settings)
    Base.metadata.drop_all(built.engine)
    Base.metadata.create_all(built.engine)
    with built.session_factory() as session:
        seed_feeds(session)
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
