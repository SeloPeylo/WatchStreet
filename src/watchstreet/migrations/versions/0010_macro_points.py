"""macro series observations

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-15 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "macro_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series", sa.String(length=24), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series", "day"),
    )
    with op.batch_alter_table("macro_points", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_macro_points_series"), ["series"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("macro_points", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_macro_points_series"))
    op.drop_table("macro_points")
