"""Deterministic tripwires: rules that turn sensor data into intel items without any LLM.

Each rule needs only structured data (coordinates, prices), so it is cheap, testable and
explainable. Items created here are the sensors of the agent loop: they become the news that
triage tickets and briefings build on.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from watchstreet.constants import (
    COMMODITY_MOVE_PCT,
    QUAKE_MIN_MAGNITUDE,
    QUAKE_RADIUS_KM,
    SEVERITY_HIGH,
    SEVERITY_MAX,
)
from watchstreet.drafts import IntelDraft
from watchstreet.geo import haversine_km
from watchstreet.intel.connectors.usgs import Quake
from watchstreet.intel.documents import store_document
from watchstreet.market.service import MarketService
from watchstreet.models import Entity, Stock
from watchstreet.services.cockpit import stock_commodities
from watchstreet.services.intel import create_intel

if TYPE_CHECKING:
    from watchstreet.commodities import Commodity

MAG_SEVERITY_BASE = 4.0  # magnitude at which severity starts to count above 1
YAHOO_QUOTE_URL = "https://finance.yahoo.com/quote/{symbol}"
PRODUCER_PROFILES = ("mining", "oil_gas")


def _severity(magnitude: float) -> int:
    return int(min(SEVERITY_MAX, max(1, round(magnitude - MAG_SEVERITY_BASE + 2))))


def quake_alerts(session: Session, quakes: list[Quake]) -> int:
    """Significant earthquakes near located assets of my stocks. Returns items created."""
    located = [
        a
        for a in session.scalars(select(Entity).where(Entity.stock_id.is_not(None)))
        if a.lat is not None and a.lon is not None and a.kind in ("mine", "facility", "port")
    ]
    created = 0
    for quake in quakes:
        if quake.magnitude < QUAKE_MIN_MAGNITUDE:
            continue
        for asset in located:
            if asset.lat is None or asset.lon is None:
                continue
            distance = haversine_km(asset.lat, asset.lon, quake.lat, quake.lon)
            if distance > QUAKE_RADIUS_KM:
                continue
            stock = session.get(Stock, asset.stock_id)
            if stock is None:
                continue
            title = f"M{quake.magnitude:.1f} – {quake.place}"
            doc, _ = store_document(
                session,
                url=quake.url,
                kind="gov",
                publisher="USGS",
                title=title,
                text=f"{title}\nZeit: {quake.time:%Y-%m-%d %H:%M} UTC\n"
                f"Epizentrum: {quake.lat:.2f}, {quake.lon:.2f}",
                published_at=quake.time,
            )
            item = create_intel(
                session,
                IntelDraft(
                    headline=f"Erdbeben M{quake.magnitude:.1f}, {distance:.0f} km von {asset.name}",
                    summary=f"USGS meldet {title}.",
                    why_it_matters=f"{asset.name} ({stock.symbol}) liegt {distance:.0f} km vom "
                    "Epizentrum entfernt. Mögliche Produktionsunterbrechung prüfen.",
                    category="hazard",
                    severity=_severity(quake.magnitude),
                    document_id=doc.id,
                    lat=quake.lat,
                    lon=quake.lon,
                    country=asset.country,
                    impacts=((stock.id, "bearish", f"Asset {asset.name} im Radius"),),
                    dedupe_key=f"quake:{quake.event_id}:{asset.id}",
                    published_at=quake.time,
                ),
                author="rules",
            )
            created += item is not None
    return created


def commodity_alerts(session: Session, market: MarketService) -> int:
    """Large daily moves in commodities my stocks depend on."""
    exposed: dict[str, tuple[Commodity, list[Stock]]] = {}
    for stock in session.scalars(select(Stock).options(selectinload(Stock.datapoints))):
        for commodity in stock_commodities(stock):
            exposed.setdefault(commodity.key, (commodity, []))[1].append(stock)
    created = 0
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    for commodity, stocks in exposed.values():
        quote = market.try_quote(commodity.symbol)
        move = quote.change_pct if quote else None
        if quote is None or move is None or abs(move) < COMMODITY_MOVE_PCT:
            continue
        impacts = []
        for stock in stocks:
            producer = stock.profile in PRODUCER_PROFILES
            direction = "bullish" if (move > 0) == producer else "bearish"
            impacts.append((stock.id, direction, f"{commodity.label} {move:+.1f} %"))
        item = create_intel(
            session,
            IntelDraft(
                headline=f"{commodity.label} {move:+.1f} % an einem Tag "
                f"({quote.price:.2f} {commodity.unit})",
                why_it_matters="Betroffen: " + ", ".join(s.symbol for s in stocks) + ".",
                category="commodity",
                severity=SEVERITY_HIGH if abs(move) >= 2 * COMMODITY_MOVE_PCT else 3,
                source_url=YAHOO_QUOTE_URL.format(symbol=commodity.symbol),
                commodities=(commodity.key,),
                impacts=tuple(impacts),
                dedupe_key=f"commodity:{commodity.key}:{today}",
            ),
            author="rules",
        )
        created += item is not None
    return created
