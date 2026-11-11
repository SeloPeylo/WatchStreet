"""financing terms and insider holdings

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-11 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("financings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("warrants", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("warrant_price", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("warrant_expiry", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("investors", sa.Text(), nullable=False, server_default=""))
    with op.batch_alter_table("people", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("prior_companies", sa.Text(), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("shares_held", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("people", schema=None) as batch_op:
        batch_op.drop_column("shares_held")
        batch_op.drop_column("prior_companies")
    with op.batch_alter_table("financings", schema=None) as batch_op:
        batch_op.drop_column("investors")
        batch_op.drop_column("warrant_expiry")
        batch_op.drop_column("warrant_price")
        batch_op.drop_column("warrants")
