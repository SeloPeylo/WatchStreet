"""Stock area: the stock detail page and everything that is edited or requested from it."""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from watchstreet.constants import (
    DEFAULT_INTERVAL,
    HIGH_PRIORITY,
    INTERVAL_RANGES,
    OPEN_PANELS,
    TECHNICAL_SCHEME,
)
from watchstreet.container import Container
from watchstreet.domain import DataOrigin, InsightCategory, TicketOrigin, WorkflowKey
from watchstreet.market.base import MarketDataError
from watchstreet.models import Datapoint, Stock
from watchstreet.profiles.registry import PROFILES, get_profile
from watchstreet.services import datapoints as datapoints_service
from watchstreet.services import portfolio, tickets
from watchstreet.services import profiles as profiles_service
from watchstreet.services.portfolio import PortfolioError
from watchstreet.services.scores import latest_per_scheme
from watchstreet.services.timeline import build_timeline
from watchstreet.web.deps import ContainerDep, SessionDep
from watchstreet.web.helpers import get_or_404, parse_date, parse_number, redirect, render
from watchstreet.workflows.definitions import REGISTRY, user_workflows

router = APIRouter()

FormStr = Annotated[str, Form()]


class DatapointForm(BaseModel):
    key: str
    subject: str = ""
    value: str = ""
    text: str = ""
    unit: str = ""
    source: str = ""
    confidence: str = "medium"
    as_of: str = ""


def _request_rescoring(session: Session, stock: Stock) -> None:
    """Queue (at most one open) valuation ticket after the user changed the evidence."""
    tickets.ensure_open(
        session,
        stock,
        WorkflowKey.VALUATION_SCORE,
        origin=TicketOrigin.USER,
        priority=HIGH_PRIORITY,
    )


def _stock_view(
    request: Request,
    session: Session,
    container: Container,
    stock: Stock,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the stock page; also used to re-render it with an error message."""
    profile = get_profile(stock.profile)
    scores = latest_per_scheme(stock)
    briefing = stock.briefings[0] if stock.briefings else None
    lens = list(profile.lens)
    return render(
        request,
        "stock.html",
        status_code,
        stock=stock,
        quote=container.market.try_quote(stock.symbol),
        row=next(iter(portfolio.holding_rows(session, container.market, stock.id)), None),
        goal=next((i for i in stock.insights if i.category == InsightCategory.GOAL), None),
        profile=profile,
        profiles=PROFILES,
        lens=lens,
        scores=scores,
        valuation=next((s for s in scores if s["latest"].scheme == profile.scheme), None),
        technical=next((s for s in scores if s["latest"].scheme == TECHNICAL_SCHEME), None),
        briefing=briefing,
        datapoints=datapoints_service.latest(stock),
        specs={spec.key: spec for spec in profile.datapoints},
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
    return _stock_view(request, session, container, get_or_404(session, Stock, stock_id))


@router.post("/stocks/{stock_id}/profile")
def stock_profile_set(stock_id: int, session: SessionDep, profile: FormStr) -> RedirectResponse:
    stock = get_or_404(session, Stock, stock_id)
    try:
        profiles_service.set_profile_by_user(session, stock, profile)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _request_rescoring(session, stock)
    return redirect(f"/stocks/{stock_id}#valuation", "profile_set")


@router.post("/stocks/{stock_id}/datapoints", response_model=None)
def datapoint_add(
    stock_id: int,
    request: Request,
    session: SessionDep,
    container: ContainerDep,
    form: Annotated[DatapointForm, Form()],
) -> Response:
    stock = get_or_404(session, Stock, stock_id)
    try:
        datapoints_service.add_datapoint(
            session,
            stock,
            datapoints_service.DatapointInput(
                key=form.key,
                subject=form.subject,
                value=parse_number(form.value, "Wert") if form.value.strip() else None,
                text=form.text,
                unit=form.unit,
                source=form.source,
                confidence=form.confidence,
                as_of=parse_date(form.as_of),
            ),
            origin=DataOrigin.USER,
        )
    except (datapoints_service.DatapointError, PortfolioError) as exc:
        session.rollback()
        return _stock_view(request, session, container, stock, error=str(exc), status_code=400)
    _request_rescoring(session, stock)
    return redirect(f"/stocks/{stock_id}#evidence", "datapoint_added")


@router.post("/datapoints/{datapoint_id}/delete")
def datapoint_delete(datapoint_id: int, session: SessionDep) -> RedirectResponse:
    point = get_or_404(session, Datapoint, datapoint_id)
    stock_id = point.stock_id
    session.delete(point)
    stock = session.get(Stock, stock_id)
    if stock:
        _request_rescoring(session, stock)
    return redirect(f"/stocks/{stock_id}#evidence", "datapoint_removed")


@router.post("/stocks/{stock_id}/briefing")
def briefing_refresh(stock_id: int, session: SessionDep) -> RedirectResponse:
    tickets.ensure_open(
        session,
        get_or_404(session, Stock, stock_id),
        WorkflowKey.BRIEFING,
        origin=TicketOrigin.USER,
        priority=HIGH_PRIORITY,
    )
    return redirect(f"/stocks/{stock_id}", "briefing_requested")


@router.get("/api/stocks/{stock_id}/candles")
def api_candles(
    stock_id: int,
    session: SessionDep,
    container: ContainerDep,
    interval: str = DEFAULT_INTERVAL,
) -> list[dict[str, float | int]]:
    """OHLCV candles for the chart, with short keys to keep the payload small."""
    stock = get_or_404(session, Stock, stock_id)
    if interval not in INTERVAL_RANGES:
        raise HTTPException(400, "Unbekanntes Intervall")
    try:
        candles = container.market.candles(stock.symbol, interval)
    except MarketDataError as exc:
        raise HTTPException(502, str(exc)) from exc
    return [
        {
            "t": int(candle.time.timestamp()),
            "o": candle.open,
            "h": candle.high,
            "l": candle.low,
            "c": candle.close,
            "v": candle.volume,
        }
        for candle in candles
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
    return redirect(f"/stocks/{stock.id}", "ticket_created")
