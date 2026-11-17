"""Purchasing-power band API: one value over time in five yardsticks at once."""

from typing import Any

from fastapi import APIRouter

from watchstreet.services import purchasing
from watchstreet.web.deps import SessionDep

router = APIRouter(prefix="/api/v1/charts", tags=["charts"])


@router.get("/purchasing")
def band(
    session: SessionDep, key: str = "gold", mode: str = "since", start: str = ""
) -> dict[str, Any]:
    """``mode``: "since" (change since ``start``, YYYY-MM) or "rolling" (change over 12 months)."""
    return purchasing.band(session, key, mode, start)
