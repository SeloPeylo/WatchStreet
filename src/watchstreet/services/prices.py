"""Commodity prices: current quotes, stored history and the price valid for a view."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.commodities import COMMODITIES
from watchstreet.constants import PRICE_HISTORY_INTERVAL
from watchstreet.market.base import MarketDataError
from watchstreet.market.service import MarketService
from watchstreet.models import PricePoint


@dataclass(frozen=True)
class CommodityQuote:
    key: str
    price: float | None
    change_pct: float | None


def current_quotes(market: MarketService) -> list[CommodityQuote]:
    quotes = []
    for commodity in COMMODITIES:
        quote = market.try_quote(commodity.symbol)
        quotes.append(
            CommodityQuote(
                commodity.key,
                quote.price if quote else None,
                quote.change_pct if quote else None,
            )
        )
    return quotes


def price_on(session: Session, commodity: str, day: date) -> float | None:
    """Last stored close on or before ``day``."""
    return session.scalars(
        select(PricePoint.close)
        .where(PricePoint.commodity == commodity, PricePoint.day <= day)
        .order_by(PricePoint.day.desc())
        .limit(1)
    ).first()


def history(session: Session, commodity: str) -> list[PricePoint]:
    return list(
        session.scalars(
            select(PricePoint).where(PricePoint.commodity == commodity).order_by(PricePoint.day)
        )
    )


def sync_history(session: Session, market: MarketService) -> int:
    """Store weekly closes of every commodity; existing days are left untouched."""
    added = 0
    for commodity in COMMODITIES:
        try:
            candles = market.candles(commodity.symbol, PRICE_HISTORY_INTERVAL)
        except MarketDataError:
            continue
        known = set(
            session.scalars(select(PricePoint.day).where(PricePoint.commodity == commodity.key))
        )
        for candle in candles:
            day = candle.time.date()
            if day in known:
                continue
            known.add(day)
            session.add(
                PricePoint(commodity=commodity.key, day=day, close=candle.close, source=market.name)
            )
            added += 1
    session.flush()
    return added
