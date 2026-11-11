"""Application factory: JSON API, the built single-page app and the manual assets."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from watchstreet.config import load_settings
from watchstreet.container import Container, build_container
from watchstreet.errors import WatchStreetError
from watchstreet.web import api_explorer, api_research, api_system
from watchstreet.web.security import security_middleware

WEB_DIR = Path(__file__).parent
APP_DIR = WEB_DIR / "static" / "app"  # output of `npm run build` in frontend/
API_MODULES = (api_explorer, api_research, api_system)
NOT_BUILT = (
    "<h1>WatchStreet</h1><p>Die Oberfläche ist noch nicht gebaut. "
    "Bitte <code>make frontend</code> ausführen (im Docker-Image geschieht das automatisch). "
    'Die API ist unter <a href="/docs">/docs</a> erreichbar.</p>'
)


async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
    """Deliberate application errors are the user's to fix: answer 400 with the message."""
    return JSONResponse({"detail": str(exc)}, status_code=400)


def create_app(container: Container | None = None) -> FastAPI:
    settings = container.settings if container else load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not hasattr(app.state, "container"):
            app.state.container = build_container(settings)
        yield

    app = FastAPI(title="WatchStreet", version="1.0", lifespan=lifespan)
    if container is not None:
        app.state.container = container
    app.middleware("http")(security_middleware)
    app.add_exception_handler(WatchStreetError, _domain_error)
    for module in API_MODULES:
        app.include_router(module.router)
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    shots = Path(settings.docs_dir) / "screenshots"
    if shots.is_dir():
        app.mount("/manual-assets", StaticFiles(directory=shots), name="manual-assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        """Every non-API path belongs to the single-page app (client-side routing)."""
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Unbekannter API-Pfad")
        index = APP_DIR / "index.html"
        if not index.is_file():
            return HTMLResponse(NOT_BUILT)
        return FileResponse(index)

    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn --factory``."""
    return create_app()
