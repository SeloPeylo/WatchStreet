"""Deterministic relevance scoring: which stored documents concern which of my stocks?

This is the cheap first filter. Only documents that clear the threshold are handed to an agent,
which is where tokens are saved: most feed items never reach a model.
"""

import re
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from watchstreet.constants import ASSET_KINDS, MAX_QUERIES_PER_STOCK, RELEVANCE_THRESHOLD
from watchstreet.models import Document, Entity, Relation, Stock

LEGAL_SUFFIX = re.compile(
    r"\b(inc|corp|corporation|co|company|ltd|limited|plc|ag|se|sa|nv|holdings|group)\b\.?,?",
    re.I,
)
MIN_TERM_CHARS = 3
TITLE_FACTOR = 2.0
WEIGHT_NAME = 2.0
WEIGHT_SYMBOL = 1.0
WEIGHT_ASSET = 1.5
WEIGHT_PARTNER = 1.0
SYMBOL_MIN_CHARS = 3
PARTNER_KINDS = ("supplier", "customer")


@dataclass(frozen=True)
class WatchTerm:
    term: str
    stock_id: int
    weight: float


def core_name(name: str) -> str:
    """'Newmont Corporation' -> 'Newmont'."""
    return " ".join(LEGAL_SUFFIX.sub("", name).replace("  ", " ").split()).strip(" ,.")


def watch_terms(session: Session) -> list[WatchTerm]:
    terms: list[WatchTerm] = []
    for stock in session.scalars(select(Stock).where(or_(Stock.holding.has(), Stock.watch.has()))):
        name = core_name(stock.name)
        if len(name) >= MIN_TERM_CHARS and not name.lower().startswith("demo "):
            terms.append(WatchTerm(name, stock.id, WEIGHT_NAME))
        if len(stock.symbol.split(".")[0]) >= SYMBOL_MIN_CHARS:
            terms.append(WatchTerm(stock.symbol.split(".")[0], stock.id, WEIGHT_SYMBOL))
        assets = session.scalars(select(Entity).where(Entity.stock_id == stock.id))
        terms.extend(
            WatchTerm(e.name, stock.id, WEIGHT_ASSET)
            for e in assets
            if e.kind in ASSET_KINDS and len(e.name) >= MIN_TERM_CHARS
        )
    for entity in session.scalars(select(Entity).where(Entity.kind.in_(PARTNER_KINDS))):
        owner = _owner_stock_ids(session, entity)
        terms += [WatchTerm(core_name(entity.name), sid, WEIGHT_PARTNER) for sid in owner]
    return terms


def _owner_stock_ids(session: Session, entity: Entity) -> list[int]:
    ids: set[int] = set()
    for rel in session.scalars(
        select(Relation).where(
            (Relation.source_id == entity.id) | (Relation.target_id == entity.id)
        ),
    ):
        other = session.get(Entity, rel.target_id if rel.source_id == entity.id else rel.source_id)
        if other is not None and other.stock_id is not None:
            ids.add(other.stock_id)
    return sorted(ids)


def _occurs(term: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.I) is not None


def score_document(doc: Document, terms: list[WatchTerm]) -> dict[int, float]:
    """Relevance per stock id (only stocks with a positive score)."""
    scores: dict[int, float] = {}
    for term in terms:
        in_title = _occurs(term.term, doc.title)
        in_body = _occurs(term.term, doc.text[:5000])
        if in_title or in_body:
            gain = term.weight * (TITLE_FACTOR if in_title else 1.0)
            scores[term.stock_id] = scores.get(term.stock_id, 0.0) + gain
    return scores


def relevant_stocks(scores: dict[int, float]) -> list[int]:
    return [
        sid
        for sid, value in sorted(scores.items(), key=lambda kv: -kv[1])
        if value >= RELEVANCE_THRESHOLD
    ]


def queries_for(session: Session, stock: Stock) -> list[str]:
    """Search queries for feeds that need one (GDELT): company, then assets and partners."""
    name = core_name(stock.name)
    queries = (
        [f'"{name}"']
        if len(name) >= MIN_TERM_CHARS and not name.lower().startswith("demo ")
        else []
    )
    queries.extend(
        f'"{t.term}"'
        for t in watch_terms(session)
        if t.stock_id == stock.id and t.weight in (WEIGHT_ASSET, WEIGHT_PARTNER)
    )
    return queries[:MAX_QUERIES_PER_STOCK]
