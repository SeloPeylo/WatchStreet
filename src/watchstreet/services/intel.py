"""Create intel items; every item must point at a direct source."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import (
    INTEL_CATEGORIES,
    INTEL_DIRECTIONS,
    SEVERITY_MAX,
    SEVERITY_MIN,
)
from watchstreet.drafts import IntelDraft
from watchstreet.geo import country_point, normalize_country
from watchstreet.models import Document, IntelImpact, IntelItem, Stock
from watchstreet.timeutil import utcnow


class IntelError(ValueError):
    """An intel item that is not acceptable (e.g. without a source)."""


def create_intel(
    session: Session,
    draft: IntelDraft,
    *,
    author: str,
    ticket_id: int | None = None,
) -> IntelItem | None:
    """Persist an item. Returns ``None`` if an item with the same dedupe key already exists."""
    doc = session.get(Document, draft.document_id) if draft.document_id else None
    if draft.document_id and doc is None:
        msg = f"Dokument {draft.document_id} existiert nicht"
        raise IntelError(msg)
    source_url = draft.source_url or (doc.url if doc else "")
    if not source_url:
        msg = "Ohne direkte Quelle (document_id oder source_url) wird nichts veröffentlicht"
        raise IntelError(msg)
    key = draft.dedupe_key or (f"doc:{doc.id}" if doc else f"url:{source_url}")
    if session.scalar(select(IntelItem.id).where(IntelItem.dedupe_key == key)):
        return None
    country = normalize_country(draft.country)
    lat, lon = draft.lat, draft.lon
    if (lat is None or lon is None) and country:
        point = country_point(country)
        lat, lon = point if point else (None, None)
    item = IntelItem(
        dedupe_key=key,
        document_id=doc.id if doc else None,
        source_url=source_url,
        headline=draft.headline.strip(),
        summary=draft.summary.strip(),
        why_it_matters=draft.why_it_matters.strip(),
        quote=draft.quote.strip(),
        category=draft.category if draft.category in INTEL_CATEGORIES else "company",
        severity=max(SEVERITY_MIN, min(SEVERITY_MAX, draft.severity)),
        country=country,
        lat=lat,
        lon=lon,
        commodities=list(draft.commodities),
        extra_sources=[{"title": t, "url": u, "publisher": p} for t, u, p in draft.extra_sources],
        author=author,
        ticket_id=ticket_id,
        published_at=draft.published_at or (doc.published_at if doc else None) or utcnow(),
    )
    session.add(item)
    session.flush()
    for stock_id, direction, note in draft.impacts:
        if session.get(Stock, stock_id) is not None:
            session.add(
                IntelImpact(
                    intel_id=item.id,
                    stock_id=stock_id,
                    note=note,
                    direction=direction if direction in INTEL_DIRECTIONS else "unknown",
                ),
            )
    session.flush()
    return item


def recent_for_stock(session: Session, stock_id: int, limit: int) -> list[IntelItem]:
    return list(
        session.scalars(
            select(IntelItem)
            .join(IntelImpact, IntelImpact.intel_id == IntelItem.id)
            .where(IntelImpact.stock_id == stock_id)
            .order_by(IntelItem.published_at.desc())
            .limit(limit),
        ),
    )


def age_days(item: IntelItem, now: datetime | None = None) -> float:
    return ((now or utcnow()) - item.published_at).total_seconds() / 86_400
