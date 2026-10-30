"""HTTP routes (server-rendered pages plus a few JSON endpoints)."""

from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

import markdown
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import (
    DEFAULT_INTERVAL,
    HIGH_PRIORITY,
    INTERVAL_RANGES,
    OPEN_PANELS,
    RECENT_LIMIT,
    TECHNICAL_SCHEME,
)
from watchstreet.container import Container
from watchstreet.domain import InsightCategory, TicketOrigin, TicketStatus, WorkflowKey
from watchstreet.market.base import MarketDataError
from watchstreet.models import Datapoint, Holding, Insight, MarketEvent, Stock, Ticket, WatchEntry
from watchstreet.profiles.registry import PROFILES, get_profile
from watchstreet.services import datapoints as datapoints_service
from watchstreet.services import portfolio, tickets
from watchstreet.services import profiles as profiles_service
from watchstreet.services.portfolio import PortfolioError
from watchstreet.services.scores import latest_per_scheme
from watchstreet.services.status import system_status
from watchstreet.services.timeline import build_timeline
from watchstreet.web.deps import ContainerDep, SessionDep
from watchstreet.web.helpers import parse_date as _date
from watchstreet.web.helpers import parse_number as _number
from watchstreet.web.helpers import redirect as _redirect
from watchstreet.web.helpers import render as _render
from watchstreet.workflows.definitions import REGISTRY, user_workflows

router = APIRouter()

FormStr = Annotated[str, Form()]
STATUS_POLL_MAX_IDS = 50
MANUAL_FILE = "user-manual.md"
MANUAL_IMAGE_PREFIX = "screenshots/"


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
    return _redirect("/holdings", "holding_added")


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
    return _redirect(f"/stocks/{holding.stock_id}", "holding_updated")


@router.post("/holdings/{holding_id}/delete")
def holdings_delete(holding_id: int, session: SessionDep) -> RedirectResponse:
    holding = session.get(Holding, holding_id)
    if holding is None:
        raise HTTPException(404)
    portfolio.remove_holding(session, holding)
    return _redirect("/holdings", "holding_removed")


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
    return _redirect("/watchlist", "watch_added")


@router.post("/watchlist/{entry_id}/delete")
def watchlist_delete(entry_id: int, session: SessionDep) -> RedirectResponse:
    entry = session.get(WatchEntry, entry_id)
    if entry is None:
        raise HTTPException(404)
    portfolio.remove_watch(session, entry)
    return _redirect("/watchlist", "watch_removed")


@router.get("/api/stocks")
def api_stocks(session: SessionDep) -> list[dict[str, str | int]]:
    """Known stocks for the quick-jump palette."""
    rows = session.scalars(select(Stock).order_by(Stock.symbol))
    return [{"id": s.id, "symbol": s.symbol, "name": s.name} for s in rows]


@router.get("/api/search")
def api_search(q: str, container: ContainerDep) -> list[dict[str, str]]:
    try:
        return [asdict(m) for m in container.market.search(q)]
    except MarketDataError:
        return []


# ------------------------------------------------------------------ stock detail
def _stock_view(
    request: Request,
    session: Session,
    container: Container,
    stock: Stock,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    profile = get_profile(stock.profile)
    quote = container.market.try_quote(stock.symbol)
    row = next(iter(portfolio.holding_rows(session, container.market, stock.id)), None)
    goal = next((i for i in stock.insights if i.category == InsightCategory.GOAL), None)
    scores = latest_per_scheme(stock)
    valuation = next((s for s in scores if s["latest"].scheme == profile.scheme), None)
    technical = next((s for s in scores if s["latest"].scheme == TECHNICAL_SCHEME), None)
    briefing = stock.briefings[0] if stock.briefings else None
    lens = list(profile.lens)
    return _render(
        request,
        "stock.html",
        status_code,
        stock=stock,
        quote=quote,
        row=row,
        goal=goal,
        profile=profile,
        profiles=PROFILES,
        lens=lens,
        scores=scores,
        valuation=valuation,
        technical=technical,
        briefing=briefing,
        datapoints=datapoints_service.latest(stock),
        specs={d.key: d for d in profile.datapoints},
        timeline=build_timeline(stock),
        workflows=user_workflows(),
        intervals=list(INTERVAL_RANGES),
        default_interval=DEFAULT_INTERVAL,
        error=error,
        open_panels=set(lens[:OPEN_PANELS]) | ({briefing.focus} if briefing else set()),
    )


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
    return _stock_view(request, session, container, stock)


@router.post("/stocks/{stock_id}/profile")
def stock_profile_set(stock_id: int, session: SessionDep, profile: FormStr) -> RedirectResponse:
    stock = session.get(Stock, stock_id)
    if stock is None:
        raise HTTPException(404)
    try:
        profiles_service.set_profile_by_user(session, stock, profile)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    tickets.ensure_open(
        session,
        stock,
        WorkflowKey.VALUATION_SCORE,
        origin=TicketOrigin.USER,
        priority=HIGH_PRIORITY,
    )
    return _redirect(f"/stocks/{stock_id}#valuation", "profile_set")


class DatapointForm(BaseModel):
    key: str
    subject: str = ""
    value: str = ""
    text: str = ""
    unit: str = ""
    source: str = ""
    confidence: str = "medium"
    as_of: str = ""


@router.post("/stocks/{stock_id}/datapoints", response_model=None)
def datapoint_add(
    stock_id: int,
    request: Request,
    session: SessionDep,
    container: ContainerDep,
    form: Annotated[DatapointForm, Form()],
) -> Response:
    stock = session.get(Stock, stock_id)
    if stock is None:
        raise HTTPException(404)
    try:
        datapoints_service.add_datapoint(
            session,
            stock,
            datapoints_service.DatapointInput(
                key=form.key,
                subject=form.subject,
                value=_number(form.value, "Wert") if form.value.strip() else None,
                text=form.text,
                unit=form.unit,
                source=form.source,
                confidence=form.confidence,
                as_of=_date(form.as_of),
            ),
            origin="user",
        )
    except (datapoints_service.DatapointError, PortfolioError) as exc:
        session.rollback()
        return _stock_view(request, session, container, stock, error=str(exc), status_code=400)
    tickets.ensure_open(
        session,
        stock,
        WorkflowKey.VALUATION_SCORE,
        origin=TicketOrigin.USER,
        priority=HIGH_PRIORITY,
    )
    return _redirect(f"/stocks/{stock_id}#evidence", "datapoint_added")


@router.post("/datapoints/{datapoint_id}/delete")
def datapoint_delete(datapoint_id: int, session: SessionDep) -> RedirectResponse:
    point = session.get(Datapoint, datapoint_id)
    if point is None:
        raise HTTPException(404)
    stock_id = point.stock_id
    session.delete(point)
    stock = session.get(Stock, stock_id)
    if stock:
        tickets.ensure_open(
            session,
            stock,
            WorkflowKey.VALUATION_SCORE,
            origin=TicketOrigin.USER,
            priority=HIGH_PRIORITY,
        )
    return _redirect(f"/stocks/{stock_id}#evidence", "datapoint_removed")


@router.post("/stocks/{stock_id}/briefing")
def briefing_refresh(stock_id: int, session: SessionDep) -> RedirectResponse:
    stock = session.get(Stock, stock_id)
    if stock is None:
        raise HTTPException(404)
    tickets.ensure_open(
        session,
        stock,
        WorkflowKey.BRIEFING,
        origin=TicketOrigin.USER,
        priority=HIGH_PRIORITY,
    )
    return _redirect(f"/stocks/{stock_id}", "briefing_requested")


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
    return _redirect(f"/stocks/{stock.id}", "ticket_created")


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


@router.get("/api/tickets/status")
def api_ticket_status(session: SessionDep, ids: str = "") -> list[dict[str, str | int]]:
    """Lightweight status lookup used by the live-update script (``?ids=1,2,3``)."""
    wanted = [int(p) for p in ids.split(",") if p.strip().isdigit()][:STATUS_POLL_MAX_IDS]
    if not wanted:
        return []
    rows = session.scalars(select(Ticket).where(Ticket.id.in_(wanted)))
    return [{"id": t.id, "status": t.status} for t in rows]


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
    return _redirect(f"/tickets/{ticket_id}", "ticket_retried")


@router.post("/tickets/{ticket_id}/cancel")
def ticket_cancel(ticket_id: int, session: SessionDep) -> RedirectResponse:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(404)
    tickets.cancel(session, ticket)
    return _redirect(f"/tickets/{ticket_id}", "ticket_cancelled")


# ------------------------------------------------------------------ system + manual
def _system_status(session: Session, container: Container) -> dict[str, Any]:
    return system_status(
        session,
        market=container.market.name,
        runner=container.runner.name,
        scan_interval_min=container.settings.event_scan_interval_min,
    )


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
