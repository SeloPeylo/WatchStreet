"""Assigning a profile to a stock. Precedence: user > agent > auto > none."""

from sqlalchemy.orm import Session

from watchstreet.constants import DEFAULT_PROFILE
from watchstreet.market.service import MarketService
from watchstreet.models import Stock
from watchstreet.profiles.classify import classify
from watchstreet.profiles.registry import PROFILES

RANK = {"none": 0, "auto": 1, "agent": 2, "user": 3}


def assign_profile(stock: Stock, profile: str, source: str) -> bool:
    """Set the profile unless a higher-ranked source already decided. Returns True if changed."""
    if profile not in PROFILES or RANK[source] < RANK[stock.profile_source or "none"]:
        return False
    changed = stock.profile != profile or stock.profile_source != source
    stock.profile, stock.profile_source = profile, source
    return changed


def auto_classify(stock: Stock, market: MarketService) -> None:
    """Fill sector/industry and derive a profile deterministically when possible."""
    info = market.company_info(stock.symbol)
    stock.sector, stock.industry = info.sector, info.industry
    key = classify(info.sector, info.industry)
    if key:
        assign_profile(stock, key, "auto")
    elif (stock.profile_source or "none") == "none":
        stock.profile, stock.profile_source = DEFAULT_PROFILE, "none"


def set_profile_by_user(session: Session, stock: Stock, profile: str) -> None:
    if profile not in PROFILES:
        msg = "Unbekanntes Profil"
        raise ValueError(msg)
    stock.profile, stock.profile_source = profile, "user"
    session.flush()
