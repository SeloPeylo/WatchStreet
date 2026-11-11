"""Company-level ratios (pure). Missing inputs yield ``None``, never a guess."""

MONTHS_PER_QUARTER = 3.0


def net_cash(cash: float | None, debt: float | None) -> float | None:
    if cash is None or debt is None:
        return None
    return cash - debt


def runway_months(cash: float | None, burn_per_quarter: float | None) -> float | None:
    """How long the cash lasts at the current burn; ``None`` if the company does not burn cash."""
    if cash is None or burn_per_quarter is None or burn_per_quarter <= 0:
        return None
    return cash / burn_per_quarter * MONTHS_PER_QUARTER


def dilution_overhang(outstanding: float | None, diluted: float | None) -> float | None:
    """Options and warrants as a share of the shares outstanding."""
    if not outstanding or diluted is None:
        return None
    return diluted / outstanding - 1


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator or denominator <= 0:
        return None
    return numerator / denominator
