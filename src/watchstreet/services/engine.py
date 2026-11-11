"""Stage 1 and 2 of the analysis engine: deterministic checks that end in findings and proposals.

Nothing here calls an LLM and nothing here starts research; the user starts proposals.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.analysis.rules import robust_outliers
from watchstreet.constants import MIN_PEER_GROUP, NEIGHBOUR_RADIUS_KM, SHORT_RUNWAY_MONTHS
from watchstreet.domain import (
    AssetStatus,
    DataOrigin,
    Epistemic,
    FindingKind,
    Provenance,
    StakeRole,
    SubjectType,
)
from watchstreet.economics.company import runway_months
from watchstreet.geo import haversine_km
from watchstreet.metrics import PRODUCING_STATUSES, key_metrics
from watchstreet.models import Asset, Company, Fact, Finding
from watchstreet.services.changes import log_change
from watchstreet.services.companies import company_facts
from watchstreet.services.proposals import create_proposal
from watchstreet.services.world import (
    Bundle,
    ViewContext,
    primary_commodity,
    stakes_on,
    status_on,
)
from watchstreet.temporal.views import latest_per_metric

EARLY_STAGES = (AssetStatus.EXPLORATION, AssetStatus.DEVELOPMENT)


@dataclass
class EngineReport:
    findings: int = 0
    proposals: int = 0


def _status(asset: Asset, ctx: ViewContext) -> str:
    period = status_on(asset, ctx.reference)
    return period.status if period else "unknown"


def peer_costs(bundle: Bundle, asset: Asset, ctx: ViewContext) -> list[Fact]:
    """Sourced unit costs of other producing assets with the same main commodity."""
    commodity = primary_commodity(asset)
    peers: list[Fact] = []
    for other in bundle.assets:
        if other.id == asset.id or primary_commodity(other) != commodity:
            continue
        if _status(other, ctx) not in PRODUCING_STATUSES:
            continue
        fact = latest_per_metric(bundle.facts.get(other.id, []), ctx.as_of, ctx.view).get("aisc")
        if fact and fact.value is not None and fact.provenance != Provenance.ESTIMATED:
            peers.append(fact)
    return peers


def _add_finding(session: Session, asset: Asset, rule_key: str, kind: str, text: str) -> bool:
    exists = session.scalars(
        select(Finding.id).where(
            Finding.subject_type == SubjectType.ASSET,
            Finding.subject_id == asset.id,
            Finding.rule_key == rule_key,
        )
    ).first()
    if exists:
        return False
    session.add(
        Finding(
            subject_type=SubjectType.ASSET,
            subject_id=asset.id,
            kind=kind,
            rule_key=rule_key,
            epistemic=Epistemic.CORRELATION,
            text=text,
            is_demo=asset.is_demo,
            uncertainty="Regelbasierte Auffälligkeit ohne geprüfte Ursache.",
        )
    )
    log_change(session, SubjectType.ASSET, asset.id, "finding", text)
    return True


def _propose(session: Session, asset: Asset, template: str, **params: str) -> int:
    proposal = create_proposal(
        session, SubjectType.ASSET, asset.id, template, params=params, origin=DataOrigin.ENGINE
    )
    return 1 if proposal else 0


def _gap_rule(session: Session, bundle: Bundle, ctx: ViewContext, report: EngineReport) -> None:
    for asset in bundle.assets:
        status = _status(asset, ctx)
        facts = latest_per_metric(bundle.facts.get(asset.id, []), ctx.as_of, ctx.view)
        for metric in key_metrics(status):
            if metric in facts:
                continue
            report.proposals += _propose(session, asset, "fill_metric", metric=metric)
            if metric == "aisc" and len(peer_costs(bundle, asset, ctx)) >= MIN_PEER_GROUP:
                report.proposals += _propose(session, asset, "estimate_cost")


def _outlier_rule(session: Session, bundle: Bundle, ctx: ViewContext, report: EngineReport) -> None:
    groups: dict[str, dict[int, float]] = {}
    for asset in bundle.assets:
        if _status(asset, ctx) not in PRODUCING_STATUSES:
            continue
        fact = latest_per_metric(bundle.facts.get(asset.id, []), ctx.as_of, ctx.view).get("aisc")
        if fact and fact.value is not None:
            groups.setdefault(primary_commodity(asset), {})[asset.id] = fact.value
    by_id = {a.id: a for a in bundle.assets}
    for values in groups.values():
        for asset_id in robust_outliers(values):
            asset = by_id[asset_id]
            text = (
                f"Stückkosten von {asset.name} ({values[asset_id]:g}) liegen deutlich ausserhalb "
                f"der Vergleichsgruppe (n={len(values)})."
            )
            if _add_finding(session, asset, "cost_outlier", FindingKind.ANOMALY, text):
                report.findings += 1
                report.proposals += _propose(session, asset, "cost_structure")


def _operators(asset: Asset, ctx: ViewContext) -> set[int]:
    return {s.company_id for s in stakes_on(asset, ctx.reference) if s.role == StakeRole.OPERATOR}


def _neighbour_rule(
    session: Session, bundle: Bundle, ctx: ViewContext, report: EngineReport
) -> None:
    producers = [a for a in bundle.assets if _status(a, ctx) in PRODUCING_STATUSES]
    for asset in bundle.assets:
        if _status(asset, ctx) not in EARLY_STAGES:
            continue
        for mine in producers:
            distance = haversine_km(asset.lat, asset.lon, mine.lat, mine.lon)
            if distance > NEIGHBOUR_RADIUS_KM or _operators(asset, ctx) & _operators(mine, ctx):
                continue
            text = (
                f"{asset.name} liegt {distance:.0f} km von der produzierenden Mine {mine.name} "
                "eines anderen Betreibers entfernt."
            )
            if _add_finding(session, asset, f"neighbour_{mine.id}", FindingKind.PATTERN, text):
                report.findings += 1
                report.proposals += _propose(session, asset, "takeover")


def _runway_rule(session: Session, ctx: ViewContext, report: EngineReport) -> None:
    """A company that runs out of cash within a year will have to raise money: say so."""
    for company in session.scalars(select(Company)):
        facts = company_facts(session, company.id, ctx)
        cash, burn = facts.get("cash"), facts.get("burn_rate")
        months = runway_months(cash.value if cash else None, burn.value if burn else None)
        if months is None or months >= SHORT_RUNWAY_MONTHS:
            continue
        exists = session.scalars(
            select(Finding.id).where(
                Finding.subject_type == SubjectType.COMPANY,
                Finding.subject_id == company.id,
                Finding.rule_key == "short_runway",
            )
        ).first()
        if exists:
            continue
        text = f"Die Kasse von {company.name} reicht beim aktuellen Mittelabfluss rund {months:.0f} Monate."
        session.add(
            Finding(
                subject_type=SubjectType.COMPANY,
                subject_id=company.id,
                kind=FindingKind.ANOMALY,
                rule_key="short_runway",
                epistemic=Epistemic.EVIDENCED,
                text=text,
                uncertainty="Rechnung aus Kasse und Mittelabfluss; künftige Einnahmen nicht berücksichtigt.",
                is_demo=company.is_demo,
            )
        )
        log_change(session, SubjectType.COMPANY, company.id, "finding", text)
        report.findings += 1
        proposal = create_proposal(
            session, SubjectType.COMPANY, company.id, "financing", origin=DataOrigin.ENGINE
        )
        report.proposals += 1 if proposal else 0


def run_engine(session: Session, bundle: Bundle, ctx: ViewContext) -> EngineReport:
    report = EngineReport()
    _gap_rule(session, bundle, ctx, report)
    _outlier_rule(session, bundle, ctx, report)
    _neighbour_rule(session, bundle, ctx, report)
    _runway_rule(session, ctx, report)
    session.flush()
    return report
