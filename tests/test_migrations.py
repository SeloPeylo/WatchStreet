"""Alembic migrations: fresh install, adoption of pre-migration databases, drift against models."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select, text

from watchstreet.migrate import alembic_config, upgrade_to_head
from watchstreet.models import Base, Stock


@pytest.fixture
def engine(tmp_path):
    built = create_engine(f"sqlite:///{tmp_path / 'migrations.db'}")
    yield built
    built.dispose()


OLD_REVISION = "0002"


def _head() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None
    return head


def _version(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def test_container_schema_comes_from_migrations_and_matches_models(container):
    assert _version(container.engine) == _head()
    with container.engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == [], "models and migrations drifted: run `alembic revision --autogenerate`"


def test_upgrade_is_idempotent(engine):
    upgrade_to_head(engine)
    upgrade_to_head(engine)
    assert _version(engine) == _head()


def test_dashboard_database_is_upgraded_keeping_the_portfolio(engine):
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), OLD_REVISION)
        connection.execute(
            text(
                "INSERT INTO stocks (id, symbol, name, currency, exchange, sector, industry, "
                "profile, profile_source, created_at) VALUES (1, 'OLD', 'Old Co', 'USD', '', '', "
                "'', 'generic', 'none', '2026-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO tickets (stock_id, workflow, title, status, origin, priority, depth, "
                "params, result, summary, error, runner, created_at) VALUES (1, 'briefing', 't', "
                "'done', 'user', 50, 0, '{}', '{}', '', '', '', '2026-01-01 00:00:00')"
            )
        )
    upgrade_to_head(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"assets", "facts", "research_tickets"} <= tables and "tickets" not in tables
    with engine.connect() as connection:
        assert connection.execute(select(Stock.symbol)).scalars().all() == ["OLD"]


def test_downgrade_below_the_explorer_schema_is_refused(engine):
    upgrade_to_head(engine)
    with engine.begin() as connection, pytest.raises(NotImplementedError):
        command.downgrade(alembic_config(connection), OLD_REVISION)
