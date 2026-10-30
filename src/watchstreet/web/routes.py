"""HTTP routes (server-rendered pages plus a few JSON endpoints)."""

from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Annotated, Any

import markdown
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import (
    DEFAULT_INTERVAL,
    HEARTBEAT_STALE_AFTER,
    INTERVAL_RANGES,
    LAST_SCAN_KEY,
    RECENT_LIMIT,
    WORKER_HEARTBEAT_KEY,
)
from watchstreet.container import Container
from watchstreet.domain import InsightCategory, TicketOrigin, TicketStatus
from watchstreet.market.base import MarketDataError
from watchstreet.models import Holding, Insight, MarketEvent, Stock, Ticket, WatchEntry
from watchstreet.services import portfolio, tickets
from watchstreet.services.portfolio import PortfolioError
from watchstreet.services.state import updated_at
from watchstreet.services.timeline import build_timeline
from watchstreet.timeutil import utcnow
from watchstreet.web.deps import ContainerDep, SessionDep
from watchstreet.web.formatting import register_filters
from watchstreet.workflows.definitions import REGISTRY, user_workflows

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")
register_filters(templates.env)
router = APIRouter()

FormStr = Annotated[str, Form()]
MANUAL_FILE = "user-manual.md"
MANUAL_IMAGE_PREFIX = "screenshots/"


def _number(raw: str, label: str) -> float:
    try:
        return float(raw.strip().replace(",", "."))
    except ValueError as exc:
        msg = f"{label} ist keine Zahl"
        raise PortfolioError(msg) from exc


def _date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        msg = "Kaufdatum muss das Format JJJJ-MM-TT haben"
        raise PortfolioError(msg) from exc


def _render(request: Request, name: str, status_code: int = 200, **ctx: Any) -> HTMLResponse:
    ctx.setdefault("error", None)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# ------------------------------------------------------------------ dashboard
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: SessionDep, container: ContainerDep) -> HTMLResponse:
    rows = portfolio.holding_rows(session, container.market)
    counts = Counter(session.scalars(select(Ticket.status)))
    recent_tickets = list(
        session.scalars(select(Ticket).order_by(Ticket.id.desc()).limit(RECENT_LIMIT)),
    )
    recent_insights = list(
        session.scalars(select(Insight).order_by(Insight.id.desc()).limit(RECENT_LIMIT)),
    )
    stocks = {s.id: s for s in session.scalars(select(Stock))}
    return _render(
        request,
        "dashboard.html",
        rows=rows,
        totals=portfolio.totals_by_currency(rows),
        counts=counts,
        recent_tickets=recent_tickets,
        recent_insights=recent_insights,
        stocks=stocks,
        watch_count=len(list(session.scalars(select(WatchEntry.id)))),
        system=_system_status(session, container),
    )


# ------------------------------------------------------------------ holdings
@router.get("/holdings", response_class=HTMLResponse)
def holdings_page(request: Request, session: SessionDep, container: ContainerDep) -> HTMLResponse:
    rows = portfolio.holding_rows(session, container.market)
    return _render(
        request,
        "holdings.html",
        rows=rows,
        totals=portfolio.totals_by_currency(rows),
        form={},
    )


class HoldingForm(BaseModel):
    symbol: str
    quantity: str
    avg_price: str
    bought_at: str = ""
    intent: str = ""


@router.post("/holdings", response_model=None)
def holdings_add(
    request: Request,
    session: SessionDep,
    container: ContainerDep,
    form: Annotated[HoldingForm, Form()],
) -> Response:
    try:
        portfolio.add_holding(
            session,
            container.market,
            portfolio.NewHolding(
                form.symbol,
                _number(form.quantity, "Menge"),
                _number(form.avg_price, "Durchschnittspreis"),
                _date(form.bought_at),
                form.intent,
            ),
        )
    except PortfolioError as exc:
        session.rollback()
        rows = portfolio.holding_rows(session, container.market)
        return _render(
            request,
            "holdings.html",
            400,
            rows=rows,
            totals=portfolio.totals_by_currency(rows),
            form=form.model_dump(),
            error=str(exc),
        )
    return _redirect("/holdings")


@router.post("/holdings/{holding_id}/update", response_model=None)
def holdings_update(
    holding_id: int,
    session: SessionDep,
    quantity: FormStr,
    avg_price: FormStr,
    bought_at: FormStr = "",
    intent: FormStr = "",
) -> Response:
    holding = session.get(Holding, holding_id)
    if holding is None:
        raise HTTPException(404)
    try:
        portfolio.update_holding(
            session,
            holding,
            _number(quantity, "Menge"),
            _number(avg_price, "Durchschnittspreis"),
            _date(bought_at),
            intent,
        )
    except PortfolioError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _redirect(f"/stocks/{holding.stock_id}")


@router.post("/holdings/{holding_id}/delete")
def holdings_delete(holding_id: int, session: SessionDep) -> RedirectResponse:
    holding = session.get(Holding, holding_id)
    if holding is None:
        raise HTTPException(404)
    portfolio.remove_holding(session, holding)
    return _redirect("/holdings")


# ------------------------------------------------------------------ watchlist
@router.get("/watchlist", response_class=HTMLResponse)
def watchlist_page(request: Request, session: SessionDep, container: ContainerDep) -> HTMLResponse:
    entries = list(session.scalars(select(WatchEntry).order_by(WatchEntry.id)))
    quotes = {e.stock_id: container.market.try_quote(e.stock.symbol) for e in entries}
    return _render(request, "watchlist.html", entries=entries, quotes=quotes, form={})


@router.post("/watchlist", response_model=None)
def watchlist_add(
    request: Request,
    session: SessionDep,
    container: ContainerDep,
    symbol: FormStr,
    note: FormStr = "",
) -> Response:
    try:
        portfolio.add_watch(session, container.market, symbol, note)
    except PortfolioError as exc:
        session.rollback()
        entries = list(session.scalars(select(WatchEntry).order_by(WatchEntry.id)))
        quotes = {e.stock_id: container.market.try_quote(e.stock.symbol) for e in entries}
        return _render(
            request,
            "watchlist.html",
            400,
            entries=entries,
            quotes=quotes,
            form={"symbol": symbol, "note": note},
            error=str(exc),
        )
    return _redirect("/watchlist")


@router.post("/watchlist/{entry_id}/delete")
def watchlist_delete(entry_id: int, session: SessionDep) -> RedirectResponse:
    entry = session.get(WatchEntry, entry_id)
    if entry is None:
        raise HTTPException(404)
    portfolio.remove_watch(session, entry)
    return _redirect("/watchlist")


@router.get("/api/search")
def api_search(q: str, container: ContainerDep) -> list[dict[str, str]]:
    try:
        return [asdict(m) for m in container.market.search(q)]
    except MarketDataError:
        return []


# ------------------------------------------------------------------ stock detail
def _latest_per_scheme(stock: Stock) -> list[dict[str, Any]]:
    grouped: dict[str, list[Any]] = {}
    for score in stock.scores:  # newest first
        grouped.setdefault(score.scheme, []).append(score)
    return [
        {"latest": rows[0], "history": [r.value for r in reversed(rows)][-RECENT_LIMIT * 2 :]}
        for rows in grouped.values()
    ]


@router.get("/stocks/{stock_id}", response_class=HTMLResponse)
def stock_page(
    stock_id: int,
    request: Request,
    session: SessionDep,
    container: ContainerDep,
) -> HTMLResponse:
    stock = session.get(Stock, stock_id)
    if stock is None:
        raise HTTPException(404)
    quote = container.market.try_quote(stock.symbol)
    row = next(
        (
            r
            for r in portfolio.holding_rows(session, container.market)
            if r.holding.stock_id == stock.id
        ),
        None,
    )
    goal = next((i for i in stock.insights if i.category == InsightCategory.GOAL), None)
    return _render(
        request,
        "stock.html",
        stock=stock,
        quote=quote,
        row=row,
        goal=goal,
        scores=_latest_per_scheme(stock),
        timeline=build_timeline(stock),
        workflows=user_workflows(),
        intervals=list(INTERVAL_RANGES),
        default_interval=DEFAULT_INTERVAL,
    )


@router.get("/api/stocks/{stock_id}/candles")
def api_candles(
    stock_id: int,
    session: SessionDep,
    container: ContainerDep,
    interval: str = DEFAULT_INTERVAL,
) -> list[dict[str, float | int]]:
    stock = session.get(Stock, stock_id)
    if stock is None:
        raise HTTPException(404)
    if interval not in INTERVAL_RANGES:
        raise HTTPException(400, "Unbekanntes Intervall")
    try:
        candles = container.market.candles(stock.symbol, interval)
    except MarketDataError as exc:
        raise HTTPException(502, str(exc)) from exc
    return [
        {
            "t": int(c.time.timestamp()),
            "o": c.open,
            "h": c.high,
            "l": c.low,
            "c": c.close,
            "v": c.volume,
        }
        for c in candles
    ]


@router.post("/stocks/{stock_id}/tickets")
def stock_ticket_create(
    stock_id: int,
    session: SessionDep,
    workflow: FormStr,
    topic: FormStr = "",
) -> RedirectResponse:
    stock = session.get(Stock, stock_id)
    definition = REGISTRY.get(workflow)
    if stock is None or definition is None or not definition.user_creatable:
        raise HTTPException(404)
    if definition.needs_topic and not topic.strip():
        raise HTTPException(400, "Für dieses Ticket wird ein Thema benötigt")
    tickets.create_ticket(session, stock, workflow, topic=topic.strip(), origin=TicketOrigin.USER)
    return _redirect(f"/stocks/{stock.id}")


# ------------------------------------------------------------------ tickets
@router.get("/tickets", response_class=HTMLResponse)
def tickets_page(request: Request, session: SessionDep, status: str = "") -> HTMLResponse:
    rows = tickets.list_tickets(session, status or None)
    return _render(
        request,
        "tickets.html",
        tickets=rows,
        status=status,
        statuses=[s.value for s in TicketStatus],
    )


@router.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_page(ticket_id: int, request: Request, session: SessionDep) -> HTMLResponse:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(404)
    insights = list(session.scalars(select(Insight).where(Insight.ticket_id == ticket.id)))
    events = list(session.scalars(select(MarketEvent).where(MarketEvent.ticket_id == ticket.id)))
    return _render(
        request,
        "ticket.html",
        ticket=ticket,
        insights=insights,
        events=events,
        workflow=REGISTRY.get(ticket.workflow),
    )


@router.post("/tickets/{ticket_id}/retry")
def ticket_retry(ticket_id: int, session: SessionDep) -> RedirectResponse:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(404)
    tickets.retry(session, ticket)
    return _redirect(f"/tickets/{ticket_id}")


@router.post("/tickets/{ticket_id}/cancel")
def ticket_cancel(ticket_id: int, session: SessionDep) -> RedirectResponse:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(404)
    tickets.cancel(session, ticket)
    return _redirect(f"/tickets/{ticket_id}")


# ------------------------------------------------------------------ system + manual
def _system_status(session: Session, container: Container) -> dict[str, Any]:
    beat = updated_at(session, WORKER_HEARTBEAT_KEY)
    return {
        "market": container.market.name,
        "runner": container.runner.name,
        "worker_alive": beat is not None and utcnow() - beat < HEARTBEAT_STALE_AFTER,
        "worker_beat": beat,
        "last_scan": updated_at(session, LAST_SCAN_KEY),
        "scan_interval": container.settings.event_scan_interval_min,
    }


@router.get("/system", response_class=HTMLResponse)
def system_page(request: Request, session: SessionDep, container: ContainerDep) -> HTMLResponse:
    return _render(
        request,
        "system.html",
        system=_system_status(session, container),
        workflows=list(REGISTRY.values()),
    )


@router.get("/manual", response_class=HTMLResponse)
def manual_page(request: Request, container: ContainerDep) -> HTMLResponse:
    path = Path(container.settings.docs_dir) / MANUAL_FILE
    if not path.is_file():
        raise HTTPException(404, "Handbuch nicht gefunden")
    source = path.read_text(encoding="utf-8").replace(
        f"]({MANUAL_IMAGE_PREFIX}",
        "](/manual-assets/",
    )
    html = markdown.markdown(source, extensions=["tables", "fenced_code", "toc"])
    return _render(request, "manual.html", content=html)
