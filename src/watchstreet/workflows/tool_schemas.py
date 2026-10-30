"""JSON schemas of the agent tools: pure data, no behaviour.

The model sees these schemas; the handlers that implement the tools live in ``tools.py`` (stock
workflows) and ``doc_tools.py`` (document workflows). Keeping the declarations here makes the
tool *contract* reviewable on one screen.
"""

from collections.abc import Iterable
from typing import Any

from watchstreet.constants import (
    ASSET_KINDS,
    ENTITY_KINDS,
    INTEL_CATEGORIES,
    INTEL_DIRECTIONS,
    INTERVAL_RANGES,
    RELATION_KINDS,
)
from watchstreet.domain import InsightCategory, ThesisStatus, WorkflowKey
from watchstreet.profiles.registry import PANELS, PROFILES
from watchstreet.services.datapoints import CONFIDENCE

Schema = dict[str, Any]

# Workflows an agent may propose as follow-up tickets (checked again by the guardrails).
FOLLOWUP_WORKFLOWS = (
    WorkflowKey.TOPIC_ANALYSIS,
    WorkflowKey.RESEARCH_DATAPOINTS,
    WorkflowKey.THESIS_CHECK,
    WorkflowKey.VALUATION_SCORE,
    WorkflowKey.TECHNICAL_SNAPSHOT,
)

TEXT: Schema = {"type": "string"}
INTEGER: Schema = {"type": "integer"}
NUMBER: Schema = {"type": "number"}


def string_enum(values: Iterable[str]) -> Schema:
    """A string argument restricted to ``values``."""
    return {"type": "string", "enum": list(values)}


def object_schema(properties: Schema, required: list[str] | None = None) -> Schema:
    """A JSON-schema object; ``required`` is omitted when empty."""
    schema: Schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


NO_ARGS = object_schema({})

# ---- stock tools (workflows/tools.py) --------------------------------------
PRICE_SUMMARY = object_schema({"interval": string_enum(INTERVAL_RANGES)})
NEWS = object_schema({"limit": INTEGER})
RECORD_DATAPOINT = object_schema(
    {
        "key": TEXT,
        "subject": TEXT,
        "value": NUMBER,
        "text": TEXT,
        "unit": TEXT,
        "source": TEXT,
        "confidence": string_enum(CONFIDENCE),
        "document_id": INTEGER,
        "quote": TEXT,
    },
    ["key", "source", "confidence"],
)
SET_PROFILE = object_schema(
    {"profile": string_enum(PROFILES), "reason": TEXT},
    ["profile"],
)
ADD_INSIGHT = object_schema(
    {
        "category": string_enum(c.value for c in InsightCategory),
        "text": TEXT,
        "document_id": INTEGER,
        "quote": TEXT,
    },
    ["category", "text"],
)
SET_GOAL = object_schema({"text": TEXT}, ["text"])
SET_THESIS = object_schema(
    {"text": TEXT, "status": string_enum(s.value for s in ThesisStatus)},
    ["status"],
)
PROPOSE_FOLLOWUP = object_schema(
    {
        "workflow": string_enum(w.value for w in FOLLOWUP_WORKFLOWS),
        "topic": TEXT,
        "reason": TEXT,
    },
    ["workflow", "reason"],
)
SET_BRIEFING = object_schema(
    {
        "headline": TEXT,
        "bullets": {"type": "array", "items": TEXT},
        "focus": string_enum(PANELS),
    },
    ["headline", "bullets"],
)

# ---- filing tools (workflows/doc_tools.py: DocToolBox) ---------------------
SEARCH_DOCUMENT = object_schema({"query": TEXT}, ["query"])
READ_DOCUMENT = object_schema({"offset": INTEGER, "length": INTEGER}, ["offset"])
RECORD_RELATION = object_schema(
    {
        "from": TEXT,
        "from_kind": string_enum(ENTITY_KINDS),
        "to": TEXT,
        "to_kind": string_enum(ENTITY_KINDS),
        "relation": string_enum(RELATION_KINDS),
        "strength": NUMBER,
        "country": TEXT,
        "note": TEXT,
        "quote": TEXT,
    },
    ["from", "to", "relation", "quote"],
)
RECORD_ASSET = object_schema(
    {
        "name": TEXT,
        "kind": string_enum(ASSET_KINDS),
        "country": TEXT,
        "lat": NUMBER,
        "lon": NUMBER,
        "ownership": NUMBER,
        "quote": TEXT,
    },
    ["name", "quote"],
)

# ---- intel tools (workflows/doc_tools.py: IntelToolBox) --------------------
GET_DOCUMENT = object_schema({"document_id": INTEGER}, ["document_id"])
PUBLISH_INTEL = object_schema(
    {
        "document_id": INTEGER,
        "headline": TEXT,
        "summary": TEXT,
        "why_it_matters": TEXT,
        "quote": TEXT,
        "category": string_enum(INTEL_CATEGORIES),
        "severity": INTEGER,
        "direction": string_enum(INTEL_DIRECTIONS),
        "country": TEXT,
        "commodities": {"type": "array", "items": TEXT},
        "also_affects": {
            "type": "array",
            "items": object_schema({"symbol": TEXT, "direction": {"type": "string"}}),
        },
    },
    [
        "document_id",
        "headline",
        "why_it_matters",
        "quote",
        "category",
        "severity",
        "direction",
    ],
)
