"""Builds the view context (reference date, scenario, effective prices) for a request."""

from collections.abc import Mapping
from datetime import date

from sqlalchemy.orm import Session

from watchstreet.commodities import COMMODITIES
from watchstreet.domain import View
from watchstreet.market.service import MarketService
from watchstreet.services.prices import current_quotes, price_on
from watchstreet.services.world import ViewContext
from watchstreet.timeutil import utcnow


def build_view(
    session: Session,
    market: MarketService,
    as_of: date | None = None,
    view: View = View.AS_KNOWN,
    scenario: Mapping[str, float] | None = None,
) -> ViewContext:
    """Effective price per commodity: scenario, else the close at the reference date or today."""
    scenario = dict(scenario or {})
    if as_of is None:
        base = {q.key: q.price for q in current_quotes(market) if q.price is not None}
    else:
        closes = {c.key: price_on(session, c.key, as_of) for c in COMMODITIES}
        base = {key: close for key, close in closes.items() if close is not None}
    return ViewContext(
        today=utcnow().date(),
        prices={**base, **scenario},
        base_prices=base,
        as_of=as_of,
        view=view,
        scenario=scenario,
    )
