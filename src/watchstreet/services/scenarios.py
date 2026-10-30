"""What-if engine: re-price a commodity and recompute the deterministic NAV."""

from dataclasses import dataclass

from watchstreet.market.base import MarketDataError
from watchstreet.market.service import MarketService
from watchstreet.models import Stock
from watchstreet.services.valuation import compute_valuation

NEUTRAL_SHOCK = 0.0


@dataclass(frozen=True)
class ScenarioRow:
    shock: float
    nav_per_share: float | None
    nav_change_pct: float | None
    p_nav: float | None
    est_position_change_pct: float | None  # assumes a constant P/NAV multiple


def mining_scenarios(
    market: MarketService,
    stock: Stock,
    shocks: tuple[float, ...],
) -> list[ScenarioRow]:
    """NAV per share under commodity price shocks; empty if the stock has no NAV model yet."""
    quote = market.try_quote(stock.symbol)
    try:
        fundamentals = market.fundamentals(stock.symbol)
    except MarketDataError:
        return []
    price = quote.price if quote else None
    rows: list[tuple[float, float | None, float | None]] = []
    for shock in shocks:
        result = compute_valuation(market, stock, price, fundamentals, commodity_shock=shock)
        nav = p_nav = None
        if result is not None:
            nav = (result.details.get("breakdown") or {}).get("nav_per_share")
            p_nav = next(
                (c["value"] for c in result.details["criteria"] if c["key"] == "p_nav"), None
            )
        rows.append((shock, nav, p_nav))
    base = next((nav for shock, nav, _p in rows if shock == NEUTRAL_SHOCK), None)
    out: list[ScenarioRow] = []
    for shock, nav, p_nav in rows:
        change = (nav / base - 1) * 100 if nav is not None and base else None
        out.append(ScenarioRow(shock, nav, change, p_nav, change))
    return out if any(r.nav_per_share is not None for r in out) else []
