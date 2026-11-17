"""Pure rules for combining time series honestly.

A series is a list of ``(day, value)`` sorted by day. Nothing here fills gaps or interpolates:
a combined value exists only where every input has a value of its own.
"""

import math
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise
from statistics import median

from watchstreet.constants import (
    GRID_MEDIAN_GAP_DAYS,
    GRIDS,
    JOINT_MIN_PIVOT,
    MAX_JOINT_DRIVERS,
    SENSITIVITY_MIN_OBS,
)

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


def weekly_mean(points: Points) -> Points:
    """Mean per calendar week, dated on the Monday of that week."""
    buckets: dict[date, list[float]] = defaultdict(list)
    for day, value in points:
        buckets[day - timedelta(days=day.weekday())].append(value)
    return [(monday, sum(v) / len(v)) for monday, v in sorted(buckets.items())]


def infer_frequency(points: Points) -> str:
    """Frequency read off the spacing of the observations (median gap), for undeclared series."""
    gaps = [(b[0] - a[0]).days for a, b in pairwise(points)]
    spacing = median(gaps) if gaps else 0
    for grid in reversed(GRIDS):
        if grid in GRID_MEDIAN_GAP_DAYS and spacing >= GRID_MEDIAN_GAP_DAYS[grid]:
            return grid
    return GRIDS[0]


def coarsest_grid(frequencies: Iterable[str]) -> str:
    """The coarsest of the given frequencies (monthly > weekly > daily); daily if none is known."""
    known = [GRIDS.index(f) for f in frequencies if f in GRIDS]
    return GRIDS[max(known, default=0)]


def resample(points: Points, grid: str) -> Points:
    """Bring a series to ``grid``: monthly or weekly means, or the days as they are."""
    if grid == "monthly":
        return monthly_mean(points)
    if grid == "weekly":
        return weekly_mean(points)
    return points


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
    r2 = cov * cov / (var_x * var_y)
    # t value of the slope; meaningless for overlapping or autocorrelated changes (caller's note)
    t = (
        math.copysign(math.sqrt(r2 * (n - 2) / (1 - r2)), cov)
        if r2 < 1
        else math.copysign(math.inf, cov)
    )
    return {"beta": cov / var_x, "r2": r2, "n": float(n), "t": t}


def own_path(
    target: Points, driver: Points, min_obs: int
) -> list[tuple[date, float, float, float]]:
    """What the driver explains of the target and what remains the target's own.

    Returns ``(day, total, explained, slope)`` as cumulative log changes from the first day a
    slope exists. Each step uses a slope fitted only on *earlier* changes, so nothing is
    explained with knowledge of the future; ``total - explained`` is the target's own part.
    """
    other = dict(driver)
    shared = [
        (day, v, other[day]) for day, v in target if day in other and v > 0 and other[day] > 0
    ]
    n = sum_x = sum_y = sum_xx = sum_xy = 0.0
    total = explained = 0.0
    out: list[tuple[date, float, float, float]] = []
    for (_, y0, x0), (day, y1, x1) in pairwise(shared):
        x, y = math.log(x1 / x0), math.log(y1 / y0)
        var = n * sum_xx - sum_x * sum_x
        if n >= min_obs and var > 0:
            slope = (n * sum_xy - sum_x * sum_y) / var
            total += y
            explained += slope * x
            out.append((day, total, explained, slope))
        n, sum_x, sum_y, sum_xx, sum_xy = (
            n + 1,
            sum_x + x,
            sum_y + y,
            sum_xx + x * x,
            sum_xy + x * y,
        )
    return out


def _standardised(values: list[float]) -> list[float] | None:
    mean = sum(values) / len(values)
    spread = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    return [(v - mean) / spread for v in values] if spread > 0 else None


def cycle(points: Points, span: int) -> list[tuple[date, float, float]]:
    """Where a series stands in its own cycle: ``(day, level, momentum)`` in standard deviations.

    Level is the distance from the mean of the window shown, momentum the change over ``span``
    observations. Both use the whole window, so the classification is hindsight, not a forecast.
    """
    if len(points) <= span + 1:
        return []
    level = _standardised([v for _, v in points])
    momentum = _standardised([points[i][1] - points[i - span][1] for i in range(span, len(points))])
    if level is None or momentum is None:
        return []
    return [(points[i][0], level[i], momentum[i - span]) for i in range(span, len(points))]


def unusual_move(points: Points, span: int, *, relative: bool) -> tuple[float, float] | None:
    """Latest change over ``span`` observations and how unusual it is among all such changes."""
    values = [v for _, v in points]
    if relative and min(values, default=0) <= 0:
        return None
    moves = [
        math.log(values[i] / values[i - span]) if relative else values[i] - values[i - span]
        for i in range(span, len(values))
    ]
    if len(moves) <= span:
        return None
    scores = _standardised(moves)
    if scores is None:
        return None
    latest = (math.exp(moves[-1]) - 1) * PERCENT if relative else moves[-1]
    return latest, scores[-1]


@dataclass(frozen=True)
class JointFit:
    """Joint least-squares fit of a target's changes on several drivers' changes.

    ``contributions[i]`` is ``betas[i]`` times the total step of driver ``i`` over the window;
    ``own`` is what is left of ``total`` (the target's own part, including its steady drift), so
    ``sum(contributions) + own == total``. All steps are log changes for relative series.
    """

    betas: tuple[float, ...]
    r_squared: float
    observations: int
    contributions: tuple[float, ...]
    own: float
    total: float


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting; ``None`` if a pivot is below the limit."""
    n = len(rhs)
    rows = [[*row, rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        best = max(range(col, n), key=lambda r: abs(rows[r][col]))
        if abs(rows[best][col]) < JOINT_MIN_PIVOT:
            return None
        rows[col], rows[best] = rows[best], rows[col]
        for r in range(col + 1, n):
            factor = rows[r][col] / rows[col][col]
            for c in range(col, n + 1):
                rows[r][c] -= factor * rows[col][c]
    solution = [0.0] * n
    for r in reversed(range(n)):
        rest = sum(rows[r][c] * solution[c] for c in range(r + 1, n))
        solution[r] = (rows[r][n] - rest) / rows[r][r]
    return solution


def joint_sensitivity(
    target: Points,
    drivers: Sequence[Points],
    *,
    relative_target: bool,
    relative_drivers: Sequence[bool],
    min_obs: int = SENSITIVITY_MIN_OBS,
) -> JointFit | None:
    """Least squares with intercept of the target's changes on up to three drivers' changes.

    Series are aligned on the days all of them share; changes are taken between consecutive shared
    days (log changes for relative series, differences otherwise). The normal equations are solved
    on standardised changes (a correlation matrix), so the pivot limit does not depend on units.
    ``None`` below ``min_obs``, without variation, or if the drivers are (nearly) collinear.
    """
    count = len(drivers)
    if not 1 <= count <= MAX_JOINT_DRIVERS or len(relative_drivers) != count:
        raise ValueError(f"1 to {MAX_JOINT_DRIVERS} drivers with one flag each are needed")
    lookups = [dict(d) for d in drivers]
    rows = [
        (value, [lookup[day] for lookup in lookups])
        for day, value in target
        if all(day in lookup for lookup in lookups)
    ]
    if relative_target:
        rows = [row for row in rows if row[0] > 0]
    for i, relative in enumerate(relative_drivers):
        if relative:
            rows = [row for row in rows if row[1][i] > 0]
    ys = _steps([row[0] for row in rows], relative=relative_target)
    xs = [_steps([row[1][i] for row in rows], relative=relative_drivers[i]) for i in range(count)]
    n = len(ys)
    if n < min_obs:
        return None
    mean_y = sum(ys) / n
    sd_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys) / n)
    means = [sum(x) / n for x in xs]
    sds = [math.sqrt(sum((v - m) ** 2 for v in x) / n) for x, m in zip(xs, means, strict=True)]
    if sd_y == 0 or 0 in sds:
        return None
    z = [[(v - m) / s for v in x] for x, m, s in zip(xs, means, sds, strict=True)]
    corr = [
        [sum(a * b for a, b in zip(z[i], z[j], strict=True)) / n for j in range(count)]
        for i in range(count)
    ]
    link = [
        sum(a * (y - mean_y) / sd_y for a, y in zip(z[i], ys, strict=True)) / n
        for i in range(count)
    ]
    standard = _solve(corr, link)
    if standard is None:
        return None
    betas = tuple(b * sd_y / s for b, s in zip(standard, sds, strict=True))
    r_squared = min(max(sum(b * r for b, r in zip(standard, link, strict=True)), 0.0), 1.0)
    contributions = tuple(beta * sum(x) for beta, x in zip(betas, xs, strict=True))
    total = sum(ys)
    return JointFit(betas, r_squared, n, contributions, total - sum(contributions), total)
