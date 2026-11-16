"""Economics, time views and engine rules: pure functions, no database."""

from dataclasses import dataclass
from datetime import date

import pytest

from watchstreet.analysis.rules import (
    KnowledgeInputs,
    knowledge_status,
    peer_range,
    robust_outliers,
    value_score,
)
from watchstreet.domain import KnowledgeStatus, View
from watchstreet.economics.mine import ByProduct, Interval, MineInputs, annuity, evaluate
from watchstreet.metrics import EXTRACT_PATTERNS, card_metrics, parse_number
from watchstreet.temporal.views import latest_per_metric


def test_point_economics():
    inputs = MineInputs(cost=Interval.point(2.0), production=Interval.point(100.0), reserves=1000.0)
    result = evaluate(inputs, 4.0, discount_rate=0.0)
    assert result.margin == Interval.point(2.0) and result.margin_pct.mid == 0.5
    assert result.cash_flow.mid == 200.0 and result.leverage == 2.0
    assert result.mine_life == 10.0 and result.nav.mid == 2000.0


@pytest.mark.parametrize("price", [1.0, 2.5, 4.0, 9.0])
def test_margin_is_monotonic_in_price_and_interval_contains_point(price):
    band = MineInputs(cost=Interval(1.8, 2.4), production=Interval.point(10.0))
    point = MineInputs(cost=Interval.point(2.0), production=Interval.point(10.0))
    low, high = evaluate(band, price), evaluate(band, price + 1)
    assert high.margin.low > low.margin.low and high.cash_flow.high > low.cash_flow.high
    exact = evaluate(point, price)
    assert low.margin.low <= exact.margin.mid <= low.margin.high
    assert not low.margin.is_point


def test_missing_inputs_yield_none_never_a_guess():
    assert evaluate(MineInputs(), 100.0).margin is None
    only_cost = evaluate(MineInputs(cost=Interval.point(5.0)), 10.0)
    assert only_cost.margin.mid == 5.0 and only_cost.cash_flow is None and only_cost.nav is None
    assert evaluate(MineInputs(cost=Interval.point(5.0)), 0.0).margin is None
    assert evaluate(MineInputs(cost=Interval.point(12.0)), 10.0).leverage is None
    assert annuity(100.0, 0.08, 0.0) == 0.0 and round(annuity(100.0, 0.1, 2.0), 2) == 173.55


def test_by_product_credit_is_repriced():
    inputs = MineInputs(
        cost=Interval.point(2.0),
        production=Interval.point(100.0),
        by_products=(ByProduct(volume=10.0, reference_price=50.0, price=30.0),),
    )
    result = evaluate(inputs, 5.0)
    assert result.by_product_adjusted and result.cost == Interval.point(4.0)


@dataclass
class F:
    id: int
    metric_key: str
    period_end: date | None
    published_at: date | None
    superseded_by: int | None = None


def test_as_known_never_shows_later_publications():
    old = F(1, "aisc", date(2024, 12, 31), date(2025, 2, 20))
    new = F(2, "aisc", date(2025, 12, 31), date(2026, 2, 20))
    undated = F(3, "reserves", date(2020, 12, 31), None)
    facts = [old, new, undated]
    assert latest_per_metric(facts, None, View.AS_KNOWN)["aisc"] is new
    then = latest_per_metric(facts, date(2025, 12, 31), View.AS_KNOWN)
    assert then["aisc"] is old and "reserves" not in then  # no date, no 'known then'
    hindsight = latest_per_metric(facts, date(2025, 12, 31), View.HINDSIGHT)
    assert hindsight["aisc"] is new and hindsight["reserves"] is undated
    assert latest_per_metric(facts, date(2020, 1, 1), View.AS_KNOWN) == {}
    replaced = F(4, "aisc", date(2025, 12, 31), date(2026, 2, 20), superseded_by=2)
    assert latest_per_metric([replaced], None, View.AS_KNOWN) == {}


def test_rules():
    assert robust_outliers({1: 2.05, 2: 1.85, 3: 2.6, 4: 4.4}) == [4]
    assert robust_outliers({1: 1.0, 2: 9.0}) == [] and robust_outliers({1: 1, 2: 1, 3: 1}) == []
    assert peer_range([1.0, 2.0]) is None and peer_range([1.0, 2.0, 3.0, 4.0, 5.0]) == (2.0, 4.0)
    assert (
        value_score(dict.fromkeys(("insight", "relevance", "novelty", "data", "investment"), 1))
        == 1
    )
    assert value_score({"insight": 5.0}) == 0.3
    states = [
        knowledge_status(KnowledgeInputs(*flags))
        for flags in (
            (False, False, False, False),
            (True, False, False, False),
            (True, True, False, False),
            (True, True, False, True),
            (True, True, True, True),
        )
    ]
    assert states == [
        KnowledgeStatus.UNEXAMINED,
        KnowledgeStatus.KNOWN,
        KnowledgeStatus.DEEP,
        KnowledgeStatus.STALE,
        KnowledgeStatus.NEW,
    ]


def test_metric_catalog_and_extraction():
    assert "aisc" in card_metrics("production") and "study_stage" in card_metrics("exploration")
    assert parse_number("1,234.5") == 1234.5
    match = EXTRACT_PATTERNS["aisc"].search("AISC averaged US$1,180.00 per oz in 2025.")
    assert parse_number(match.group("value")) == 1180.0


def test_losing_mine_has_no_negative_nav_and_company_ratios():
    from watchstreet.economics import company

    inputs = MineInputs(cost=Interval.point(5.0), production=Interval.point(10.0), reserves=100.0)
    result = evaluate(inputs, 4.0)
    assert result.cash_flow.mid == -10.0 and result.nav.mid == 0.0
    assert company.enterprise_value(100.0, 30.0, 10.0) == 80.0
    assert company.enterprise_value(None, 30.0, 10.0) is None
    assert company.funding_gap(50.0, 20.0) == 30.0 and company.funding_gap(10.0, 20.0) == 0.0
    assert company.funding_gap(None, 20.0) is None


def test_macro_rules_never_fill_gaps():
    from datetime import date as d

    from watchstreet.analysis import macro

    wed, fri = d(2026, 11, 4), d(2026, 11, 6)
    sheet, account = [(wed, 6800.0)], [(wed, 900.0)]
    repo = [(wed, 300.0), (fri, 999.0)]
    assert macro.net_liquidity(sheet, account, repo) == [(wed, 5600.0)]  # Friday changes nothing
    assert macro.combine([(wed, 10.0), (fri, 12.0)], [(fri, 4.0)], "ratio") == [(fri, 3.0)]
    cpi = [(d(2025, 10, 1), 100.0), (d(2026, 10, 1), 103.0)]
    assert macro.year_over_year(cpi) == [(d(2026, 10, 1), 3.0000000000000027)]
    prices = [(d(2025, 10, 6), 50.0), (d(2025, 10, 20), 150.0), (d(2026, 11, 3), 500.0)]
    real, base = macro.deflate(prices, cpi)
    assert base == d(2026, 10, 1) and real == [(d(2025, 10, 1), 103.0)]  # November: no CPI yet
    parts = macro.decompose([(wed, 100.0), (fri, 121.0)], [(wed, 2000.0), (fri, 2200.0)], wed, fri)
    assert round(parts["total_pct"], 6) == 21 and round(parts["denominator_pct"], 6) == 10
    assert round(parts["in_denominator_pct"], 6) == 10
    assert macro.decompose([(wed, 1.0)], [], wed, fri) is None


def test_lever_chain_adds_up_exactly_and_refuses_stale_inputs():
    import math
    from datetime import date as d
    from datetime import timedelta

    from watchstreet.analysis import macro

    days = [d(2026, 1, 5) + timedelta(weeks=i) for i in range(4)]
    series = {
        "asset": list(zip(days, [10.0, 11.0, 9.0, 13.0], strict=True)),  # in Canadian dollars
        "fx": list(zip(days, [1.30, 1.32, 1.35, 1.40], strict=True)),  # CAD per USD
        "gold": list(zip(days, [2000.0, 2100.0, 1900.0, 2200.0], strict=True)),
        "commodity": [(days[0], 4.0), (days[1] - timedelta(days=5), 4.2), (days[3], 4.4)],
    }
    links = [
        ("currency", ("fx",), ()),
        ("gold", ("gold",), ()),
        ("commodity in gold", ("commodity",), ("gold",)),
        ("company in commodity", ("asset",), ("fx", "commodity")),
    ]
    path = macro.chain_path(series, links, days, 10)
    assert [day for day, _ in path] == [days[0], days[1], days[3]]  # week 3: copper too old
    for day, parts in path:
        price = dict(series["asset"])[day]
        assert sum(parts) == pytest.approx(math.log(price / 10.0), abs=1e-12)
    assert path[-1][1][0] == pytest.approx(math.log(1.40 / 1.30))
    assert macro.chain_levels({"asset": []}, [("x", ("asset",), ())], days[0], 10) is None
    assert macro.level_on(series["gold"], days[0] - timedelta(days=1), 10) is None
    monthly = macro.monthly_ratio(
        [(d(2026, 1, 5), 10.0), (d(2026, 1, 19), 30.0)], [(d(2026, 1, 1), 4.0)]
    )
    assert monthly == [(d(2026, 1, 1), 5.0)]
    assert macro.range_position([(days[0], 1.0), (days[1], 5.0), (days[2], 2.0)]) == 0.25
    assert macro.range_position([]) is None and macro.range_position([(days[0], 1.0)]) is None


def test_expressions_check_units_and_never_fill_gaps():
    from datetime import date as d
    from datetime import timedelta

    from watchstreet.analysis.expression import ExpressionError, Operand, evaluate

    days = [d(2025, 1, 6) + timedelta(weeks=i) for i in range(60)]
    data = {
        "share": Operand([(day, 10.0 + i) for i, day in enumerate(days)], "USD"),
        "gold": Operand([(day, 2000.0) for day in days[::2]], "USD/oz"),
        "copper": Operand([(day, 4.0) for day in days], "USD/lb"),
        "rate": Operand([(day, 2.0) for day in days], "%"),
        "long": Operand([(day, 4.5) for day in days], "%"),
    }

    def resolve(name):
        if name not in data:
            raise ExpressionError(f"unbekannt: {name}")
        return data[name]

    in_gold = evaluate("share / gold", resolve)
    assert in_gold.unit == "oz" and len(in_gold.points) == 30 and in_gold.dropped == 30
    assert in_gold.points[1] == (days[2], 12.0 / 2000.0) and in_gold.terms == ["share", "gold"]
    assert evaluate("copper / gold", resolve).unit == "oz je lb"
    assert evaluate("gold / gold", resolve).unit.startswith("Verhältnis")
    assert evaluate("long - rate", resolve).points[0][1] == 2.5
    assert evaluate("(long - rate) * 2 + 1", resolve).points[0][1] == 6.0
    assert evaluate("-rate", resolve).points[0][1] == -2.0
    assert evaluate("100 / copper", resolve).unit == "1 je USD/lb"
    smooth = evaluate("ma(share, 4)", resolve)
    assert smooth.points[0] == (days[3], 11.5) and smooth.unit == "USD"
    assert evaluate("lag(share, 2)", resolve).points[0] == (days[2], 10.0)
    assert evaluate("chg(share, 1)", resolve).points[0] == (days[1], pytest.approx(10.0))
    yearly = evaluate("yoy(share)", resolve)
    assert yearly.unit == "%" and yearly.points[0][0] == days[53]
    assert yearly.points[0][1] == pytest.approx((63.0 / 10.0 - 1) * 100)
    assert evaluate("log(share)", resolve).unit == "ln(USD)"
    for bad, message in (
        ("share + rate", "Einheiten"),
        ("share + 1", "ohne Einheit"),
        ("share /", "unvollständig"),
        ("share ) 2", "Unerwartetes"),
        ("nope / gold", "unbekannt"),
        ("sqrt(share)", "Unbekannte Funktion"),
        ("ma(share)", "braucht 2"),
        ("ma(share, 1.5)", "ganze Zahl"),
        ("ma(3, 2)", "braucht eine Reihe"),
        ("1 + 2", "keine Reihe"),
        ("1 / 0", "Division"),
        ("", "Leere"),
        ("share" + " + share" * 200, "zu lang"),
        ("(" * 90 + "share", "verschachtelt"),
        ("ma(share, 2", "erwartet"),
    ):
        with pytest.raises(ExpressionError, match=message):
            evaluate(bad, resolve)
