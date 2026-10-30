"""Pure technical indicator functions."""

import itertools

from watchstreet.constants import PERCENT, RSI_PERIOD


def sma(values: list[float], period: int) -> float | None:
    """Simple moving average of the last ``period`` values."""
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def rsi(values: list[float], period: int = RSI_PERIOD) -> float | None:
    """Wilder's relative strength index."""
    if len(values) <= period:
        return None
    deltas = [b - a for a, b in itertools.pairwise(values)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:], strict=True):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return PERCENT
    relative_strength = avg_gain / avg_loss
    return PERCENT - PERCENT / (1 + relative_strength)


def pct_change(values: list[float], bars: int) -> float | None:
    """Percentage change over the last ``bars`` bars."""
    if len(values) <= bars or values[-bars - 1] == 0:
        return None
    return (values[-1] / values[-bars - 1] - 1.0) * PERCENT
