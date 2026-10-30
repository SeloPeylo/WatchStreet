import pytest
from fastapi.testclient import TestClient

from watchstreet.config import Settings
from watchstreet.container import build_container
from watchstreet.web.app import create_app


@pytest.fixture
def container(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        market_provider="demo",
        agent_runner="offline",
        docs_dir=str(tmp_path / "docs"),
    )
    built = build_container(settings)
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
