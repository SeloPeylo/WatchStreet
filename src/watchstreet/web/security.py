"""Security headers and a same-origin check for state-changing requests."""

from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from watchstreet.web.auth import COOKIE, Auth

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
# MapLibre needs blob: workers and injects inline styles; scripts stay strictly same-origin.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; worker-src 'self' blob:; child-src blob:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


def is_cross_site(request: Request) -> bool:
    """A browser sends ``Origin`` on writes; if present it must match the host it talks to."""
    origin = request.headers.get("origin")
    if request.method in SAFE_METHODS or not origin:
        return False
    return urlparse(origin).netloc != request.headers.get("host", "")


async def security_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if is_cross_site(request):
        return JSONResponse({"detail": "Anfrage von fremder Herkunft abgelehnt"}, status_code=403)
    auth: Auth = request.app.state.auth
    allowed = auth.is_valid(request.cookies.get(COOKIE)) or auth.accepts_bearer(
        request.headers.get("authorization")
    )
    if auth.needs_session(request.url.path) and not allowed:
        return JSONResponse({"detail": "Anmeldung erforderlich"}, status_code=401)
    response = await call_next(request)
    for name, value in HEADERS.items():
        response.headers.setdefault(name, value)
    return response
