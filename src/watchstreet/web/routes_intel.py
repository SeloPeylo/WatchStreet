"""Intel area: news center, world map, dependency graph, commodity cockpit, documents."""

from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.commodities import BY_KEY
from watchstreet.constants import (
    ENTITY_KINDS,
    GRAPH_DEFAULT_DEPTH,
    INTEL_CATEGORIES,
    LIST_LIMIT,
    MAP_RECENT_DAYS,
    PRIMARY_KINDS,
    RELATION_KINDS,
    SCAN_REQUEST_KEY,
    SCENARIO_SHOCKS,
    SEVERITY_MIN,
)
from watchstreet.container import Container
from watchstreet.domain import TicketOrigin, WorkflowKey
from watchstreet.intel.documents import outline
from watchstreet.models import (
    Datapoint,
    Document,
    Entity,
    Feed,
    Insight,
    IntelImpact,
    IntelItem,
    Relation,
    Stock,
)
from watchstreet.services import cockpit, entities, portfolio, scenarios, tickets
from watchstreet.services.entities import GraphError, RelationInput
from watchstreet.services.state import touch
from watchstreet.timeutil import utcnow
from watchstreet.web.deps import ContainerDep, SessionDep
from watchstreet.web.routes import _number, _redirect, _render

router = APIRouter()
DOC_PREVIEW_CHARS = 20_000


# ------------------------------------------------------------------ news center
@router.get("/intel", response_class=HTMLResponse)
def intel_page(
    request: Request,
    session: SessionDep,
    category: str = "",
    stock: int = 0,
    severity: int = SEVERITY_MIN,
    primary: str = "",
) -> HTMLResponse:
    query = select(IntelItem).order_by(IntelItem.published_at.desc()).limit(LIST_LIMIT)
    if category in INTEL_CATEGORIES:
        query = query.where(IntelItem.category == category)
    if severity > SEVERITY_MIN:
        query = query.where(IntelItem.severity >= severity)
    if stock:
        query = query.where(
            IntelItem.id.in_(select(IntelImpact.intel_id).where(IntelImpact.stock_id == stock))
        )
    items = list(session.scalars(query))
    if primary:
        items = [i for i in items if i.document is None or i.document.kind in PRIMARY_KINDS]
    stocks = list(session.scalars(select(Stock).order_by(Stock.symbol)))
    return _render(
        request,
        "intel.html",
        items=items,
        stocks=stocks,
        categories=INTEL_CATEGORIES,
        f_category=category,
        f_stock=stock,
        f_severity=severity,
        f_primary=bool(primary),
        feed_errors=[f for f in session.scalars(select(Feed)) if f.last_error],
    )


@router.post("/intel/refresh")
def intel_refresh(session: SessionDep) -> RedirectResponse:
    touch(session, SCAN_REQUEST_KEY)
    return _redirect("/intel", "scan_requested")


@router.get("/intel/feeds", response_class=HTMLResponse)
def feeds_page(request: Request, session: SessionDep) -> HTMLResponse:
    return _render(
        request, "feeds.html", feeds=list(session.scalars(select(Feed).order_by(Feed.id)))
    )


class FeedForm(BaseModel):
    name: str
    url: str
    publisher: str = ""
    doc_kind: str = "news"


@router.post("/intel/feeds")
def feed_add(session: SessionDep, form: Annotated[FeedForm, Form()]) -> RedirectResponse:
    if not form.url.startswith(("http://", "https://")) or not form.name.strip():
        raise HTTPException(400, "Name und http(s)-URL sind nötig")
    session.add(
        Feed(
            name=form.name.strip(),
            kind="rss",
            url=form.url.strip(),
            publisher=form.publisher.strip() or form.name.strip(),
            doc_kind=form.doc_kind
            if form.doc_kind in ("news", "gov", "press", "filing")
            else "news",
        )
    )
    return _redirect("/intel/feeds", "feed_added")


@router.post("/intel/feeds/{feed_id}/toggle")
def feed_toggle(feed_id: int, session: SessionDep) -> RedirectResponse:
    feed = session.get(Feed, feed_id)
    if feed is None:
        raise HTTPException(404)
    feed.enabled, feed.failures = not feed.enabled, 0
    return _redirect("/intel/feeds", "feed_toggled")


@router.post("/intel/feeds/{feed_id}/delete")
def feed_delete(feed_id: int, session: SessionDep) -> RedirectResponse:
    feed = session.get(Feed, feed_id)
    if feed is None:
        raise HTTPException(404)
    session.delete(feed)
    return _redirect("/intel/feeds", "feed_removed")


# ------------------------------------------------------------------ documents
@router.get("/documents/{doc_id}", response_class=HTMLResponse)
def document_page(doc_id: int, request: Request, session: SessionDep) -> HTMLResponse:
    doc = session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404)
    return _render(
        request,
        "document.html",
        doc=doc,
        preview=doc.text[:DOC_PREVIEW_CHARS],
        truncated=len(doc.text) > DOC_PREVIEW_CHARS,
        stock=session.get(Stock, doc.stock_id) if doc.stock_id else None,
        datapoints=list(session.scalars(select(Datapoint).where(Datapoint.document_id == doc.id))),
        relations=_relations_for_document(session, doc.id),
        insights=list(session.scalars(select(Insight).where(Insight.document_id == doc.id))),
        intel=list(session.scalars(select(IntelItem).where(IntelItem.document_id == doc.id))),
        sections=outline(doc)[:30],
    )


def _relations_for_document(session: Session, doc_id: int) -> list[dict[str, Any]]:
    rows = []
    for rel in session.scalars(select(Relation).where(Relation.document_id == doc_id)):
        src, dst = session.get(Entity, rel.source_id), session.get(Entity, rel.target_id)
        rows.append(
            {"rel": rel, "source": src.name if src else "?", "target": dst.name if dst else "?"}
        )
    return rows


@router.post("/documents/{doc_id}/read")
def document_read(doc_id: int, session: SessionDep) -> RedirectResponse:
    doc = session.get(Document, doc_id)
    stock = session.get(Stock, doc.stock_id) if doc and doc.stock_id else None
    if doc is None or stock is None:
        raise HTTPException(400, "Das Dokument gehört zu keiner Aktie")
    ticket = tickets.create_ticket(
        session,
        stock,
        WorkflowKey.READ_FILING,
        topic=f"doc:{doc.id}",
        origin=TicketOrigin.USER,
    )
    return _redirect(f"/tickets/{ticket.id}")


# ------------------------------------------------------------------ graph
@router.get("/graph", response_class=HTMLResponse)
def graph_page(request: Request, session: SessionDep, stock: int = 0) -> HTMLResponse:
    return _render(
        request,
        "graph.html",
        stocks=list(session.scalars(select(Stock).order_by(Stock.symbol))),
        selected=stock,
        depth=GRAPH_DEFAULT_DEPTH,
        names=[e.name for e in session.scalars(select(Entity).order_by(Entity.name))],
        entity_kinds=ENTITY_KINDS,
        relation_kinds=RELATION_KINDS,
    )


@router.get("/api/graph")
def api_graph(
    session: SessionDep, stock: int = 0, depth: int = GRAPH_DEFAULT_DEPTH
) -> dict[str, Any]:
    return entities.graph(session, stock or None, max(1, min(depth, 3)))


class RelationForm(BaseModel):
    source: str
    source_kind: str = "company"
    target: str
    target_kind: str = "supplier"
    kind: str = "supplies"
    strength: str = ""
    note: str = ""
    country: str = ""


@router.post("/graph/relations")
def relation_add(session: SessionDep, form: Annotated[RelationForm, Form()]) -> RedirectResponse:
    try:
        src = entities.get_or_create_entity(session, form.source, form.source_kind)
        dst = entities.get_or_create_entity(
            session,
            form.target,
            form.target_kind,
            country=form.country,
        )
        strength = _number(form.strength, "Anteil") if form.strength.strip() else None
        entities.add_relation(
            session,
            src,
            dst,
            RelationInput(form.kind, strength, form.note, origin="user"),
        )
    except (GraphError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return _redirect("/graph", "relation_added")


# ------------------------------------------------------------------ map
def _position_values(session: Session, container: Container) -> dict[int, float]:
    rows = portfolio.holding_rows(session, container.market)
    return {r.holding.stock_id: r.market_value for r in rows if r.market_value}


@router.get("/map", response_class=HTMLResponse)
def map_page(request: Request, session: SessionDep) -> HTMLResponse:
    unlocated = [e for e in entities.assets(session) if e.lat is None or e.lon is None]
    return _render(request, "map.html", unlocated=unlocated, days=MAP_RECENT_DAYS)


@router.get("/api/map")
def api_map(session: SessionDep, container: ContainerDep) -> dict[str, Any]:
    symbols = {s.id: s.symbol for s in session.scalars(select(Stock))}
    cutoff = utcnow() - timedelta(days=MAP_RECENT_DAYS)
    exposure = entities.country_exposure(session, _position_values(session, container))
    items = session.scalars(
        select(IntelItem).where(IntelItem.lat.is_not(None), IntelItem.published_at >= cutoff),
    )
    asset_ids = {a.id: a for a in entities.assets(session) if a.lat is not None}
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
            for a in asset_ids.values()
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
            name: {"share": e.share, "reasons": e.contributions[:6]} for name, e in exposure.items()
        },
    }


class LocationForm(BaseModel):
    lat: str
    lon: str
    country: str = ""


@router.post("/entities/{entity_id}/location")
def entity_location(
    entity_id: int,
    session: SessionDep,
    form: Annotated[LocationForm, Form()],
) -> RedirectResponse:
    entity = session.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(404)
    try:
        entities.set_location(
            entity,
            _number(form.lat, "Breite"),
            _number(form.lon, "Länge"),
            form.country,
        )
    except (GraphError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return _redirect("/map", "location_set")


# ------------------------------------------------------------------ commodity cockpit
@router.get("/commodities", response_class=HTMLResponse)
def commodities_page(
    request: Request,
    session: SessionDep,
    container: ContainerDep,
) -> HTMLResponse:
    rows = cockpit.commodity_rows(container.market)
    values = _position_values(session, container)
    miners = [
        s
        for s in session.scalars(select(Stock).where(Stock.holding.has()))
        if s.profile == "mining"
    ]
    scenario_rows = {
        s: scenarios.mining_scenarios(container.market, s, SCENARIO_SHOCKS) for s in miners
    }
    return _render(
        request,
        "commodities.html",
        rows=rows,
        macro=cockpit.macro_rows(container.market),
        ratios=cockpit.ratios(rows),
        exposure=cockpit.exposure_by_commodity(session, values),
        scenarios={s: r for s, r in scenario_rows.items() if r},
        shocks=SCENARIO_SHOCKS,
        catalog=BY_KEY,
    )
