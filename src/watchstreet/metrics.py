"""Catalog of the figures an asset can carry (data, not logic)."""

import re
from dataclasses import dataclass

from watchstreet.domain import AssetStatus


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    is_cost: bool = False  # cost figures must name their definition (basis)
    per_unit: bool = False  # unit is "USD/<commodity unit>"
    annual: bool = False  # unit is "<commodity unit>/Jahr"
    is_text: bool = False


METRICS: dict[str, Metric] = {
    m.key: m
    for m in (
        Metric("production", "Jahresproduktion", annual=True),
        Metric("aisc", "AISC", is_cost=True, per_unit=True),
        Metric("cash_cost", "Cash Cost", is_cost=True, per_unit=True),
        Metric("reserves", "Reserven"),
        Metric("resources", "Ressourcen"),
        Metric("grade", "Gehalt"),
        Metric("study_stage", "Studienstand", is_text=True),
        Metric("capex", "Capex"),
        Metric("expected_production", "Erwartete Produktion", annual=True),
        Metric("expected_aisc", "Erwartete AISC", is_cost=True, per_unit=True),
        Metric("study_price", "Preisannahme der Studie", per_unit=True),
        Metric("study_npv", "NPV laut Studie"),
        Metric("first_production", "Geplante Inbetriebnahme", is_text=True),
    )
}

PRODUCING_CARD = ("production", "aisc", "reserves", "grade")
PROJECT_CARD = (
    "study_stage",
    "resources",
    "capex",
    "expected_production",
    "expected_aisc",
    "study_price",
    "study_npv",
    "first_production",
)
# figures whose absence makes the engine suggest research
KEY_METRICS_PRODUCING = ("production", "aisc", "reserves")
KEY_METRICS_PROJECT = ("study_stage", "resources")
PRODUCING_STATUSES = (AssetStatus.PRODUCTION,)

_NUMBER = r"(?P<value>\d{1,3}(?:[,.  ]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
# deterministic extraction: label, a short gap without sentence end, then the number
EXTRACT_PATTERNS: dict[str, re.Pattern[str]] = {
    "aisc": re.compile(
        rf"(?:all-in sustaining costs?|AISC)[^.\n]{{0,60}}?(?:US\$|USD|\$)\s?{_NUMBER}", re.I
    ),
    "cash_cost": re.compile(rf"cash costs?[^.\n]{{0,60}}?(?:US\$|USD|\$)\s?{_NUMBER}", re.I),
    "production": re.compile(
        rf"(?:annual production|produced|production of)[^.\n]{{0,40}}?{_NUMBER}", re.I
    ),
    "reserves": re.compile(
        rf"(?:proven and probable|mineral) reserves[^.\n]{{0,60}}?{_NUMBER}", re.I
    ),
}


def card_metrics(status: str) -> tuple[str, ...]:
    return PRODUCING_CARD if status in PRODUCING_STATUSES else PROJECT_CARD


def key_metrics(status: str) -> tuple[str, ...]:
    return KEY_METRICS_PRODUCING if status in PRODUCING_STATUSES else KEY_METRICS_PROJECT


def parse_number(raw: str) -> float:
    """'1,234' or '1 234.5' -> float (thousands separators removed)."""
    return float(re.sub(r"[,  ]", "", raw))
