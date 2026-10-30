"""Deterministic scoring schemes. Pure functions, no I/O.

A criterion maps a raw figure linearly onto 0..100 between a ``good`` and a ``bad`` anchor.
``good`` below ``bad`` means lower is better (e.g. P/E). All anchors are data in the tables
below, so changing the scheme means editing a table, never the logic.
"""

from dataclasses import dataclass
from typing import Any

from watchstreet.constants import (
    MIN_CRITERIA_FOR_SCORE,
    MOMENTUM_BARS,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    SCORE_BAD,
    SCORE_GOOD,
    SCORE_MAX,
    SCORE_MIN,
    SMA_FAST,
    SMA_SLOW,
    TECHNICAL_SCHEME,
)
from watchstreet.market.base import Candle
from watchstreet.market.indicators import pct_change, rsi, sma


@dataclass(frozen=True)
class Criterion:
    key: str
    label: str
    weight: float
    good: float
    bad: float
    positive_only: bool = False  # non-positive values (losses) score zero


@dataclass(frozen=True)
class ScoreResult:
    scheme: str
    value: float
    label: str
    details: dict[str, Any]


# Technical criteria operate on derived percentages computed in `technical_score`.
TECHNICAL_CRITERIA: tuple[Criterion, ...] = (
    Criterion("price_vs_slow_sma", f"Kurs vs. SMA{SMA_SLOW} (%)", 1.0, good=5.0, bad=-5.0),
    Criterion("fast_vs_slow_sma", f"SMA{SMA_FAST} vs. SMA{SMA_SLOW} (%)", 1.0, good=3.0, bad=-3.0),
    Criterion("momentum", f"Momentum {MOMENTUM_BARS} Bars (%)", 1.0, good=8.0, bad=-8.0),
)
RSI_SCORE_OVERSOLD = 70.0
RSI_SCORE_OVERBOUGHT = 30.0
RSI_SCORE_NEUTRAL = 55.0
RSI_WEIGHT = 1.0


def interpolate(value: float, good: float, bad: float) -> float:
    """Linear map: ``good`` -> 100, ``bad`` -> 0, clamped."""
    span = good - bad
    ratio = (value - bad) / span
    return max(SCORE_MIN, min(SCORE_MAX, ratio * SCORE_MAX))


def label_for(value: float, scheme: str) -> str:
    """Human label for a score band."""
    if value >= SCORE_GOOD:
        return "bullisch" if scheme == TECHNICAL_SCHEME else "attraktiv"
    if value <= SCORE_BAD:
        return "bärisch" if scheme == TECHNICAL_SCHEME else "schwach"
    return "neutral"


def _aggregate(
    scheme: str,
    rows: list[dict[str, Any]],
    total_criteria: int,
) -> ScoreResult | None:
    if len(rows) < MIN_CRITERIA_FOR_SCORE:
        return None
    weights = sum(row["weight"] for row in rows)
    value = sum(row["score"] * row["weight"] for row in rows) / weights
    return ScoreResult(
        scheme=scheme,
        value=round(value, 1),
        label=label_for(value, scheme),
        details={"criteria": rows, "coverage": f"{len(rows)}/{total_criteria}"},
    )


def _row(criterion: Criterion, value: float) -> dict[str, Any]:
    if criterion.positive_only and value <= 0:
        score = SCORE_MIN
    else:
        score = interpolate(value, criterion.good, criterion.bad)
    return {
        "key": criterion.key,
        "label": criterion.label,
        "value": round(value, 4),
        "score": round(score, 1),
        "weight": criterion.weight,
    }


def score_metrics(
    scheme: str,
    criteria: tuple[Criterion, ...],
    metrics: dict[str, float],
    *,
    core_metrics: tuple[str, ...] = (),
    missing: list[str] | None = None,
    breakdown: dict[str, Any] | None = None,
) -> ScoreResult | None:
    """Generic criteria engine: score whichever criteria have a metric available."""
    rows = [_row(c, metrics[c.key]) for c in criteria if c.key in metrics]
    result = _aggregate(scheme, rows, len(criteria))
    if result is None:
        return None
    result.details["missing"] = list(missing or [])
    result.details["provisional"] = any(k not in metrics for k in core_metrics)
    if breakdown:
        result.details["breakdown"] = breakdown
    return result


def _rsi_row(rsi_value: float) -> dict[str, Any]:
    if rsi_value <= RSI_OVERSOLD:
        score = RSI_SCORE_OVERSOLD
    elif rsi_value >= RSI_OVERBOUGHT:
        score = RSI_SCORE_OVERBOUGHT
    else:
        score = RSI_SCORE_NEUTRAL
    return {
        "key": "rsi",
        "label": "RSI",
        "value": round(rsi_value, 1),
        "score": score,
        "weight": RSI_WEIGHT,
    }


def technical_score(candles: list[Candle]) -> ScoreResult | None:
    """Trend/momentum score from candle closes."""
    closes = [c.close for c in candles]
    fast, slow = sma(closes, SMA_FAST), sma(closes, SMA_SLOW)
    momentum = pct_change(closes, MOMENTUM_BARS)
    rsi_value = rsi(closes)
    if fast is None or slow is None or momentum is None or rsi_value is None:
        return None
    derived = {
        "price_vs_slow_sma": (closes[-1] / slow - 1.0) * 100.0,
        "fast_vs_slow_sma": (fast / slow - 1.0) * 100.0,
        "momentum": momentum,
    }
    rows = [_row(c, derived[c.key]) for c in TECHNICAL_CRITERIA]
    rows.append(_rsi_row(rsi_value))
    return _aggregate(TECHNICAL_SCHEME, rows, len(rows))
