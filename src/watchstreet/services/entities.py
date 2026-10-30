"""Entities, relations, assets and the derived graph/map/exposure views."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from watchstreet.constants import (
    ASSET_KINDS,
    DEFAULT_RELATION_STRENGTH,
    ENTITY_KINDS,
    GRAPH_DEFAULT_DEPTH,
    MAX_GRAPH_NODES,
    RELATION_KINDS,
)
from watchstreet.domain import DataOrigin
from watchstreet.errors import WatchStreetError
from watchstreet.geo import country_point, normalize_country
from watchstreet.intel.documents import verify_quote
from watchstreet.models import Datapoint, Document, Entity, Relation, Stock

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
        origin="api",
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
        mine = get_or_create_entity(session, name, "mine", stock_id=stock.id, origin="api")
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
                RelationInput("owns", own.get(name, 1.0), origin="api", confidence="medium"),
            )
        mines.append(mine)
    return mines


# --------------------------------------------------------------------------- views
def graph(
    session: Session, stock_id: int | None = None, depth: int = GRAPH_DEFAULT_DEPTH
) -> dict[str, Any]:
    entities = {e.id: e for e in session.scalars(select(Entity))}
    relations = list(session.scalars(select(Relation)))
    keep: set[int]
    if stock_id is None:
        keep = {e.id for e in entities.values() if e.stock_id is not None}
        keep |= {r.source_id for r in relations} | {r.target_id for r in relations}
    else:
        keep = {e.id for e in entities.values() if e.stock_id == stock_id and e.kind == "company"}
        frontier = set(keep)
        for _ in range(depth):
            frontier = {
                n
                for r in relations
                for n in (r.source_id, r.target_id)
                if (r.source_id in frontier or r.target_id in frontier) and n not in keep
            }
            keep |= frontier
    nodes = [
        {
            "id": e.id,
            "name": e.name,
            "kind": e.kind,
            "stock_id": e.stock_id,
            "country": e.country,
            "lat": e.lat,
            "lon": e.lon,
        }
        for e in entities.values()
        if e.id in keep
    ][:MAX_GRAPH_NODES]
    ids = {n["id"] for n in nodes}
    edges = [
        {
            "id": r.id,
            "source": r.source_id,
            "target": r.target_id,
            "kind": r.kind,
            "strength": r.strength,
            "note": r.note,
            "confidence": r.confidence,
            "origin": r.origin,
            "document_id": r.document_id,
            "quote": r.quote,
        }
        for r in relations
        if r.source_id in ids and r.target_id in ids
    ]
    return {"nodes": nodes, "edges": edges}


def relations_for_document(session: Session, doc_id: int) -> list[dict[str, Any]]:
    """Relations quoted from one document, with entity names resolved in a single query."""
    rels = list(session.scalars(select(Relation).where(Relation.document_id == doc_id)))
    ids = {r.source_id for r in rels} | {r.target_id for r in rels}
    names = {e.id: e.name for e in session.scalars(select(Entity).where(Entity.id.in_(ids)))}
    return [
        {"rel": r, "source": names.get(r.source_id, "?"), "target": names.get(r.target_id, "?")}
        for r in rels
    ]


def assets(session: Session) -> list[Entity]:
    return list(session.scalars(select(Entity).where(Entity.kind.in_(ASSET_KINDS))))


@dataclass
class CountryExposure:
    share: float = 0.0
    contributions: list[dict[str, Any]] = field(default_factory=list)


def _asset_shares(
    stock: Stock,
    owned: list[tuple[Relation, Entity]],
) -> list[tuple[Entity, float]]:
    """Owned assets with their weight inside the company (production x ownership if known)."""
    production = {
        d.subject: d.value for d in stock.datapoints if d.key == "mine_production" and d.value
    }
    rows: list[tuple[Entity, float]] = []
    for edge, asset in owned:
        if asset.kind not in ASSET_KINDS:
            continue
        weight = (production.get(asset.name) or 1.0) * (edge.strength or 1.0)
        rows.append((asset, weight))
    total = sum(w for _a, w in rows)
    return [(a, w / total) for a, w in rows] if total else []


def _load_exposure_inputs(
    session: Session, stock_ids: list[int]
) -> tuple[dict[int, Stock], dict[int, Entity], dict[int, list[tuple[Relation, Entity]]]]:
    """Load stocks, company entities and connected relations in a fixed number of queries."""
    stocks = {
        s.id: s
        for s in session.scalars(
            select(Stock).where(Stock.id.in_(stock_ids)).options(selectinload(Stock.datapoints)),
        )
    }
    companies: dict[int, Entity] = {}
    for company in session.scalars(
        select(Entity)
        .where(Entity.stock_id.in_(stock_ids), Entity.kind == "company")
        .order_by(Entity.id),
    ):
        if company.stock_id is not None:
            companies.setdefault(company.stock_id, company)
    company_ids = {c.id for c in companies.values()}
    relations = list(
        session.scalars(
            select(Relation)
            .where(Relation.source_id.in_(company_ids) | Relation.target_id.in_(company_ids))
            .order_by(Relation.id),
        ),
    )
    other_ids = {r.target_id for r in relations} | {r.source_id for r in relations}
    others = {e.id: e for e in session.scalars(select(Entity).where(Entity.id.in_(other_ids)))}
    connected: dict[int, list[tuple[Relation, Entity]]] = {}
    for rel in relations:
        for company_id, other_id in (
            (rel.source_id, rel.target_id),
            (rel.target_id, rel.source_id),
        ):
            other = others.get(other_id)
            if company_id in company_ids and other is not None:
                connected.setdefault(company_id, []).append((rel, other))
    return stocks, companies, connected


def country_exposure(session: Session, values: dict[int, float]) -> dict[str, CountryExposure]:
    """Share of the portfolio (by position value) tied to each country, with the reasons."""
    total = sum(values.values())
    out: dict[str, CountryExposure] = {}
    if not total:
        return out

    def add(country: str, share: float, stock: Stock, via: str) -> None:
        name = normalize_country(country)
        if name and share > 0:
            entry = out.setdefault(name, CountryExposure())
            entry.share += share
            entry.contributions.append({"stock": stock.symbol, "via": via, "share": share})

    stocks, companies, connected = _load_exposure_inputs(session, list(values))
    for stock_id, value in values.items():
        stock, company = stocks.get(stock_id), companies.get(stock_id)
        if stock is None or company is None:
            continue
        weight = value / total
        edges = connected.get(company.id, [])
        owned = [
            (rel, other)
            for rel, other in edges
            if rel.source_id == company.id and rel.kind == "owns"
        ]
        for asset, share in _asset_shares(stock, owned):
            add(asset.country, weight * share, stock, f"Asset {asset.name}")
        for rel, other in edges:
            if rel.kind == "owns":
                continue
            strength = rel.strength if rel.strength is not None else DEFAULT_RELATION_STRENGTH
            country = other.name if other.kind == "country" else other.country
            if other.kind == "country" or other.kind in ("supplier", "customer"):
                add(country, weight * strength, stock, f"{rel.kind}: {other.name}")
    return out


def datapoint_subjects(session: Session, stock_id: int) -> list[Datapoint]:
    return list(session.scalars(select(Datapoint).where(Datapoint.stock_id == stock_id)))
