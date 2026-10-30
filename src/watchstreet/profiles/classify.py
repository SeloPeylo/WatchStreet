"""Deterministic sector/industry -> profile mapping (first match wins)."""

# (profile key, substrings matched against "industry sector", lower-cased)
RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "mining",
        ("gold", "silver", "copper", "metals & mining", "uranium", "coking coal", "coal", "mining"),
    ),
    ("oil_gas", ("oil & gas", "oil and gas")),
    ("reit", ("reit", "real estate")),
    ("utility", ("utilities", "utility")),
    ("financial", ("financial", "bank", "insurance", "asset management", "capital markets")),
    ("healthcare", ("healthcare", "biotech", "drug manufacturers", "medical")),
    ("tech", ("technology", "software", "semiconductor", "internet", "information technology")),
)


def classify(sector: str, industry: str) -> str | None:
    """Return a profile key, or ``None`` if the text matches nothing."""
    haystack = f"{industry} {sector}".lower()
    for profile, needles in RULES:
        if any(needle in haystack for needle in needles):
            return profile
    return None
