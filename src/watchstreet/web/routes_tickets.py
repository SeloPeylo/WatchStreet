"""Ticket area: list, detail, retry/cancel and the status endpoint used by live updates."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from watchstreet.domain import TicketStatus
from watchstreet.models import Insight, MarketEvent, Ticket
from watchstreet.services import tickets
from watchstreet.web.deps import SessionDep
from watchstreet.web.helpers import get_or_404, redirect, render
from watchstreet.workflows.definitions import REGISTRY

router = APIRouter()

STATUS_POLL_MAX_IDS = 50


@router.get("/tickets", response_class=HTMLResponse)
def tickets_page(request: Request, session: SessionDep, status: str = "") -> HTMLResponse:
    rows = tickets.list_tickets(session, status or None)
    return render(
        request,
        "tickets.html",
        tickets=rows,
        status=status,
        statuses=[s.value for s in TicketStatus],
    )


@router.get("/api/tickets/status")
def api_ticket_status(session: SessionDep, ids: str = "") -> list[dict[str, str | int]]:
    """Lightweight status lookup used by the live-update script (``?ids=1,2,3``)."""
    wanted = [int(part) for part in ids.split(",") if part.strip().isdigit()][:STATUS_POLL_MAX_IDS]
    if not wanted:
        return []
    rows = session.scalars(select(Ticket).where(Ticket.id.in_(wanted)))
    return [{"id": ticket.id, "status": ticket.status} for ticket in rows]


@router.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_page(ticket_id: int, request: Request, session: SessionDep) -> HTMLResponse:
    ticket = get_or_404(session, Ticket, ticket_id)
    insights = list(session.scalars(select(Insight).where(Insight.ticket_id == ticket.id)))
    events = list(session.scalars(select(MarketEvent).where(MarketEvent.ticket_id == ticket.id)))
    return render(
        request,
        "ticket.html",
        ticket=ticket,
        insights=insights,
        events=events,
        workflow=REGISTRY.get(ticket.workflow),
    )


@router.post("/tickets/{ticket_id}/retry")
def ticket_retry(ticket_id: int, session: SessionDep) -> RedirectResponse:
    tickets.retry(session, get_or_404(session, Ticket, ticket_id))
    return redirect(f"/tickets/{ticket_id}", "ticket_retried")


@router.post("/tickets/{ticket_id}/cancel")
def ticket_cancel(ticket_id: int, session: SessionDep) -> RedirectResponse:
    tickets.cancel(session, get_or_404(session, Ticket, ticket_id))
    return redirect(f"/tickets/{ticket_id}", "ticket_cancelled")
