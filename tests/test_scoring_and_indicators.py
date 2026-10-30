import pytest

from watchstreet.market.demo import DemoProvider
from watchstreet.market.indicators import pct_change, rsi, sma
from watchstreet.profiles.registry import get_profile
from watchstreet.profiles.scoring import interpolate, score_metrics, technical_score


def test_sma_and_pct_change():
    assert sma([1, 2, 3, 4], 2) == 3.5
    assert sma([1], 2) is None
    assert pct_change([100, 110], 1) == pytest.approx(10.0)
    assert pct_change([100], 1) is None


def test_rsi_extremes():
    assert rsi(list(map(float, range(1, 40)))) == 100.0
    falling = rsi(list(map(float, range(40, 1, -1))))
    assert falling is not None and falling < 5
    assert rsi([1.0, 2.0]) is None


@pytest.mark.parametrize(("value", "expected"), [(10, 100), (40, 0), (25, 50), (0, 100), (99, 0)])
def test_interpolate_clamps(value, expected):
    assert interpolate(value, good=10, bad=40) == pytest.approx(expected)


def generic(metrics):
    profile = get_profile("generic")
    return score_metrics(profile.scheme, profile.criteria, metrics)


def test_valuation_score_good_vs_bad():
    good = generic(
        {"trailing_pe": 10, "price_to_book": 1.2, "profit_margin": 0.25, "return_on_equity": 0.3}
    )
    bad = generic(
        {"trailing_pe": 60, "price_to_book": 12, "profit_margin": 0.0, "return_on_equity": 0.0}
    )
    assert good and bad
    assert good.value > 90 > 10 > bad.value
    assert good.label == "attraktiv" and bad.label == "schwach"


def test_valuation_needs_minimum_criteria_and_handles_losses():
    assert generic({"trailing_pe": 10}) is None
    result = generic({"trailing_pe": -5, "price_to_book": 1.0, "profit_margin": 0.2})
    assert result is not None
    pe_row = next(r for r in result.details["criteria"] if r["key"] == "trailing_pe")
    assert pe_row["score"] == 0


def test_provisional_until_core_metrics_exist():
    mining = get_profile("mining")
    partial = score_metrics(
        mining.scheme,
        mining.criteria,
        {"price_to_book": 1.0, "debt_to_equity": 30, "revenue_growth": 0.1},
        core_metrics=mining.core_metrics,
    )
    assert partial.details["provisional"] is True
    full = score_metrics(
        mining.scheme,
        mining.criteria,
        {"p_nav": 0.8, "aisc_margin_pct": 30, "reserve_life_years": 10},
        core_metrics=mining.core_metrics,
    )
    assert full.details["provisional"] is False


def test_technical_score_on_demo_candles_and_short_history():
    candles = DemoProvider().candles("AAPL", "1h")
    result = technical_score(candles)
    assert result is not None and 0 <= result.value <= 100
    assert technical_score(candles[:10]) is None


def test_demo_provider_is_deterministic():
    demo = DemoProvider()
    assert demo.candles("X", "1d")[-1].close == demo.candles("X", "1d")[-1].close
    assert demo.candles("X", "1d")[-1].close != demo.candles("Y", "1d")[-1].close
