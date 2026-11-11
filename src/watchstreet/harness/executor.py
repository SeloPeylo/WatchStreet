"""Run a single ticket through its workflow and persist the outcome."""

import logging

from watchstreet.container import Container
from watchstreet.db import session_scope
from watchstreet.domain import TicketStatus
from watchstreet.models import Ticket
from watchstreet.services.viewing import build_view
from watchstreet.timeutil import utcnow
from watchstreet.workflows.research import ResearchContext, run_workflow

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
            run_workflow(
                ResearchContext(
                    session=session,
                    ticket=ticket,
                    runner=container.runner,
                    fetcher=container.fetcher,
                    view=build_view(session, container.market),
                    is_demo=container.is_demo,
                )
            )
            ticket.runner = container.runner.name
            ticket.status = TicketStatus.DONE
            ticket.finished_at = utcnow()
    except Exception as exc:  # harness boundary: record, never crash the worker
        logger.exception("Ticket %s failed", ticket_id)
        _fail(container, ticket_id, f"{type(exc).__name__}: {exc}")
        return TicketStatus.FAILED
    return TicketStatus.DONE
