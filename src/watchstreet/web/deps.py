"""FastAPI dependencies."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from watchstreet.container import Container
from watchstreet.db import session_scope


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def get_session(container: Annotated[Container, Depends(get_container)]) -> Iterator[Session]:
    with session_scope(container.session_factory) as session:
        yield session


ContainerDep = Annotated[Container, Depends(get_container)]
SessionDep = Annotated[Session, Depends(get_session)]
