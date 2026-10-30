"""Write side of the dependency graph: entities, relations (with provenance checks) and assets.

Read-only views live in ``graph.py`` (nodes/edges) and ``exposure.py`` (country exposure)."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import (
    ASSET_KINDS,
    ENTITY_KINDS,
    RELATION_KINDS,
)
from watchstreet.domain import DataOrigin
from watchstreet.errors import WatchStreetError
from watchstreet.geo import country_point, normalize_country
from watchstreet.intel.documents import verify_quote
from watchstreet.models import Document, Entity, Relation, Stock

COUNTRY_RELATIONS = ("located_in", "operates", "exposed_to")
LAT_LIMIT, LON_LIMIT = 90.0, 180.0


class GraphError(WatchStreetError, ValueError):
    """Invalid entity/relation input."""


def get_or_create_entity(  # noqa: PLR0913
    session: Session,
    name: str,
    kind: str,
    *,
    stock_id: int | None = None,
    country: str = "",
    lat: float | None = None,
    lon: float | None = None,
    origin: str = DataOrigin.USER,
) -> Entity:
    name = name.strip()
    if not name:
        msg = "Name fehlt"
        raise GraphError(msg)
    if kind not in ENTITY_KINDS:
        msg = f"Art muss eine von {', '.join(ENTITY_KINDS)} sein"
        raise GraphError(msg)
    entity = session.scalar(select(Entity).where(Entity.kind == kind, Entity.name == name))
    if entity is None:
        entity = Entity(name=name, kind=kind, stock_id=stock_id, origin=origin)
        session.add(entity)
    if country:
        entity.country = normalize_country(country) or entity.country
    if lat is not None and lon is not None:
        set_location(entity, lat, lon)
    elif entity.lat is None and entity.country:
        point = country_point(entity.country)
        if point and kind == "country":
            entity.lat, entity.lon = point
    session.flush()
    return entity


def set_location(entity: Entity, lat: float, lon: float, country: str = "") -> None:
    if abs(lat) > LAT_LIMIT or abs(lon) > LON_LIMIT:
        msg = "Koordinaten außerhalb des gültigen Bereichs"
        raise GraphError(msg)
    entity.lat, entity.lon = lat, lon
    if country:
        entity.country = normalize_country(country) or entity.country


def entity_for_stock(session: Session, stock: Stock) -> Entity:
    return get_or_create_entity(
        session,
        stock.name or stock.symbol,
        "company",
        stock_id=stock.id,
        origin=DataOrigin.API,
    )


@dataclass(frozen=True)
class RelationInput:
    kind: str
    strength: float | None = None
    note: str = ""
    document_id: int | None = None
    quote: str = ""
    confidence: str = "low"
    origin: str = DataOrigin.USER
    ticket_id: int | None = None


def add_relation(
    session: Session,
    source: Entity,
    target: Entity,
    data: RelationInput,
) -> Relation:
    """Create an edge. A quote is verified against its document; unverifiable claims are refused."""
    if data.kind not in RELATION_KINDS:
        msg = f"Beziehung muss eine von {', '.join(RELATION_KINDS)} sein"
        raise GraphError(msg)
    if data.strength is not None and not 0.0 <= data.strength <= 1.0:
        msg = "Anteil muss zwischen 0 und 1 liegen"
        raise GraphError(msg)
    confidence = data.confidence
    if data.document_id is not None:
        doc = session.get(Document, data.document_id)
        if doc is None or not verify_quote(doc, data.quote):
            msg = (
                "Zitat wurde im Dokument nicht gefunden (wörtlich zitieren, mindestens 20 Zeichen)"
            )
            raise GraphError(msg)
    else:
        confidence = "low"
    existing = session.scalar(
        select(Relation).where(
            Relation.source_id == source.id,
            Relation.target_id == target.id,
            Relation.kind == data.kind,
        ),
    )
    if existing and existing.origin == DataOrigin.USER and data.origin != DataOrigin.USER:
        msg = "durch einen Nutzer-Eintrag geschützt"
        raise GraphError(msg)
    relation = existing or Relation(source_id=source.id, target_id=target.id, kind=data.kind)
    relation.strength, relation.note = data.strength, data.note
    relation.document_id, relation.quote = data.document_id, data.quote if data.document_id else ""
    relation.confidence, relation.origin, relation.ticket_id = (
        confidence,
        data.origin,
        data.ticket_id,
    )
    session.add(relation)
    session.flush()
    return relation


def sync_mine_entities(session: Session, stock: Stock) -> list[Entity]:
    """One 'mine' entity per mine subject in the datapoints, owned by the company."""
    company = entity_for_stock(session, stock)
    mines: list[Entity] = []
    own: dict[str, float] = {}
    for point in stock.datapoints:  # newest first: first occurrence wins
        if point.key == "mine_ownership" and point.subject not in own and point.value:
            own[point.subject] = point.value
    for name in sorted(
        {p.subject for p in stock.datapoints if p.key.startswith("mine_") and p.subject}
    ):
        mine = get_or_create_entity(session, name, "mine", stock_id=stock.id, origin=DataOrigin.API)
        has_edge = session.scalar(
            select(Relation.id).where(
                Relation.source_id == company.id,
                Relation.target_id == mine.id,
                Relation.kind == "owns",
            ),
        )
        if not has_edge:
            add_relation(
                session,
                company,
                mine,
                RelationInput(
                    "owns", own.get(name, 1.0), origin=DataOrigin.API, confidence="medium"
                ),
            )
        mines.append(mine)
    return mines


def assets(session: Session) -> list[Entity]:
    return list(session.scalars(select(Entity).where(Entity.kind.in_(ASSET_KINDS))))
