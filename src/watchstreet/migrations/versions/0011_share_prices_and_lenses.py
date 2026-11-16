"""share price history and saved lenses

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-16 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "share_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "day"),
    )
    with op.batch_alter_table("share_prices", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_share_prices_symbol"), ["symbol"], unique=False)
    op.create_table(
        "lenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("lenses")
    with op.batch_alter_table("share_prices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_share_prices_symbol"))
    op.drop_table("share_prices")
