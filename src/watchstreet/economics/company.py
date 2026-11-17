"""Company-level ratios (pure). Missing inputs yield ``None``, never a guess."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS_PER_QUARTER = 3.0
DAYS_PER_MONTH = 30.44


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


def enterprise_value(
    market_cap: float | None, cash: float | None, debt: float | None
) -> float | None:
    """What a buyer pays for the business: market value plus debt minus cash."""
    if market_cap is None or cash is None or debt is None:
        return None
    return market_cap + debt - cash


def funding_gap(capex: float | None, cash: float | None) -> float | None:
    """Capital still to be raised to build the projects; 0 if the cash covers it."""
    if capex is None or cash is None:
        return None
    return max(capex - cash, 0.0)


@dataclass(frozen=True)
class Raise:
    """One financing after the balance sheet date."""

    amount: float
    is_equity: bool = True
    price: float | None = None
    shares: float | None = None
    warrants: float | None = None


def new_shares(raises: Sequence[Raise]) -> float:
    """Shares issued by the raises: as stated, else amount / price for equity."""
    total = 0.0
    for r in raises:
        if r.shares:
            total += r.shares
        elif r.is_equity and r.price:
            total += r.amount / r.price
    return total


def pro_forma_cash(cash: float | None, raises: Sequence[Raise]) -> float | None:
    return None if cash is None else cash + sum(r.amount for r in raises)


def cash_today(
    cash: float | None, raised: float, burn_per_quarter: float | None, days: int | None
) -> float | None:
    """Reported cash plus later raises minus the burn since the balance sheet date (not below 0)."""
    if cash is None:
        return None
    spent = 0.0
    if burn_per_quarter and burn_per_quarter > 0 and days and days > 0:
        spent = burn_per_quarter * days / (DAYS_PER_MONTH * MONTHS_PER_QUARTER)
    return max(cash + raised - spent, 0.0)


def cash_empty_on(as_at: date | None, months: float | None) -> date | None:
    """The day the cash runs out if the burn continues from the balance sheet date."""
    if as_at is None or months is None:
        return None
    return as_at + timedelta(days=round(months * DAYS_PER_MONTH))


@dataclass(frozen=True)
class CashOutlook:
    """Everything said about the cash on one basis: the estimate for the reference day."""

    cash_now: float | None
    runway_months: float | None  # from the reference day on; 0 once the cash is used up
    empty_on: date | None
    exhausted: bool  # the estimate reached zero on or before the reference day
    balance_day: date | None


def cash_outlook(
    cash: float | None,
    raises: Sequence[Raise],
    burn_per_quarter: float | None,
    balance_day: date | None,
    reference: date,
) -> CashOutlook:
    """Today's estimated cash, the runway from today and the day it runs out, all consistent.

    ``exhausted`` means the balance sheet is older than the runway: the reported cash is used up
    on paper, so a financing that is not on file has probably happened since.
    """
    days = (reference - balance_day).days if balance_day else None
    now = cash_today(cash, sum(r.amount for r in raises), burn_per_quarter, days)
    burning = burn_per_quarter is not None and burn_per_quarter > 0
    empty_on = cash_empty_on(
        balance_day, runway_months(pro_forma_cash(cash, raises), burn_per_quarter)
    )
    exhausted = burning and now is not None and now <= 0 and empty_on is not None
    if exhausted and empty_on is not None:
        empty_on = min(empty_on, reference)  # rounding to whole days must not put it in the future
    runway = 0.0 if exhausted else runway_months(now, burn_per_quarter)
    return CashOutlook(now, runway, empty_on, exhausted, balance_day)


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator or denominator <= 0:
        return None
    return numerator / denominator
