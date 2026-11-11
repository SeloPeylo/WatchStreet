"""Holdings and watchlist use cases."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from watchstreet.constants import PERCENT
from watchstreet.errors import WatchStreetError
from watchstreet.market.base import MarketDataError
from watchstreet.market.service import MarketService
from watchstreet.models import Holding, Stock, WatchEntry

SYMBOL_MAX_LEN = 32


class PortfolioError(WatchStreetError, ValueError):
    """Invalid user input for a portfolio operation."""


def normalize_symbol(raw: str) -> str:
    symbol = raw.strip().upper()
    if not symbol or len(symbol) > SYMBOL_MAX_LEN or " " in symbol:
        msg = "Ungültiges Symbol"
        raise PortfolioError(msg)
    return symbol


def get_or_create_stock(session: Session, market: MarketService, raw_symbol: str) -> Stock:
    """Find the stock or create it, enriching name/currency from the provider."""
    symbol = normalize_symbol(raw_symbol)
    stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock:
        return stock
    try:
        quote = market.quote(symbol)
    except MarketDataError as exc:
        msg = f"Symbol '{symbol}' wurde beim Datenanbieter nicht gefunden: {exc}"
        raise PortfolioError(msg) from exc
    info = market.company_info(symbol)
    stock = Stock(
        symbol=symbol,
        name=quote.name,
        currency=quote.currency,
        exchange=quote.exchange,
        sector=info.sector,
        industry=info.industry,
    )
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
        msg = f"{stock.symbol} ist bereits in den Beständen"
        raise PortfolioError(msg)
    holding = Holding(
        stock_id=stock.id,
        quantity=data.quantity,
        avg_price=data.avg_price,
        bought_at=data.bought_at,
        intent=data.intent.strip(),
    )
    session.add(holding)
    session.flush()
    session.refresh(stock)
    return holding


def add_watch(session: Session, market: MarketService, symbol: str, note: str = "") -> WatchEntry:
    stock = get_or_create_stock(session, market, symbol)
    if stock.watch:
        msg = f"{stock.symbol} ist bereits auf der Watchlist"
        raise PortfolioError(msg)
    entry = WatchEntry(stock_id=stock.id, note=note.strip())
    session.add(entry)
    session.flush()
    session.refresh(stock)
    return entry


@dataclass(frozen=True)
class HoldingRow:
    holding: Holding
    price: float | None
    market_value: float | None
    pnl_abs: float | None
    pnl_pct: float | None
    day_change_pct: float | None


def holding_rows(session: Session, market: MarketService) -> list[HoldingRow]:
    rows: list[HoldingRow] = []
    for holding in session.scalars(
        select(Holding).options(joinedload(Holding.stock)).order_by(Holding.id)
    ):
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
                (value / cost - 1) * PERCENT,
                quote.change_pct,
            )
        )
    return rows


def watch_entries(session: Session) -> list[WatchEntry]:
    return list(
        session.scalars(
            select(WatchEntry).options(joinedload(WatchEntry.stock)).order_by(WatchEntry.id)
        )
    )
