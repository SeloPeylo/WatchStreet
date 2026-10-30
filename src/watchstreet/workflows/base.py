"""Workflow contract and result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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


@dataclass
class WorkflowResult:
    summary: str
    insights: list[InsightDraft] = field(default_factory=list)
    scores: list[ScoreDraft] = field(default_factory=list)
    thesis: ThesisDraft | None = None
    followups: list[FollowUp] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowContext:
    session: Session
    ticket: Ticket
    stock: Stock
    market: MarketService
    runner: AgentRunner


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
