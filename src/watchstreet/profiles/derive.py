"""Pure derived-metric calculators (NAV, margins, ...). No I/O.

They take sourced datapoints plus market inputs and return metrics for the criteria engine,
a breakdown for display, and the list of inputs still missing. All maths lives here, so an
agent only ever supplies *inputs*, never results.
"""

from dataclasses import dataclass, field
from typing import Any

from watchstreet.constants import (
    DEFAULT_DISCOUNT_RATE,
    DEFAULT_OWNERSHIP,
    DEFAULT_REPORTING_CURRENCY,
    MAX_MINE_LIFE_YEARS,
    PERCENT,
)


@dataclass(frozen=True)
class Point:
    """Read-only view of a datapoint."""

    key: str
    subject: str = ""
    value: float | None = None
    text: str = ""


@dataclass(frozen=True)
class DeriveInput:
    metrics: dict[str, float]
    points: list[Point]
    price: float | None
    currency: str
    commodity_price: float | None = None


@dataclass
class DeriveOutput:
    metrics: dict[str, float] = field(default_factory=dict)
    breakdown: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)


def _global(points: list[Point], key: str) -> Point | None:
    return next((p for p in points if p.key == key and not p.subject), None)


def _global_value(points: list[Point], key: str) -> float | None:
    point = _global(points, key)
    return point.value if point else None


def annuity(cash_flow: float, rate: float, years: float) -> float:
    """Present value of a constant yearly cash flow."""
    if years <= 0:
        return 0.0
    if rate == 0:
        return cash_flow * years
    factor: float = 1 - (1 + rate) ** -years
    return cash_flow * factor / rate


def _fx_missing(inp: DeriveInput) -> tuple[float | None, str | None]:
    """Factor from reporting currency to the stock's currency, or a missing-input note."""
    reporting = _global(inp.points, "reporting_currency")
    reporting_ccy = (reporting.text if reporting else DEFAULT_REPORTING_CURRENCY).upper()
    if not inp.currency or reporting_ccy == inp.currency.upper():
        return 1.0, None
    rate = _global_value(inp.points, "fx_rate")
    if rate:
        return rate, None
    return None, f"Wechselkurs {reporting_ccy}→{inp.currency} (fx_rate)"


def _mine_rows(points: list[Point], commodity: float, rate: float) -> list[dict[str, Any]]:
    subjects = sorted({p.subject for p in points if p.subject})
    rows: list[dict[str, Any]] = []
    for name in subjects:
        vals = {p.key: p.value for p in points if p.subject == name}
        production, aisc, reserves = (
            vals.get(k) for k in ("mine_production", "mine_aisc", "mine_reserves")
        )
        if not production or aisc is None or not reserves:
            continue
        own = vals.get("mine_ownership") or DEFAULT_OWNERSHIP
        years = min(reserves / production, MAX_MINE_LIFE_YEARS)
        annual = production * (commodity - aisc) * own
        rows.append(
            {
                "mine": name,
                "production": production,
                "aisc": aisc,
                "margin_pct": (commodity - aisc) / commodity * PERCENT,
                "years": years,
                "ownership": own,
                "npv": annuity(annual, rate, years) if annual > 0 else 0.0,
            },
        )
    return rows


def _incomplete_mines(points: list[Point], complete: list[dict[str, Any]]) -> list[str]:
    done = {r["mine"] for r in complete}
    return [
        f"Mine '{p}': Produktion, AISC und Reserven nötig"
        for p in sorted({q.subject for q in points if q.subject} - done)
    ]


def derive_mining(inp: DeriveInput) -> DeriveOutput:
    """Net asset value (NPV of each mine's margin over its reserve life) and cost margins."""
    out = DeriveOutput()
    if inp.commodity_price is None:
        out.missing.append("Rohstoffpreis (commodity_price oder commodity_symbol)")
    if not any(p.subject for p in inp.points):
        out.missing.append("Mindestens eine Mine (Produktion, AISC, Reserven)")
    if inp.commodity_price is None:
        return out
    configured = _global_value(inp.points, "discount_rate")
    rate = DEFAULT_DISCOUNT_RATE if configured is None else configured
    rows = _mine_rows(inp.points, inp.commodity_price, rate)
    out.missing += _incomplete_mines(inp.points, rows)
    if not rows:
        return out
    weight = sum(r["production"] * r["ownership"] for r in rows)
    out.metrics["aisc_margin_pct"] = (
        sum(r["margin_pct"] * r["production"] * r["ownership"] for r in rows) / weight
    )
    out.metrics["reserve_life_years"] = sum(r["years"] * r["production"] for r in rows) / sum(
        r["production"] for r in rows
    )
    gross_nav = sum(r["npv"] for r in rows)
    net_debt = _global_value(inp.points, "net_debt")
    fx, fx_note = _fx_missing(inp)
    if fx_note:
        out.missing.append(fx_note)
    shares = _global_value(inp.points, "shares_outstanding")
    if shares is None and inp.metrics.get("market_cap") and inp.price:
        shares = inp.metrics["market_cap"] / inp.price
    if shares is None:
        out.missing.append("Anzahl Aktien (shares_outstanding)")
    out.breakdown = {
        "kind": "nav",
        "commodity_price": inp.commodity_price,
        "discount_rate": rate,
        "mines": rows,
        "gross_nav": gross_nav,
        "net_debt": net_debt,
    }
    if net_debt is not None and fx and shares and inp.price:
        nav_per_share = (gross_nav - net_debt) * fx / shares
        out.breakdown["nav_per_share"] = nav_per_share
        if nav_per_share > 0:
            out.metrics["p_nav"] = inp.price / nav_per_share
    return out


def derive_oil_gas(inp: DeriveInput) -> DeriveOutput:
    """Margin over the breakeven oil/gas price, reserve life and free-cash-flow yield."""
    out = DeriveOutput()
    breakeven = _global_value(inp.points, "breakeven_price")
    if inp.commodity_price is None:
        out.missing.append("Rohstoffpreis (commodity_price oder commodity_symbol)")
    if inp.commodity_price and breakeven is not None:
        out.metrics["commodity_margin_pct"] = (
            (inp.commodity_price - breakeven) / inp.commodity_price * PERCENT
        )
    reserves, production = (_global_value(inp.points, k) for k in ("reserves", "production"))
    if reserves and production:
        out.metrics["reserve_life_years"] = reserves / production
    fcf, cap = _global_value(inp.points, "free_cash_flow"), inp.metrics.get("market_cap")
    if fcf is not None and cap:
        out.metrics["fcf_yield"] = fcf / cap * PERCENT
    return out


def derive_tech(inp: DeriveInput) -> DeriveOutput:
    """Rule of 40: revenue growth plus profit margin, in percent."""
    out = DeriveOutput()
    growth, margin = inp.metrics.get("revenue_growth"), inp.metrics.get("profit_margin")
    if growth is not None and margin is not None:
        out.metrics["rule_of_40"] = (growth + margin) * PERCENT
    return out


def derive_reit(inp: DeriveInput) -> DeriveOutput:
    """Price/FFO and price/NAV from per-share datapoints."""
    out = DeriveOutput()
    for source, target in (("ffo_per_share", "p_ffo"), ("nav_per_share", "p_nav")):
        value = _global_value(inp.points, source)
        if value and inp.price:
            out.metrics[target] = inp.price / value
    return out
