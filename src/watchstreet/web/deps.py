"""FastAPI dependencies."""

from collections.abc import Iterator
from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from watchstreet.commodities import BY_KEY
from watchstreet.container import Container
from watchstreet.db import session_scope
from watchstreet.domain import View
from watchstreet.services.viewing import build_view
from watchstreet.services.world import ViewContext
from watchstreet.timeutil import utcnow


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def get_session(container: Annotated[Container, Depends(get_container)]) -> Iterator[Session]:
    with session_scope(container.session_factory) as session:
        yield session


ContainerDep = Annotated[Container, Depends(get_container)]
SessionDep = Annotated[Session, Depends(get_session)]


def parse_scenario(raw: str) -> dict[str, float]:
    """'copper:5.2,gold:3000' -> prices per commodity; anything else is a client error."""
    prices: dict[str, float] = {}
    for part in filter(None, raw.split(",")):
        key, _, value = part.partition(":")
        try:
            price = float(value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Ungültiges Szenario") from exc
        if key not in BY_KEY or price <= 0:
            raise HTTPException(status_code=422, detail="Ungültiges Szenario")
        prices[key] = price
    return prices


def get_view(
    session: SessionDep,
    container: ContainerDep,
    asof: date | None = None,
    view: View = View.AS_KNOWN,
    scenario: str = "",
    proven: bool = False,  # noqa: FBT001, FBT002 - a query flag
) -> ViewContext:
    if asof is not None and asof > utcnow().date():
        raise HTTPException(status_code=422, detail="Der Stichtag liegt in der Zukunft")
    return build_view(
        session, container.market, asof, view, parse_scenario(scenario), proven_only=proven
    )


ViewDep = Annotated[ViewContext, Depends(get_view)]


def get_or_404[T](session: Session, model: type[T], ident: int) -> T:
    row = session.get(model, ident)
    if row is None:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return row
