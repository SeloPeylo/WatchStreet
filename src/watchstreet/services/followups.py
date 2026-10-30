"""Guardrails for tickets proposed by agents.

An agent may *suggest* follow-ups; this module decides which of them become tickets. It
enforces the registry, a maximum chain depth, a per-stock backlog limit and de-duplication.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import (
    DEDUPE_WINDOW,
    LOW_PRIORITY,
    MAX_FOLLOWUP_DEPTH,
    MAX_FOLLOWUPS_PER_TICKET,
    MAX_OPEN_TICKETS_PER_STOCK,
)
from watchstreet.domain import OPEN_STATUSES, TicketOrigin, TicketStatus
from watchstreet.models import Ticket
from watchstreet.services.tickets import count_open, create_ticket
from watchstreet.timeutil import utcnow
from watchstreet.workflows.base import FollowUp
from watchstreet.workflows.definitions import REGISTRY


@dataclass(frozen=True)
class FollowUpDecision:
    workflow: str
    topic: str
    accepted: bool
    reason: str
    ticket_id: int | None = None


def _is_duplicate(session: Session, parent: Ticket, workflow: str, topic: str) -> bool:
    cutoff = utcnow() - DEDUPE_WINDOW
    rows = session.scalars(
        select(Ticket).where(Ticket.stock_id == parent.stock_id, Ticket.workflow == workflow),
    )
    for row in rows:
        same_topic = row.params.get("topic", "").casefold() == topic.casefold()
        recent = row.created_at >= cutoff or row.status in OPEN_STATUSES
        alive = row.status != TicketStatus.CANCELLED
        if same_topic and recent and alive:
            return True
    return False


def _static_rejection(parent: Ticket, proposal: FollowUp) -> str | None:
    definition = REGISTRY.get(proposal.workflow)
    if definition is None:
        return "unknown workflow"
    if definition.needs_topic and not proposal.topic.strip():
        return "topic required"
    if parent.depth + 1 > MAX_FOLLOWUP_DEPTH:
        return "max follow-up depth reached"
    return None


def _capacity_rejection(
    session: Session,
    parent: Ticket,
    proposal: FollowUp,
    accepted: int,
) -> str | None:
    if accepted >= MAX_FOLLOWUPS_PER_TICKET:
        return "too many follow-ups from one ticket"
    if count_open(session, parent.stock_id) >= MAX_OPEN_TICKETS_PER_STOCK:
        return "stock backlog full"
    if _is_duplicate(session, parent, proposal.workflow, proposal.topic.strip()):
        return "duplicate"
    return None


def _rejection(session: Session, parent: Ticket, proposal: FollowUp, accepted: int) -> str | None:
    return _static_rejection(parent, proposal) or _capacity_rejection(
        session,
        parent,
        proposal,
        accepted,
    )


def apply_followups(
    session: Session,
    parent: Ticket,
    proposals: list[FollowUp],
) -> list[FollowUpDecision]:
    """Create tickets for acceptable proposals; report a decision for each one."""
    decisions: list[FollowUpDecision] = []
    accepted = 0
    for proposal in proposals:
        topic = proposal.topic.strip()
        reason = _rejection(session, parent, proposal, accepted)
        if reason:
            decisions.append(
                FollowUpDecision(proposal.workflow, topic, accepted=False, reason=reason)
            )
            continue
        ticket = create_ticket(
            session,
            parent.stock,
            proposal.workflow,
            topic=topic,
            origin=TicketOrigin.FOLLOWUP,
            parent=parent,
            priority=LOW_PRIORITY,
            params={"reason": proposal.reason},
        )
        accepted += 1
        decisions.append(
            FollowUpDecision(
                proposal.workflow,
                topic,
                accepted=True,
                reason="created",
                ticket_id=ticket.id,
            )
        )
    return decisions
