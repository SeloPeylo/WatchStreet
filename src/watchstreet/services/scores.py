"""Views over the score history of a stock."""

from typing import Any

from watchstreet.constants import SCORE_HISTORY_POINTS
from watchstreet.models import Stock


def latest_per_scheme(stock: Stock) -> list[dict[str, Any]]:
    """Newest score per scheme with its value history (oldest first, bounded for sparklines)."""
    grouped: dict[str, list[Any]] = {}
    for score in stock.scores:  # newest first
        grouped.setdefault(score.scheme, []).append(score)
    return [
        {"latest": rows[0], "history": [r.value for r in reversed(rows)][-SCORE_HISTORY_POINTS:]}
        for rows in grouped.values()
    ]
