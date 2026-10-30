"""Run a single ticket through its workflow and persist the outcome."""

import logging
from dataclasses import asdict

from watchstreet.constants import BRIEFING_PRIORITY
from watchstreet.container import Container
from watchstreet.db import session_scope
from watchstreet.domain import TicketOrigin, TicketStatus, WorkflowKey
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


def execute_ticket(container: Container, ticket_id: int) -> TicketStatus:
    """Run the ticket's workflow. Never raises: failures are recorded on the ticket."""
    try:
        with session_scope(container.session_factory) as session:
            ticket = session.get(Ticket, ticket_id)
            if ticket is None:
                return TicketStatus.FAILED
            workflow = get_workflow(ticket.workflow)
            ctx = WorkflowContext(
                session,
                ticket,
                ticket.stock,
                container.market,
                container.runner,
                followup_check=lambda proposal, accepted: rejection_reason(
                    session,
                    ticket,
                    proposal,
                    accepted,
                ),
            )
            result = workflow.run(ctx)
            store_result(session, ticket, result)
            decisions = apply_followups(session, ticket, result.followups)
            ticket.summary = result.summary
            ticket.result = {
                "data": result.data,
                "scores": [asdict(s) for s in result.scores],
                "followups": [asdict(d) for d in decisions],
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
    except Exception as exc:  # harness boundary: record, never crash the worker
        logger.exception("Ticket %s failed", ticket_id)
        _fail(container, ticket_id, f"{type(exc).__name__}: {exc}")
        return TicketStatus.FAILED
    return TicketStatus.DONE
