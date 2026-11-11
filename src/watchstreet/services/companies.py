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

from watchstreet.constants import DEFAULT_DISCOUNT_RATE, PERCENT, SENSITIVITY_FACTORS
from watchstreet.domain import DataOrigin, Provenance, StakeRole, SubjectType
from watchstreet.economics import company as ratios
from watchstreet.economics.mine import MineInputs, annuity, mine_life
from watchstreet.market.service import MarketService
from watchstreet.metrics import COMPANY_CARD, PRODUCING_STATUSES
from watchstreet.models import Asset, Company, Fact, Financing, Person, Stake
from watchstreet.services.world import (
    COST_METRICS,
    Bundle,
    ViewContext,
    asset_economics,
    card,
    fact_interval,
    fact_payload,
    load_bundle,
    primary_commodity,
    stakes_on,
    status_on,
)
from watchstreet.temporal.views import latest_per_metric

PRO_FORMA = ("cash_pro_forma", "shares_pro_forma")  # shown only once a later raise exists
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
    formula = "Bilanzstichtag + (Kasse + seither erfasste Finanzierungen) / Mittelabfluss"
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


def _reserves(facts: Mapping[str, Fact]) -> float | None:
    fact = facts.get("reserves")
    return fact.value if fact else None


def _royalty_income(
    asset: Asset, facts: Mapping[str, Fact], company_id: int, ctx: ViewContext
) -> float | None:
    """Yearly revenue share of a royalty or stream the company holds on this asset."""
    pct = sum(
        s.share_pct or 0.0
        for s in stakes_on(asset, ctx.reference)
        if s.company_id == company_id and s.role in BURDEN_ROLES
    )
    production, price = facts.get("production"), ctx.prices.get(primary_commodity(asset))
    if pct <= 0 or production is None or production.value is None or price is None:
        return None
    return production.value * price * pct / PERCENT


def _costs_known(bundle: Bundle, ctx: ViewContext) -> bool:
    """True only if every producing asset has a unit cost on file."""
    producing = [
        a
        for a in bundle.assets
        if (p := status_on(a, ctx.reference)) is not None and p.status in PRODUCING_STATUSES
    ]
    return bool(producing) and all(
        any(
            k in latest_per_metric(bundle.facts.get(a.id, []), ctx.as_of, ctx.view)
            for k in COST_METRICS
        )
        for a in producing
    )


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
        income = _royalty_income(asset, facts, company_id, ctx)
        if income is not None:
            cash_flow += income
            life = mine_life(
                MineInputs(
                    production=fact_interval(facts.get("production")), reserves=_reserves(facts)
                )
            )
            if life is not None:
                nav_total += annuity(income, DEFAULT_DISCOUNT_RATE, life)
                valued += 1
        if econ is None or share <= 0:
            continue
        if econ.result.nav is not None:
            nav_total += econ.result.nav.mid * share
            valued += 1
        if econ.result.cash_flow is not None:
            cash_flow += max(econ.result.cash_flow.mid, 0.0) * share  # a losing mine is closed
    return Attributable(nav_total if valued else None, cash_flow, valued, producing)


def _project_sum(
    bundle: Bundle, company_id: int, ctx: ViewContext, metric: str
) -> tuple[float | None, list[Fact]]:
    """A study figure of the projects not yet producing, by ownership; ``None`` if none is known."""
    used: list[Fact] = []
    total = 0.0
    for asset in bundle.assets:
        period = status_on(asset, ctx.reference)
        if period is not None and period.status in PRODUCING_STATUSES:
            continue
        fact = latest_per_metric(bundle.facts.get(asset.id, []), ctx.as_of, ctx.view).get(metric)
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
    costs_known: bool,  # noqa: FBT001
    burdens: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Answered means evidence is on file; it does not mean the answer is good."""
    evidence = {
        "people": any(p.track_record.strip() for p in people),
        "financings": bool(financings),
        "costs": costs_known,
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
    capex, capex_facts = _project_sum(bundle, company.id, ctx, "capex")
    study_npv, npv_facts = _project_sum(bundle, company.id, ctx, "study_npv")
    balance_day = cash.period_end if cash else None
    later = [f for f in financings if balance_day and f.day > balance_day and f.amount]
    raises = [
        ratios.Raise(f.amount or 0.0, f.kind == "equity", f.price, f.shares, f.warrants)
        for f in later
    ]
    cash_pf = ratios.pro_forma_cash(_value(cash), raises)
    issued = ratios.new_shares(raises)
    shares_pf = shares.value + issued if shares and shares.value and raises else None
    runway = ratios.runway_months(_value(cash), _value(burn))
    empty_on = ratios.cash_empty_on(balance_day, ratios.runway_months(cash_pf, _value(burn)))
    gap = ratios.funding_gap(capex, _value(cash))
    cap_diluted = quote.price * diluted.value if quote and diluted and diluted.value else None
    burdens = _burdens(bundle, ctx)
    derived = [
        _derived("net_cash", "Nettokasse", net, "USD", "Kasse − Finanzschulden", (cash, debt)),
        _derived(
            "runway_months", "Reichweite ab Bilanzstichtag", runway,
            "Monate", "Kasse / Mittelabfluss je Quartal × 3", (cash, burn),
        ),
        _derived(
            "cash_pro_forma", f"Kasse pro forma ({len(later)} spätere Finanzierung(en))",
            cash_pf if later else None, "USD",
            "Kasse am Bilanzstichtag + seither erfasste Finanzierungen; Ausgaben seither fehlen",
            (cash,),
        ),
        _derived(
            "shares_pro_forma", "Aktien pro forma", shares_pf, "Aktien",
            "Ausstehende Aktien + seither ausgegebene (angegeben oder Betrag / Preis)", (shares,),
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
            "study_npv_sum", "NPV der Projekte laut Studien (anteilig)", study_npv, "USD",
            "Σ NPV laut Studie × Eigentumsanteil – zu den Preisannahmen der Studien, vor Finanzierung",
            tuple(npv_facts),
        ),
        _derived(
            "p_study_npv", "Börsenwert / Studien-NPV", ratios.ratio(market_cap, study_npv), "×",
            "Börsenwert / NPV der Projekte laut Studien", (shares, *npv_facts),
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
    derived = [m for m in derived if "value" in m or m["metric"] not in PRO_FORMA]
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
                "prior_companies": p.prior_companies, "shares_held": p.shares_held,
                "ownership": ratios.ratio(p.shares_held, _value(shares)),
                "own_entry": p.origin == DataOrigin.USER and not p.is_demo,
            }
            for p in people
        ],
        "financings": [
            {
                "id": f.id, "day": f.day.isoformat(), "kind": f.kind, "amount": f.amount,
                "price": f.price, "shares": f.shares, "note": f.note, "sourced": bool(f.quote),
                "warrants": f.warrants, "warrant_price": f.warrant_price,
                "warrant_expiry": f.warrant_expiry.isoformat() if f.warrant_expiry else None,
                "investors": f.investors, "after_balance": f in later,
                "own_entry": f.origin == DataOrigin.USER and not f.is_demo,
            }
            for f in financings
        ],
        "burdens": burdens,
        "sensitivity": _sensitivity(bundle, company.id, ctx),
        "checklist": _checklist(facts, people, financings, _costs_known(bundle, ctx), burdens),
        "assets": [
            {**c, "owner_share": owner_share(stakes_on(a, ctx.reference), company.id)}
            for a, c in zip(bundle.assets, cards, strict=True)
        ],
    }  # fmt: skip
