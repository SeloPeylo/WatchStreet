"""Read-only views over the dependency graph: nodes/edges for the graph page, document relations."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import GRAPH_DEFAULT_DEPTH, MAX_GRAPH_NODES
from watchstreet.models import Entity, Relation


def _stock_neighbourhood(
    entities: dict[int, Entity],
    relations: Sequence[Relation],
    stock_id: int,
    depth: int,
) -> set[int]:
    """Ids of the stock's company entity plus everything within ``depth`` relation hops."""
    keep = {e.id for e in entities.values() if e.stock_id == stock_id and e.kind == "company"}
    frontier = set(keep)
    for _hop in range(depth):
        frontier = {
            node
            for rel in relations
            for node in (rel.source_id, rel.target_id)
            if (rel.source_id in frontier or rel.target_id in frontier) and node not in keep
        }
        keep |= frontier
    return keep


def _whole_portfolio(entities: dict[int, Entity], relations: Sequence[Relation]) -> set[int]:
    """Ids of all stock companies and every entity that takes part in any relation."""
    keep = {e.id for e in entities.values() if e.stock_id is not None}
    for rel in relations:
        keep |= {rel.source_id, rel.target_id}
    return keep


def _node(entity: Entity) -> dict[str, Any]:
    return {
        "id": entity.id,
        "name": entity.name,
        "kind": entity.kind,
        "stock_id": entity.stock_id,
        "country": entity.country,
        "lat": entity.lat,
        "lon": entity.lon,
    }


def _edge(rel: Relation) -> dict[str, Any]:
    return {
        "id": rel.id,
        "source": rel.source_id,
        "target": rel.target_id,
        "kind": rel.kind,
        "strength": rel.strength,
        "note": rel.note,
        "confidence": rel.confidence,
        "origin": rel.origin,
        "document_id": rel.document_id,
        "quote": rel.quote,
    }


def build_graph(
    session: Session,
    stock_id: int | None = None,
    depth: int = GRAPH_DEFAULT_DEPTH,
) -> dict[str, Any]:
    """Nodes and edges for the graph page: the whole portfolio, or one stock's neighbourhood."""
    entities = {e.id: e for e in session.scalars(select(Entity))}
    relations = list(session.scalars(select(Relation)))
    if stock_id is None:
        keep = _whole_portfolio(entities, relations)
    else:
        keep = _stock_neighbourhood(entities, relations, stock_id, depth)
    nodes = [_node(e) for e in entities.values() if e.id in keep][:MAX_GRAPH_NODES]
    node_ids = {node["id"] for node in nodes}
    edges = [
        _edge(rel) for rel in relations if rel.source_id in node_ids and rel.target_id in node_ids
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
