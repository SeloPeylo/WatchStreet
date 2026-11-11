"""Deterministic checks and scores of the analysis engine (pure, no LLM)."""

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from watchstreet.constants import (
    LOWER_QUARTILE,
    MAD_TO_SIGMA,
    MIN_PEER_GROUP,
    OUTLIER_MAD_FACTOR,
    UPPER_QUARTILE,
    VALUE_WEIGHTS,
)
from watchstreet.domain import KnowledgeStatus


def missing_metrics(required: Sequence[str], present: Sequence[str]) -> list[str]:
    return [key for key in required if key not in present]


def robust_outliers(values: Mapping[int, float]) -> list[int]:
    """Ids whose value lies outside median +/- k * MAD; too small groups give no result."""
    if len(values) < MIN_PEER_GROUP:
        return []
    median = statistics.median(values.values())
    mad = statistics.median(abs(v - median) for v in values.values())
    if mad == 0:
        return []
    limit = OUTLIER_MAD_FACTOR * MAD_TO_SIGMA * mad
    return [key for key, value in values.items() if abs(value - median) > limit]


def peer_range(values: Sequence[float]) -> tuple[float, float] | None:
    """Inter-quartile range of a peer group, used as a transparent estimate band."""
    if len(values) < MIN_PEER_GROUP:
        return None
    ordered = sorted(values)

    def quantile(q: float) -> float:
        position = q * (len(ordered) - 1)
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    return quantile(LOWER_QUARTILE), quantile(UPPER_QUARTILE)


def value_score(parts: Mapping[str, float]) -> float:
    """Weighted sum of the five part scores (each clamped to 0..1). It sorts, it never hides."""
    return round(
        sum(
            weight * min(max(parts.get(key, 0.0), 0.0), 1.0)
            for key, weight in VALUE_WEIGHTS.items()
        ),
        3,
    )


@dataclass(frozen=True)
class KnowledgeInputs:
    has_facts: bool
    has_agent_research: bool
    changed_since_visit: bool
    is_stale: bool


def knowledge_status(inputs: KnowledgeInputs) -> KnowledgeStatus:
    """Derived, never set by hand. 'Unexamined' means nothing is known, not 'nothing there'."""
    if inputs.changed_since_visit:
        return KnowledgeStatus.NEW
    if inputs.is_stale:
        return KnowledgeStatus.STALE
    if inputs.has_agent_research:
        return KnowledgeStatus.DEEP
    if inputs.has_facts:
        return KnowledgeStatus.KNOWN
    return KnowledgeStatus.UNEXAMINED
