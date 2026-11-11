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
    scope: str = "asset"  # asset | company
    unit: str = ""  # fixed unit of company figures


METRICS: dict[str, Metric] = {
    m.key: m
    for m in (
        Metric("production", "Jahresproduktion", annual=True),
        Metric("aisc", "AISC", is_cost=True, per_unit=True),
        Metric("cash_cost", "Cash Cost", is_cost=True, per_unit=True),
        Metric("reserves", "Reserven"),
        Metric("resources", "Ressourcen"),
        Metric("resources_mi", "Ressourcen gemessen + angezeigt (M&I)"),
        Metric("resources_inferred", "Ressourcen vermutet (Inferred)"),
        Metric("grade", "Gehalt"),
        Metric("recovery", "Ausbringung", unit="%"),
        Metric("study_date", "Datum der Studie", is_text=True),
        Metric("study_stage", "Studienstand", is_text=True),
        Metric("capex", "Capex", unit="USD"),
        Metric("permit_status", "Genehmigungen und Jurisdiktion", is_text=True),
        Metric("expected_production", "Erwartete Produktion", annual=True),
        Metric("expected_aisc", "Erwartete AISC", is_cost=True, per_unit=True),
        Metric("study_price", "Preisannahme der Studie", per_unit=True),
        Metric("study_npv", "NPV laut Studie", unit="USD"),
        Metric("first_production", "Geplante Inbetriebnahme", is_text=True),
        Metric("cash", "Kasse", scope="company", unit="USD"),
        Metric("debt", "Finanzschulden", scope="company", unit="USD"),
        Metric("burn_rate", "Mittelabfluss je Quartal", scope="company", unit="USD/Quartal"),
        Metric("shares_outstanding", "Ausstehende Aktien", scope="company", unit="Aktien"),
        Metric("shares_diluted", "Aktien voll verwässert", scope="company", unit="Aktien"),
        Metric("insider_ownership", "Insiderbesitz", scope="company", unit="%"),
        Metric("royalty_burden", "Royalties und Streams", is_text=True, scope="company"),
        Metric("next_catalyst", "Nächster Katalysator", is_text=True, scope="company"),
    )
}

PRODUCING_CARD = ("production", "aisc", "reserves", "grade", "permit_status")
PROJECT_CARD = (
    "study_stage",
    "permit_status",
    "study_date",
    "resources",
    "resources_mi",
    "resources_inferred",
    "grade",
    "recovery",
    "capex",
    "expected_production",
    "expected_aisc",
    "study_price",
    "study_npv",
    "first_production",
)
COMPANY_CARD = (
    "cash",
    "debt",
    "burn_rate",
    "shares_outstanding",
    "shares_diluted",
    "insider_ownership",
    "royalty_burden",
    "next_catalyst",
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
    "cash": re.compile(
        rf"cash and cash equivalents[^.\n]{{0,60}}?(?:US\$|USD|\$)\s?{_NUMBER}(?P<scale>\s?(?:million|billion))?",
        re.I,
    ),
    "debt": re.compile(
        rf"(?:total|long-term) debt[^.\n]{{0,60}}?(?:US\$|USD|\$)\s?{_NUMBER}(?P<scale>\s?(?:million|billion))?",
        re.I,
    ),
    "shares_outstanding": re.compile(
        rf"{_NUMBER}(?P<scale>\s?(?:million|billion))?\s+(?:common )?shares (?:issued and )?outstanding",
        re.I,
    ),
    "reserves": re.compile(
        rf"(?:proven and probable|mineral) reserves[^.\n]{{0,60}}?{_NUMBER}", re.I
    ),
}


def card_metrics(status: str) -> tuple[str, ...]:
    return PRODUCING_CARD if status in PRODUCING_STATUSES else PROJECT_CARD


def key_metrics(status: str) -> tuple[str, ...]:
    return KEY_METRICS_PRODUCING if status in PRODUCING_STATUSES else KEY_METRICS_PROJECT


SCALES = {"million": 1e6, "billion": 1e9}


def scale_factor(raw: str | None) -> float:
    """'million' -> 1e6; no word -> 1."""
    return SCALES.get((raw or "").strip().lower(), 1.0)


def parse_number(raw: str) -> float:
    """'1,234' or '1 234.5' -> float (thousands separators removed)."""
    return float(re.sub(r"[,  ]", "", raw))
