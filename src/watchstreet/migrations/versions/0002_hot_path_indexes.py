"""indexes for the hot queries

* ``ix_tickets_claim``: worker claim (``status = 'queued' ORDER BY priority DESC, id``)
* ``ix_documents_triaged``: triage intake scans only untriaged documents
* ``ix_intel_items_published_at``: news center and map order/filter by publication date

Databases that were created by ``create_all`` before migrations existed may already have some of
these (a fresh ``create_all`` includes them), so each index is created only if it is missing.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ix_tickets_claim", "tickets", ("status", "priority", "id")),
    ("ix_documents_triaged", "documents", ("triaged",)),
    ("ix_intel_items_published_at", "intel_items", ("published_at",)),
)


def _existing(table: str) -> set[str]:
    if op.get_context().as_sql:  # offline (--sql): nothing to inspect, emit every statement
        return set()
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table)
        if index["name"] is not None
    }


def upgrade() -> None:
    for name, table, columns in INDEXES:
        if name not in _existing(table):
            op.create_index(name, table, list(columns))


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        if op.get_context().as_sql or name in _existing(table):
            op.drop_index(name, table_name=table)
