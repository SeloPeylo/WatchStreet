"""Portfolio area: dashboard, holdings, watchlist and the stock search/quick-jump endpoints."""

from collections import Counter
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from watchstreet.constants import RECENT_LIMIT
from watchstreet.container import Container
from watchstreet.market.base import MarketDataError
from watchstreet.models import Holding, Insight, Stock, Ticket, WatchEntry
from watchstreet.services import portfolio
from watchstreet.services.portfolio import PortfolioError
from watchstreet.web.deps import ContainerDep, SessionDep
from watchstreet.web.helpers import (
    current_system_status,
    get_or_404,
    parse_date,
    parse_number,
    redirect,
    render,
)

router = APIRouter()

FormStr = Annotated[str, Form()]


def _recent(session: Session, model: type[Ticket] | type[Insight]) -> list[Ticket | Insight]:
    """Newest ``RECENT_LIMIT`` rows of a model, newest first."""
    return list(session.scalars(select(model).order_by(model.id.desc()).limit(RECENT_LIMIT)))


def _holdings_context(session: Session, container: Container) -> dict[str, Any]:
    """Template variables shared by the holdings page and its error re-render."""
    rows = portfolio.holding_rows(session, container.market)
    return {"rows": rows, "totals": portfolio.totals_by_currency(rows)}


def _watchlist_context(session: Session, container: Container) -> dict[str, Any]:
    """Template variables shared by the watchlist page and its error re-render."""
    entries = list(session.scalars(select(WatchEntry).order_by(WatchEntry.id)))
    quotes = {entry.stock_id: container.market.try_quote(entry.stock.symbol) for entry in entries}
    return {"entries": entries, "quotes": quotes}


# ------------------------------------------------------------------ dashboard
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: SessionDep, container: ContainerDep) -> HTMLResponse:
    return render(
        request,
        "dashboard.html",
        **_holdings_context(session, container),
        counts=Counter(session.scalars(select(Ticket.status))),
        recent_tickets=_recent(session, Ticket),
        recent_insights=_recent(session, Insight),
        stocks={stock.id: stock for stock in session.scalars(select(Stock))},
        watch_count=session.scalar(select(func.count(WatchEntry.id))),
        system=current_system_status(session, container),
    )


# ------------------------------------------------------------------ holdings
class HoldingForm(BaseModel):
    symbol: str
    quantity: str
    avg_price: str
    bought_at: str = ""
    intent: str = ""


@router.get("/holdings", response_class=HTMLResponse)
def holdings_page(request: Request, session: SessionDep, container: ContainerDep) -> HTMLResponse:
    return render(request, "holdings.html", **_holdings_context(session, container), form={})


@router.post("/holdings", response_model=None)
def holdings_add(
    request: Request,
    session: SessionDep,
    container: ContainerDep,
    form: Annotated[HoldingForm, Form()],
) -> Response:
    try:
        new_holding = portfolio.NewHolding(
            form.symbol,
            parse_number(form.quantity, "Menge"),
            parse_number(form.avg_price, "Durchschnittspreis"),
            parse_date(form.bought_at),
            form.intent,
        )
        portfolio.add_holding(session, container.market, new_holding)
    except PortfolioError as exc:
        session.rollback()
        return render(
            request,
            "holdings.html",
            400,
            **_holdings_context(session, container),
            form=form.model_dump(),
            error=str(exc),
        )
    return redirect("/holdings", "holding_added")


@router.post("/holdings/{holding_id}/update", response_model=None)
def holdings_update(
    holding_id: int,
    session: SessionDep,
    quantity: FormStr,
    avg_price: FormStr,
    bought_at: FormStr = "",
    intent: FormStr = "",
) -> Response:
    holding = get_or_404(session, Holding, holding_id)
    try:
        portfolio.update_holding(
            session,
            holding,
            parse_number(quantity, "Menge"),
            parse_number(avg_price, "Durchschnittspreis"),
            parse_date(bought_at),
            intent,
        )
    except PortfolioError as exc:
        raise HTTPException(400, str(exc)) from exc
    return redirect(f"/stocks/{holding.stock_id}", "holding_updated")


@router.post("/holdings/{holding_id}/delete")
def holdings_delete(holding_id: int, session: SessionDep) -> RedirectResponse:
    portfolio.remove_holding(session, get_or_404(session, Holding, holding_id))
    return redirect("/holdings", "holding_removed")


# ------------------------------------------------------------------ watchlist
@router.get("/watchlist", response_class=HTMLResponse)
def watchlist_page(request: Request, session: SessionDep, container: ContainerDep) -> HTMLResponse:
    return render(request, "watchlist.html", **_watchlist_context(session, container), form={})


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
        return render(
            request,
            "watchlist.html",
            400,
            **_watchlist_context(session, container),
            form={"symbol": symbol, "note": note},
            error=str(exc),
        )
    return redirect("/watchlist", "watch_added")


@router.post("/watchlist/{entry_id}/delete")
def watchlist_delete(entry_id: int, session: SessionDep) -> RedirectResponse:
    portfolio.remove_watch(session, get_or_404(session, WatchEntry, entry_id))
    return redirect("/watchlist", "watch_removed")


# ------------------------------------------------------------------ lookup APIs
@router.get("/api/stocks")
def api_stocks(session: SessionDep) -> list[dict[str, str | int]]:
    """Known stocks for the quick-jump palette."""
    stocks = session.scalars(select(Stock).order_by(Stock.symbol))
    return [{"id": s.id, "symbol": s.symbol, "name": s.name} for s in stocks]


@router.get("/api/search")
def api_search(q: str, container: ContainerDep) -> list[dict[str, str]]:
    """Symbol search at the market provider; an unreachable provider yields no matches."""
    try:
        return [asdict(match) for match in container.market.search(q)]
    except MarketDataError:
        return []
