"""Which facts count for a reference date (pure).

Every fact has a reporting period (what it is about) and a publication date (since when it was
public). "As known" shows only what had been published by the reference date, so no later
knowledge leaks into the past. A fact without publication date is unavailable in that view:
a gap is better than hindsight bias.
"""

from collections.abc import Iterable
from datetime import date
from typing import Protocol

from watchstreet.domain import View


class DatedFact(Protocol):
    id: int
    metric_key: str
    period_end: date | None
    published_at: date | None
    superseded_by: int | None


def is_visible(fact: DatedFact, as_of: date | None, view: View) -> bool:
    if fact.superseded_by == fact.id:
        return False  # withdrawn by the user: it never counts, in no view
    if as_of is None:
        return fact.superseded_by is None
    if view == View.AS_KNOWN:
        return fact.published_at is not None and fact.published_at <= as_of
    reference = fact.period_end or fact.published_at
    return reference is not None and reference <= as_of and fact.superseded_by is None


def _recency(fact: DatedFact) -> tuple[date, int]:
    return (fact.period_end or fact.published_at or date.min, fact.id)


def latest_per_metric[F: DatedFact](
    facts: Iterable[F], as_of: date | None, view: View
) -> dict[str, F]:
    """The newest visible fact per metric (by reporting period, then by id)."""
    best: dict[str, F] = {}
    for fact in facts:
        if not is_visible(fact, as_of, view):
            continue
        current = best.get(fact.metric_key)
        if current is None or _recency(fact) > _recency(current):
            best[fact.metric_key] = fact
    return best
