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


class SystemState(Base):
    """Small key/value store (worker heartbeat, last scan)."""

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
