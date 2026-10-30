"""Declarative profile definitions. Changing a scheme means editing a table here."""

from collections.abc import Callable
from dataclasses import dataclass

from watchstreet.constants import DEFAULT_PROFILE
from watchstreet.profiles.derive import (
    DeriveInput,
    DeriveOutput,
    derive_mining,
    derive_oil_gas,
    derive_reit,
    derive_tech,
)
from watchstreet.profiles.scoring import Criterion

# Panels a stock page can show. The profile decides their order (its "lens").
PANELS = ("valuation", "chart", "evidence", "thesis", "history")


@dataclass(frozen=True)
class DatapointSpec:
    """An input a scheme needs that no free API delivers reliably."""

    key: str
    label: str
    unit: str = ""
    hint: str = ""
    required: bool = False
    per_subject: bool = False  # one value per subject (e.g. per mine)
    textual: bool = False  # value is text (e.g. a ticker symbol)


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    description: str
    scheme: str
    criteria: tuple[Criterion, ...]
    lens: tuple[str, ...]
    core_metrics: tuple[str, ...] = ()  # score is "vorläufig" while any of these is absent
    datapoints: tuple[DatapointSpec, ...] = ()
    derive: Callable[[DeriveInput], DeriveOutput] | None = None
    subject_label: str = ""  # what a subject is called in the UI ("Mine", "Segment")

    def spec(self, key: str) -> DatapointSpec | None:
        return next((d for d in self.datapoints if d.key == key), None)


def _c(
    key: str, label: str, weight: float, good: float, bad: float, *, pos: bool = False
) -> Criterion:
    return Criterion(key, label, weight, good=good, bad=bad, positive_only=pos)


COMMON_UPSIDE = _c("analyst_upside", "Analysten-Kurspotenzial", 0.75, 0.20, -0.10)

GENERIC = Profile(
    "generic",
    "Allgemein",
    "Standardschema aus Kennzahlen, wenn kein Branchenprofil passt.",
    "valuation_v1",
    (
        _c("trailing_pe", "KGV (trailing)", 1.5, 12.0, 35.0, pos=True),
        _c("forward_pe", "KGV (erwartet)", 1.5, 12.0, 30.0, pos=True),
        _c("price_to_book", "Kurs/Buchwert", 1.0, 1.5, 8.0, pos=True),
        _c("peg_ratio", "PEG", 1.0, 1.0, 3.0, pos=True),
        _c("dividend_yield", "Dividendenrendite", 0.5, 0.04, 0.0),
        _c("profit_margin", "Gewinnmarge", 1.0, 0.20, 0.0),
        _c("return_on_equity", "Eigenkapitalrendite", 1.0, 0.20, 0.0),
        _c("revenue_growth", "Umsatzwachstum", 1.0, 0.15, -0.05),
        _c("debt_to_equity", "Verschuldung (D/E)", 0.75, 40.0, 250.0),
        COMMON_UPSIDE,
    ),
    ("chart", "valuation", "thesis", "evidence", "history"),
)

COMMODITY_SPECS = (
    DatapointSpec(
        "commodity_symbol",
        "Rohstoff-Symbol (Kursquelle)",
        hint="z. B. GC=F Gold, SI=F Silber, HG=F Kupfer, CL=F Öl",
        textual=True,
    ),
    DatapointSpec(
        "commodity_price", "Rohstoffpreis (manuell)", "je Einheit", "überschreibt die Kursquelle"
    ),
)

MINING = Profile(
    "mining",
    "Minen / Rohstoffförderer",
    "Net Asset Value aus Minen (NPV der Marge über die Reservenlaufzeit), AISC-Marge, "
    "Reservenlaufzeit.",
    "valuation_mining_v1",
    (
        _c("p_nav", "Kurs/NAV", 3.0, 0.7, 1.5, pos=True),
        _c("aisc_margin_pct", "AISC-Marge (%)", 2.0, 40.0, 5.0),
        _c("reserve_life_years", "Reservenlaufzeit (Jahre)", 1.0, 15.0, 4.0),
        _c("price_to_book", "Kurs/Buchwert", 0.75, 1.0, 3.0, pos=True),
        _c("debt_to_equity", "Verschuldung (D/E)", 0.75, 30.0, 120.0),
        _c("revenue_growth", "Umsatzwachstum", 0.5, 0.15, -0.10),
        COMMON_UPSIDE,
    ),
    ("valuation", "evidence", "chart", "thesis", "history"),
    core_metrics=("p_nav", "aisc_margin_pct"),
    datapoints=(
        *COMMODITY_SPECS,
        DatapointSpec(
            "mine_production",
            "Jahresproduktion",
            "Einheiten/Jahr",
            "z. B. Unzen pro Jahr",
            required=True,
            per_subject=True,
        ),
        DatapointSpec(
            "mine_aisc",
            "AISC (Gesamtkosten je Einheit)",
            "je Einheit",
            "All-in sustaining cost",
            required=True,
            per_subject=True,
        ),
        DatapointSpec(
            "mine_reserves",
            "Reserven",
            "Einheiten",
            "wirtschaftlich gewinnbar",
            required=True,
            per_subject=True,
        ),
        DatapointSpec(
            "mine_ownership", "Beteiligung", "Anteil 0–1", "Standard 1,0", per_subject=True
        ),
        DatapointSpec("net_debt", "Nettoverschuldung", "Berichtswährung", required=True),
        DatapointSpec("shares_outstanding", "Anzahl Aktien", "Stück", "sonst Marktkap./Kurs"),
        DatapointSpec("discount_rate", "Diskontsatz", "Anteil", "Standard 0,08"),
        DatapointSpec("reporting_currency", "Berichtswährung", hint="Standard USD", textual=True),
        DatapointSpec(
            "fx_rate", "Wechselkurs Berichts- → Aktienwährung", hint="nur bei abweichender Währung"
        ),
    ),
    derive=derive_mining,
    subject_label="Mine",
)

OIL_GAS = Profile(
    "oil_gas",
    "Öl & Gas",
    "Marge über dem Break-even-Preis, Reservenlaufzeit und Free-Cash-Flow-Rendite.",
    "valuation_oil_gas_v1",
    (
        _c("commodity_margin_pct", "Marge über Break-even (%)", 2.5, 40.0, 0.0),
        _c("fcf_yield", "FCF-Rendite (%)", 2.0, 10.0, 2.0),
        _c("reserve_life_years", "Reservenlaufzeit (Jahre)", 1.0, 12.0, 5.0),
        _c("forward_pe", "KGV (erwartet)", 1.0, 8.0, 18.0, pos=True),
        _c("dividend_yield", "Dividendenrendite", 0.75, 0.05, 0.01),
        _c("debt_to_equity", "Verschuldung (D/E)", 1.0, 40.0, 120.0),
        COMMON_UPSIDE,
    ),
    ("valuation", "chart", "evidence", "thesis", "history"),
    core_metrics=("commodity_margin_pct",),
    datapoints=(
        *COMMODITY_SPECS,
        DatapointSpec("breakeven_price", "Break-even-Preis", "je Einheit", required=True),
        DatapointSpec("reserves", "Reserven", "Einheiten"),
        DatapointSpec("production", "Jahresproduktion", "Einheiten/Jahr"),
        DatapointSpec("free_cash_flow", "Free Cash Flow (12 Monate)", "Berichtswährung"),
    ),
    derive=derive_oil_gas,
)

TECH = Profile(
    "tech",
    "Technologie",
    "Wachstum und Skalierung: Rule of 40, erwartetes KGV, PEG, Marge.",
    "valuation_tech_v1",
    (
        _c("rule_of_40", "Rule of 40", 2.0, 40.0, 10.0),
        _c("forward_pe", "KGV (erwartet)", 1.5, 20.0, 45.0, pos=True),
        _c("peg_ratio", "PEG", 1.0, 1.2, 3.0, pos=True),
        _c("revenue_growth", "Umsatzwachstum", 1.5, 0.20, 0.0),
        _c("profit_margin", "Gewinnmarge", 1.0, 0.25, 0.0),
        COMMON_UPSIDE,
    ),
    ("chart", "valuation", "thesis", "evidence", "history"),
    derive=derive_tech,
)

UTILITY = Profile(
    "utility",
    "Versorger",
    "Stabile Erträge: Dividende, Verschuldung, KGV, Eigenkapitalrendite.",
    "valuation_utility_v1",
    (
        _c("dividend_yield", "Dividendenrendite", 2.0, 0.045, 0.015),
        _c("debt_to_equity", "Verschuldung (D/E)", 1.5, 100.0, 250.0),
        _c("forward_pe", "KGV (erwartet)", 1.0, 15.0, 25.0, pos=True),
        _c("return_on_equity", "Eigenkapitalrendite", 1.0, 0.12, 0.05),
        _c("price_to_book", "Kurs/Buchwert", 0.75, 1.5, 3.0, pos=True),
        COMMON_UPSIDE,
    ),
    ("valuation", "chart", "thesis", "evidence", "history"),
)

FINANCIAL = Profile(
    "financial",
    "Banken & Finanz",
    "Kurs/Buchwert gegen Eigenkapitalrendite, Kapitalquote, KGV, Dividende.",
    "valuation_financial_v1",
    (
        _c("price_to_book", "Kurs/Buchwert", 2.0, 1.0, 2.5, pos=True),
        _c("return_on_equity", "Eigenkapitalrendite", 2.0, 0.14, 0.06),
        _c("trailing_pe", "KGV (trailing)", 1.0, 10.0, 20.0, pos=True),
        _c("dividend_yield", "Dividendenrendite", 0.75, 0.05, 0.015),
        _c("cet1_ratio", "CET1-Quote", 1.0, 0.15, 0.10),
        COMMON_UPSIDE,
    ),
    ("valuation", "chart", "thesis", "evidence", "history"),
    datapoints=(DatapointSpec("cet1_ratio", "CET1-Kapitalquote", "Anteil", "z. B. 0,14"),),
)

REIT = Profile(
    "reit",
    "Immobilien / REIT",
    "Kurs/FFO und Kurs/NAV statt KGV, dazu Ausschüttung und Verschuldung.",
    "valuation_reit_v1",
    (
        _c("p_ffo", "Kurs/FFO", 2.0, 12.0, 22.0, pos=True),
        _c("p_nav", "Kurs/NAV", 2.0, 0.85, 1.2, pos=True),
        _c("dividend_yield", "Dividendenrendite", 1.5, 0.05, 0.02),
        _c("debt_to_equity", "Verschuldung (D/E)", 1.0, 60.0, 150.0),
        COMMON_UPSIDE,
    ),
    ("valuation", "evidence", "chart", "thesis", "history"),
    core_metrics=("p_ffo",),
    datapoints=(
        DatapointSpec("ffo_per_share", "FFO je Aktie", "Aktienwährung", required=True),
        DatapointSpec("nav_per_share", "NAV je Aktie", "Aktienwährung"),
    ),
    derive=derive_reit,
)

HEALTHCARE = Profile(
    "healthcare",
    "Gesundheit / Pharma",
    "Wachstum und Profitabilität bei vertretbarem KGV; Pipeline-Risiken per Themenanalyse.",
    "valuation_healthcare_v1",
    (
        _c("forward_pe", "KGV (erwartet)", 1.5, 14.0, 30.0, pos=True),
        _c("revenue_growth", "Umsatzwachstum", 1.5, 0.12, 0.0),
        _c("profit_margin", "Gewinnmarge", 1.5, 0.20, 0.0),
        _c("return_on_equity", "Eigenkapitalrendite", 1.0, 0.18, 0.05),
        _c("debt_to_equity", "Verschuldung (D/E)", 0.75, 50.0, 200.0),
        COMMON_UPSIDE,
    ),
    ("chart", "valuation", "thesis", "evidence", "history"),
)

PROFILES: dict[str, Profile] = {
    p.key: p for p in (GENERIC, MINING, OIL_GAS, TECH, UTILITY, FINANCIAL, REIT, HEALTHCARE)
}


def get_profile(key: str | None) -> Profile:
    return PROFILES.get(key or DEFAULT_PROFILE, GENERIC)
