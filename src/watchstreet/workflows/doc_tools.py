"""Toolboxes for document-grounded work: reading filings and cutting news to size.

Both enforce the provenance rule: a claim is only accepted together with a verbatim quote that
the harness finds in the stored document. What a model cannot quote, it cannot record.
"""

from typing import Any

from sqlalchemy import select

from watchstreet.agents.tools import Tool, ToolError
from watchstreet.constants import (
    ENTITY_KINDS,
    INTEL_CATEGORIES,
    INTEL_DIRECTIONS,
    MAX_INTEL_PER_TICKET,
    MAX_RELATIONS_PER_TICKET,
    READ_CHUNK_CHARS,
    RELATION_KINDS,
    SEVERITY_MAX,
    SEVERITY_MIN,
)
from watchstreet.intel import documents
from watchstreet.models import Document, Stock
from watchstreet.services.entities import ASSET_KINDS
from watchstreet.services.knowledge import SELF
from watchstreet.workflows.base import EntityDraft, IntelDraft, RelationDraft, WorkflowContext
from watchstreet.workflows.tools import ToolBox, _dump, _text_arg

TEXT = {"type": "string"}
GROUNDED = ("record_datapoint", "add_insight")
PREVIEW_CHARS = 1500


def _number(args: dict[str, Any], key: str) -> float | None:
    raw = args.get(key)
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        msg = f"'{key}' must be a number"
        raise ToolError(msg) from exc


class DocToolBox(ToolBox):
    """Tools bound to one stored document (a filing)."""

    def __init__(self, ctx: WorkflowContext, doc: Document) -> None:
        super().__init__(ctx)
        self.doc = doc

    def _grounding(self, args: dict[str, Any]) -> tuple[int | None, str]:
        return super()._grounding({**args, "document_id": args.get("document_id") or self.doc.id})

    def _list_sections(self, _args: dict[str, Any]) -> str:
        return _dump([{"offset": s.offset, "heading": s.text} for s in documents.outline(self.doc)])

    def _search(self, args: dict[str, Any]) -> str:
        hits = documents.search(self.doc, _text_arg(args, "query"))
        return _dump([{"offset": h.offset, "text": h.text} for h in hits])

    def _read(self, args: dict[str, Any]) -> str:
        offset = int(_number(args, "offset") or 0)
        return documents.read_chunk(
            self.doc, offset, int(_number(args, "length") or READ_CHUNK_CHARS)
        )

    def _entity(self, name: str, kind: str, country: str = "") -> EntityDraft:
        if kind not in ENTITY_KINDS:
            msg = f"kind must be one of: {', '.join(ENTITY_KINDS)}"
            raise ToolError(msg)
        return EntityDraft(SELF if name.strip().upper() == SELF else name.strip(), kind, country)

    def _record_relation(self, args: dict[str, Any]) -> str:
        if len(self.relations) >= MAX_RELATIONS_PER_TICKET:
            msg = f"relation limit ({MAX_RELATIONS_PER_TICKET}) reached"
            raise ToolError(msg)
        kind = str(args.get("relation", ""))
        if kind not in RELATION_KINDS:
            msg = f"'relation' must be one of: {', '.join(RELATION_KINDS)}"
            raise ToolError(msg)
        strength = _number(args, "strength")
        if strength is not None and not 0 <= strength <= 1:
            msg = "'strength' must be between 0 and 1 (share), or omitted if unknown"
            raise ToolError(msg)
        document_id, quote = self._grounding(args)
        source_name, target_name = _text_arg(args, "from"), _text_arg(args, "to")
        country = str(args.get("country", ""))  # belongs to the counterpart, never to SELF
        self.relations.append(
            RelationDraft(
                self._entity(
                    source_name,
                    str(args.get("from_kind", "supplier")),
                    "" if source_name.upper() == SELF else country,
                ),
                self._entity(
                    target_name,
                    str(args.get("to_kind", "company")),
                    "" if source_name.upper() != SELF else country,
                ),
                kind,
                strength,
                str(args.get("note", "")),
                document_id,
                quote,
                "medium",
            ),
        )
        return "recorded"

    def _record_asset(self, args: dict[str, Any]) -> str:
        kind = str(args.get("kind", "mine"))
        if kind not in ASSET_KINDS:
            msg = f"'kind' must be one of: {', '.join(ASSET_KINDS)}"
            raise ToolError(msg)
        document_id, quote = self._grounding(args)
        lat, lon = _number(args, "lat"), _number(args, "lon")
        asset = EntityDraft(
            _text_arg(args, "name"),
            kind,
            str(args.get("country", "")),
            lat if lon is not None else None,
            lon if lat is not None else None,
        )
        self.relations.append(
            RelationDraft(
                EntityDraft(SELF, "company"),
                asset,
                "owns",
                _number(args, "ownership") or 1.0,
                "",
                document_id,
                quote,
                "medium",
            ),
        )
        return "recorded"

    def tools(self) -> list[Tool]:
        base = {t.name: t for t in super().tools()}
        extra = [
            Tool(
                "list_sections",
                "Headings (Item 1A, Item 2, ...) with character offsets.",
                {"type": "object", "properties": {}},
                self._list_sections,
            ),
            Tool(
                "search_document",
                "Search the filing; returns snippets with offsets.",
                {"type": "object", "properties": {"query": TEXT}, "required": ["query"]},
                self._search,
            ),
            Tool(
                "read_document",
                f"Read up to {READ_CHUNK_CHARS} characters from an offset.",
                {
                    "type": "object",
                    "properties": {"offset": {"type": "integer"}, "length": {"type": "integer"}},
                    "required": ["offset"],
                },
                self._read,
            ),
            Tool(
                "record_relation",
                "Record a dependency (supplier, customer, location ...). A verbatim quote from "
                "the filing is required; use from='SELF' for the filing company.",
                {
                    "type": "object",
                    "properties": {
                        "from": TEXT,
                        "from_kind": {"type": "string", "enum": list(ENTITY_KINDS)},
                        "to": TEXT,
                        "to_kind": {"type": "string", "enum": list(ENTITY_KINDS)},
                        "relation": {"type": "string", "enum": list(RELATION_KINDS)},
                        "strength": {"type": "number"},
                        "country": TEXT,
                        "note": TEXT,
                        "quote": TEXT,
                    },
                    "required": ["from", "to", "relation", "quote"],
                },
                self._record_relation,
            ),
            Tool(
                "record_asset",
                "Record an owned mine/facility/port with country and (if stated) coordinates "
                "and ownership share. Quote required.",
                {
                    "type": "object",
                    "properties": {
                        "name": TEXT,
                        "kind": {"type": "string", "enum": list(ASSET_KINDS)},
                        "country": TEXT,
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "ownership": {"type": "number"},
                        "quote": TEXT,
                    },
                    "required": ["name", "quote"],
                },
                self._record_asset,
            ),
        ]
        return [*extra, *(base[n] for n in GROUNDED)]


class IntelToolBox(ToolBox):
    """Tools for cutting a batch of stored sources down to what matters for one stock."""

    def __init__(self, ctx: WorkflowContext, allowed: list[int]) -> None:
        super().__init__(ctx)
        self._allowed = set(allowed)

    def _get_document(self, args: dict[str, Any]) -> str:
        doc = self._doc(args)
        return _dump(
            {
                "id": doc.id,
                "title": doc.title,
                "publisher": doc.publisher,
                "kind": doc.kind,
                "url": doc.url,
                "text": doc.text[:PREVIEW_CHARS],
            }
        )

    def _doc(self, args: dict[str, Any]) -> Document:
        doc_id = int(_number(args, "document_id") or 0)
        if doc_id not in self._allowed:
            msg = f"document_id must be one of {sorted(self._allowed)}"
            raise ToolError(msg)
        doc = self._ctx.session.get(Document, doc_id)
        if doc is None:
            msg = "unknown document"
            raise ToolError(msg)
        return doc

    def _publish(self, args: dict[str, Any]) -> str:
        if len(self.intel) >= MAX_INTEL_PER_TICKET:
            msg = f"intel limit ({MAX_INTEL_PER_TICKET}) reached"
            raise ToolError(msg)
        doc = self._doc(args)
        document_id, quote = self._grounding({**args, "document_id": doc.id})
        category = str(args.get("category", "company"))
        direction = str(args.get("direction", "unknown"))
        if category not in INTEL_CATEGORIES or direction not in INTEL_DIRECTIONS:
            msg = f"category in {INTEL_CATEGORIES}, direction in {INTEL_DIRECTIONS}"
            raise ToolError(msg)
        severity = int(_number(args, "severity") or SEVERITY_MIN)
        if not SEVERITY_MIN <= severity <= SEVERITY_MAX:
            msg = f"severity must be {SEVERITY_MIN}..{SEVERITY_MAX}"
            raise ToolError(msg)
        impacts = [(self._ctx.stock.id, direction, str(args.get("why_it_matters", "")))]
        for other in args.get("also_affects", []) or []:
            stock = self._ctx.session.scalar(
                select(Stock).where(Stock.symbol == str(other.get("symbol", "")).upper()),
            )
            if stock is not None and stock.id != self._ctx.stock.id:
                impacts.append((stock.id, str(other.get("direction", "unknown")), ""))
        self.intel.append(
            IntelDraft(
                headline=_text_arg(args, "headline"),
                category=category,
                severity=severity,
                summary=str(args.get("summary", "")),
                why_it_matters=str(args.get("why_it_matters", "")),
                document_id=document_id,
                quote=quote,
                country=str(args.get("country", "")),
                commodities=tuple(str(c) for c in args.get("commodities", []) or []),
                impacts=tuple(impacts),
            ),
        )
        return "published"

    def tools(self) -> list[Tool]:
        base = {t.name: t for t in super().tools()}
        return [
            Tool(
                "get_document",
                "Metadata and the beginning of a source document.",
                {
                    "type": "object",
                    "properties": {"document_id": {"type": "integer"}},
                    "required": ["document_id"],
                },
                self._get_document,
            ),
            base["get_knowledge"],
            Tool(
                "publish_intel",
                "Publish one intel item for a relevant source. 'quote' must be copied verbatim "
                "from that document; summary and why_it_matters must stay within what it says.",
                {
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "integer"},
                        "headline": TEXT,
                        "summary": TEXT,
                        "why_it_matters": TEXT,
                        "quote": TEXT,
                        "category": {"type": "string", "enum": list(INTEL_CATEGORIES)},
                        "severity": {"type": "integer"},
                        "direction": {"type": "string", "enum": list(INTEL_DIRECTIONS)},
                        "country": TEXT,
                        "commodities": {"type": "array", "items": TEXT},
                        "also_affects": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"symbol": TEXT, "direction": {"type": "string"}},
                            },
                        },
                    },
                    "required": [
                        "document_id",
                        "headline",
                        "why_it_matters",
                        "quote",
                        "category",
                        "severity",
                        "direction",
                    ],
                },
                self._publish,
            ),
        ]
