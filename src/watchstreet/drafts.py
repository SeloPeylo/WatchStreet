"""Result and draft types a workflow hands to the harness (pure data, no behaviour).

They live below ``services`` so the knowledge store can persist them without importing the
workflow layer. Workflows build them, ``services.knowledge`` / ``services.followups`` consume them.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from watchstreet.domain import InsightCategory, ThesisStatus


@dataclass(frozen=True)
class FollowUp:
    workflow: str
    topic: str = ""
    reason: str = ""


@dataclass(frozen=True)
class InsightDraft:
    category: InsightCategory
    text: str
    document_id: int | None = None


@dataclass(frozen=True)
class ScoreDraft:
    scheme: str
    value: float
    label: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ThesisDraft:
    text: str
    status: ThesisStatus


@dataclass(frozen=True)
class DatapointDraft:
    key: str
    subject: str = ""
    value: float | None = None
    text: str = ""
    unit: str = ""
    source: str = ""
    confidence: str = "medium"
    as_of: date | None = None
    origin: str = "agent"
    document_id: int | None = None
    quote: str = ""


@dataclass(frozen=True)
class EntityDraft:
    name: str
    kind: str
    country: str = ""
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True)
class RelationDraft:
    source: EntityDraft
    target: EntityDraft
    kind: str
    strength: float | None = None
    note: str = ""
    document_id: int | None = None
    quote: str = ""
    confidence: str = "low"


@dataclass(frozen=True)
class IntelDraft:
    headline: str
    category: str = "company"
    severity: int = 2
    summary: str = ""
    why_it_matters: str = ""
    document_id: int | None = None
    source_url: str = ""
    country: str = ""
    lat: float | None = None
    lon: float | None = None
    commodities: tuple[str, ...] = ()
    quote: str = ""
    impacts: tuple[tuple[int, str, str], ...] = ()  # (stock_id, direction, note)
    extra_sources: tuple[tuple[str, str, str], ...] = ()  # (title, url, publisher)
    dedupe_key: str = ""
    published_at: datetime | None = None


@dataclass(frozen=True)
class ProfileDraft:
    profile: str
    reason: str = ""


@dataclass(frozen=True)
class BriefingDraft:
    headline: str
    bullets: list[str]
    focus: str = ""
    author: str = "rules"


@dataclass
class WorkflowResult:
    summary: str
    insights: list[InsightDraft] = field(default_factory=list)
    scores: list[ScoreDraft] = field(default_factory=list)
    thesis: ThesisDraft | None = None
    followups: list[FollowUp] = field(default_factory=list)
    datapoints: list[DatapointDraft] = field(default_factory=list)
    relations: list[RelationDraft] = field(default_factory=list)
    intel: list[IntelDraft] = field(default_factory=list)
    profile: ProfileDraft | None = None
    briefing: BriefingDraft | None = None
    data: dict[str, Any] = field(default_factory=dict)
