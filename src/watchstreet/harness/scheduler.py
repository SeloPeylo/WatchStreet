"""Periodic jobs: scan for events and refresh stale analyses."""

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import (
    LAST_SCAN_KEY,
    LOW_PRIORITY,
    MAX_EVENTS_PER_REVIEW,
    MAX_OPEN_TICKETS_PER_STOCK,
    REFRESH_INTERVALS,
    SCAN_REQUEST_KEY,
    SECONDS_PER_MINUTE,
)
from watchstreet.container import Container
from watchstreet.db import session_scope
from watchstreet.domain import TicketOrigin, TicketStatus, WorkflowKey
from watchstreet.intel.ingest import run_ingest, seed_feeds
from watchstreet.market.base import MarketDataError
from watchstreet.models import MarketEvent, Stock, Ticket
from watchstreet.services.state import touch, updated_at
from watchstreet.services.tickets import count_open, create_ticket
from watchstreet.timeutil import utcnow
from watchstreet.workflows.definitions import get_workflow

logger = logging.getLogger(__name__)


def scan_stock_events(container: Container, session: Session, stock: Stock) -> Ticket | None:
    """Store unseen news for a stock and open one review ticket for them."""
    try:
        items = container.market.news(stock.symbol)
    except MarketDataError:
        logger.warning("News fetch failed for %s", stock.symbol)
        return None
    known = set(
        session.scalars(select(MarketEvent.external_id).where(MarketEvent.stock_id == stock.id)),
    )
    fresh = [
        MarketEvent(
            stock_id=stock.id,
            external_id=item.external_id,
            source=item.source,
            title=item.title,
            url=item.url,
            published_at=item.published_at,
        )
        for item in items
        if item.external_id not in known
    ]
    session.add_all(fresh)
    session.flush()
    if not fresh or count_open(session, stock.id) >= MAX_OPEN_TICKETS_PER_STOCK:
        return None
    batch = sorted(fresh, key=lambda e: e.published_at, reverse=True)[:MAX_EVENTS_PER_REVIEW]
    ticket = create_ticket(
        session,
        stock,
        WorkflowKey.EVENT_REVIEW,
        origin=TicketOrigin.EVENT,
        priority=LOW_PRIORITY,
        params={"event_ids": [e.id for e in batch]},
        title=f"Ereignis-Prüfung – {stock.symbol} ({len(batch)} neue Meldungen)",
    )
    for event in batch:
        event.reviewed, event.ticket_id = True, ticket.id
    return ticket


def _has_recent(session: Session, stock_id: int, workflow: str, window: timedelta) -> bool:
    cutoff = utcnow() - window
    return (
        session.scalar(
            select(Ticket.id)
            .where(
                Ticket.stock_id == stock_id,
                Ticket.workflow == workflow,
                Ticket.status != TicketStatus.CANCELLED,
                Ticket.created_at >= cutoff,
            )
            .limit(1),
        )
        is not None
    )


def schedule_refreshes(session: Session, stock: Stock) -> list[Ticket]:
    """Create periodic refresh tickets, but only for stocks whose first assessment is done."""
    assessed = any(t.status == TicketStatus.DONE for t in stock.tickets)
    if not assessed or count_open(session, stock.id) >= MAX_OPEN_TICKETS_PER_STOCK:
        return []
    created: list[Ticket] = []
    for key, window in REFRESH_INTERVALS.items():
        if key == WorkflowKey.THESIS_CHECK and not stock.theses:
            continue
        if _has_recent(session, stock.id, key, window):
            continue
        created.append(
            create_ticket(
                session,
                stock,
                get_workflow(key).key,
                origin=TicketOrigin.SCHEDULE,
                priority=LOW_PRIORITY,
            ),
        )
    return created


def run_scan(container: Container) -> int:
    """One scan over all stocks; returns the number of tickets created."""
    created = 0
    with session_scope(container.session_factory) as session:
        seed_feeds(session)
        for stock in session.scalars(select(Stock)):
            created += scan_stock_events(container, session, stock) is not None
            created += len(schedule_refreshes(session, stock))
        touch(session, LAST_SCAN_KEY)
    created += run_ingest(container).tickets
    return created


def scan_due(container: Container) -> bool:
    with session_scope(container.session_factory) as session:
        last = updated_at(session, LAST_SCAN_KEY)
        requested = updated_at(session, SCAN_REQUEST_KEY)
    if requested is not None and (last is None or requested > last):
        return True
    interval = container.settings.event_scan_interval_min * SECONDS_PER_MINUTE
    return last is None or (utcnow() - last).total_seconds() >= interval
