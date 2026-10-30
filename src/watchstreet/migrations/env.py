"""Alembic environment.

Two ways in:

* the application calls :func:`watchstreet.migrate.upgrade_to_head` and hands over an open
  connection via ``config.attributes["connection"]``;
* the ``alembic`` CLI (``alembic -c alembic.ini revision --autogenerate -m ...``) builds its own
  engine from ``WATCHSTREET_DATABASE_URL``; ``--sql`` renders the migration without a database.
"""

from alembic import context
from sqlalchemy.engine import Connection

from watchstreet.config import load_settings
from watchstreet.db import make_engine
from watchstreet.models import Base

config = context.config
target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # SQLite cannot ALTER most things in place; batch mode recreates the table instead.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Emit SQL instead of executing it (``alembic upgrade head --sql``)."""
    context.configure(
        url=load_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = make_engine(load_settings().database_url)
    with engine.begin() as own_connection:
        _run(own_connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
