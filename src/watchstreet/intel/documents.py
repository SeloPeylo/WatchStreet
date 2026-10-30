"""Document store: dedupe, search, outline and quote verification.

Quote verification is the backbone of "no source, no fact": an agent may only attach a claim
to a document if it can quote the document verbatim, and the harness checks that here.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchstreet.constants import (
    MAX_DOCUMENT_CHARS,
    MAX_SEARCH_HITS,
    MAX_SECTIONS,
    MIN_QUOTE_CHARS,
    READ_CHUNK_CHARS,
    SEARCH_SNIPPET_CHARS,
)
from watchstreet.models import Document

SECTION_RE = re.compile(r"^(item\s+\d+[a-c]?\.?[^\n]{0,80}|part\s+[ivx]+[^\n]{0,60})$", re.I | re.M)
QUOTE_MARKS = str.maketrans(
    {
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u2013": "-",
        "\u2014": "-",
    },
)


@dataclass(frozen=True)
class Snippet:
    offset: int
    text: str


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def store_document(  # noqa: PLR0913
    session: Session,
    *,
    url: str,
    text: str,
    kind: str,
    publisher: str = "",
    title: str = "",
    published_at: datetime | None = None,
    stock_id: int | None = None,
    meta: dict[str, object] | None = None,
) -> tuple[Document, bool]:
    """Insert a document unless the same URL+content is already stored. Returns (doc, created)."""
    digest = content_hash(text[:MAX_DOCUMENT_CHARS])
    existing = session.scalar(
        select(Document).where(Document.url == url, Document.content_hash == digest),
    )
    if existing:
        return existing, False
    doc = Document(
        url=url,
        kind=kind,
        publisher=publisher,
        title=title,
        published_at=published_at,
        stock_id=stock_id,
        text=text[:MAX_DOCUMENT_CHARS],
        content_hash=digest,
        meta=meta or {},
    )
    session.add(doc)
    session.flush()
    return doc, True


def _normalize(text: str) -> str:
    return " ".join(text.translate(QUOTE_MARKS).lower().split())


def verify_quote(doc: Document, quote: str) -> bool:
    """True if ``quote`` occurs verbatim (modulo whitespace, case and typographic quotes)."""
    needle = _normalize(quote)
    if len(needle) < MIN_QUOTE_CHARS:
        return False
    return needle in _normalize(doc.text)


def search(doc: Document, query: str) -> list[Snippet]:
    """Case-insensitive search; every term must occur in the snippet window."""
    terms = [t for t in re.split(r"\s+", query.lower().strip()) if t]
    if not terms:
        return []
    lowered = doc.text.lower()
    hits: list[Snippet] = []
    pos = lowered.find(terms[0])
    while pos != -1 and len(hits) < MAX_SEARCH_HITS:
        start = max(0, pos - SEARCH_SNIPPET_CHARS // 2)
        window = lowered[start : pos + SEARCH_SNIPPET_CHARS]
        if all(t in window for t in terms):
            hits.append(Snippet(start, doc.text[start : pos + SEARCH_SNIPPET_CHARS]))
            pos = lowered.find(terms[0], pos + SEARCH_SNIPPET_CHARS)
        else:
            pos = lowered.find(terms[0], pos + 1)
    return hits


def read_chunk(doc: Document, offset: int = 0, length: int = READ_CHUNK_CHARS) -> str:
    offset = max(0, offset)
    return doc.text[offset : offset + min(length, READ_CHUNK_CHARS)]


def outline(doc: Document) -> list[Snippet]:
    """Headings such as 'Item 1A. Risk Factors' with their character offsets."""
    return [Snippet(m.start(), m.group(0).strip()) for m in SECTION_RE.finditer(doc.text)][
        :MAX_SECTIONS
    ]
