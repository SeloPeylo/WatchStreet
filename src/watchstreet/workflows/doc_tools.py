"""Toolboxes for document-grounded work: reading filings and cutting news to size.

Both enforce the provenance rule: a claim is only accepted together with a verbatim quote that
the harness finds in the stored document. What a model cannot quote, it cannot record.
Their JSON schemas live in ``tool_schemas.py``.
"""

from typing import Any

from sqlalchemy import select

from watchstreet.agents.tools import Tool, ToolError
from watchstreet.constants import (
    ASSET_KINDS,
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
from watchstreet.drafts import EntityDraft, IntelDraft, RelationDraft
from watchstreet.intel import documents
from watchstreet.models import Document, Stock
from watchstreet.services.knowledge import SELF
from watchstreet.workflows import tool_schemas
from watchstreet.workflows.base import WorkflowContext
from watchstreet.workflows.tool_args import choice_arg, int_arg, number_arg, text_arg, to_json
from watchstreet.workflows.tools import RECORDED, ToolBox

# The two tools of the base ToolBox that stay available when reading a filing.
GROUNDED = ("record_datapoint", "add_insight")
PREVIEW_CHARS = 1500
DEFAULT_OWNERSHIP = 1.0  # an owned asset without a stated share counts as fully owned


def _entity_draft(name: str, kind: str, country: str = "") -> EntityDraft:
    """Validate an entity kind; the filing company is always written as ``SELF``."""
    if kind not in ENTITY_KINDS:
        msg = f"kind must be one of: {', '.join(ENTITY_KINDS)}"
        raise ToolError(msg)
    name = name.strip()
    return EntityDraft(SELF if name.upper() == SELF else name, kind, country)


def _relation_endpoints(args: dict[str, Any]) -> tuple[EntityDraft, EntityDraft]:
    """Source and target of a relation; the country belongs to the counterpart, never to SELF."""
    source_name, target_name = text_arg(args, "from"), text_arg(args, "to")
    country = str(args.get("country", ""))
    source_is_self = source_name.upper() == SELF
    source = _entity_draft(
        source_name,
        str(args.get("from_kind", "supplier")),
        "" if source_is_self else country,
    )
    target = _entity_draft(
        target_name,
        str(args.get("to_kind", "company")),
        country if source_is_self else "",
    )
    return source, target


class DocToolBox(ToolBox):
    """Tools bound to one stored document (a filing)."""

    def __init__(self, ctx: WorkflowContext, doc: Document) -> None:
        super().__init__(ctx)
        self.doc = doc

    def _grounding(self, args: dict[str, Any]) -> tuple[int | None, str]:
        """Quotes are checked against the filing being read unless another document is named."""
        return super()._grounding({**args, "document_id": args.get("document_id") or self.doc.id})

    def _list_sections(self, _args: dict[str, Any]) -> str:
        sections = documents.outline(self.doc)
        return to_json([{"offset": s.offset, "heading": s.text} for s in sections])

    def _search(self, args: dict[str, Any]) -> str:
        hits = documents.search(self.doc, text_arg(args, "query"))
        return to_json([{"offset": hit.offset, "text": hit.text} for hit in hits])

    def _read(self, args: dict[str, Any]) -> str:
        offset = int_arg(args, "offset")
        length = int_arg(args, "length", READ_CHUNK_CHARS)
        return documents.read_chunk(self.doc, offset, length)

    def _record_relation(self, args: dict[str, Any]) -> str:
        if len(self.relations) >= MAX_RELATIONS_PER_TICKET:
            msg = f"relation limit ({MAX_RELATIONS_PER_TICKET}) reached"
            raise ToolError(msg)
        kind = choice_arg(args, "relation", RELATION_KINDS)
        strength = number_arg(args, "strength")
        if strength is not None and not 0 <= strength <= 1:
            msg = "'strength' must be between 0 and 1 (share), or omitted if unknown"
            raise ToolError(msg)
        document_id, quote = self._grounding(args)
        source, target = _relation_endpoints(args)
        note = str(args.get("note", ""))
        self.relations.append(
            RelationDraft(source, target, kind, strength, note, document_id, quote, "medium"),
        )
        return RECORDED

    def _record_asset(self, args: dict[str, Any]) -> str:
        kind = choice_arg({"kind": args.get("kind", "mine")}, "kind", ASSET_KINDS)
        document_id, quote = self._grounding(args)
        lat, lon = number_arg(args, "lat"), number_arg(args, "lon")
        asset = EntityDraft(
            text_arg(args, "name"),
            kind,
            str(args.get("country", "")),
            lat if lon is not None else None,  # coordinates only count as a pair
            lon if lat is not None else None,
        )
        ownership = number_arg(args, "ownership") or DEFAULT_OWNERSHIP
        self.relations.append(
            RelationDraft(
                EntityDraft(SELF, "company"),
                asset,
                "owns",
                ownership,
                "",
                document_id,
                quote,
                "medium",
            ),
        )
        return RECORDED

    def tools(self) -> list[Tool]:
        base = {tool.name: tool for tool in super().tools()}
        filing_tools = [
            Tool(
                "list_sections",
                "Headings (Item 1A, Item 2, ...) with character offsets.",
                tool_schemas.NO_ARGS,
                self._list_sections,
            ),
            Tool(
                "search_document",
                "Search the filing; returns snippets with offsets.",
                tool_schemas.SEARCH_DOCUMENT,
                self._search,
            ),
            Tool(
                "read_document",
                f"Read up to {READ_CHUNK_CHARS} characters from an offset.",
                tool_schemas.READ_DOCUMENT,
                self._read,
            ),
            Tool(
                "record_relation",
                "Record a dependency (supplier, customer, location ...). A verbatim quote from "
                "the filing is required; use from='SELF' for the filing company.",
                tool_schemas.RECORD_RELATION,
                self._record_relation,
            ),
            Tool(
                "record_asset",
                "Record an owned mine/facility/port with country and (if stated) coordinates "
                "and ownership share. Quote required.",
                tool_schemas.RECORD_ASSET,
                self._record_asset,
            ),
        ]
        return [*filing_tools, *(base[name] for name in GROUNDED)]


class IntelToolBox(ToolBox):
    """Tools for cutting a batch of stored sources down to what matters for one stock."""

    def __init__(self, ctx: WorkflowContext, allowed: list[int]) -> None:
        super().__init__(ctx)
        self._allowed = set(allowed)

    def _get_document(self, args: dict[str, Any]) -> str:
        doc = self._allowed_document(args)
        return to_json(
            {
                "id": doc.id,
                "title": doc.title,
                "publisher": doc.publisher,
                "kind": doc.kind,
                "url": doc.url,
                "text": doc.text[:PREVIEW_CHARS],
            },
        )

    def _allowed_document(self, args: dict[str, Any]) -> Document:
        """The document named by ``document_id``, if it belongs to this ticket's batch."""
        doc_id = int_arg(args, "document_id")
        if doc_id not in self._allowed:
            msg = f"document_id must be one of {sorted(self._allowed)}"
            raise ToolError(msg)
        doc = self._ctx.session.get(Document, doc_id)
        if doc is None:
            msg = "unknown document"
            raise ToolError(msg)
        return doc

    def _impacts(self, args: dict[str, Any], direction: str) -> tuple[tuple[int, str, str], ...]:
        """(stock_id, direction, why) for this stock plus other known stocks the agent names."""
        own_id = self._ctx.stock.id
        impacts = [(own_id, direction, str(args.get("why_it_matters", "")))]
        for other in args.get("also_affects", []) or []:
            symbol = str(other.get("symbol", "")).upper()
            stock = self._ctx.session.scalar(select(Stock).where(Stock.symbol == symbol))
            if stock is not None and stock.id != own_id:
                impacts.append((stock.id, str(other.get("direction", "unknown")), ""))
        return tuple(impacts)

    def _publish(self, args: dict[str, Any]) -> str:
        if len(self.intel) >= MAX_INTEL_PER_TICKET:
            msg = f"intel limit ({MAX_INTEL_PER_TICKET}) reached"
            raise ToolError(msg)
        doc = self._allowed_document(args)
        document_id, quote = self._grounding({**args, "document_id": doc.id})
        category = str(args.get("category", "company"))
        direction = str(args.get("direction", "unknown"))
        if category not in INTEL_CATEGORIES or direction not in INTEL_DIRECTIONS:
            msg = f"category in {INTEL_CATEGORIES}, direction in {INTEL_DIRECTIONS}"
            raise ToolError(msg)
        severity = int_arg(args, "severity", SEVERITY_MIN)
        if not SEVERITY_MIN <= severity <= SEVERITY_MAX:
            msg = f"severity must be {SEVERITY_MIN}..{SEVERITY_MAX}"
            raise ToolError(msg)
        self.intel.append(
            IntelDraft(
                headline=text_arg(args, "headline"),
                category=category,
                severity=severity,
                summary=str(args.get("summary", "")),
                why_it_matters=str(args.get("why_it_matters", "")),
                document_id=document_id,
                quote=quote,
                country=str(args.get("country", "")),
                commodities=tuple(str(c) for c in args.get("commodities", []) or []),
                impacts=self._impacts(args, direction),
            ),
        )
        return "published"

    def tools(self) -> list[Tool]:
        base = {tool.name: tool for tool in super().tools()}
        return [
            Tool(
                "get_document",
                "Metadata and the beginning of a source document.",
                tool_schemas.GET_DOCUMENT,
                self._get_document,
            ),
            base["get_knowledge"],
            Tool(
                "publish_intel",
                "Publish one intel item for a relevant source. 'quote' must be copied verbatim "
                "from that document; summary and why_it_matters must stay within what it says.",
                tool_schemas.PUBLISH_INTEL,
                self._publish,
            ),
        ]
