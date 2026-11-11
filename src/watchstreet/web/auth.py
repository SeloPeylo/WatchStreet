"""Single-password login with a signed session cookie.

WatchStreet has one user. If ``WATCHSTREET_PASSWORD`` is set, every API call needs a valid session
cookie; without a password the app is open and must only listen on localhost.
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field

from watchstreet.config import Settings
from watchstreet.constants import LOGIN_LOCK, MAX_LOGIN_FAILURES, SESSION_TTL

COOKIE = "ws_session"
OPEN_PATHS = ("/api/v1/login", "/api/v1/session", "/healthz")


@dataclass
class Auth:
    password: str
    key: bytes
    failures: int = 0
    locked_until: float = 0.0
    _clock: object = field(default=time.time, repr=False)

    @classmethod
    def from_settings(cls, settings: Settings) -> "Auth":
        key = settings.secret_key.encode() if settings.secret_key else secrets.token_bytes(32)
        return cls(settings.password, key)

    @property
    def required(self) -> bool:
        return bool(self.password)

    def _now(self) -> float:
        return float(self._clock())  # type: ignore[operator]

    def _sign(self, expires: int) -> str:
        return hmac.new(self.key, str(expires).encode(), hashlib.sha256).hexdigest()

    def login(self, password: str) -> str | None:
        """A fresh session token, or ``None`` for a wrong password or while locked."""
        if self._now() < self.locked_until:
            return None
        if not hmac.compare_digest(password.encode(), self.password.encode()):
            self.failures += 1
            if self.failures >= MAX_LOGIN_FAILURES:
                self.locked_until = self._now() + LOGIN_LOCK.total_seconds()
                self.failures = 0
            return None
        self.failures = 0
        expires = int(self._now() + SESSION_TTL.total_seconds())
        return f"{expires}.{self._sign(expires)}"

    def is_valid(self, token: str | None) -> bool:
        if not self.required:
            return True
        expires, _, signature = (token or "").partition(".")
        if not expires.isdigit() or int(expires) < self._now():
            return False
        return hmac.compare_digest(signature, self._sign(int(expires)))

    def needs_session(self, path: str) -> bool:
        """Only the API is protected; the page itself has to load to show the login form."""
        return self.required and path.startswith("/api/") and path not in OPEN_PATHS
