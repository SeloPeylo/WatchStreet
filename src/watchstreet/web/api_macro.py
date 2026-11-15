"""Macro API: tracked series, derived measures and charts in other denominators."""

from typing import Any

from fastapi import APIRouter, HTTPException

from watchstreet.constants import SCAN_REQUEST_KEY
from watchstreet.services import macro
from watchstreet.services.state import touch
from watchstreet.web.deps import SessionDep

router = APIRouter(prefix="/api/v1/macro", tags=["macro"])


@router.get("")
def overview(session: SessionDep) -> dict[str, Any]:
    return macro.overview(session)


@router.get("/chart")
def chart(session: SessionDep, key: str, den: str = "usd") -> dict[str, Any]:
    if key not in macro.ITEMS:
        raise HTTPException(404, "Unbekannte Reihe")
    if den not in macro.DENOMINATORS:
        raise HTTPException(422, "Unbekannter Nenner")
    return macro.chart(session, key, den)


@router.post("/refresh", status_code=202)
def refresh(session: SessionDep) -> dict[str, str]:
    """Ask the worker to fetch the series with its next scan; nothing is fetched in the request."""
    touch(session, SCAN_REQUEST_KEY)
    return {"status": "requested"}
