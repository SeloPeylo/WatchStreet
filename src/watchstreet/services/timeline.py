"""Merge everything that happened to a stock into one chronological feed."""

from dataclasses import dataclass
from datetime import datetime

from watchstreet.constants import TIMELINE_LIMIT
from watchstreet.domain import TicketStatus
from watchstreet.models import Stock


@dataclass(frozen=True)
class TimelineEntry:
    at: datetime
    kind: str
    text: str
    ticket_id: int | None = None
    url: str = ""


def build_timeline(stock: Stock) -> list[TimelineEntry]:
    entries: list[TimelineEntry] = []
    for ticket in stock.tickets:
        entries.append(
            TimelineEntry(
                ticket.created_at, "ticket", f"Ticket erstellt: {ticket.title}", ticket.id
            )
        )
        if ticket.status == TicketStatus.DONE and ticket.finished_at:
            entries.append(
                TimelineEntry(
                    ticket.finished_at, "done", ticket.summary or ticket.title, ticket.id
                ),
            )
        if ticket.status == TicketStatus.FAILED and ticket.finished_at:
            entries.append(
                TimelineEntry(
                    ticket.finished_at, "failed", f"Fehlgeschlagen: {ticket.title}", ticket.id
                ),
            )
    entries += [
        TimelineEntry(t.created_at, "thesis", f"These ({t.status}): {t.text}", t.ticket_id)
        for t in stock.theses
    ]
    entries += [
        TimelineEntry(
            s.created_at, "score", f"Score {s.scheme}: {s.value} ({s.label})", s.ticket_id
        )
        for s in stock.scores
    ]
    entries += [
        TimelineEntry(e.published_at, "event", e.title, e.ticket_id, e.url) for e in stock.events
    ]
    entries.sort(key=lambda e: e.at, reverse=True)
    return entries[:TIMELINE_LIMIT]
