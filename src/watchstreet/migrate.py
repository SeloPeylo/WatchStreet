"""Schema management: bring a database to the current Alembic revision.

``upgrade_to_head`` is called by ``build_container`` (so by web and worker alike) and is safe to
run concurrently and repeatedly:

* On PostgreSQL a transaction-scoped advisory lock serialises concurrent starters; the loser
  waits, then finds the schema already at ``head``.
* Databases created by the former ``create_all`` (tables but no ``alembic_version``) are stamped
  with the baseline revision first, so existing installations adopt migrations without data loss.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, inspect, text

from watchstreet.constants import MIGRATION_LOCK_ID, STARTUP_LOCK_ID

try:  # POSIX only; without it SQLite starts are simply not serialised
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
BASELINE_REVISION = "0001"
VERSION_TABLE = "alembic_version"
LEGACY_MARKER_TABLE = "stocks"  # exists in every database created by the old create_all


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def _is_legacy(connection: Connection) -> bool:
    tables = set(inspect(connection).get_table_names())
    return LEGACY_MARKER_TABLE in tables and VERSION_TABLE not in tables


@contextmanager
def startup_lock(engine: Engine) -> Iterator[None]:
    """Only one process at a time may migrate and seed a database.

    Web and worker start together; without this both would create the same tables (SQLite) or
    insert the same demo rows. PostgreSQL uses a session advisory lock, SQLite a lock file.
    """
    database = engine.url.database
    if engine.dialect.name == "postgresql":
        with engine.connect() as connection:
            connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": STARTUP_LOCK_ID})
            try:
                yield
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": STARTUP_LOCK_ID}
                )
        return
    if fcntl is None or not database or database == ":memory:":
        yield
        return
    with Path(f"{database}.startup.lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def upgrade_to_head(engine: Engine) -> None:
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_ID}
            )
        config = alembic_config(connection)
        if _is_legacy(connection):
            command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")
