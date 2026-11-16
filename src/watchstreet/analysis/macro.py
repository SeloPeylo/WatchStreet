"""Pure rules for combining time series honestly.

A series is a list of ``(day, value)`` sorted by day. Nothing here fills gaps or interpolates:
a combined value exists only where every input has a value of its own.
"""

import math
from collections import defaultdict
from datetime import date

Points = list[tuple[date, float]]
PERCENT = 100.0


def combine(first: Points, second: Points, op: str) -> Points:
    """Ratio or difference on the days both series have a value."""
    other = dict(second)
    out: Points = []
    for day, value in first:
        if day not in other:
            continue
        if op == "ratio":
            if other[day] != 0:
                out.append((day, value / other[day]))
        else:
            out.append((day, value - other[day]))
    return out


def net_liquidity(balance_sheet: Points, treasury_account: Points, reverse_repo: Points) -> Points:
    """Fed balance sheet minus Treasury account minus reverse repo, on balance-sheet days only."""
    return combine(combine(balance_sheet, treasury_account, "diff"), reverse_repo, "diff")


def year_over_year(monthly: Points) -> Points:
    """Percent change against the same month one year earlier."""
    by_month = {(day.year, day.month): value for day, value in monthly}
    out: Points = []
    for day, value in monthly:
        before = by_month.get((day.year - 1, day.month))
        if before:
            out.append((day, (value / before - 1) * PERCENT))
    return out


def monthly_mean(points: Points) -> Points:
    buckets: dict[tuple[int, int], list[float]] = defaultdict(list)
    for day, value in points:
        buckets[(day.year, day.month)].append(value)
    return [(date(y, m, 1), sum(v) / len(v)) for (y, m), v in sorted(buckets.items())]


def deflate(prices: Points, index: Points) -> tuple[Points, date | None]:
    """Monthly means of a price in money of the last published index month.

    The result has the resolution of the coarser series (months) and ends with the last month
    the index covers; later prices are left out rather than deflated with a guess.
    """
    if not index:
        return [], None
    level = {(day.year, day.month): value for day, value in index}
    base_day, base = index[-1]
    out = [
        (day, value * base / level[(day.year, day.month)])
        for day, value in monthly_mean(prices)
        if level.get((day.year, day.month))
    ]
    return out, base_day


def value_on(points: Points, day: date) -> tuple[date, float] | None:
    """Last observation on or before ``day``."""
    hit = None
    for point in points:
        if point[0] > day:
            break
        hit = point
    return hit


def decompose(
    asset: Points, denominator: Points, start: date, end: date
) -> dict[str, float] | None:
    """Split the change of a dollar price into "in the denominator" and "the denominator itself".

    Exact in logarithms: ln change in dollars = ln change in units of the denominator + ln change
    of the denominator. This is arithmetic, not a statement about causes.
    """
    a0, a1 = value_on(asset, start), value_on(asset, end)
    d0, d1 = value_on(denominator, start), value_on(denominator, end)
    if not (a0 and a1 and d0 and d1) or min(a0[1], a1[1], d0[1], d1[1]) <= 0:
        return None
    total = math.log(a1[1] / a0[1])
    carrier = math.log(d1[1] / d0[1])
    return {
        "total_pct": (math.exp(total) - 1) * PERCENT,
        "denominator_pct": (math.exp(carrier) - 1) * PERCENT,
        "in_denominator_pct": (math.exp(total - carrier) - 1) * PERCENT,
    }
