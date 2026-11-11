"""Safe retrieval of external documents.

Everything the agents read comes through here. Guards: http(s) only, no private/loopback/
link-local targets (SSRF), bounded redirects, bounded size, content-type allow-list, polite
per-host rate limit. Fetched content is *data*: it is never interpreted as instructions.
"""

import io
import ipaddress
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from watchstreet.constants import (
    FETCH_MIN_INTERVAL_S,
    FETCH_USER_AGENT,
    HTTP_TIMEOUT_S,
    MAX_DOCUMENT_CHARS,
    MAX_FETCH_BYTES,
    MAX_PDF_PAGES,
    MAX_REDIRECTS,
)
from watchstreet.errors import WatchStreetError

TEXT_TYPES = ("text/", "application/json", "application/xml", "application/rss", "application/atom")
HTML_TYPES = ("text/html", "application/xhtml")
PDF_TYPE = "application/pdf"
BLOCK_TAGS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section"}
SKIP_TAGS = {"script", "style", "noscript", "head"}
HTTP_OK = 200
REDIRECT_CODES = {301, 302, 303, 307, 308}


class FetchError(WatchStreetError, RuntimeError):
    """The URL could not be fetched safely."""


@dataclass(frozen=True)
class Fetched:
    url: str
    content_type: str
    text: str
    raw: bytes


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


def pdf_to_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages[:MAX_PDF_PAGES]
        return "\n".join((page.extract_text() or "") for page in pages)
    except (PyPdfError, ValueError, KeyError) as exc:
        msg = f"PDF could not be read: {exc}"
        raise FetchError(msg) from exc


def system_resolver(host: str) -> list[str]:
    try:
        return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]
    except socket.gaierror as exc:
        msg = f"cannot resolve {host}"
        raise FetchError(msg) from exc


def assert_public(url: str, resolver: Callable[[str], list[str]]) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        msg = "only http(s) URLs are allowed"
        raise FetchError(msg)
    for address in resolver(parsed.hostname):
        if not ipaddress.ip_address(address).is_global:
            msg = f"blocked non-public address for {parsed.hostname}"
            raise FetchError(msg)


class Fetcher:
    """HTTP client with the guards above. ``client`` and ``resolver`` are injectable for tests."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        resolver: Callable[[str], list[str]] = system_resolver,
        user_agent: str = FETCH_USER_AGENT,
        min_interval_s: float = FETCH_MIN_INTERVAL_S,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=HTTP_TIMEOUT_S,
            headers={"User-Agent": user_agent},
            follow_redirects=False,
        )
        self._resolver = resolver
        self._min_interval = min_interval_s
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()

    def _throttle(self, host: str) -> None:
        with self._lock:
            wait = self._last_call.get(host, 0.0) + self._min_interval - time.monotonic()
            self._last_call[host] = time.monotonic() + max(wait, 0.0)
        if wait > 0:
            time.sleep(wait)

    def _get(self, url: str) -> httpx.Response:
        for _ in range(MAX_REDIRECTS + 1):
            assert_public(url, self._resolver)
            self._throttle(urlparse(url).hostname or "")
            try:
                response = self._client.get(url)
            except httpx.HTTPError as exc:
                msg = f"request failed: {exc}"
                raise FetchError(msg) from exc
            if response.status_code in REDIRECT_CODES and response.headers.get("location"):
                url = urljoin(url, response.headers["location"])
                continue
            if response.status_code != HTTP_OK:
                msg = f"HTTP {response.status_code} for {url}"
                raise FetchError(msg)
            return response
        msg = "too many redirects"
        raise FetchError(msg)

    def fetch(self, url: str) -> Fetched:
        response = self._get(url)
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if not content_type.startswith(TEXT_TYPES) and content_type != PDF_TYPE:
            msg = f"content type not allowed: {content_type or 'unknown'}"
            raise FetchError(msg)
        raw = response.content
        if len(raw) > MAX_FETCH_BYTES:
            msg = "document too large"
            raise FetchError(msg)
        if content_type == PDF_TYPE:
            text = pdf_to_text(raw)
        elif content_type.startswith(HTML_TYPES):
            text = html_to_text(raw.decode(response.encoding or "utf-8", errors="replace"))
        else:
            text = raw.decode(response.encoding or "utf-8", errors="replace")
        return Fetched(str(response.url), content_type, text[:MAX_DOCUMENT_CHARS], raw)
