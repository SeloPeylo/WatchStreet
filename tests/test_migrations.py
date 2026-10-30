"""Alembic migrations: fresh install, adoption of pre-migration databases, drift against models."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select, text

from watchstreet.migrate import BASELINE_REVISION, alembic_config, upgrade_to_head
from watchstreet.models import Base, Stock


@pytest.fixture
def engine(tmp_path):
    built = create_engine(f"sqlite:///{tmp_path / 'migrations.db'}")
    yield built
    built.dispose()


NEW_INDEXES = ("ix_tickets_claim", "ix_documents_triaged", "ix_intel_items_published_at")


def _head() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None
    return head


def _version(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _index_names(engine) -> set[str]:
    inspector = inspect(engine)
    return {i["name"] for t in inspector.get_table_names() for i in inspector.get_indexes(t)}


def test_container_schema_comes_from_migrations_and_matches_models(container):
    assert _version(container.engine) == _head()
    with container.engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == [], "models and migrations drifted: run `alembic revision --autogenerate`"


def test_upgrade_is_idempotent(engine):
    upgrade_to_head(engine)
    upgrade_to_head(engine)
    assert _version(engine) == _head()
    assert set(NEW_INDEXES) <= _index_names(engine)


def test_database_created_by_create_all_is_adopted_without_data_loss(engine):
    Base.metadata.create_all(engine)  # how installations were created before migrations
    with engine.begin() as connection:
        for name in NEW_INDEXES:  # a pre-migration schema did not have these yet
            connection.execute(text(f"DROP INDEX {name}"))
        connection.execute(
            text(
                "INSERT INTO stocks (symbol, name, currency, exchange, sector, "
                "industry, profile, profile_source, created_at) VALUES "
                "('OLD', 'Old Co', 'USD', '', '', '', 'general', 'none', "
                "'2026-01-01 00:00:00')"
            )
        )
    upgrade_to_head(engine)
    assert _version(engine) == _head()
    assert set(NEW_INDEXES) <= _index_names(engine)
    with engine.connect() as connection:
        assert connection.execute(select(Stock.symbol)).scalars().all() == ["OLD"]


def test_database_from_create_all_with_all_indexes_is_adopted(engine):
    Base.metadata.create_all(engine)
    upgrade_to_head(engine)
    assert _version(engine) == _head()


def test_downgrade_to_baseline_and_back(engine):
    upgrade_to_head(engine)
    with engine.begin() as connection:
        config = alembic_config(connection)
        command.downgrade(config, BASELINE_REVISION)
    assert _version(engine) == BASELINE_REVISION
    assert not set(NEW_INDEXES) & _index_names(engine)
    upgrade_to_head(engine)
    assert _version(engine) == _head()
