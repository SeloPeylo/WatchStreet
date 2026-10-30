"""Application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from watchstreet.config import load_settings
from watchstreet.container import Container, build_container
from watchstreet.web.routes import router
from watchstreet.web.routes_intel import router as intel_router

WEB_DIR = Path(__file__).parent


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
    app.include_router(router)
    app.include_router(intel_router)
    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn --factory``."""
    return create_app()
