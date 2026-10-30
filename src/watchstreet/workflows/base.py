"""Workflow contract: the context a workflow runs in and the abstract base class."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from watchstreet.agents.base import AgentRunner
from watchstreet.domain import WorkflowKey
from watchstreet.drafts import FollowUp, WorkflowResult
from watchstreet.intel.connectors.edgar import EdgarClient
from watchstreet.market.service import MarketService
from watchstreet.models import Stock, Ticket
from watchstreet.workflow_specs import WorkflowSpec, get_spec


@dataclass
class WorkflowContext:
    session: Session
    ticket: Ticket
    stock: Stock
    market: MarketService
    runner: AgentRunner
    # Guardrail preview supplied by the harness: (proposal, already_accepted) -> rejection reason
    followup_check: Callable[[FollowUp, int], str | None] | None = None
    edgar: EdgarClient | None = None


class Workflow(ABC):
    """A predefined, named procedure a ticket is bound to.

    Presentation and ticket rules (label, description, ``user_creatable``, ``needs_topic``) come
    from the declarative catalogue in ``watchstreet.workflow_specs``.
    """

    key: WorkflowKey

    @property
    def spec(self) -> WorkflowSpec:
        return get_spec(self.key)

    @property
    def label(self) -> str:
        return self.spec.label

    @property
    def description(self) -> str:
        return self.spec.description

    @property
    def user_creatable(self) -> bool:
        return self.spec.user_creatable

    @property
    def needs_topic(self) -> bool:
        return self.spec.needs_topic

    @abstractmethod
    def run(self, ctx: WorkflowContext) -> WorkflowResult: ...

    def default_title(self, stock: Stock, topic: str) -> str:
        return self.spec.default_title(stock.symbol, topic)
