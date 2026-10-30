"""SQLAlchemy ORM models."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from watchstreet.constants import DEFAULT_PRIORITY, DEFAULT_PROFILE
from watchstreet.db import UtcDateTime
from watchstreet.domain import InsightCategory, ThesisStatus, TicketOrigin, TicketStatus
from watchstreet.timeutil import utcnow


class Base(DeclarativeBase):
    """Declarative base."""


class Stock(Base):
    """A security. Knowledge (tickets, insights, scores, theses) hangs off the stock."""

    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    currency: Mapped[str] = mapped_column(String(8), default="")
    exchange: Mapped[str] = mapped_column(String(64), default="")
    sector: Mapped[str] = mapped_column(String(120), default="")
    industry: Mapped[str] = mapped_column(String(120), default="")
    profile: Mapped[str] = mapped_column(String(24), default=DEFAULT_PROFILE)
    profile_source: Mapped[str] = mapped_column(String(8), default="none")  # none|auto|agent|user
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    holding: Mapped["Holding | None"] = relationship(
        back_populates="stock",
        cascade="all, delete-orphan",
        uselist=False,
    )
    watch: Mapped["WatchEntry | None"] = relationship(
        back_populates="stock",
        cascade="all, delete-orphan",
        uselist=False,
    )
    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="stock",
        cascade="all, delete-orphan",
        order_by="Ticket.id.desc()",
    )
    insights: Mapped[list["Insight"]] = relationship(
        cascade="all, delete-orphan",
        order_by="Insight.id.desc()",
    )
    scores: Mapped[list["Score"]] = relationship(
        cascade="all, delete-orphan",
        order_by="Score.id.desc()",
    )
    theses: Mapped[list["Thesis"]] = relationship(
        cascade="all, delete-orphan",
        order_by="Thesis.id.desc()",
    )
    events: Mapped[list["MarketEvent"]] = relationship(
        cascade="all, delete-orphan",
        order_by="MarketEvent.published_at.desc()",
    )
    datapoints: Mapped[list["Datapoint"]] = relationship(
        cascade="all, delete-orphan",
        order_by="Datapoint.id.desc()",
    )
    briefings: Mapped[list["Briefing"]] = relationship(
        cascade="all, delete-orphan",
        order_by="Briefing.id.desc()",
    )


class Holding(Base):
    """Something the user owns."""

    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), unique=True)
    quantity: Mapped[float] = mapped_column(Float)
    avg_price: Mapped[float] = mapped_column(Float)
    bought_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    intent: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    stock: Mapped[Stock] = relationship(back_populates="holding")


class WatchEntry(Base):
    """A stock the user is interested in."""

    __tablename__ = "watch_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), unique=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    stock: Mapped[Stock] = relationship(back_populates="watch")


class Ticket(Base):
    """A unit of analysis work bound to exactly one predefined workflow."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    workflow: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16), default=TicketStatus.QUEUED, index=True)
    origin: Mapped[str] = mapped_column(String(16), default=TicketOrigin.USER)
    priority: Mapped[int] = mapped_column(Integer, default=DEFAULT_PRIORITY)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    runner: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    stock: Mapped[Stock] = relationship(back_populates="tickets")
    parent: Mapped["Ticket | None"] = relationship(
        remote_side="Ticket.id", back_populates="children"
    )
    children: Mapped[list["Ticket"]] = relationship(back_populates="parent")


class Insight(Base):
    """A durable finding produced by a ticket."""

    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(16), default=InsightCategory.NOTE)
    text: Mapped[str] = mapped_column(Text)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Score(Base):
    """A scheme-based score; the series over time is the score history."""

    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    scheme: Mapped[str] = mapped_column(String(48))
    value: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(64), default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Thesis(Base):
    """A version of the investment thesis; each check appends a new version."""

    __tablename__ = "theses"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=ThesisStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class MarketEvent(Base):
    """A news item or other external event."""

    __tablename__ = "market_events"
    __table_args__ = (UniqueConstraint("stock_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    reviewed: Mapped[bool] = mapped_column(default=False)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)


class Datapoint(Base):
    """A sourced input for valuation schemes (e.g. a mine's AISC). Newest per key+subject wins."""

    __tablename__ = "datapoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    key: Mapped[str] = mapped_column(String(48))
    subject: Mapped[str] = mapped_column(String(120), default="")  # e.g. mine name
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    text: Mapped[str] = mapped_column(String(200), default="")
    unit: Mapped[str] = mapped_column(String(32), default="")
    source: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(8), default="medium")  # high|medium|low
    origin: Mapped[str] = mapped_column(String(8), default="user")  # user|agent
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")  # verified verbatim excerpt
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Briefing(Base):
    """The short 'what matters now' layer shown on top of a stock; stored, never ephemeral."""

    __tablename__ = "briefings"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    headline: Mapped[str] = mapped_column(Text)
    bullets: Mapped[list[str]] = mapped_column(JSON, default=list)
    focus: Mapped[str] = mapped_column(String(24), default="")  # panel to open first
    author: Mapped[str] = mapped_column(String(8), default="rules")  # rules|agent
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Document(Base):
    """A stored source (filing, press release, news article, dataset) with its extracted text."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("url", "content_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(12), default="other")
    publisher: Mapped[str] = mapped_column(String(120), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    triaged: Mapped[bool] = mapped_column(default=False)


class Entity(Base):
    """A node in the dependency graph: company, supplier, mine, port, country, commodity ..."""

    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("kind", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(16))
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    country: Mapped[str] = mapped_column(String(80), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    origin: Mapped[str] = mapped_column(String(8), default="user")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Relation(Base):
    """A directed, sourced edge between two entities."""

    __tablename__ = "relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    strength: Mapped[float | None] = mapped_column(Float, nullable=True)  # share 0..1 if known
    note: Mapped[str] = mapped_column(Text, default="")
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(8), default="low")
    origin: Mapped[str] = mapped_column(String(8), default="user")
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class IntelItem(Base):
    """A tailored news/intel item pointing at direct sources, with portfolio impact."""

    __tablename__ = "intel_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    headline: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    why_it_matters: Mapped[str] = mapped_column(Text, default="")
    quote: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(16), default="company")
    severity: Mapped[int] = mapped_column(Integer, default=2)
    country: Mapped[str] = mapped_column(String(80), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    commodities: Mapped[list[str]] = mapped_column(JSON, default=list)
    extra_sources: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    author: Mapped[str] = mapped_column(String(8), default="rules")  # rules|agent
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    published_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    impacts: Mapped[list["IntelImpact"]] = relationship(
        cascade="all, delete-orphan",
        order_by="IntelImpact.id",
    )
    document: Mapped["Document | None"] = relationship()


class IntelImpact(Base):
    """How an intel item affects one of the user's stocks."""

    __tablename__ = "intel_impacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    intel_id: Mapped[int] = mapped_column(ForeignKey("intel_items.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    direction: Mapped[str] = mapped_column(String(8), default="unknown")
    note: Mapped[str] = mapped_column(Text, default="")

    stock: Mapped[Stock] = relationship()


class Feed(Base):
    """A configured external source that is polled for documents."""

    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(8))  # rss|gdelt|usgs
    url: Mapped[str] = mapped_column(Text, default="")  # feed URL, or search query for gdelt
    publisher: Mapped[str] = mapped_column(String(120), default="")
    doc_kind: Mapped[str] = mapped_column(String(12), default="news")
    enabled: Mapped[bool] = mapped_column(default=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_fetched_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class SystemState(Base):
    """Small key/value store (worker heartbeat, last scan)."""

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
