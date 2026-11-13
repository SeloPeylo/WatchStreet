"""checkable exit thresholds and announced financings

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-12 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("holdings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("stop_price", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("min_runway_months", sa.Float(), nullable=True))
    with op.batch_alter_table("financings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("announced", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("financings", schema=None) as batch_op:
        batch_op.drop_column("announced")
    with op.batch_alter_table("holdings", schema=None) as batch_op:
        batch_op.drop_column("min_runway_months")
        batch_op.drop_column("stop_price")
