"""Helpers shared by all route modules: template rendering, redirects and form parsing.

Route modules import from here and never from each other (enforced by import-linter).
"""

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from watchstreet.container import Container
from watchstreet.services.portfolio import PortfolioError
from watchstreet.services.status import system_status
from watchstreet.web.flash import FLASH_MESSAGES, FLASH_PARAM, with_flash
from watchstreet.web.formatting import register_filters

WEB_DIR = Path(__file__).parent
REDIRECT_STATUS = 303  # POST -> GET after a form submission

templates = Jinja2Templates(directory=WEB_DIR / "templates")
register_filters(templates.env)


def parse_number(raw: str, label: str) -> float:
    """Parse a user-entered number (comma or dot as decimal separator)."""
    try:
        return float(raw.strip().replace(",", "."))
    except ValueError as exc:
        msg = f"{label} ist keine Zahl"
        raise PortfolioError(msg) from exc


def parse_date(raw: str) -> date | None:
    """Parse an optional ISO date; blank input means "no date"."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        msg = "Kaufdatum muss das Format JJJJ-MM-TT haben"
        raise PortfolioError(msg) from exc


def render(request: Request, name: str, status_code: int = 200, **ctx: Any) -> HTMLResponse:
    ctx.setdefault("error", None)
    ctx["flash"] = FLASH_MESSAGES.get(request.query_params.get(FLASH_PARAM, ""))
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def redirect(url: str, flash: str | None = None) -> RedirectResponse:
    """303 redirect; ``flash`` is a ``web.flash`` message code shown once afterwards."""
    return RedirectResponse(with_flash(url, flash), status_code=REDIRECT_STATUS)


def get_or_404[Model](session: Session, model: type[Model], primary_key: int) -> Model:
    """Load one row by primary key or answer HTTP 404."""
    row = session.get(model, primary_key)
    if row is None:
        raise HTTPException(404)
    return row


def current_system_status(session: Session, container: Container) -> dict[str, Any]:
    """System-status panel data (dashboard and system page) for the running container."""
    return system_status(
        session,
        market=container.market.name,
        runner=container.runner.name,
        scan_interval_min=container.settings.event_scan_interval_min,
    )
