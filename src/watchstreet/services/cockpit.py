"""Commodity and macro cockpit: prices, ratios and the portfolio's commodity exposure."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.commodities import BY_SYMBOL, COMMODITIES, COPPER_GOLD_FACTOR, MACRO, Commodity
from watchstreet.constants import COMMODITY_SYMBOL_KEY, PERCENT
from watchstreet.market.base import MarketDataError
from watchstreet.market.indicators import pct_change
from watchstreet.market.service import MarketService
from watchstreet.models import Stock
from watchstreet.services.datapoints import latest

SPARK_BARS = 60
MONTH_BARS = 21


@dataclass(frozen=True)
class PriceRow:
    commodity: Commodity
    price: float | None
    change_1d: float | None
    change_1m: float | None
    spark: list[float] = field(default_factory=list)


def stock_commodities(stock: Stock) -> list[Commodity]:
    """Commodities a stock is exposed to, from its commodity_symbol datapoint."""
    found = {
        BY_SYMBOL[p.text.strip()]
        for p in latest(stock)
        if p.key == COMMODITY_SYMBOL_KEY and p.text.strip() in BY_SYMBOL
    }
    return sorted(found, key=lambda c: c.key)


def price_row(market: MarketService, commodity: Commodity) -> PriceRow:
    quote = market.try_quote(commodity.symbol)
    try:
        closes = [c.close for c in market.candles(commodity.symbol, "1d")]
    except MarketDataError:
        closes = []
    return PriceRow(
        commodity,
        quote.price if quote else None,
        quote.change_pct if quote else None,
        pct_change(closes, MONTH_BARS),
        closes[-SPARK_BARS:],
    )


def commodity_rows(market: MarketService) -> list[PriceRow]:
    return [price_row(market, c) for c in COMMODITIES]


def macro_rows(market: MarketService) -> list[PriceRow]:
    return [price_row(market, c) for c in MACRO]


def ratios(rows: list[PriceRow]) -> list[tuple[str, float, str]]:
    """Classic cross-commodity ratios: (label, value, reading hint)."""
    price = {r.commodity.key: r.price for r in rows if r.price}
    out: list[tuple[str, float, str]] = []
    if "gold" in price and "silver" in price:
        out.append(
            (
                "Gold/Silber",
                price["gold"] / price["silver"],
                "hoch = Silber relativ günstig / Risk-off",
            )
        )
    if "copper" in price and "gold" in price:
        out.append(
            (
                "Kupfer/Gold (×1000)",
                price["copper"] / price["gold"] * COPPER_GOLD_FACTOR,
                "steigend = Konjunkturoptimismus",
            )
        )
    if "wti" in price and "natgas" in price:
        out.append(("Öl/Gas", price["wti"] / price["natgas"], "hoch = Gas relativ günstig"))
    return out


def exposure_by_commodity(
    session: Session,
    values: dict[int, float],
) -> list[tuple[Commodity, list[Stock], float]]:
    """Which stocks depend on which commodity, and their share of the portfolio value."""
    total = sum(values.values()) or 1.0
    grouped: dict[str, tuple[Commodity, list[Stock], float]] = {}
    for stock in session.scalars(select(Stock)):
        for commodity in stock_commodities(stock):
            entry = grouped.setdefault(commodity.key, (commodity, [], 0.0))
            entry[1].append(stock)
            grouped[commodity.key] = (
                commodity,
                entry[1],
                entry[2] + values.get(stock.id, 0.0) / total * PERCENT,
            )
    return sorted(grouped.values(), key=lambda e: -e[2])
