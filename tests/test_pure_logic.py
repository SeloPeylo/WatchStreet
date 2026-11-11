"""Economics, time views and engine rules: pure functions, no database."""

from dataclasses import dataclass
from datetime import date

import pytest

from watchstreet.analysis.rules import (
    KnowledgeInputs,
    knowledge_status,
    missing_metrics,
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
    assert missing_metrics(("a", "b"), ("a",)) == ["b"]
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
