"""Ticket creation, claiming and lifecycle."""

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from watchstreet.constants import CLAIM_ATTEMPTS, DEFAULT_PRIORITY, LIST_LIMIT, STUCK_TICKET_TIMEOUT
from watchstreet.domain import TicketStatus
from watchstreet.models import Ticket
from watchstreet.timeutil import utcnow


def create_ticket(  # noqa: PLR0913
    session: Session,
    subject_type: str,
    subject_id: int,
    workflow: str,
    title: str,
    *,
    params: dict[str, Any] | None = None,
    proposal_id: int | None = None,
    priority: int = DEFAULT_PRIORITY,
) -> Ticket:
    ticket = Ticket(
        subject_type=subject_type,
        subject_id=subject_id,
        workflow=workflow,
        title=title,
        params=dict(params or {}),
        proposal_id=proposal_id,
        priority=priority,
    )
    session.add(ticket)
    session.flush()
    return ticket


def claim_next(session: Session) -> Ticket | None:
    """Move the best queued ticket to running; ``None`` if nothing is queued.

    The claim is a conditional ``UPDATE ... WHERE status = 'queued'``, so concurrent workers can
    never both win the same ticket. The caller owns the transaction.
    """
    for _ in range(CLAIM_ATTEMPTS):
        candidate = session.scalars(
            select(Ticket.id)
            .where(Ticket.status == TicketStatus.QUEUED)
            .order_by(Ticket.priority.desc(), Ticket.id)
            .limit(1),
        ).first()
        if candidate is None:
            return None
        claimed = session.execute(
            update(Ticket)
            .where(Ticket.id == candidate, Ticket.status == TicketStatus.QUEUED)
            .values(status=TicketStatus.RUNNING, started_at=utcnow()),
        )
        if claimed.rowcount == 1:  # type: ignore[attr-defined]
            return session.get(Ticket, candidate)
    return None


def requeue_stuck(session: Session) -> int:
    """Tickets left ``running`` by a crashed worker go back to the queue."""
    cutoff = utcnow() - STUCK_TICKET_TIMEOUT
    result = session.execute(
        update(Ticket)
        .where(Ticket.status == TicketStatus.RUNNING, Ticket.started_at < cutoff)
        .values(status=TicketStatus.QUEUED, started_at=None),
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


def retry(session: Session, ticket: Ticket) -> None:
    if ticket.status not in (TicketStatus.FAILED, TicketStatus.CANCELLED):
        return
    ticket.status = TicketStatus.QUEUED
    ticket.error = ""
    ticket.started_at = None
    ticket.finished_at = None
    session.flush()


def cancel(session: Session, ticket: Ticket) -> None:
    if ticket.status == TicketStatus.QUEUED:
        ticket.status = TicketStatus.CANCELLED
        ticket.finished_at = utcnow()
        session.flush()


def list_tickets(session: Session, status: str | None = None) -> list[Ticket]:
    query = select(Ticket).order_by(Ticket.id.desc()).limit(LIST_LIMIT)
    if status:
        query = query.where(Ticket.status == status)
    return list(session.scalars(query))
