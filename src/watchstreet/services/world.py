"""The explorer's read model: assets with their facts, economics and knowledge status.

One :class:`Bundle` is loaded per request (a handful of queries, no N+1); everything below it is
plain computation on that snapshot for one :class:`ViewContext`.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from watchstreet.analysis.rules import KnowledgeInputs, knowledge_status
from watchstreet.commodities import BY_KEY
from watchstreet.constants import PERCENT, STALE_FACT_AFTER
from watchstreet.domain import (
    ClaimKind,
    DataOrigin,
    ProposalState,
    Provenance,
    StakeRole,
    SubjectType,
    TicketStatus,
    View,
)
from watchstreet.economics.mine import Interval, MineEconomics, MineInputs, evaluate
from watchstreet.metrics import METRICS, PRODUCING_STATUSES, card_metrics, key_metrics
from watchstreet.models import (
    Asset,
    ChangeEntry,
    Company,
    Fact,
    Proposal,
    Stake,
    StatusPeriod,
    Ticket,
)
from watchstreet.services.changes import last_visit
from watchstreet.temporal.views import latest_per_metric

MODE_TODAY, MODE_AS_OF, MODE_SCENARIO = "today", "as_of", "scenario"
COST_METRICS = ("aisc", "cash_cost")


@dataclass(frozen=True)
class ViewContext:
    """Which state of knowledge and which prices a request wants to see."""

    today: date
    prices: Mapping[str, float]  # effective price per commodity for this view
    base_prices: Mapping[str, float] = field(default_factory=dict)  # same view without scenario
    as_of: date | None = None
    view: View = View.AS_KNOWN
    scenario: Mapping[str, float] = field(default_factory=dict)

    @property
    def reference(self) -> date:
        return self.as_of or self.today

    def mode(self, commodity: str) -> str:
        if commodity in self.scenario:
            return MODE_SCENARIO
        return MODE_AS_OF if self.as_of else MODE_TODAY


@dataclass
class Bundle:
    assets: list[Asset]
    facts: dict[int, list[Fact]]
    open_proposals: dict[int, int]
    running: set[int]
    unseen_results: set[int]
    researched: set[int]
    changed: set[int]


def load_bundle(session: Session, asset_ids: Iterable[int] | None = None) -> Bundle:
    query = (
        select(Asset)
        .options(
            selectinload(Asset.commodities),
            selectinload(Asset.statuses),
            selectinload(Asset.stakes).selectinload(Stake.company),
        )
        .order_by(Asset.id)
    )
    if asset_ids is not None:
        query = query.where(Asset.id.in_(list(asset_ids)))
    assets = list(session.scalars(query))
    ids = [a.id for a in assets]
    asset = SubjectType.ASSET
    facts: dict[int, list[Fact]] = defaultdict(list)
    for fact in session.scalars(
        select(Fact)
        .where(Fact.subject_type == asset, Fact.subject_id.in_(ids))
        .options(selectinload(Fact.document))
    ):
        facts[fact.subject_id].append(fact)
    open_proposals: dict[int, int] = defaultdict(int)
    for subject_id in session.scalars(
        select(Proposal.subject_id).where(
            Proposal.subject_type == asset, Proposal.state == ProposalState.DRAFT
        )
    ):
        open_proposals[subject_id] += 1
    running, unseen, researched = set(), set(), set()
    for ticket in session.scalars(select(Ticket).where(Ticket.subject_type == asset)):
        if ticket.status in (TicketStatus.QUEUED, TicketStatus.RUNNING):
            running.add(ticket.subject_id)
        elif ticket.status == TicketStatus.DONE:
            if ticket.result.get("fact_ids") or ticket.result.get("agent_used"):
                researched.add(ticket.subject_id)
            if not ticket.seen:
                unseen.add(ticket.subject_id)
    visit = last_visit(session)
    changed_query = select(ChangeEntry.subject_id).where(ChangeEntry.subject_type == asset)
    if visit is not None:
        changed_query = changed_query.where(ChangeEntry.at > visit)
    changed = set(session.scalars(changed_query)) if visit is not None else set()
    return Bundle(assets, facts, open_proposals, running, unseen, researched, changed)


# --- time-dependent attributes ------------------------------------------------


def status_on(asset: Asset, day: date) -> StatusPeriod | None:
    valid = [
        p
        for p in asset.statuses
        if p.valid_from <= day and (p.valid_to is None or p.valid_to > day)
    ]
    return valid[-1] if valid else None


def stakes_on(asset: Asset, day: date) -> list[Stake]:
    return [
        s
        for s in asset.stakes
        if (s.valid_from is None or s.valid_from <= day)
        and (s.valid_to is None or s.valid_to > day)
    ]


def royalty_rate(asset: Asset, day: date) -> float:
    """Share of revenue paid to royalty and stream holders (0..1), capped at all of it."""
    burdens = (StakeRole.ROYALTY, StakeRole.STREAM)
    total = sum(s.share_pct or 0.0 for s in stakes_on(asset, day) if s.role in burdens)
    return min(total / PERCENT, 1.0)


def primary_commodity(asset: Asset) -> str:
    primary = [c.commodity for c in asset.commodities if c.role == "primary"]
    return primary[0] if primary else (asset.commodities[0].commodity if asset.commodities else "")


def metric_unit(subject: Asset | Company, metric_key: str) -> str:
    """The unit a figure of this subject carries, from the commodity or the metric catalog."""
    metric = METRICS[metric_key]
    if metric.unit or isinstance(subject, Company) or metric.is_text:
        return metric.unit
    commodity = BY_KEY.get(primary_commodity(subject))
    if commodity is None:
        return ""
    if metric.per_unit:
        return commodity.price_unit
    return f"{commodity.unit}/Jahr" if metric.annual else commodity.unit


# --- facts as payload -----------------------------------------------------------


def fact_payload(fact: Fact | None, metric_key: str, ctx: ViewContext) -> dict[str, Any]:
    """The one shape every figure has in every API answer; a missing fact is 'unknown'."""
    label = METRICS[metric_key].label
    if fact is None:
        return {"metric": metric_key, "label": label, "provenance": Provenance.UNKNOWN}
    reference = fact.period_end or fact.published_at
    return {
        "metric": metric_key,
        "label": label,
        "value": fact.value,
        "low": fact.value_low,
        "high": fact.value_high,
        "text": fact.text,
        "unit": fact.unit,
        "provenance": fact.provenance,
        "claim_kind": fact.claim_kind,
        "basis": fact.basis,
        "period_end": fact.period_end.isoformat() if fact.period_end else None,
        "published_at": fact.published_at.isoformat() if fact.published_at else None,
        "stale": reference is not None
        and ctx.as_of is None
        and ctx.today - reference > STALE_FACT_AFTER,
        "confidence": fact.confidence,
        "origin": fact.origin,
        "unverified": fact.origin == DataOrigin.IMPORT,
        "fact_id": fact.id,
        "document_id": fact.document_id,
        "is_demo": fact.is_demo,
    }


def _interval(fact: Fact | None) -> Interval | None:
    if fact is None:
        return None
    if fact.value is not None:
        return Interval.point(fact.value)
    if fact.value_low is not None and fact.value_high is not None:
        return Interval(fact.value_low, fact.value_high)
    return None


# --- economics --------------------------------------------------------------------


@dataclass(frozen=True)
class AssetEconomics:
    result: MineEconomics
    base: MineEconomics | None  # same inputs at the non-scenario price
    inputs: tuple[Fact, ...]
    is_forecast: bool  # built on study values of a project

    @property
    def provenance(self) -> str:
        weakest_is_estimate = any(f.provenance == Provenance.ESTIMATED for f in self.inputs)
        return Provenance.ESTIMATED if weakest_is_estimate else Provenance.DERIVED


def asset_economics(
    asset: Asset, facts: Mapping[str, Fact], status: str, ctx: ViewContext
) -> AssetEconomics | None:
    """Mine economics at the view's price; ``None`` if price or cost are unknown."""
    commodity = primary_commodity(asset)
    price = ctx.prices.get(commodity)
    producing = status in PRODUCING_STATUSES
    cost = (
        next((facts[k] for k in COST_METRICS if k in facts), None)
        if producing
        else facts.get("expected_aisc")
    )
    production = facts.get("production" if producing else "expected_production")
    reserves = facts.get("reserves")
    if price is None or cost is None:
        return None
    inputs = MineInputs(
        cost=_interval(cost),
        production=_interval(production),
        reserves=reserves.value if reserves else None,
        royalty=royalty_rate(asset, ctx.reference),
    )
    base_price = ctx.base_prices.get(commodity)
    used = tuple(f for f in (cost, production, reserves) if f is not None)
    return AssetEconomics(
        evaluate(inputs, price),
        evaluate(inputs, base_price) if base_price is not None else None,
        used,
        is_forecast=not producing,
    )


def _derived(
    key: str, label: str, value: Interval | None, unit: str, formula: str, econ: AssetEconomics
) -> dict[str, Any]:
    if value is None:
        return {"metric": key, "label": label, "provenance": Provenance.UNKNOWN}
    return {
        "metric": key,
        "label": label,
        "value": value.mid if value.is_point else None,
        "low": None if value.is_point else value.low,
        "high": None if value.is_point else value.high,
        "unit": unit,
        "provenance": econ.provenance,
        "claim_kind": ClaimKind.GUIDANCE if econ.is_forecast else ClaimKind.ACTUAL,
        "formula": formula,
        "input_fact_ids": [f.id for f in econ.inputs],
        "origin": DataOrigin.ENGINE,
    }


def economics_payload(econ: AssetEconomics | None, commodity: str) -> list[dict[str, Any]]:
    if econ is None:
        return []
    unit = BY_KEY[commodity].price_unit if commodity in BY_KEY else "USD"
    result = econ.result
    life = Interval.point(result.mine_life) if result.mine_life is not None else None
    return [
        _derived(
            "margin",
            "Marge je Einheit",
            result.margin,
            unit,
            "Preis × (1 − Royalties) − Kosten",
            econ,
        ),
        _derived(
            "margin_pct",
            "Marge",
            result.margin_pct,
            "Anteil",
            "(Preis nach Royalties − Kosten) / Preis",
            econ,
        ),
        _derived(
            "cash_flow",
            "Operativer Cashflow p. a.",
            result.cash_flow,
            "USD",
            "Produktion × (Preis nach Royalties − Kosten)",
            econ,
        ),
        _derived("mine_life", "Restlaufzeit", life, "Jahre", "Reserven / Produktion", econ),
        _derived(
            "nav",
            "Einfacher Asset-NAV",
            result.nav,
            "USD",
            "Barwert des Cashflows über die Reservenlaufzeit, 8 % Diskontsatz; "
            "bei Verlust Stilllegung (0)",
            econ,
        ),
    ]


# --- knowledge status ----------------------------------------------------------------


def knowledge_payload(
    asset: Asset, facts: Mapping[str, Fact], status: str, bundle: Bundle, ctx: ViewContext
) -> dict[str, Any]:
    newest = [f.period_end or f.published_at for k, f in facts.items() if k in key_metrics(status)]
    dated = [d for d in newest if d is not None]
    stale = bool(dated) and ctx.as_of is None and ctx.today - max(dated) > STALE_FACT_AFTER
    state = knowledge_status(
        KnowledgeInputs(
            has_facts=bool(facts),
            has_agent_research=asset.id in bundle.researched,
            changed_since_visit=asset.id in bundle.changed,
            is_stale=stale,
        )
    )
    return {
        "status": state,
        "open_questions": bundle.open_proposals.get(asset.id, 0),
        "running": asset.id in bundle.running,
        "new_result": asset.id in bundle.unseen_results,
        "missing": [k for k in key_metrics(status) if k not in facts],
    }


# --- cards and map features -------------------------------------------------------------


def _stake_payload(stake: Stake) -> dict[str, Any]:
    return {
        "company_id": stake.company_id,
        "company": stake.company.name,
        "company_slug": stake.company.slug,
        "role": stake.role,
        "share_pct": stake.share_pct,
        "since": stake.valid_from.isoformat() if stake.valid_from else None,
    }


def card(asset: Asset, bundle: Bundle, ctx: ViewContext) -> dict[str, Any]:
    """The compact 'character card' of one asset for the given view."""
    period = status_on(asset, ctx.reference)
    status = period.status if period else "unknown"
    facts = latest_per_metric(bundle.facts.get(asset.id, []), ctx.as_of, ctx.view)
    commodity = primary_commodity(asset)
    econ = asset_economics(asset, facts, status, ctx)
    stakes = stakes_on(asset, ctx.reference)
    operator = next((s for s in stakes if s.role == StakeRole.OPERATOR), None)
    return {
        "id": asset.id,
        "slug": asset.slug,
        "name": asset.name,
        "kind": asset.kind,
        "lat": asset.lat,
        "lon": asset.lon,
        "country": asset.country,
        "region": asset.region,
        "mining_method": asset.mining_method,
        "summary": asset.summary,
        "is_demo": asset.is_demo,
        "registry_source": asset.registry_source,
        "commodity": commodity,
        "commodities": [{"key": c.commodity, "role": c.role} for c in asset.commodities],
        "status": status,
        "status_since": period.valid_from.isoformat() if period else None,
        "operator": operator.company.name if operator else None,
        "stakes": [_stake_payload(s) for s in stakes],
        "metrics": [fact_payload(facts.get(k), k, ctx) for k in card_metrics(status)],
        "economics": economics_payload(econ, commodity),
        "economics_is_forecast": bool(econ and econ.is_forecast),
        "by_product_note": bool(
            ctx.scenario
            and len(asset.commodities) > 1
            and econ
            and not econ.result.by_product_adjusted
        ),
        "price": ctx.prices.get(commodity),
        "royalty_pct": royalty_rate(asset, ctx.reference) * PERCENT,
        "mode": ctx.mode(commodity),
        "knowledge": knowledge_payload(asset, facts, status, bundle, ctx),
    }


def _color_value(card_data: dict[str, Any], econ: AssetEconomics | None, mode: str) -> float | None:
    if mode == "quality":
        metrics = card_data["metrics"]
        reported = sum(1 for m in metrics if m["provenance"] == Provenance.REPORTED)
        return reported / len(metrics) if metrics else None
    if econ is None or econ.is_forecast or econ.result.margin_pct is None:
        return None
    if mode == "margin":
        return econ.result.margin_pct.mid
    if mode == "delta" and econ.base is not None and econ.base.margin_pct is not None:
        return econ.result.margin_pct.mid - econ.base.margin_pct.mid
    return None


def map_feature(asset: Asset, bundle: Bundle, ctx: ViewContext, color: str) -> dict[str, Any]:
    data = card(asset, bundle, ctx)
    facts = latest_per_metric(bundle.facts.get(asset.id, []), ctx.as_of, ctx.view)
    econ = asset_economics(asset, facts, data["status"], ctx)
    value = _color_value(data, econ, color)
    knowledge = data["knowledge"]
    return {
        "type": "Feature",
        "id": asset.id,
        "geometry": {"type": "Point", "coordinates": [asset.lon, asset.lat]},
        "properties": {
            "id": asset.id,
            "slug": asset.slug,
            "name": asset.name,
            "status": data["status"],
            "commodity": data["commodity"],
            "commodities": ",".join(c["key"] for c in data["commodities"]),
            "company_ids": ",".join(str(s["company_id"]) for s in data["stakes"]),
            "operator": data["operator"] or "",
            "country": asset.country,
            "color_value": value,
            # plain figures for the cost table and the scenario summary (no forecasts)
            "margin": _mid(econ.result.margin_pct) if econ and not econ.is_forecast else None,
            "unit_cost": _mid(econ.result.cost) if econ and not econ.is_forecast else None,
            "production": _mid(_interval(facts.get("production"))),
            "color_known": value is not None,
            "knowledge": knowledge["status"],
            "open_questions": knowledge["open_questions"],
            "running": knowledge["running"],
            "new_result": knowledge["new_result"],
            "is_demo": asset.is_demo,
        },
    }


def _mid(value: Interval | None) -> float | None:
    return value.mid if value is not None else None


def existed_on(asset: Asset, day: date) -> bool:
    """An asset appears on the map from its first known status onwards.

    Registry entries have a location but no dated status yet; they are shown for today only,
    as "status unknown", never in a view of the past.
    """
    if not asset.statuses:
        return day >= asset.created_at.date()
    return any(p.valid_from <= day for p in asset.statuses)
