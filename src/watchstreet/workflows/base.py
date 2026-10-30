"""Workflow contract and result types."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from watchstreet.agents.base import AgentRunner
from watchstreet.domain import InsightCategory, ThesisStatus, WorkflowKey
from watchstreet.market.service import MarketService
from watchstreet.models import Stock, Ticket


@dataclass(frozen=True)
class FollowUp:
    workflow: str
    topic: str = ""
    reason: str = ""


@dataclass(frozen=True)
class InsightDraft:
    category: InsightCategory
    text: str


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
    profile: ProfileDraft | None = None
    briefing: BriefingDraft | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowContext:
    session: Session
    ticket: Ticket
    stock: Stock
    market: MarketService
    runner: AgentRunner
    # Guardrail preview supplied by the harness: (proposal, already_accepted) -> rejection reason
    followup_check: Callable[[FollowUp, int], str | None] | None = None


class Workflow(ABC):
    """A predefined, named procedure a ticket is bound to."""

    key: WorkflowKey
    label: str
    description: str
    user_creatable: bool = True
    needs_topic: bool = False

    @abstractmethod
    def run(self, ctx: WorkflowContext) -> WorkflowResult: ...

    def default_title(self, stock: Stock, topic: str) -> str:
        suffix = f": {topic}" if topic else ""
        return f"{self.label} – {stock.symbol}{suffix}"
