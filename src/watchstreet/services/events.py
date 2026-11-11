"""External events with a place; linked to the assets they may affect."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import QUAKE_MIN_MAGNITUDE, QUAKE_RADIUS_KM, SEVERITY_HIGH
from watchstreet.domain import SubjectType
from watchstreet.geo import haversine_km
from watchstreet.intel.connectors.usgs import Quake
from watchstreet.models import Asset, Event, EventLink
from watchstreet.services.changes import log_change

MODERATE_SEVERITY = 3
STRONG_MAGNITUDE = 6.5


def record_quakes(session: Session, quakes: list[Quake], *, is_demo: bool) -> int:
    """Store strong earthquakes once and link every asset within the alert radius."""
    assets = list(session.scalars(select(Asset)))
    known = set(session.scalars(select(Event.external_id)))
    added = 0
    for quake in quakes:
        external_id = f"usgs:{quake.event_id}"
        if quake.magnitude < QUAKE_MIN_MAGNITUDE or external_id in known:
            continue
        event = Event(
            external_id=external_id,
            kind="earthquake",
            title=f"Erdbeben M{quake.magnitude:.1f} – {quake.place}",
            occurred_at=quake.time,
            lat=quake.lat,
            lon=quake.lon,
            severity=SEVERITY_HIGH if quake.magnitude >= STRONG_MAGNITUDE else MODERATE_SEVERITY,
            url=quake.url,
            is_demo=is_demo,
        )
        session.add(event)
        session.flush()
        for asset in assets:
            distance = haversine_km(asset.lat, asset.lon, quake.lat, quake.lon)
            if distance <= QUAKE_RADIUS_KM:
                session.add(
                    EventLink(
                        event_id=event.id, asset_id=asset.id, note=f"{distance:.0f} km entfernt"
                    )
                )
                log_change(
                    session,
                    SubjectType.ASSET,
                    asset.id,
                    "event",
                    f"{event.title} ({distance:.0f} km entfernt)",
                )
        added += 1
    return added
