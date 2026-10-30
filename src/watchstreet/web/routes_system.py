"""System area: health probe, system status page and the rendered user manual."""

from pathlib import Path

import markdown
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from watchstreet.web.deps import ContainerDep, SessionDep
from watchstreet.web.helpers import current_system_status, render
from watchstreet.workflows.definitions import REGISTRY

router = APIRouter()

MANUAL_FILE = "user-manual.md"
MANUAL_IMAGE_PREFIX = "screenshots/"
MANUAL_ASSET_URL = "/manual-assets/"
MANUAL_MARKDOWN_EXTENSIONS = ["tables", "fenced_code", "toc"]


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/system", response_class=HTMLResponse)
def system_page(request: Request, session: SessionDep, container: ContainerDep) -> HTMLResponse:
    return render(
        request,
        "system.html",
        system=current_system_status(session, container),
        workflows=list(REGISTRY.values()),
    )


@router.get("/manual", response_class=HTMLResponse)
def manual_page(request: Request, container: ContainerDep) -> HTMLResponse:
    path = Path(container.settings.docs_dir) / MANUAL_FILE
    if not path.is_file():
        raise HTTPException(404, "Handbuch nicht gefunden")
    source = path.read_text(encoding="utf-8")
    # Screenshots are served from /manual-assets/, not from the docs folder layout.
    source = source.replace(f"]({MANUAL_IMAGE_PREFIX}", f"]({MANUAL_ASSET_URL}")
    html = markdown.markdown(source, extensions=MANUAL_MARKDOWN_EXTENSIONS)
    return render(request, "manual.html", content=html)
