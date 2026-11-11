"""The company view: balance sheet, dilution, people, royalties and the due-diligence checklist.

Assets tell what a company owns; this view tells whether the company survives to benefit from
them. Everything derived here names its formula and inherits the weakest origin of its inputs.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import PERCENT, SENSITIVITY_FACTORS
from watchstreet.domain import DataOrigin, Provenance, StakeRole, SubjectType
from watchstreet.economics import company as ratios
from watchstreet.market.service import MarketService
from watchstreet.metrics import COMPANY_CARD, PRODUCING_STATUSES
from watchstreet.models import Company, Fact, Financing, Person, Stake
from watchstreet.services.world import (
    Bundle,
    ViewContext,
    asset_economics,
    card,
    fact_payload,
    load_bundle,
    stakes_on,
    status_on,
)
from watchstreet.temporal.views import latest_per_metric

BURDEN_ROLES = (StakeRole.ROYALTY, StakeRole.STREAM)


@dataclass(frozen=True)
class Question:
    """One due-diligence question and what counts as an answer."""

    key: str
    text: str
    metrics: tuple[str, ...] = ()
    needs: str = ""  # people | financings | costs | royalties


CHECKLIST: tuple[Question, ...] = (
    Question("people", "Wer führt das Unternehmen, und mit welcher Erfolgsbilanz?", needs="people"),
    Question("insiders", "Wie viel des Unternehmens besitzt das Management selbst?", ("insider_ownership",)),
    Question("cash", "Wie viel Kasse ist vorhanden?", ("cash",)),
    Question("debt", "Wie hoch sind die Finanzschulden?", ("debt",)),
    Question("burn", "Wie lange reicht das Geld beim aktuellen Mittelabfluss?", ("cash", "burn_rate")),
    Question("shares", "Wie viele Aktien stehen aus – auch voll verwässert?", ("shares_outstanding", "shares_diluted")),
    Question("financing", "Wie und zu welchem Preis wurde zuletzt finanziert?", needs="financings"),
    Question("costs", "Wo liegen die Assets auf der Kostenkurve?", needs="costs"),
    Question("royalties", "Welche Royalties und Streams belasten die Assets?", ("royalty_burden",), "royalties"),
    Question("catalyst", "Was ist der nächste Meilenstein, der den Wert verändert?", ("next_catalyst",)),
)  # fmt: skip


def company_facts(session: Session, company_id: int, ctx: ViewContext) -> dict[str, Fact]:
    rows = session.scalars(
        select(Fact).where(Fact.subject_type == SubjectType.COMPANY, Fact.subject_id == company_id)
    )
    return latest_per_metric(rows, ctx.as_of, ctx.view)


def _derived(
    key: str,
    label: str,
    value: float | None,
    unit: str,
    formula: str,
    inputs: tuple[Fact | None, ...],
) -> dict[str, Any]:
    used = [f for f in inputs if f is not None]
    if value is None:
        return {"metric": key, "label": label, "provenance": Provenance.UNKNOWN, "formula": formula}
    estimated = any(f.provenance == Provenance.ESTIMATED for f in used)
    return {
        "metric": key,
        "label": label,
        "value": value,
        "unit": unit,
        "provenance": Provenance.ESTIMATED if estimated else Provenance.DERIVED,
        "claim_kind": "actual",
        "formula": formula,
        "input_fact_ids": [f.id for f in used],
        "origin": DataOrigin.ENGINE,
    }


def _cash_empty(
    empty_on: date | None, reference: date, inputs: tuple[Fact | None, ...]
) -> dict[str, Any]:
    """States plainly when the reported cash is used up; an old balance sheet must not look fresh."""
    formula = "Bilanzstichtag + Reichweite; spätere Finanzierungen sind nicht eingerechnet"
    label = "Kasse rechnerisch leer"
    if empty_on is None:
        return {
            "metric": "cash_empty",
            "label": label,
            "provenance": Provenance.UNKNOWN,
            "formula": formula,
        }
    word = "seit" if empty_on <= reference else "am"
    return {
        "metric": "cash_empty", "label": label, "text": f"{word} {empty_on:%d.%m.%Y}",
        "provenance": Provenance.DERIVED, "claim_kind": "actual", "formula": formula,
        "stale": empty_on <= reference, "origin": DataOrigin.ENGINE,
        "input_fact_ids": [f.id for f in inputs if f is not None],
    }  # fmt: skip


def _value(fact: Fact | None) -> float | None:
    return fact.value if fact else None


def owner_share(stakes: list[Stake], company_id: int) -> float:
    """The company's ownership share of an asset (0..1); an operator without stake owns nothing."""
    shares = [
        s.share_pct for s in stakes if s.company_id == company_id and s.role == StakeRole.OWNER
    ]
    return (shares[0] or 0.0) / PERCENT if shares else 0.0


@dataclass(frozen=True)
class Attributable:
    nav: float | None  # sum of the simple asset NAVs, by ownership
    cash_flow: float  # per year, by ownership
    valued: int  # producing assets that entered the NAV
    producing: int


def _attributable(bundle: Bundle, company_id: int, ctx: ViewContext) -> Attributable:
    nav_total, cash_flow, valued, producing = 0.0, 0.0, 0, 0
    for asset in bundle.assets:
        period = status_on(asset, ctx.reference)
        if period is None or period.status not in PRODUCING_STATUSES:
            continue
        facts = latest_per_metric(bundle.facts.get(asset.id, []), ctx.as_of, ctx.view)
        econ = asset_economics(asset, facts, period.status, ctx)
        share = owner_share(stakes_on(asset, ctx.reference), company_id)
        producing += 1
        if econ is None or share <= 0:
            continue
        if econ.result.nav is not None:
            nav_total += econ.result.nav.mid * share
            valued += 1
        if econ.result.cash_flow is not None:
            cash_flow += max(econ.result.cash_flow.mid, 0.0) * share  # a losing mine is closed
    return Attributable(nav_total if valued else None, cash_flow, valued, producing)


def _open_capex(
    bundle: Bundle, company_id: int, ctx: ViewContext
) -> tuple[float | None, list[Fact]]:
    """Capex of the projects not yet producing, weighted by ownership; ``None`` if none is known."""
    used: list[Fact] = []
    total = 0.0
    for asset in bundle.assets:
        period = status_on(asset, ctx.reference)
        if period is not None and period.status in PRODUCING_STATUSES:
            continue
        fact = latest_per_metric(bundle.facts.get(asset.id, []), ctx.as_of, ctx.view).get("capex")
        share = owner_share(stakes_on(asset, ctx.reference), company_id)
        if fact is None or fact.value is None or share <= 0:
            continue
        total += fact.value * share
        used.append(fact)
    return (total if used else None), used


def _sensitivity(bundle: Bundle, company_id: int, ctx: ViewContext) -> list[dict[str, float]]:
    """Attributable cash flow of the producing assets if every price moves by the same factor."""
    rows = []
    for change in SENSITIVITY_FACTORS:
        shifted = replace(ctx, prices={k: v * (1 + change) for k, v in ctx.prices.items()})
        rows.append(
            {"change": change, "cash_flow": _attributable(bundle, company_id, shifted).cash_flow}
        )
    return rows if _attributable(bundle, company_id, ctx).valued else []


def _burdens(bundle: Bundle, ctx: ViewContext) -> list[dict[str, Any]]:
    return [
        {
            "asset_id": asset.id,
            "asset": asset.name,
            "holder": stake.company.name,
            "role": stake.role,
            "share_pct": stake.share_pct,
        }
        for asset in bundle.assets
        for stake in stakes_on(asset, ctx.reference)
        if stake.role in BURDEN_ROLES
    ]


def _checklist(
    facts: Mapping[str, Fact],
    people: list[Person],
    financings: list[Financing],
    cards: list[dict[str, Any]],
    burdens: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Answered means evidence is on file; it does not mean the answer is good."""
    evidence = {
        "people": any(p.track_record.strip() for p in people),
        "financings": bool(financings),
        "costs": any(m["provenance"] != Provenance.UNKNOWN for c in cards for m in c["economics"]),
        "royalties": bool(burdens),
    }
    rows = []
    for question in CHECKLIST:
        by_metrics = bool(question.metrics) and all(m in facts for m in question.metrics)
        answered = by_metrics or evidence.get(question.needs, False)
        missing = [m for m in question.metrics if m not in facts]
        rows.append(
            {"key": question.key, "text": question.text, "answered": answered, "missing": missing}
        )
    return rows


def company_view(
    session: Session, company: Company, ctx: ViewContext, market: MarketService
) -> dict[str, Any]:
    facts = company_facts(session, company.id, ctx)
    asset_ids = set(session.scalars(select(Stake.asset_id).where(Stake.company_id == company.id)))
    bundle = load_bundle(session, asset_ids)
    cards = [card(a, bundle, ctx) for a in bundle.assets]
    people = list(session.scalars(select(Person).where(Person.company_id == company.id)))
    financings = list(
        session.scalars(
            select(Financing)
            .where(Financing.company_id == company.id, Financing.day <= ctx.reference)
            .order_by(Financing.day.desc())
        )
    )
    cash, debt, burn = facts.get("cash"), facts.get("debt"), facts.get("burn_rate")
    shares, diluted = facts.get("shares_outstanding"), facts.get("shares_diluted")
    # only today's quote is known here; a past reference date gets no price instead of today's
    quote = market.try_quote(company.stock.symbol) if company.stock and not ctx.as_of else None
    market_cap = quote.price * shares.value if quote and shares and shares.value else None
    net = ratios.net_cash(_value(cash), _value(debt))
    attributable = _attributable(bundle, company.id, ctx)
    nav_sum = attributable.nav
    capex, capex_facts = _open_capex(bundle, company.id, ctx)
    runway = ratios.runway_months(_value(cash), _value(burn))
    empty_on = ratios.cash_empty_on(cash.period_end if cash else None, runway)
    gap = ratios.funding_gap(capex, _value(cash))
    cap_diluted = quote.price * diluted.value if quote and diluted and diluted.value else None
    burdens = _burdens(bundle, ctx)
    derived = [
        _derived("net_cash", "Nettokasse", net, "USD", "Kasse − Finanzschulden", (cash, debt)),
        _derived(
            "runway_months", "Reichweite ab Bilanzstichtag", runway,
            "Monate", "Kasse / Mittelabfluss je Quartal × 3", (cash, burn),
        ),
        _cash_empty(empty_on, ctx.reference, (cash, burn)),
        _derived(
            "dilution_overhang", "Verwässerungsüberhang",
            ratios.dilution_overhang(_value(shares), _value(diluted)),
            "Anteil", "Aktien voll verwässert / ausstehende Aktien − 1", (shares, diluted),
        ),
        _derived(
            "market_cap", "Börsenwert", market_cap, "USD", "Kurs × ausstehende Aktien", (shares,)
        ),
        _derived(
            "market_cap_diluted", "Börsenwert voll verwässert", cap_diluted, "USD",
            "Kurs × Aktien voll verwässert", (diluted,),
        ),
        _derived(
            "enterprise_value", "Unternehmenswert (EV)",
            ratios.enterprise_value(market_cap, _value(cash), _value(debt)), "USD",
            "Börsenwert + Finanzschulden − Kasse", (shares, cash, debt),
        ),
        _derived(
            "open_capex", "Capex der Projekte (anteilig)", capex, "USD",
            "Σ Capex laut Studie × Eigentumsanteil, nur Objekte ohne Produktion", tuple(capex_facts),
        ),
        _derived(
            "funding_gap", "Finanzierungslücke", gap, "USD",
            "Capex der Projekte − Kasse (mindestens 0): muss über Aktien, Schulden oder Royalties beschafft werden",
            (cash, *capex_facts),
        ),
        _derived(
            "gap_to_market_cap", "Finanzierungslücke / Börsenwert", ratios.ratio(gap, market_cap),
            "×", "Finanzierungslücke / Börsenwert: Mass für die bevorstehende Verwässerung",
            (cash, shares, *capex_facts),
        ),
        _derived(
            "nav_sum", "Summe einfacher Asset-NAV (anteilig)", nav_sum, "USD",
            f"Σ Asset-NAV × Eigentumsanteil, aus {attributable.valued} von "
            f"{attributable.producing} produzierenden Objekten – ohne Steuern, Investitionen, Schulden",
            (),
        ),
        _derived(
            "p_nav", "Börsenwert / Asset-NAV", ratios.ratio(market_cap, nav_sum), "×",
            "Börsenwert / Summe einfacher Asset-NAV", (shares,),
        ),
    ]  # fmt: skip
    return {
        "id": company.id,
        "name": company.name,
        "country": company.country,
        "is_demo": company.is_demo,
        "symbol": company.stock.symbol if company.stock else None,
        "price": quote.price if quote else None,
        "metrics": [fact_payload(facts.get(k), k, ctx) for k in COMPANY_CARD],
        "derived": derived,
        "people": [
            {
                "id": p.id, "name": p.name, "role": p.role, "track_record": p.track_record,
                "since": p.since.isoformat() if p.since else None, "sourced": bool(p.quote),
                "is_demo": p.is_demo,
            }
            for p in people
        ],
        "financings": [
            {
                "id": f.id, "day": f.day.isoformat(), "kind": f.kind, "amount": f.amount,
                "price": f.price, "shares": f.shares, "note": f.note, "sourced": bool(f.quote),
            }
            for f in financings
        ],
        "burdens": burdens,
        "sensitivity": _sensitivity(bundle, company.id, ctx),
        "checklist": _checklist(facts, people, financings, cards, burdens),
        "assets": [
            {**c, "owner_share": owner_share(stakes_on(a, ctx.reference), company.id)}
            for a, c in zip(bundle.assets, cards, strict=True)
        ],
    }  # fmt: skip
