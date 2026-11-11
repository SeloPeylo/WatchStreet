"""SQLAlchemy ORM models.

The asset (mine or project) is the primary unit; companies, facts, tickets, findings, theses and
events refer to it. Facts are append-only: a correction writes a new row and marks the old one
as superseded.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from watchstreet.constants import DEFAULT_PRIORITY
from watchstreet.db import UtcDateTime
from watchstreet.domain import (
    ClaimKind,
    DataOrigin,
    Epistemic,
    FindingKind,
    ProposalState,
    Provenance,
    Stance,
    ThesisStatus,
    TicketStatus,
)
from watchstreet.timeutil import utcnow


class Base(DeclarativeBase):
    """Declarative base."""


# --- Portfolio ------------------------------------------------------------


class Stock(Base):
    """A listed security the user holds or watches."""

    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    currency: Mapped[str] = mapped_column(String(8), default="")
    exchange: Mapped[str] = mapped_column(String(64), default="")
    sector: Mapped[str] = mapped_column(String(120), default="")
    industry: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    holding: Mapped["Holding | None"] = relationship(
        back_populates="stock", cascade="all, delete-orphan", uselist=False
    )
    watch: Mapped["WatchEntry | None"] = relationship(
        back_populates="stock", cascade="all, delete-orphan", uselist=False
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


# --- World model ------------------------------------------------------------


class Company(Base):
    """An operator or owner; listed companies point at their stock."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True)
    country: Mapped[str] = mapped_column(String(80), default="")
    is_demo: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    stock: Mapped[Stock | None] = relationship()


class Person(Base):
    """Management and directors: who runs the company and what they did before."""

    __tablename__ = "people"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(120), default="")
    since: Mapped[date | None] = mapped_column(Date, nullable=True)
    track_record: Mapped[str] = mapped_column(Text, default="")
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(8), default=DataOrigin.USER)
    is_demo: Mapped[bool] = mapped_column(default=False)


class Financing(Base):
    """One capital raise: the history of dilution and of what money cost."""

    __tablename__ = "financings"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(16), default="equity")  # equity|debt|royalty_sale
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # USD raised
    price: Mapped[float | None] = mapped_column(Float, nullable=True)  # per share
    shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(8), default=DataOrigin.USER)
    is_demo: Mapped[bool] = mapped_column(default=False)


class Asset(Base):
    """A mine, project or deposit with its own location, status history and facts."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(12))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    country: Mapped[str] = mapped_column(String(80), default="")
    region: Mapped[str] = mapped_column(String(120), default="")
    mining_method: Mapped[str] = mapped_column(String(16), default="unknown")
    summary: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(default=False)
    # where a registry import found it (wikidata, mrds); empty for hand-made and demo assets
    registry_source: Mapped[str] = mapped_column(String(16), default="")
    registry_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    commodities: Mapped[list["AssetCommodity"]] = relationship(
        cascade="all, delete-orphan", order_by="AssetCommodity.id"
    )
    statuses: Mapped[list["StatusPeriod"]] = relationship(
        cascade="all, delete-orphan", order_by="StatusPeriod.valid_from"
    )
    stakes: Mapped[list["Stake"]] = relationship(cascade="all, delete-orphan", order_by="Stake.id")
    milestones: Mapped[list["Milestone"]] = relationship(
        cascade="all, delete-orphan", order_by="Milestone.day"
    )


class AssetCommodity(Base):
    __tablename__ = "asset_commodities"
    __table_args__ = (UniqueConstraint("asset_id", "commodity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    commodity: Mapped[str] = mapped_column(String(16), index=True)
    role: Mapped[str] = mapped_column(
        String(12), default="primary"
    )  # primary|co_product|by_product


class StatusPeriod(Base):
    """The asset's status over a period; ``valid_to`` is open while it still holds."""

    __tablename__ = "status_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")


class Stake(Base):
    """Operator, ownership, royalty or stream relation between a company and an asset over time."""

    __tablename__ = "stakes"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    role: Mapped[str] = mapped_column(String(12))
    share_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")

    company: Mapped[Company] = relationship()


class Milestone(Base):
    """One step in an asset's life: discovery, studies, permits, construction, production ..."""

    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    day: Mapped[date] = mapped_column(Date)
    precision: Mapped[str] = mapped_column(String(8), default="year")  # day|month|year
    title: Mapped[str] = mapped_column(Text, default="")
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")


class Fact(Base):
    """One figure about a subject with its origin, definition and three points in time."""

    __tablename__ = "facts"
    __table_args__ = (Index("ix_facts_subject", "subject_type", "subject_id", "metric_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(12))
    subject_id: Mapped[int] = mapped_column(Integer)
    metric_key: Mapped[str] = mapped_column(String(32))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(32), default="")
    basis: Mapped[str] = mapped_column(String(200), default="")  # definition, e.g. cost concept
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)  # what it refers to
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)  # public since
    recorded_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)  # learned here
    provenance: Mapped[str] = mapped_column(String(12), default=Provenance.REPORTED)
    claim_kind: Mapped[str] = mapped_column(String(16), default=ClaimKind.ACTUAL)
    formula_key: Mapped[str] = mapped_column(String(48), default="")
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(8), default="medium")
    origin: Mapped[str] = mapped_column(String(8), default=DataOrigin.USER)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("research_tickets.id"), nullable=True)
    superseded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_demo: Mapped[bool] = mapped_column(default=False)

    document: Mapped["Document | None"] = relationship()


# --- Research ---------------------------------------------------------------


class Thesis(Base):
    """An investment hypothesis the user examines; evidence is linked, not copied."""

    __tablename__ = "research_theses"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    statement: Mapped[str] = mapped_column(Text, default="")
    horizon: Mapped[str] = mapped_column(String(80), default="")
    commodity: Mapped[str] = mapped_column(String(16), default="")
    status: Mapped[str] = mapped_column(String(12), default=ThesisStatus.ACTIVE)
    is_demo: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    assumptions: Mapped[list["ThesisAssumption"]] = relationship(
        cascade="all, delete-orphan", order_by="ThesisAssumption.id"
    )
    links: Mapped[list["ThesisLink"]] = relationship(
        cascade="all, delete-orphan", order_by="ThesisLink.id"
    )


class ThesisAssumption(Base):
    __tablename__ = "thesis_assumptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    thesis_id: Mapped[int] = mapped_column(ForeignKey("research_theses.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|supported|contradicted
    criterion: Mapped[str] = mapped_column(Text, default="")  # what observation would refute it
    review_by: Mapped[date | None] = mapped_column(Date, nullable=True)  # when to check again
    status_reason: Mapped[str] = mapped_column(Text, default="")  # why the status was set


class ThesisLink(Base):
    """Connects a thesis to an asset, company, finding or document with a stance."""

    __tablename__ = "thesis_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    thesis_id: Mapped[int] = mapped_column(ForeignKey("research_theses.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(12))  # asset|company|finding|document
    target_id: Mapped[int] = mapped_column(Integer)
    stance: Mapped[str] = mapped_column(String(12), default=Stance.CONTEXT)
    note: Mapped[str] = mapped_column(Text, default="")
    # the assumption this evidence speaks to, if any
    assumption_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Proposal(Base):
    """A suggested research task. Nothing runs until the user starts it."""

    __tablename__ = "proposals"
    __table_args__ = (Index("ix_proposals_subject", "subject_type", "subject_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(12))
    subject_id: Mapped[int] = mapped_column(Integer)
    thesis_id: Mapped[int | None] = mapped_column(ForeignKey("research_theses.id"), nullable=True)
    template_key: Mapped[str] = mapped_column(String(32))
    question: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    origin: Mapped[str] = mapped_column(String(8), default=DataOrigin.USER)
    value_score: Mapped[float] = mapped_column(Float, default=0.0)
    value_parts: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(12), default=ProposalState.DRAFT, index=True)
    ticket_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Ticket(Base):
    """A started research task bound to one predefined workflow and one subject."""

    __tablename__ = "research_tickets"
    __table_args__ = (Index("ix_research_tickets_claim", "status", "priority", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(12))
    subject_id: Mapped[int] = mapped_column(Integer)
    proposal_id: Mapped[int | None] = mapped_column(ForeignKey("proposals.id"), nullable=True)
    workflow: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16), default=TicketStatus.QUEUED, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=DEFAULT_PRIORITY)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    runner: Mapped[str] = mapped_column(String(32), default="")
    seen: Mapped[bool] = mapped_column(default=False)  # result acknowledged in the UI
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class Finding(Base):
    """A durable insight from a ticket or from the deterministic engine."""

    __tablename__ = "findings"
    __table_args__ = (Index("ix_findings_subject", "subject_type", "subject_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(12))
    subject_id: Mapped[int] = mapped_column(Integer)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("research_tickets.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(12), default=FindingKind.ANSWER)
    epistemic: Mapped[str] = mapped_column(String(12), default=Epistemic.HYPOTHESIS)
    rule_key: Mapped[str] = mapped_column(String(32), default="")
    text: Mapped[str] = mapped_column(Text)
    uncertainty: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


# --- Sources and events -----------------------------------------------------


class Document(Base):
    """A stored source (filing, technical report, press release) with its extracted text."""

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
    triaged: Mapped[bool] = mapped_column(default=False, index=True)


class DocumentLink(Base):
    """Which asset or company a document is about."""

    __tablename__ = "document_links"
    __table_args__ = (UniqueConstraint("document_id", "subject_type", "subject_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    subject_type: Mapped[str] = mapped_column(String(12))
    subject_id: Mapped[int] = mapped_column(Integer)

    document: Mapped[Document] = relationship()


class Event(Base):
    """A dated external event with a place (earthquake, strike, permit decision ...)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[int] = mapped_column(Integer, default=2)
    url: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(default=False)

    links: Mapped[list["EventLink"]] = relationship(cascade="all, delete-orphan")


class EventLink(Base):
    __tablename__ = "event_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    note: Mapped[str] = mapped_column(Text, default="")


class PricePoint(Base):
    """One close of a commodity price series (long history for the timeline)."""

    __tablename__ = "price_points"
    __table_args__ = (UniqueConstraint("commodity", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    commodity: Mapped[str] = mapped_column(String(16), index=True)
    day: Mapped[date] = mapped_column(Date)
    close: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="")


class ChangeEntry(Base):
    """What changed and when; feeds the 'since your last visit' report."""

    __tablename__ = "change_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, index=True)
    subject_type: Mapped[str] = mapped_column(String(12))
    subject_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))  # fact|status|stake|ticket|event|finding
    summary: Mapped[str] = mapped_column(Text)
    old: Mapped[str] = mapped_column(Text, default="")
    new: Mapped[str] = mapped_column(Text, default="")


class SystemState(Base):
    """Small key/value store (worker heartbeat, last scan, last visit)."""

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
