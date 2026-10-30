"""Holdings and watchlist use cases, including ticket intake."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from watchstreet.constants import HIGH_PRIORITY
from watchstreet.domain import TicketOrigin, WorkflowKey
from watchstreet.market.base import MarketDataError
from watchstreet.market.service import MarketService
from watchstreet.models import Holding, Stock, WatchEntry
from watchstreet.services.profiles import auto_classify
from watchstreet.services.tickets import create_ticket

SYMBOL_MAX_LEN = 32


class PortfolioError(ValueError):
    """Invalid user input for a portfolio operation."""


def normalize_symbol(raw: str) -> str:
    symbol = raw.strip().upper()
    if not symbol or len(symbol) > SYMBOL_MAX_LEN or " " in symbol:
        msg = "Ungültiges Symbol"
        raise PortfolioError(msg)
    return symbol


def get_or_create_stock(session: Session, market: MarketService, raw_symbol: str) -> Stock:
    """Find the stock or create it, enriching name/currency from the provider if possible."""
    symbol = normalize_symbol(raw_symbol)
    stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock:
        return stock
    stock = Stock(symbol=symbol)
    try:
        quote = market.quote(symbol)
    except MarketDataError as exc:
        msg = f"Symbol '{symbol}' wurde beim Datenanbieter nicht gefunden: {exc}"
        raise PortfolioError(msg) from exc
    stock.name, stock.currency, stock.exchange = quote.name, quote.currency, quote.exchange
    auto_classify(stock, market)
    session.add(stock)
    session.flush()
    return stock


@dataclass(frozen=True)
class NewHolding:
    symbol: str
    quantity: float
    avg_price: float
    bought_at: date | None = None
    intent: str = ""


def add_holding(session: Session, market: MarketService, data: NewHolding) -> Holding:
    if data.quantity <= 0 or data.avg_price <= 0:
        msg = "Menge und Durchschnittspreis müssen größer als 0 sein"
        raise PortfolioError(msg)
    stock = get_or_create_stock(session, market, data.symbol)
    if stock.holding:
        msg = f"{stock.symbol} ist bereits in den Holdings"
        raise PortfolioError(msg)
    intent = data.intent.strip()
    holding = Holding(
        stock_id=stock.id,
        quantity=data.quantity,
        avg_price=data.avg_price,
        bought_at=data.bought_at,
        intent=intent,
    )
    session.add(holding)
    session.flush()
    session.refresh(stock)
    create_ticket(
        session,
        stock,
        WorkflowKey.INITIAL_HOLDING,
        origin=TicketOrigin.INTAKE,
        priority=HIGH_PRIORITY,
        params={"intent": intent},
    )
    return holding


def update_holding(
    session: Session,
    holding: Holding,
    quantity: float,
    avg_price: float,
    bought_at: date | None,
    intent: str,
) -> None:
    if quantity <= 0 or avg_price <= 0:
        msg = "Menge und Durchschnittspreis müssen größer als 0 sein"
        raise PortfolioError(msg)
    holding.quantity, holding.avg_price = quantity, avg_price
    holding.bought_at, holding.intent = bought_at, intent.strip()
    session.flush()


def add_watch(session: Session, market: MarketService, symbol: str, note: str = "") -> WatchEntry:
    stock = get_or_create_stock(session, market, symbol)
    if stock.watch:
        msg = f"{stock.symbol} ist bereits auf der Watchlist"
        raise PortfolioError(msg)
    entry = WatchEntry(stock_id=stock.id, note=note.strip())
    session.add(entry)
    session.flush()
    session.refresh(stock)
    create_ticket(
        session,
        stock,
        WorkflowKey.INITIAL_WATCH,
        origin=TicketOrigin.INTAKE,
        priority=HIGH_PRIORITY,
    )
    return entry


def remove_holding(session: Session, holding: Holding) -> None:
    session.delete(holding)


def remove_watch(session: Session, entry: WatchEntry) -> None:
    session.delete(entry)


@dataclass(frozen=True)
class HoldingRow:
    holding: Holding
    price: float | None
    market_value: float | None
    pnl_abs: float | None
    pnl_pct: float | None
    day_change_pct: float | None


def holding_rows(
    session: Session, market: MarketService, stock_id: int | None = None
) -> list[HoldingRow]:
    """Priced holding rows, optionally restricted to one stock (its detail page)."""
    query = select(Holding).options(joinedload(Holding.stock)).order_by(Holding.id)
    if stock_id is not None:
        query = query.where(Holding.stock_id == stock_id)
    rows: list[HoldingRow] = []
    for holding in session.scalars(query):
        quote = market.try_quote(holding.stock.symbol)
        if quote is None:
            rows.append(HoldingRow(holding, None, None, None, None, None))
            continue
        cost = holding.avg_price * holding.quantity
        value = quote.price * holding.quantity
        rows.append(
            HoldingRow(
                holding,
                quote.price,
                value,
                value - cost,
                (value / cost - 1) * 100,
                quote.change_pct,
            ),
        )
    return rows


def totals_by_currency(rows: list[HoldingRow]) -> dict[str, dict[str, float]]:
    """Cost, value and P/L per currency; mixed currencies are never added together."""
    totals: dict[str, dict[str, float]] = {}
    for row in rows:
        if row.market_value is None:
            continue
        bucket = totals.setdefault(
            row.holding.stock.currency or "?",
            {"cost": 0.0, "value": 0.0},
        )
        bucket["cost"] += row.holding.avg_price * row.holding.quantity
        bucket["value"] += row.market_value
    for bucket in totals.values():
        bucket["pnl"] = bucket["value"] - bucket["cost"]
        bucket["pnl_pct"] = (bucket["value"] / bucket["cost"] - 1) * 100 if bucket["cost"] else 0.0
    return totals
