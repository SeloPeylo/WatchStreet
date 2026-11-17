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


def test_cash_outlook_has_one_basis_and_says_when_the_cash_is_used_up():
    from watchstreet.economics.company import MONTHS_PER_QUARTER, Raise, cash_outlook

    balance, burn = date(2025, 6, 30), 3.0e6  # per quarter, i.e. 1 million a month
    # nine million last for nine months: on the balance date plus nine months it is gone
    early = cash_outlook(9e6, [], burn, balance, date(2025, 9, 30))
    assert early.cash_now == pytest.approx(9e6 - 3e6 * 92 / (30.44 * MONTHS_PER_QUARTER))
    assert not early.exhausted and early.empty_on is not None and early.empty_on > date(2025, 9, 30)
    assert early.runway_months == pytest.approx(early.cash_now / burn * MONTHS_PER_QUARTER)
    assert early.balance_day == balance
    late = cash_outlook(9e6, [], burn, balance, date(2026, 11, 16))
    assert late.exhausted and late.cash_now == 0.0 and late.runway_months == 0.0
    assert late.empty_on is not None and balance < late.empty_on <= date(2026, 11, 16)
    # a later financing is part of the same estimate, so the cash is no longer used up
    raised = cash_outlook(9e6, [Raise(30e6)], burn, balance, date(2026, 11, 16))
    assert not raised.exhausted and raised.cash_now is not None and raised.cash_now > 0
    assert raised.empty_on is not None and raised.empty_on > date(2026, 11, 16)
    assert raised.runway_months == pytest.approx(raised.cash_now / burn * MONTHS_PER_QUARTER)
    # no burn or no balance sheet: nothing is claimed
    quiet = cash_outlook(9e6, [], None, balance, date(2026, 11, 16))
    assert not quiet.exhausted and quiet.runway_months is None and quiet.empty_on is None
    assert quiet.cash_now == 9e6
    assert cash_outlook(None, [], burn, None, date(2026, 11, 16)).cash_now is None


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


def test_resampling_to_the_coarsest_grid():
    from datetime import date as d
    from datetime import timedelta

    from watchstreet.analysis import macro
    from watchstreet.analysis.expression import Operand, evaluate

    days = [d(2026, 1, 1) + timedelta(days=i) for i in range(90)]
    daily = [(day, 100.0 + i) for i, day in enumerate(days)]
    # weeks are keyed on their Monday, months on their first day
    weekly = macro.weekly_mean([(d(2026, 1, 7), 1.0), (d(2026, 1, 9), 3.0), (d(2026, 1, 12), 5.0)])
    assert weekly == [(d(2026, 1, 5), 2.0), (d(2026, 1, 12), 5.0)]
    assert macro.resample(daily, "daily") is daily
    assert macro.resample(daily, "monthly") == macro.monthly_mean(daily)
    assert macro.resample(daily, "weekly") == macro.weekly_mean(daily)
    assert macro.coarsest_grid(["daily", "weekly"]) == "weekly"
    assert macro.coarsest_grid(["weekly", "monthly", "daily"]) == "monthly"
    assert macro.coarsest_grid(["daily", "daily"]) == "daily"
    assert (
        macro.coarsest_grid(["wie die gröbere Reihe"]) == "daily"
        and macro.coarsest_grid([]) == "daily"
    )
    assert macro.infer_frequency(daily) == "daily"
    assert macro.infer_frequency(daily[::7]) == "weekly"
    assert macro.infer_frequency(macro.monthly_mean(daily)) == "monthly"
    assert macro.infer_frequency(daily[:1]) == "daily"

    # a daily series divided by a monthly one: unaligned it has almost no common days
    monthly = [(d(2026, m, 1), 10.0 * m) for m in (1, 2, 3)]
    raw = evaluate("price / index", lambda n: Operand(daily if n == "price" else monthly, "USD"))
    assert len(raw.points) == 3  # only the first of each month survives
    grid = macro.coarsest_grid(["daily", "monthly"])
    fixed = evaluate(
        "price / index",
        lambda n: Operand(macro.resample(daily if n == "price" else monthly, grid), "USD"),
    )
    assert [day for day, _ in fixed.points] == [day for day, _ in monthly]
    january = sum(100.0 + i for i in range(31)) / 31
    assert fixed.points[0][1] == pytest.approx(january / 10.0)
    from watchstreet.analysis.expression import series_names

    assert series_names("ma($objekt / gold, 4) + gold - 2") == ["$objekt", "gold"]


def _joint_series(count: int = 80, *, relative: bool, noise: float = 0.0):
    """Target steps are 2 x1 - 1 x2 + 0.5 x3 + a small drift; the drivers move independently."""
    import math
    from datetime import date as d
    from datetime import timedelta

    days = [d(2024, 1, 1) + timedelta(weeks=i) for i in range(count)]
    levels = [[100.0, 50.0, 20.0]]
    target = [80.0]
    for i in range(1, count):
        a, b, c = math.sin(i * 0.7) * 0.01, math.cos(i * 1.3) * 0.02, math.sin(i * 2.1 + 1) * 0.015
        own = 2 * a - b + 0.5 * c + 0.001 + noise * math.sin(i * 5.3)
        levels.append(
            [
                v * math.exp(s) if relative else v + s
                for v, s in zip(levels[-1], (a, b, c), strict=True)
            ]
        )
        target.append(target[-1] * math.exp(own) if relative else target[-1] + own)
    drivers = [list(zip(days, [row[j] for row in levels], strict=True)) for j in range(3)]
    return list(zip(days, target, strict=True)), drivers


def test_joint_sensitivity_recovers_betas_and_adds_up():
    import math

    from watchstreet.analysis import macro

    for relative in (False, True):
        target, drivers = _joint_series(relative=relative)
        fit = macro.joint_sensitivity(
            target, drivers, relative_target=relative, relative_drivers=[relative] * 3
        )
        assert fit is not None and fit.observations == 79
        assert fit.betas == pytest.approx((2.0, -1.0, 0.5), abs=1e-6)
        assert fit.r_squared == pytest.approx(1.0, abs=1e-9)
        assert sum(fit.contributions) + fit.own == pytest.approx(fit.total, abs=1e-9)
        assert fit.own == pytest.approx(0.001 * 79, rel=1e-6)  # only the steady drift is left
        # contribution = beta x the driver's total step
        first = drivers[0]
        total_step = (
            math.log(first[-1][1] / first[0][1]) if relative else first[-1][1] - first[0][1]
        )
        assert fit.contributions[0] == pytest.approx(2.0 * total_step, abs=1e-9)
        # one driver alone is the ordinary regression; fewer drivers explain less
        single = macro.joint_sensitivity(
            target, drivers[:1], relative_target=relative, relative_drivers=[relative]
        )
        assert single is not None and single.r_squared < fit.r_squared

    noisy, drivers = _joint_series(relative=False, noise=0.002)
    fit = macro.joint_sensitivity(
        noisy, drivers, relative_target=False, relative_drivers=[False] * 3
    )
    assert fit is not None and 0.5 < fit.r_squared < 1.0
    assert sum(fit.contributions) + fit.own == pytest.approx(fit.total, abs=1e-9)


def test_joint_sensitivity_refuses_collinear_thin_and_flat_input():
    from watchstreet.analysis import macro

    target, drivers = _joint_series(relative=False)
    twin = [(day, 2.0 * value + 7.0) for day, value in drivers[0]]  # same moves, other scale
    assert (
        macro.joint_sensitivity(
            target, [drivers[0], twin], relative_target=False, relative_drivers=[False, False]
        )
        is None
    )
    assert (
        macro.joint_sensitivity(
            target[:20], drivers, relative_target=False, relative_drivers=[False] * 3
        )
        is None
    )
    flat = [(day, 1.0) for day, _ in drivers[0]]
    assert (
        macro.joint_sensitivity(
            target, [drivers[0], flat], relative_target=False, relative_drivers=[False, False]
        )
        is None
    )
    assert (
        macro.joint_sensitivity(flat, drivers, relative_target=False, relative_drivers=[False] * 3)
        is None
    )
    with pytest.raises(ValueError, match="drivers"):
        macro.joint_sensitivity(
            target, [*drivers, drivers[0]], relative_target=False, relative_drivers=[False] * 4
        )
    # only the days all series share count
    sparse = drivers[1][::2]
    shared = macro.joint_sensitivity(
        target, [drivers[0], sparse], relative_target=False, relative_drivers=[False, False]
    )
    assert shared is not None and shared.observations == 39


def test_plain_sentences_state_only_what_the_numbers_support():
    from datetime import date as d

    from watchstreet.analysis import plain

    assert plain.amount(42.4) == "42" and plain.amount(6.04) == "6" and plain.amount(6.5) == "6,5"
    assert plain.amount(-0.0123) == "−0,012" and plain.amount(0) == "0"
    assert plain.span_text(3 * 365.25) == "3 Jahren" and plain.span_text(365) == "einem Jahr"
    assert plain.span_text(200) == "7 Monaten" and plain.span_text(31) == "einem Monat"
    chain = plain.chain_sentence(
        "Demo Aktie",
        "USD",
        3 * 365.25,
        42.0,
        [("Goldpreis in US-Dollar", 18.0), ("Unternehmen, gemessen in Gold", 24.0)],
    )
    assert chain.startswith("Demo Aktie stieg in 3 Jahren um 42 % in US-Dollar.")
    assert (
        "+18 Punkte aus „Goldpreis in US-Dollar“" in chain and "und +24 aus „Unternehmen" in chain
    )
    assert "fiel" in plain.chain_sentence(
        "X", "CAD", 30, -12.0, []
    ) and "in CAD" in plain.chain_sentence("X", "CAD", 30, -12.0, [])
    assert "unverändert" in plain.chain_sentence("X", "USD", 400, 0.01, [])

    strong = plain.ladder_sentence(
        "Gold",
        "Realzins",
        beta=-6.0,
        r2=0.31,
        weak=False,
        relative_target=True,
        relative_driver=False,
    )
    assert strong == (
        "Stieg Realzins um 1 Prozentpunkt, dann fiel Gold in diesem Zeitraum im Schnitt um 6 %. "
        "Das erklärt 31 % der Bewegung."
    )
    rate = plain.ladder_sentence(
        "Rendite", "Öl", beta=0.2, r2=0.5, weak=False, relative_target=False, relative_driver=True
    )
    assert "um 1 %" in rate and "stieg Rendite" in rate and "Prozentpunkte" in rate
    for weak, r2 in ((True, 0.6), (False, 0.03)):
        text = plain.ladder_sentence(
            "Gold",
            "Realzins",
            beta=-6.0,
            r2=r2,
            weak=weak,
            relative_target=True,
            relative_driver=False,
        )
        assert "Der Zusammenhang ist schwach – nicht als Regel verwenden." in text
        assert "fiel" not in text  # no slope is quoted for a fit that cannot be told from noise
    assert "zu wenige gemeinsame Werte" in plain.missing_sentence("Gold", "Realzins")
    assert "kein Treiber hinterlegt" in plain.missing_sentence("Gold", None)

    joint = plain.joint_sentence("Kupfer", ["Dollar", "Realzins"], [-4.0, 1.0], 6.0, 0.4, "Punkte")
    assert "Dollar und Realzins" in joint and "40 %" in joint and "(−4 Punkte)" in joint
    assert "Der Zusammenhang ist schwach" in plain.joint_sentence(
        "Kupfer", ["a", "b"], [1.0, 1.0], 1.0, 0.02, "Punkte"
    )

    lens = plain.lens_sentence("Aktie / Gold", "oz", (d(2024, 1, 1), 0.5), (d(2026, 1, 1), 0.6))
    assert "0,6 oz (01.01.2026)" in lens and "+20 %" in lens
    assert "zu wenige gemeinsame Werte" in plain.lens_sentence("x", "", None, None)
    assert plain.grid_sentence("monthly", ["Geldmenge M2"]) == (
        "Gerechnet auf Monatsmitteln, weil „Geldmenge M2“ nur monatlich erscheint."
    )
    assert (
        "erscheinen" in plain.grid_sentence("weekly", ["A", "B"])
        and plain.grid_sentence("daily", ["A"]) == ""
    )
    assert "kein Eintrag" in plain.regime_sentence(
        ("A", "%", 1.0, 2.0), ("B", "Pkt", 5.0, 3.0), d(2024, 1, 1), 0
    )
    assert "nicht genug" in plain.matrix_sentence(
        [("A", None, 3.0)]
    ) or "fehlen" in plain.matrix_sentence([("A", None, 3.0)])
    assert "fiel um 5 % gemessen in Gold" in plain.matrix_sentence([("Gold-Aktie", 10.0, -5.0)])
    assert "zu wenige Werte" in plain.sheet_sentence(3, [], measured=0)
    assert "Keine der 3 Stufen" in plain.sheet_sentence(3, [], measured=3)
    assert "Dollar (+3 %)" in plain.sheet_sentence(3, [("Dollar", 3.0, "%")], measured=3)
    assert "zu wenige Zeiträume" in plain.cycle_sentence("Gold", "Realzins", "tief", [5.0, -1.0])
    assert "Rückschau" in plain.cycle_sentence("Gold", "Realzins", "tief", [5.0, -1.0, 2.0, 4.0])
    assert "keinen früheren" in plain.cycle_sentence("Gold", "Realzins", "tief", [])
