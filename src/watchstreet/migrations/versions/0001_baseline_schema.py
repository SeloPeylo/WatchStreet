"""baseline schema

Revision ID: 0001
Revises:
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feeds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("publisher", sa.String(length=120), nullable=False),
        sa.Column("doc_kind", sa.String(length=12), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=False),
        sa.Column("sector", sa.String(length=120), nullable=False),
        sa.Column("industry", sa.String(length=120), nullable=False),
        sa.Column("profile", sa.String(length=24), nullable=False),
        sa.Column("profile_source", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol"),
    )
    op.create_table(
        "system_state",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("publisher", sa.String(length=120), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("relevance", sa.Float(), nullable=False),
        sa.Column("triaged", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", "content_hash"),
    )
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_documents_stock_id"), ["stock_id"], unique=False)

    op.create_table(
        "entities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=True),
        sa.Column("country", sa.String(length=80), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("origin", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "name"),
    )
    with op.batch_alter_table("entities", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_entities_stock_id"), ["stock_id"], unique=False)

    op.create_table(
        "holdings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=False),
        sa.Column("bought_at", sa.Date(), nullable=True),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stock_id"),
    )
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("workflow", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("runner", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["tickets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("tickets", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tickets_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_tickets_stock_id"), ["stock_id"], unique=False)

    op.create_table(
        "watch_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stock_id"),
    )
    op.create_table(
        "briefings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("bullets", sa.JSON(), nullable=False),
        sa.Column("focus", sa.String(length=24), nullable=False),
        sa.Column("author", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("briefings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_briefings_stock_id"), ["stock_id"], unique=False)

    op.create_table(
        "datapoints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("key", sa.String(length=48), nullable=False),
        sa.Column("subject", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("text", sa.String(length=200), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=8), nullable=False),
        sa.Column("origin", sa.String(length=8), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("datapoints", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_datapoints_stock_id"), ["stock_id"], unique=False)

    op.create_table(
        "insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("insights", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_insights_stock_id"), ["stock_id"], unique=False)

    op.create_table(
        "intel_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=80), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("commodities", sa.JSON(), nullable=False),
        sa.Column("extra_sources", sa.JSON(), nullable=False),
        sa.Column("author", sa.String(length=8), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_table(
        "market_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stock_id", "external_id"),
    )
    with op.batch_alter_table("market_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_market_events_stock_id"), ["stock_id"], unique=False)

    op.create_table(
        "relations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("strength", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=8), nullable=False),
        sa.Column("origin", sa.String(length=8), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["entities.id"],
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["entities.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("relations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_relations_source_id"), ["source_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_relations_target_id"), ["target_id"], unique=False)

    op.create_table(
        "scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("scheme", sa.String(length=48), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("scores", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_scores_stock_id"), ["stock_id"], unique=False)

    op.create_table(
        "theses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("theses", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_theses_stock_id"), ["stock_id"], unique=False)

    op.create_table(
        "intel_impacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("intel_id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["intel_id"],
            ["intel_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("intel_impacts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_intel_impacts_intel_id"), ["intel_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_intel_impacts_stock_id"), ["stock_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("intel_impacts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_intel_impacts_stock_id"))
        batch_op.drop_index(batch_op.f("ix_intel_impacts_intel_id"))

    op.drop_table("intel_impacts")
    with op.batch_alter_table("theses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_theses_stock_id"))

    op.drop_table("theses")
    with op.batch_alter_table("scores", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_scores_stock_id"))

    op.drop_table("scores")
    with op.batch_alter_table("relations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_relations_target_id"))
        batch_op.drop_index(batch_op.f("ix_relations_source_id"))

    op.drop_table("relations")
    with op.batch_alter_table("market_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_market_events_stock_id"))

    op.drop_table("market_events")
    op.drop_table("intel_items")
    with op.batch_alter_table("insights", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_insights_stock_id"))

    op.drop_table("insights")
    with op.batch_alter_table("datapoints", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_datapoints_stock_id"))

    op.drop_table("datapoints")
    with op.batch_alter_table("briefings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_briefings_stock_id"))

    op.drop_table("briefings")
    op.drop_table("watch_entries")
    with op.batch_alter_table("tickets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tickets_stock_id"))
        batch_op.drop_index(batch_op.f("ix_tickets_status"))

    op.drop_table("tickets")
    op.drop_table("holdings")
    with op.batch_alter_table("entities", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_entities_stock_id"))

    op.drop_table("entities")
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_documents_stock_id"))

    op.drop_table("documents")
    op.drop_table("system_state")
    op.drop_table("stocks")
    op.drop_table("feeds")
