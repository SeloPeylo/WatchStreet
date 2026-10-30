"""Payload of the world map: located assets, recent located intel and country exposure."""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from watchstreet.constants import MAP_REASONS_PER_COUNTRY, MAP_RECENT_DAYS
from watchstreet.models import IntelItem, Stock
from watchstreet.services import entities
from watchstreet.timeutil import utcnow


def map_payload(session: Session, position_values: dict[int, float]) -> dict[str, Any]:
    symbols = {s.id: s.symbol for s in session.scalars(select(Stock))}
    cutoff = utcnow() - timedelta(days=MAP_RECENT_DAYS)
    exposure = entities.country_exposure(session, position_values)
    items = session.scalars(
        select(IntelItem)
        .where(IntelItem.lat.is_not(None), IntelItem.published_at >= cutoff)
        .options(selectinload(IntelItem.impacts)),
    )
    located = [a for a in entities.assets(session) if a.lat is not None]
    return {
        "assets": [
            {
                "id": a.id,
                "name": a.name,
                "kind": a.kind,
                "lat": a.lat,
                "lon": a.lon,
                "country": a.country,
                "stock": symbols.get(a.stock_id or 0, ""),
            }
            for a in located
        ],
        "intel": [
            {
                "id": i.id,
                "headline": i.headline,
                "category": i.category,
                "severity": i.severity,
                "lat": i.lat,
                "lon": i.lon,
                "country": i.country,
                "why": i.why_it_matters,
                "url": i.source_url,
                "stocks": [symbols.get(x.stock_id, "") for x in i.impacts],
            }
            for i in items
        ],
        "exposure": {
            name: {"share": e.share, "reasons": e.contributions[:MAP_REASONS_PER_COUNTRY]}
            for name, e in exposure.items()
        },
    }
