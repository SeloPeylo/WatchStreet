import pytest

from watchstreet.market.base import Fundamentals
from watchstreet.market.demo import DemoProvider
from watchstreet.market.indicators import pct_change, rsi, sma
from watchstreet.workflows.scoring import interpolate, technical_score, valuation_score


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


def test_valuation_score_good_vs_bad():
    cheap = Fundamentals(
        {"trailing_pe": 10, "price_to_book": 1.2, "profit_margin": 0.25, "return_on_equity": 0.3},
    )
    pricey = Fundamentals(
        {"trailing_pe": 60, "price_to_book": 12, "profit_margin": 0.0, "return_on_equity": 0.0},
    )
    good, bad = valuation_score(cheap, 100), valuation_score(pricey, 100)
    assert good and bad
    assert good.value > 90 > 10 > bad.value
    assert good.label == "attraktiv" and bad.label == "schwach"


def test_valuation_needs_minimum_criteria_and_handles_losses():
    assert valuation_score(Fundamentals({"trailing_pe": 10}), 1) is None
    loss = Fundamentals({"trailing_pe": -5, "price_to_book": 1.0, "profit_margin": 0.2})
    result = valuation_score(loss, 1)
    assert result is not None
    pe_row = next(r for r in result.details["criteria"] if r["key"] == "trailing_pe")
    assert pe_row["score"] == 0


def test_analyst_upside_is_derived_from_price():
    fund = Fundamentals({"target_mean_price": 120, "trailing_pe": 15, "forward_pe": 14})
    result = valuation_score(fund, 100)
    assert result is not None
    assert any(r["key"] == "analyst_upside" for r in result.details["criteria"])


def test_technical_score_on_demo_candles_and_short_history():
    candles = DemoProvider().candles("AAPL", "1h")
    result = technical_score(candles)
    assert result is not None and 0 <= result.value <= 100
    assert technical_score(candles[:10]) is None


def test_demo_provider_is_deterministic():
    demo = DemoProvider()
    assert demo.candles("X", "1d")[-1].close == demo.candles("X", "1d")[-1].close
    assert demo.candles("X", "1d")[-1].close != demo.candles("Y", "1d")[-1].close
