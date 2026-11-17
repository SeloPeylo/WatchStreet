"""Charts API: yardstick matrix, lever chain, lenses and the regime map."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from watchstreet.constants import EXPRESSION_MAX_CHARS, LENS_NAME_CHARS, REGIME_DEFAULT_YEARS
from watchstreet.services import charts
from watchstreet.web.deps import SessionDep

router = APIRouter(prefix="/api/v1/charts", tags=["charts"])
MAX_YEARS = 30.0


class LensIn(BaseModel):
    expression: str = Field(min_length=1, max_length=EXPRESSION_MAX_CHARS)
    subject: str = ""


class DriversIn(BaseModel):
    drivers: list[str]


class LensSave(BaseModel):
    name: str = Field(min_length=1, max_length=LENS_NAME_CHARS)
    expression: str = Field(min_length=1, max_length=EXPRESSION_MAX_CHARS)


def _years(years: float) -> float:
    if not 0 < years <= MAX_YEARS:
        raise HTTPException(422, "Zeitraum ausserhalb des erlaubten Bereichs")
    return years


@router.get("/series")
def series(session: SessionDep) -> list[dict[str, Any]]:
    return charts.Universe(session).catalog()


@router.get("/matrix")
def matrix(session: SessionDep) -> dict[str, Any]:
    return charts.matrix(session)


@router.get("/chain")
def chain(session: SessionDep, key: str, years: float = 1.0) -> dict[str, Any]:
    return charts.chain(session, key, _years(years))


@router.post("/lens")
def lens(session: SessionDep, body: LensIn) -> dict[str, Any]:
    return charts.lens(session, body.expression, body.subject)


@router.get("/lenses")
def lenses(session: SessionDep) -> list[dict[str, Any]]:
    return charts.lenses(session)


@router.post("/lenses")
def save_lens(session: SessionDep, body: LensSave) -> dict[str, Any]:
    return charts.save_lens(session, body.name, body.expression)


@router.delete("/lenses/{lens_id}", status_code=204)
def delete_lens(session: SessionDep, lens_id: int) -> None:
    if not charts.delete_lens(session, lens_id):
        raise HTTPException(404, "Unbekannte Linse")


@router.get("/ladder")
def ladder(
    session: SessionDep, key: str, driver: str = "", years: float = 3.0, drivers: str = ""
) -> dict[str, Any]:
    return charts.ladder(session, key, driver, _years(years), drivers)


@router.get("/drivers/{key}")
def get_drivers(session: SessionDep, key: str) -> dict[str, Any]:
    return charts.driver_set(session, key)


@router.put("/drivers/{key}")
def put_drivers(session: SessionDep, key: str, body: DriversIn) -> dict[str, Any]:
    return charts.save_driver_set(session, key, body.drivers)


@router.delete("/drivers/{key}", status_code=204)
def delete_drivers(session: SessionDep, key: str) -> None:
    charts.delete_driver_set(session, key)


@router.get("/sheet")
def sheet(session: SessionDep, key: str, years: float = 3.0) -> dict[str, Any]:
    return charts.sheet(session, key, _years(years))


@router.get("/cycle")
def cycle(session: SessionDep, key: str, driver: str = "", years: float = 5.0) -> dict[str, Any]:
    return charts.cycle(session, key, driver, _years(years))


@router.get("/regime")
def regime(
    session: SessionDep,
    x: str = "DFII10",
    y: str = "DTWEXBGS",
    years: float = REGIME_DEFAULT_YEARS,
) -> dict[str, Any]:
    return charts.regime(session, x, y, _years(years))
