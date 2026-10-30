"""Application factory: wires the container, static files and one router per area."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from watchstreet.config import load_settings
from watchstreet.container import Container, build_container
from watchstreet.web import (
    routes_intel,
    routes_portfolio,
    routes_stocks,
    routes_system,
    routes_tickets,
)

WEB_DIR = Path(__file__).parent
ROUTE_MODULES = (
    routes_portfolio,
    routes_stocks,
    routes_tickets,
    routes_intel,
    routes_system,
)


def create_app(container: Container | None = None) -> FastAPI:
    settings = container.settings if container else load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not hasattr(app.state, "container"):
            app.state.container = build_container(settings)
        yield

    app = FastAPI(title="WatchStreet", lifespan=lifespan)
    if container is not None:
        app.state.container = container
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    shots = Path(settings.docs_dir) / "screenshots"
    if shots.is_dir():
        app.mount("/manual-assets", StaticFiles(directory=shots), name="manual-assets")
    for route_module in ROUTE_MODULES:
        app.include_router(route_module.router)
    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn --factory``."""
    return create_app()
