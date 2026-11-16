"""Pure rules for combining time series honestly.

A series is a list of ``(day, value)`` sorted by day. Nothing here fills gaps or interpolates:
a combined value exists only where every input has a value of its own.
"""

import math
from bisect import bisect_right
from collections import defaultdict
from datetime import date
from itertools import pairwise

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


def level_on(points: Points, day: date, max_gap_days: int) -> tuple[date, float] | None:
    """Last observation on or before ``day`` that is not older than ``max_gap_days``."""
    index = bisect_right(points, (day, math.inf)) - 1
    if index < 0 or (day - points[index][0]).days > max_gap_days:
        return None
    return points[index]


def monthly_ratio(prices: Points, index: Points) -> Points:
    """Monthly mean of a price divided by a monthly series, for the months both cover."""
    level = {(day.year, day.month): value for day, value in index}
    return [
        (day, value / level[(day.year, day.month)])
        for day, value in monthly_mean(prices)
        if level.get((day.year, day.month))
    ]


def range_position(points: Points) -> float | None:
    """Where the last value sits between the lowest (0) and highest (1) value of the series."""
    if not points:
        return None
    values = [v for _, v in points]
    low, high = min(values), max(values)
    return (values[-1] - low) / (high - low) if high > low else None


# One link of a lever chain: the level is the product of ``top`` divided by the product of
# ``bottom``. The links of a chain multiply to the asset price, so their log changes add up to
# the log change of the price exactly.
Link = tuple[str, tuple[str, ...], tuple[str, ...]]


def chain_levels(
    series: dict[str, Points], links: list[Link], day: date, max_gap_days: int
) -> tuple[list[float], dict[str, date]] | None:
    """Level of every link on ``day`` and the observation day used per input."""
    values: dict[str, float] = {}
    used: dict[str, date] = {}
    for _, top, bottom in links:
        for name in (*top, *bottom):
            if name in values:
                continue
            hit = level_on(series.get(name, []), day, max_gap_days)
            if hit is None or hit[1] <= 0:
                return None
            used[name], values[name] = hit
    levels = [
        math.prod(values[n] for n in top) / math.prod(values[n] for n in bottom)
        for _, top, bottom in links
    ]
    return levels, used


def chain_path(
    series: dict[str, Points], links: list[Link], days: list[date], max_gap_days: int
) -> list[tuple[date, list[float]]]:
    """Cumulative log change of every link from the first usable day on."""
    base: list[float] | None = None
    out: list[tuple[date, list[float]]] = []
    for day in days:
        hit = chain_levels(series, links, day, max_gap_days)
        if hit is None:
            continue
        levels = hit[0]
        if base is None:
            base = levels
        out.append((day, [math.log(now / then) for now, then in zip(levels, base, strict=True)]))
    return out


def _steps(values: list[float], *, relative: bool) -> list[float]:
    if relative:
        return [math.log(b / a) for a, b in pairwise(values)]
    return [b - a for a, b in pairwise(values)]


def sensitivity(
    target: Points, driver: Points, *, relative_target: bool, relative_driver: bool, min_obs: int
) -> dict[str, float] | None:
    """Least-squares slope of the target's changes on the driver's changes (an estimate).

    Changes are taken between consecutive days both series share; relative changes are log
    changes, others plain differences. ``None`` below ``min_obs`` or without variation.
    """
    other = dict(driver)
    shared = [(value, other[day]) for day, value in target if day in other]
    if relative_target:
        shared = [(a, b) for a, b in shared if a > 0]
    if relative_driver:
        shared = [(a, b) for a, b in shared if b > 0]
    ys = _steps([a for a, _ in shared], relative=relative_target)
    xs = _steps([b for _, b in shared], relative=relative_driver)
    n = len(xs)
    if n < min_obs:
        return None
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    return {"beta": cov / var_x, "r2": cov * cov / (var_x * var_y), "n": float(n)}
