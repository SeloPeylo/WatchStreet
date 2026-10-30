"""Ticket creation, claiming and lifecycle."""

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from watchstreet.constants import DEFAULT_PRIORITY, LIST_LIMIT, STUCK_TICKET_TIMEOUT
from watchstreet.domain import OPEN_STATUSES, TicketOrigin, TicketStatus, WorkflowKey
from watchstreet.models import Stock, Ticket
from watchstreet.timeutil import utcnow
from watchstreet.workflow_specs import get_spec


def create_ticket(  # noqa: PLR0913
    session: Session,
    stock: Stock,
    workflow: WorkflowKey | str,
    *,
    topic: str = "",
    origin: TicketOrigin = TicketOrigin.USER,
    parent: Ticket | None = None,
    priority: int = DEFAULT_PRIORITY,
    params: dict[str, Any] | None = None,
    title: str = "",
) -> Ticket:
    definition = get_spec(workflow)
    merged = dict(params or {})
    if topic:
        merged["topic"] = topic
    ticket = Ticket(
        stock_id=stock.id,
        workflow=definition.key,
        title=title or definition.default_title(stock.symbol, topic),
        origin=origin,
        priority=priority,
        depth=(parent.depth + 1) if parent else 0,
        parent_id=parent.id if parent else None,
        params=merged,
    )
    session.add(ticket)
    session.flush()
    return ticket


def ensure_open(
    session: Session,
    stock: Stock,
    workflow: WorkflowKey,
    *,
    origin: TicketOrigin,
    priority: int = DEFAULT_PRIORITY,
) -> Ticket:
    """Return the queued/running ticket of this workflow for the stock, creating one if absent."""
    existing = session.scalars(
        select(Ticket).where(
            Ticket.stock_id == stock.id,
            Ticket.workflow == workflow,
            Ticket.status.in_(OPEN_STATUSES),
        ),
    ).first()
    if existing:
        return existing
    return create_ticket(session, stock, workflow, origin=origin, priority=priority)


def claim_next(session: Session) -> Ticket | None:
    """Atomically move the best queued ticket to running; ``None`` if nothing is queued."""
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
    session.commit()
    if claimed.rowcount != 1:  # type: ignore[attr-defined]
        return None
    return session.get(Ticket, candidate)


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


def list_tickets(
    session: Session,
    status: str | None = None,
    stock_id: int | None = None,
) -> list[Ticket]:
    query = select(Ticket).order_by(Ticket.id.desc()).limit(LIST_LIMIT)
    if status:
        query = query.where(Ticket.status == status)
    if stock_id:
        query = query.where(Ticket.stock_id == stock_id)
    return list(session.scalars(query))


def count_open(session: Session, stock_id: int) -> int:
    return len(
        list(
            session.scalars(
                select(Ticket.id).where(
                    Ticket.stock_id == stock_id,
                    Ticket.status.in_(OPEN_STATUSES),
                ),
            ),
        ),
    )
