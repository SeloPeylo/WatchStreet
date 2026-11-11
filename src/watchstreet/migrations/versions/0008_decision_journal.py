"""decision journal and thesis link on holdings

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-11 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("holdings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("thesis_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("exit_condition", sa.Text(), nullable=False, server_default="")
        )
    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("thesis_id", sa.Integer(), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decisions_stock_id", "decisions", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_decisions_stock_id", table_name="decisions")
    op.drop_table("decisions")
    with op.batch_alter_table("holdings", schema=None) as batch_op:
        batch_op.drop_column("exit_condition")
        batch_op.drop_column("thesis_id")
