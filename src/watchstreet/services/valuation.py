"""Profile-aware valuation: assemble metrics, run the profile's derivations, score."""

from watchstreet.market.base import Fundamentals
from watchstreet.market.service import MarketService
from watchstreet.models import Stock
from watchstreet.profiles.derive import DeriveInput, Point
from watchstreet.profiles.registry import Profile, get_profile
from watchstreet.profiles.scoring import ScoreResult, score_metrics
from watchstreet.services.datapoints import as_points, latest

COMMODITY_SYMBOL_KEY = "commodity_symbol"
COMMODITY_PRICE_KEY = "commodity_price"


def commodity_price(market: MarketService, points: list[Point]) -> float | None:
    """Manual price wins; otherwise quote the configured commodity symbol."""
    manual = next((p.value for p in points if p.key == COMMODITY_PRICE_KEY and p.value), None)
    if manual:
        return manual
    symbol = next((p.text for p in points if p.key == COMMODITY_SYMBOL_KEY and p.text), "")
    quote = market.try_quote(symbol) if symbol else None
    return quote.price if quote else None


def missing_inputs(profile: Profile, points: list[Point]) -> list[str]:
    """Required company-wide datapoints that are absent."""
    present = {p.key for p in points if p.value is not None or p.text}
    return [
        f"{spec.label} ({spec.key})"
        for spec in profile.datapoints
        if spec.required and not spec.per_subject and spec.key not in present
    ]


def compute_valuation(
    market: MarketService,
    stock: Stock,
    price: float | None,
    fundamentals: Fundamentals,
    commodity_shock: float = 0.0,
) -> ScoreResult | None:
    """Profile valuation. ``commodity_shock`` (e.g. -0.1) re-prices the commodity for what-ifs."""
    profile = get_profile(stock.profile)
    points = as_points(latest(stock))
    metrics = dict(fundamentals.values)
    target = metrics.get("target_mean_price")
    if target and price:
        metrics["analyst_upside"] = target / price - 1.0
    metrics.update({p.key: p.value for p in points if p.value is not None and not p.subject})
    missing = missing_inputs(profile, points)
    breakdown: dict[str, object] = {}
    if profile.derive is not None:
        spot = commodity_price(market, points)
        shocked = spot * (1 + commodity_shock) if spot is not None else None
        derived = profile.derive(DeriveInput(metrics, points, price, stock.currency, shocked))
        metrics.update(derived.metrics)
        missing += derived.missing
        breakdown = derived.breakdown
    return score_metrics(
        profile.scheme,
        profile.criteria,
        metrics,
        core_metrics=profile.core_metrics,
        missing=missing,
        breakdown=breakdown,
    )
