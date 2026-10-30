"""Run a single ticket through its workflow and persist the outcome."""

import logging
from dataclasses import asdict

from sqlalchemy.orm import Session

from watchstreet.constants import BRIEFING_PRIORITY
from watchstreet.container import Container
from watchstreet.db import session_scope
from watchstreet.domain import TicketOrigin, TicketStatus, WorkflowKey
from watchstreet.drafts import WorkflowResult
from watchstreet.models import Ticket
from watchstreet.services.followups import apply_followups, rejection_reason
from watchstreet.services.knowledge import store_result
from watchstreet.services.tickets import ensure_open
from watchstreet.timeutil import utcnow
from watchstreet.workflows.base import WorkflowContext
from watchstreet.workflows.definitions import get_workflow

logger = logging.getLogger(__name__)
ERROR_MAX_CHARS = 2000


def _fail(container: Container, ticket_id: int, error: str) -> None:
    with session_scope(container.session_factory) as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            return
        ticket.status = TicketStatus.FAILED
        ticket.error = error[:ERROR_MAX_CHARS]
        ticket.runner = container.runner.name
        ticket.finished_at = utcnow()


def _build_context(container: Container, session: Session, ticket: Ticket) -> WorkflowContext:
    """Everything a workflow may touch; the guardrail preview is bound to this ticket."""
    return WorkflowContext(
        session,
        ticket,
        ticket.stock,
        container.market,
        container.runner,
        edgar=container.edgar,
        followup_check=lambda proposal, accepted: rejection_reason(
            session,
            ticket,
            proposal,
            accepted,
        ),
    )


def _record_success(
    container: Container,
    session: Session,
    ticket: Ticket,
    result: WorkflowResult,
) -> None:
    """Persist knowledge and follow-ups, mark the ticket done and queue a fresh briefing."""
    store_result(session, ticket, result)
    decisions = apply_followups(session, ticket, result.followups)
    ticket.summary = result.summary
    ticket.result = {
        "data": result.data,
        "scores": [asdict(score) for score in result.scores],
        "followups": [asdict(decision) for decision in decisions],
    }
    ticket.runner = container.runner.name
    ticket.status = TicketStatus.DONE
    ticket.finished_at = utcnow()
    if ticket.workflow != WorkflowKey.BRIEFING:
        ensure_open(
            session,
            ticket.stock,
            WorkflowKey.BRIEFING,
            origin=TicketOrigin.SCHEDULE,
            priority=BRIEFING_PRIORITY,
        )


def execute_ticket(container: Container, ticket_id: int) -> TicketStatus:
    """Run the ticket's workflow. Never raises: failures are recorded on the ticket."""
    try:
        with session_scope(container.session_factory) as session:
            ticket = session.get(Ticket, ticket_id)
            if ticket is None:
                return TicketStatus.FAILED
            workflow = get_workflow(ticket.workflow)
            result = workflow.run(_build_context(container, session, ticket))
            _record_success(container, session, ticket, result)
    except Exception as exc:  # harness boundary: record, never crash the worker
        logger.exception("Ticket %s failed", ticket_id)
        _fail(container, ticket_id, f"{type(exc).__name__}: {exc}")
        return TicketStatus.FAILED
    return TicketStatus.DONE
