"""Explorer API: commodities, map, asset cards, derivations, comparison, companies, search."""

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from watchstreet.commodities import BY_KEY, COMMODITIES
from watchstreet.constants import DAYS_PER_YEAR, MAP_RECENT_DAYS, MAX_SELECTION, RECENT_LIMIT
from watchstreet.domain import DataOrigin, Provenance, SubjectType
from watchstreet.metrics import METRICS
from watchstreet.models import (
    Asset,
    Company,
    Event,
    Fact,
    Financing,
    Finding,
    Person,
    Proposal,
    Thesis,
    Ticket,
)
from watchstreet.services import imports, prices
from watchstreet.services.changes import log_change
from watchstreet.services.companies import company_view
from watchstreet.services.facts import FactInput, fact_history, record_fact
from watchstreet.services.world import card, existed_on, load_bundle, map_feature
from watchstreet.timeutil import utcnow
from watchstreet.web import payloads
from watchstreet.web.deps import ContainerDep, SessionDep, ViewDep, get_or_404
from watchstreet.workflows.research import linked_documents

router = APIRouter(prefix="/api/v1", tags=["explorer"])
COLOR_MODES = ("status", "margin", "delta", "knowledge", "quality")
ASSET = SubjectType.ASSET
COMPANY = SubjectType.COMPANY


@router.get("/commodities")
def commodities(container: ContainerDep) -> list[dict[str, Any]]:
    quotes = {q.key: q for q in prices.current_quotes(container.market)}
    return [
        {
            "key": c.key,
            "label": c.label,
            "unit": c.unit,
            "price_unit": c.price_unit,
            "color": c.color,
            "price": quotes[c.key].price,
            "change_pct": quotes[c.key].change_pct,
        }
        for c in COMMODITIES
    ]


@router.get("/commodities/{key}/prices")
def price_history(key: str, session: SessionDep) -> list[dict[str, Any]]:
    if key not in BY_KEY:
        raise HTTPException(status_code=404, detail="Unbekannter Rohstoff")
    return [{"day": p.day.isoformat(), "close": p.close} for p in prices.history(session, key)]


def _stress_summary(features: list[dict[str, Any]], commodity: str) -> dict[str, Any]:
    """How many producing mines lose money at the view's prices, and how much is unknown.

    Only mines whose main product is the chosen commodity count: a by-product is measured in
    another unit and at another cost, so adding it up would mix pounds with ounces.
    """
    producing = [
        f["properties"]
        for f in features
        if f["properties"]["status"] == "production"
        and (not commodity or f["properties"]["commodity"] == commodity)
    ]
    known = [p for p in producing if p["margin"] is not None]
    under = [p for p in known if p["margin"] < 0]
    total = sum(p["production"] or 0.0 for p in known)
    lost = sum(p["production"] or 0.0 for p in under)
    return {
        "producing": len(producing),
        "unknown": len(producing) - len(known),
        "under_water": len(under),
        "production_share_under_water": lost / total if total else None,
    }


@router.get("/map")
def world_map(
    session: SessionDep, ctx: ViewDep, commodity: str = "", color: str = "status"
) -> dict[str, Any]:
    """GeoJSON of all assets that existed at the reference date, plus recent events."""
    if color not in COLOR_MODES:
        raise HTTPException(status_code=422, detail="Unbekannter Farbmodus")
    bundle = load_bundle(session)
    features = [
        map_feature(asset, bundle, ctx, color)
        for asset in bundle.assets
        if existed_on(asset, ctx.reference)
        and (not commodity or commodity in {c.commodity for c in asset.commodities})
    ]
    events = session.scalars(
        select(Event).options(selectinload(Event.links)).order_by(Event.occurred_at.desc())
    )
    recent = [e for e in events if (utcnow() - e.occurred_at).days <= MAP_RECENT_DAYS]
    return {
        "type": "FeatureCollection",
        "features": features,
        "summary": _stress_summary(features, commodity),
        "events": [payloads.event(e) for e in recent],
        "prices": dict(ctx.prices),
        "reference": ctx.reference.isoformat(),
    }


@router.get("/cards")
def cards(session: SessionDep, ctx: ViewDep, ids: str) -> list[dict[str, Any]]:
    wanted = [int(part) for part in ids.split(",") if part.isdigit()][:MAX_SELECTION]
    bundle = load_bundle(session, wanted)
    by_id = {a.id: a for a in bundle.assets}
    return [card(by_id[i], bundle, ctx) for i in wanted if i in by_id]


@router.get("/assets/{asset_id}")
def asset_detail(asset_id: int, session: SessionDep, ctx: ViewDep) -> dict[str, Any]:
    asset = get_or_404(session, Asset, asset_id)
    bundle = load_bundle(session, [asset_id])
    where_subject = (Finding.subject_type == ASSET, Finding.subject_id == asset_id)
    findings = session.scalars(select(Finding).where(*where_subject).order_by(Finding.id.desc()))
    tickets = session.scalars(
        select(Ticket)
        .where(Ticket.subject_type == ASSET, Ticket.subject_id == asset_id)
        .order_by(Ticket.id.desc())
        .limit(RECENT_LIMIT)
    )
    proposals = session.scalars(
        select(Proposal).where(Proposal.subject_type == ASSET, Proposal.subject_id == asset_id)
    )

    def then(rows: Any) -> list[Any]:
        """Research recorded after the reference date did not exist back then."""
        return [r for r in rows if ctx.as_of is None or r.created_at.date() <= ctx.as_of]

    return {
        "card": card(bundle.assets[0], bundle, ctx),
        "milestones": [payloads.milestone(m) for m in asset.milestones],
        "statuses": [
            {"status": p.status, "from": p.valid_from.isoformat()} for p in asset.statuses
        ],
        "findings": [payloads.finding(f) for f in then(findings)],
        "tickets": [payloads.ticket(t) for t in then(tickets)],
        "proposals": [payloads.proposal(p) for p in proposals if p.state == "draft"],
        "documents": [payloads.document(d) for d in linked_documents(session, ASSET, asset_id)],
    }


@router.get("/assets/{asset_id}/facts/{metric}")
def fact_derivation(asset_id: int, metric: str, session: SessionDep) -> dict[str, Any]:
    """Everything behind one figure: every stored value with source, quote and definition."""
    if metric not in METRICS:
        raise HTTPException(status_code=404, detail="Unbekannte Kennzahl")
    history = fact_history(session, ASSET, asset_id, metric)
    input_ids = {i for f in history for i in f.inputs.get("fact_ids", [])}
    inputs = list(session.scalars(select(Fact).where(Fact.id.in_(input_ids)))) if input_ids else []
    return {
        "metric": metric,
        "label": METRICS[metric].label,
        "history": [payloads.fact_detail(f) for f in history],
        "inputs": [payloads.fact_detail(f) for f in inputs],
    }


class FactBody(BaseModel):
    subject_type: str = SubjectType.ASSET
    subject_id: int
    metric: str
    value: float | None = None
    low: float | None = None
    high: float | None = None
    text: str = ""
    unit: str = ""
    basis: str = ""
    period_end: date | None = None
    published_at: date | None = None
    provenance: str = Provenance.REPORTED


@router.post("/facts")
def add_fact(body: FactBody, session: SessionDep, container: ContainerDep) -> dict[str, Any]:
    """A figure entered by the user; it outranks agent and API values for the same period."""
    get_or_404(session, Company if body.subject_type == COMPANY else Asset, body.subject_id)
    fact = record_fact(
        session,
        FactInput(
            body.subject_type,
            body.subject_id,
            body.metric,
            value=body.value,
            low=body.low,
            high=body.high,
            text=body.text,
            unit=body.unit or METRICS[body.metric].unit if body.metric in METRICS else body.unit,
            basis=body.basis,
            period_end=body.period_end,
            published_at=body.published_at,
            provenance=body.provenance,
            origin=DataOrigin.USER,
            is_demo=container.is_demo,
        ),
    )
    return payloads.fact_detail(fact)


@router.post("/facts/{fact_id}/confirm")
def confirm_fact(fact_id: int, session: SessionDep) -> dict[str, Any]:
    """The user vouches for an imported figure; it then counts as the user's own entry."""
    fact = imports.confirm(session, get_or_404(session, Fact, fact_id))
    session.commit()
    return payloads.fact_detail(fact)


@router.post("/facts/{fact_id}/retract")
def retract_fact(fact_id: int, session: SessionDep) -> dict[str, Any]:
    """Withdraw an own or imported figure. It stays in the history, marked as withdrawn."""
    fact = get_or_404(session, Fact, fact_id)
    imports.retract(session, fact)
    session.commit()
    return payloads.fact_detail(fact)


@router.get("/compare")
def compare(
    session: SessionDep, ctx: ViewDep, ids: str, anchor: str = "discovery"
) -> dict[str, Any]:
    """Cards side by side plus each life line relative to a shared anchor milestone (year 0)."""
    wanted = [int(part) for part in ids.split(",") if part.isdigit()][:MAX_SELECTION]
    bundle = load_bundle(session, wanted)
    lanes = []
    for asset in bundle.assets:
        milestones = session.get(Asset, asset.id).milestones  # type: ignore[union-attr]
        zero = next((m.day for m in milestones if m.kind == anchor), None)
        lanes.append(
            {
                "asset_id": asset.id,
                "anchor_day": zero.isoformat() if zero else None,
                "milestones": [
                    {
                        **payloads.milestone(m),
                        "years": round((m.day - zero).days / DAYS_PER_YEAR, 1) if zero else None,
                    }
                    for m in milestones
                ],
            }
        )
    by_id = {a.id: a for a in bundle.assets}
    return {
        "cards": [card(by_id[i], bundle, ctx) for i in wanted if i in by_id],  # selection order
        "lanes": lanes,
        "anchor": anchor,
    }


@router.get("/companies/{company_id}")
def company_detail(
    company_id: int, session: SessionDep, ctx: ViewDep, container: ContainerDep
) -> dict[str, Any]:
    """Balance sheet, dilution, people, royalties, checklist and assets of one company."""
    company = get_or_404(session, Company, company_id)
    view = company_view(session, company, ctx, container.market)
    subject = (Finding.subject_type == COMPANY, Finding.subject_id == company_id)
    findings = session.scalars(select(Finding).where(*subject).order_by(Finding.id.desc()))
    proposals = session.scalars(
        select(Proposal).where(Proposal.subject_type == COMPANY, Proposal.subject_id == company_id)
    )
    return {
        **view,
        "findings": [payloads.finding(f) for f in findings],
        "proposals": [payloads.proposal(p) for p in proposals if p.state == "draft"],
        "documents": [payloads.document(d) for d in linked_documents(session, COMPANY, company_id)],
    }


class PersonBody(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    role: str = Field(default="", max_length=120)
    since: date | None = None
    track_record: str = ""
    prior_companies: str = ""
    shares_held: float | None = Field(default=None, ge=0)


class FinancingBody(BaseModel):
    day: date
    kind: Literal["equity", "debt", "royalty_sale"] = "equity"
    amount: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    shares: float | None = Field(default=None, gt=0)
    warrants: float | None = Field(default=None, gt=0)
    warrant_price: float | None = Field(default=None, gt=0)
    warrant_expiry: date | None = None
    investors: str = ""
    note: str = ""


@router.post("/companies/{company_id}/people", status_code=201)
def add_person(company_id: int, body: PersonBody, session: SessionDep) -> dict[str, int]:
    """A user entry: who runs the company. Kept as the user's own statement, without a source."""
    company = get_or_404(session, Company, company_id)
    person = Person(company_id=company.id, origin=DataOrigin.USER, **body.model_dump())
    session.add(person)
    log_change(session, COMPANY, company.id, "person", f"Person erfasst: {body.name}")
    session.commit()
    return {"id": person.id}


@router.post("/companies/{company_id}/financings", status_code=201)
def add_financing(company_id: int, body: FinancingBody, session: SessionDep) -> dict[str, int]:
    """A user entry: one capital raise."""
    company = get_or_404(session, Company, company_id)
    if body.day > utcnow().date():
        raise HTTPException(status_code=422, detail="Das Datum liegt in der Zukunft")
    financing = Financing(company_id=company.id, origin=DataOrigin.USER, **body.model_dump())
    session.add(financing)
    log_change(
        session, COMPANY, company.id, "financing", f"Finanzierung erfasst: {body.day.isoformat()}"
    )
    session.commit()
    return {"id": financing.id}


def _own_entry(session: SessionDep, model: type[Person | Financing], entry_id: int) -> Any:
    entry = get_or_404(session, model, entry_id)
    if entry.origin != DataOrigin.USER or entry.is_demo:
        raise HTTPException(status_code=400, detail="Nur eigene Einträge lassen sich löschen")
    return entry


@router.delete("/people/{person_id}", status_code=204)
def delete_person(person_id: int, session: SessionDep) -> None:
    """Remove a person the user entered (typing errors must not stay)."""
    person = _own_entry(session, Person, person_id)
    log_change(session, COMPANY, person.company_id, "person", f"Person gelöscht: {person.name}")
    session.delete(person)
    session.commit()


@router.delete("/financings/{financing_id}", status_code=204)
def delete_financing(financing_id: int, session: SessionDep) -> None:
    """Remove a financing the user entered."""
    financing = _own_entry(session, Financing, financing_id)
    log_change(
        session, COMPANY, financing.company_id, "financing",
        f"Finanzierung gelöscht: {financing.day.isoformat()}",
    )  # fmt: skip
    session.delete(financing)
    session.commit()


@router.get("/companies/{company_id}/facts/{metric}")
def company_fact_derivation(company_id: int, metric: str, session: SessionDep) -> dict[str, Any]:
    if metric not in METRICS:
        raise HTTPException(status_code=404, detail="Unbekannte Kennzahl")
    history = fact_history(session, COMPANY, company_id, metric)
    return {
        "metric": metric,
        "label": METRICS[metric].label,
        "history": [payloads.fact_detail(f) for f in history],
        "inputs": [],
    }


@router.get("/search")
def search(session: SessionDep, q: str) -> list[dict[str, Any]]:
    needle = f"%{q.strip()}%"
    if len(q.strip()) < 2:  # noqa: PLR2004 - a single letter matches everything
        return []
    hits: list[dict[str, Any]] = []
    sources: tuple[tuple[str, Any, Any], ...] = (
        ("asset", Asset, Asset.name),
        ("company", Company, Company.name),
        ("thesis", Thesis, Thesis.title),
    )
    for kind, model, column in sources:
        rows = session.scalars(select(model).where(column.ilike(needle)).limit(RECENT_LIMIT))
        hits.extend({"type": kind, "id": r.id, "label": getattr(r, column.key)} for r in rows)
    return hits
