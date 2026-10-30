"""Builders for the JSON payloads of the read-only agent tools.

Each function turns already-loaded data into a small dict; no I/O happens here, so the output
is easy to test and the token cost of every tool is visible in one place.
"""

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from watchstreet.constants import (
    MOMENTUM_BARS,
    PRICE_SUMMARY_TAIL_BARS,
    RECENT_LIMIT,
    RSI_PERIOD,
    SCORE_HISTORY_LIMIT,
    SMA_FAST,
    SMA_SLOW,
    THESIS_PREVIEW_CHARS,
)
from watchstreet.market.base import Candle
from watchstreet.market.indicators import pct_change, rsi, sma
from watchstreet.models import MarketEvent, Stock
from watchstreet.profiles.registry import Profile


def price_summary(candles: Sequence[Candle], interval: str) -> dict[str, Any]:
    """High/low, moving averages, RSI, momentum and the last closes of a candle series."""
    closes = [candle.close for candle in candles]
    return {
        "interval": interval,
        "bars": len(closes),
        "high": max(candle.high for candle in candles),
        "low": min(candle.low for candle in candles),
        f"sma{SMA_FAST}": sma(closes, SMA_FAST),
        f"sma{SMA_SLOW}": sma(closes, SMA_SLOW),
        f"rsi{RSI_PERIOD}": rsi(closes),
        f"change_{MOMENTUM_BARS}_bars_pct": pct_change(closes, MOMENTUM_BARS),
        "last_closes": [round(close, 2) for close in closes[-PRICE_SUMMARY_TAIL_BARS:]],
    }


def news_headlines(events: Sequence[MarketEvent]) -> list[dict[str, str]]:
    """Date and title per stored news event."""
    return [{"date": f"{event.published_at:%Y-%m-%d}", "title": event.title} for event in events]


def knowledge_summary(stock: Stock) -> dict[str, Any]:
    """Earlier theses, per-scheme score history (oldest first) and insights of a stock."""
    score_history: dict[str, list[float]] = defaultdict(list)
    for score in reversed(stock.scores):  # stock.scores is newest first
        score_history[score.scheme].append(score.value)
    return {
        "theses": [
            {
                "status": thesis.status,
                "date": f"{thesis.created_at:%Y-%m-%d}",
                "text": thesis.text[:THESIS_PREVIEW_CHARS],
            }
            for thesis in stock.theses[:RECENT_LIMIT]
        ],
        "score_history": {
            scheme: values[-SCORE_HISTORY_LIMIT:] for scheme, values in score_history.items()
        },
        "insights": [
            {"category": insight.category, "text": insight.text}
            for insight in stock.insights[:RECENT_LIMIT]
        ],
    }


def datapoint_specs(stock: Stock, profile: Profile) -> dict[str, Any]:
    """The inputs the stock's profile wants and whether each key already has a value."""
    recorded_keys = {datapoint.key for datapoint in stock.datapoints}
    return {
        "profile": profile.key,
        "subject_label": profile.subject_label,
        "specs": [
            {
                "key": spec.key,
                "label": spec.label,
                "unit": spec.unit,
                "hint": spec.hint,
                "required": spec.required,
                "per_subject": spec.per_subject,
                "textual": spec.textual,
                "recorded": spec.key in recorded_keys,
            }
            for spec in profile.datapoints
        ],
    }
