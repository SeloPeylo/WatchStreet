"""Tools the agent can call during an LLM workflow.

Division of labour: the harness computes everything deterministic up front (quote, scores,
holding P/L) and hands over a compact fact sheet. The agent pulls *details* on demand through
read tools and records its conclusions through write tools. Write tools only fill drafts; the
harness persists them after the run, and follow-ups still pass the guardrails, which are also
previewed to the model so it can correct itself immediately instead of wasting a ticket.
"""

import json
from dataclasses import asdict
from typing import Any

from watchstreet.agents.tools import Tool, ToolError
from watchstreet.constants import (
    DEFAULT_INTERVAL,
    DEFAULT_NEWS_LIMIT,
    INTERVAL_RANGES,
    MAX_BRIEFING_BULLETS,
    MAX_DATAPOINTS_PER_TICKET,
    MAX_INSIGHTS_PER_TICKET,
    MIN_QUOTE_CHARS,
    MOMENTUM_BARS,
    PRICE_SUMMARY_TAIL_BARS,
    RECENT_LIMIT,
    RSI_PERIOD,
    SCORE_HISTORY_LIMIT,
    SMA_FAST,
    SMA_SLOW,
    THESIS_PREVIEW_CHARS,
)
from watchstreet.domain import InsightCategory, ThesisStatus, WorkflowKey
from watchstreet.intel.documents import verify_quote
from watchstreet.market.base import MarketDataError
from watchstreet.market.indicators import pct_change, rsi, sma
from watchstreet.models import Document
from watchstreet.profiles.registry import PANELS, PROFILES, get_profile
from watchstreet.services.datapoints import (
    CONFIDENCE,
    DatapointError,
    DatapointInput,
    is_user_protected,
    validate,
)
from watchstreet.workflows.base import (
    BriefingDraft,
    DatapointDraft,
    FollowUp,
    InsightDraft,
    IntelDraft,
    ProfileDraft,
    RelationDraft,
    ThesisDraft,
    WorkflowContext,
    WorkflowResult,
)

FOLLOWUP_WORKFLOWS = (
    WorkflowKey.TOPIC_ANALYSIS,
    WorkflowKey.RESEARCH_DATAPOINTS,
    WorkflowKey.THESIS_CHECK,
    WorkflowKey.VALUATION_SCORE,
    WorkflowKey.TECHNICAL_SNAPSHOT,
)
NO_ARGS: dict[str, Any] = {"type": "object", "properties": {}}


def _enum_arg(
    args: dict[str, Any], key: str, enum: type[InsightCategory] | type[ThesisStatus]
) -> Any:
    try:
        return enum(str(args.get(key)))
    except ValueError as exc:
        allowed = ", ".join(e.value for e in enum)
        msg = f"'{key}' must be one of: {allowed}"
        raise ToolError(msg) from exc


def _text_arg(args: dict[str, Any], key: str) -> str:
    value = str(args.get(key, "")).strip()
    if not value:
        msg = f"'{key}' is required"
        raise ToolError(msg)
    return value


def _dump(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, default=str, separators=(",", ":"))


class ToolBox:
    """Tool set bound to one ticket run; collects the agent's conclusions as drafts."""

    def __init__(self, ctx: WorkflowContext) -> None:
        self._ctx = ctx
        self.insights: list[InsightDraft] = []
        self.goal: str | None = None
        self.thesis: ThesisDraft | None = None
        self.followups: list[FollowUp] = []
        self.datapoints: list[DatapointDraft] = []
        self.relations: list[RelationDraft] = []
        self.intel: list[IntelDraft] = []
        self.profile: ProfileDraft | None = None
        self.briefing: BriefingDraft | None = None

    # ---- read tools -------------------------------------------------------
    def _price_summary(self, args: dict[str, Any]) -> str:
        interval = str(args.get("interval") or DEFAULT_INTERVAL)
        if interval not in INTERVAL_RANGES:
            msg = f"interval must be one of: {', '.join(INTERVAL_RANGES)}"
            raise ToolError(msg)
        try:
            candles = self._ctx.market.candles(self._ctx.stock.symbol, interval)
        except MarketDataError as exc:
            raise ToolError(str(exc)) from exc
        closes = [c.close for c in candles]
        return _dump(
            {
                "interval": interval,
                "bars": len(closes),
                "high": max(c.high for c in candles),
                "low": min(c.low for c in candles),
                f"sma{SMA_FAST}": sma(closes, SMA_FAST),
                f"sma{SMA_SLOW}": sma(closes, SMA_SLOW),
                f"rsi{RSI_PERIOD}": rsi(closes),
                f"change_{MOMENTUM_BARS}_bars_pct": pct_change(closes, MOMENTUM_BARS),
                "last_closes": [round(c, 2) for c in closes[-PRICE_SUMMARY_TAIL_BARS:]],
            },
        )

    def _fundamentals(self, _args: dict[str, Any]) -> str:
        try:
            return _dump(self._ctx.market.fundamentals(self._ctx.stock.symbol).values)
        except MarketDataError as exc:
            raise ToolError(str(exc)) from exc

    def _news(self, args: dict[str, Any]) -> str:
        limit = int(args.get("limit") or DEFAULT_NEWS_LIMIT)
        events = self._ctx.stock.events[:limit]
        return _dump([{"date": f"{e.published_at:%Y-%m-%d}", "title": e.title} for e in events])

    def _knowledge(self, _args: dict[str, Any]) -> str:
        stock = self._ctx.stock
        history: dict[str, list[float]] = {}
        for score in reversed(stock.scores):
            history.setdefault(score.scheme, []).append(score.value)
        return _dump(
            {
                "theses": [
                    {
                        "status": t.status,
                        "date": f"{t.created_at:%Y-%m-%d}",
                        "text": t.text[:THESIS_PREVIEW_CHARS],
                    }
                    for t in stock.theses[:RECENT_LIMIT]
                ],
                "score_history": {k: v[-SCORE_HISTORY_LIMIT:] for k, v in history.items()},
                "insights": [
                    {"category": i.category, "text": i.text} for i in stock.insights[:RECENT_LIMIT]
                ],
            },
        )

    def _datapoint_specs(self, _args: dict[str, Any]) -> str:
        profile = get_profile(self._ctx.stock.profile)
        have = {(d.key, d.subject) for d in self._ctx.stock.datapoints}
        return _dump(
            {
                "profile": profile.key,
                "subject_label": profile.subject_label,
                "specs": [
                    {
                        "key": d.key,
                        "label": d.label,
                        "unit": d.unit,
                        "hint": d.hint,
                        "required": d.required,
                        "per_subject": d.per_subject,
                        "textual": d.textual,
                        "recorded": any(k == d.key for k, _s in have),
                    }
                    for d in profile.datapoints
                ],
            },
        )

    # ---- write tools ------------------------------------------------------
    def _record_datapoint(self, args: dict[str, Any]) -> str:
        if len(self.datapoints) >= MAX_DATAPOINTS_PER_TICKET:
            msg = f"datapoint limit ({MAX_DATAPOINTS_PER_TICKET}) reached"
            raise ToolError(msg)
        raw = args.get("value")
        try:
            value = float(raw) if raw is not None and raw != "" else None
        except (TypeError, ValueError) as exc:
            msg = "'value' must be a number"
            raise ToolError(msg) from exc
        document_id, quote = self._grounding(args)
        entry = DatapointInput(
            key=str(args.get("key", "")),
            subject=str(args.get("subject", "")).strip(),
            value=value,
            text=str(args.get("text", "")),
            unit=str(args.get("unit", "")),
            source=str(args.get("source", "")),
            confidence=str(args.get("confidence", "medium")),
            document_id=document_id,
            quote=quote,
        )
        try:
            validate(self._ctx.stock, entry)
        except DatapointError as exc:
            raise ToolError(str(exc)) from exc
        draft = DatapointDraft(**asdict(entry))
        if is_user_protected(self._ctx.stock, draft.key, draft.subject):
            msg = "protected: the user entered this value; do not overwrite"
            raise ToolError(msg)
        self.datapoints.append(draft)
        return "recorded"

    def _set_profile(self, args: dict[str, Any]) -> str:
        key = str(args.get("profile", ""))
        if key not in PROFILES:
            msg = f"'profile' must be one of: {', '.join(PROFILES)}"
            raise ToolError(msg)
        if self._ctx.stock.profile_source == "user":
            msg = "the user fixed the profile; do not change it"
            raise ToolError(msg)
        self.profile = ProfileDraft(key, str(args.get("reason", "")))
        return "recorded"

    def _set_briefing(self, args: dict[str, Any]) -> str:
        bullets = [str(b).strip() for b in args.get("bullets", []) if str(b).strip()]
        focus = str(args.get("focus", ""))
        if focus and focus not in PANELS:
            msg = f"'focus' must be one of: {', '.join(PANELS)}"
            raise ToolError(msg)
        self.briefing = BriefingDraft(
            _text_arg(args, "headline"),
            bullets[:MAX_BRIEFING_BULLETS],
            focus,
            "agent",
        )
        return "recorded"

    def _grounding(self, args: dict[str, Any]) -> tuple[int | None, str]:
        """Validate an optional document reference: the quote must occur verbatim in it."""
        raw = args.get("document_id")
        if raw in (None, ""):
            return None, ""
        try:
            doc = self._ctx.session.get(Document, int(raw))
        except (TypeError, ValueError) as exc:
            msg = "'document_id' must be an integer"
            raise ToolError(msg) from exc
        if doc is None:
            msg = f"unknown document_id {raw}"
            raise ToolError(msg)
        quote = str(args.get("quote", ""))
        if not verify_quote(doc, quote):
            msg = (
                "quote not found verbatim in the document (copy at least "
                f"{MIN_QUOTE_CHARS} characters exactly, e.g. via search_document/read_document)"
            )
            raise ToolError(msg)
        return doc.id, quote

    def _add_insight(self, args: dict[str, Any]) -> str:
        if len(self.insights) >= MAX_INSIGHTS_PER_TICKET:
            msg = f"insight limit ({MAX_INSIGHTS_PER_TICKET}) reached; summarise instead"
            raise ToolError(msg)
        category = _enum_arg(args, "category", InsightCategory)
        document_id, _quote = self._grounding(args)
        self.insights.append(InsightDraft(category, _text_arg(args, "text"), document_id))
        return "recorded"

    def _set_goal(self, args: dict[str, Any]) -> str:
        self.goal = _text_arg(args, "text")
        return "recorded"

    def _set_thesis(self, args: dict[str, Any]) -> str:
        status = _enum_arg(args, "status", ThesisStatus)
        text = args.get("text") or (
            self._ctx.stock.theses[0].text if self._ctx.stock.theses else ""
        )
        if not str(text).strip():
            msg = "'text' is required when no thesis exists yet"
            raise ToolError(msg)
        self.thesis = ThesisDraft(str(text).strip(), status)
        return "recorded"

    def _propose_followup(self, args: dict[str, Any]) -> str:
        proposal = FollowUp(
            str(args.get("workflow", "")),
            str(args.get("topic", "")).strip(),
            str(args.get("reason", "")).strip(),
        )
        reason = self._followup_rejection(proposal)
        if reason:
            msg = f"rejected by guardrails: {reason}"
            raise ToolError(msg)
        self.followups.append(proposal)
        return "accepted; the ticket is created after this run"

    def _followup_rejection(self, proposal: FollowUp) -> str | None:
        if proposal.workflow not in FOLLOWUP_WORKFLOWS:
            return f"workflow must be one of: {', '.join(FOLLOWUP_WORKFLOWS)}"
        key = (proposal.workflow, proposal.topic.casefold())
        if any((f.workflow, f.topic.casefold()) == key for f in self.followups):
            return "duplicate"
        check = self._ctx.followup_check
        return check(proposal, len(self.followups)) if check else None

    # ---- assembly ---------------------------------------------------------
    def tools(self) -> list[Tool]:
        categories = [c.value for c in InsightCategory]
        statuses = [s.value for s in ThesisStatus]
        text = {"type": "string"}
        return [
            Tool(
                "get_price_summary",
                "Compact price statistics (high/low, SMA, RSI, momentum, last closes).",
                {
                    "type": "object",
                    "properties": {"interval": {"type": "string", "enum": list(INTERVAL_RANGES)}},
                },
                self._price_summary,
            ),
            Tool(
                "get_fundamentals",
                "Key figures (P/E, P/B, margins, growth, ...).",
                NO_ARGS,
                self._fundamentals,
            ),
            Tool(
                "get_news",
                "Recent stored headlines for this stock.",
                {"type": "object", "properties": {"limit": {"type": "integer"}}},
                self._news,
            ),
            Tool(
                "get_knowledge",
                "Earlier theses, score history and insights.",
                NO_ARGS,
                self._knowledge,
            ),
            Tool(
                "get_datapoint_specs",
                "Inputs the stock's valuation profile needs and which are already recorded.",
                NO_ARGS,
                self._datapoint_specs,
            ),
            Tool(
                "record_datapoint",
                "Record a sourced input (e.g. a mine's AISC). Give a source and honest "
                "confidence; never guess. Per-subject keys need 'subject'.",
                {
                    "type": "object",
                    "properties": {
                        "key": text,
                        "subject": text,
                        "value": {"type": "number"},
                        "text": text,
                        "unit": text,
                        "source": text,
                        "confidence": {"type": "string", "enum": list(CONFIDENCE)},
                        "document_id": {"type": "integer"},
                        "quote": text,
                    },
                    "required": ["key", "source", "confidence"],
                },
                self._record_datapoint,
            ),
            Tool(
                "set_profile",
                "Set the valuation profile (stock type) if the current one is wrong.",
                {
                    "type": "object",
                    "properties": {
                        "profile": {"type": "string", "enum": list(PROFILES)},
                        "reason": text,
                    },
                    "required": ["profile"],
                },
                self._set_profile,
            ),
            Tool(
                "add_insight",
                "Record one durable finding. With document_id + a verbatim quote it becomes "
                "a cited, verified finding.",
                {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "enum": categories},
                        "text": text,
                        "document_id": {"type": "integer"},
                        "quote": text,
                    },
                    "required": ["category", "text"],
                },
                self._add_insight,
            ),
            Tool(
                "set_goal",
                "Set the goal for this stock.",
                {"type": "object", "properties": {"text": text}, "required": ["text"]},
                self._set_goal,
            ),
            Tool(
                "set_thesis",
                "Write a new thesis version or re-rate the current one.",
                {
                    "type": "object",
                    "properties": {"text": text, "status": {"type": "string", "enum": statuses}},
                    "required": ["status"],
                },
                self._set_thesis,
            ),
            Tool(
                "propose_followup",
                "Propose a follow-up ticket. Guardrails apply and answer immediately.",
                {
                    "type": "object",
                    "properties": {
                        "workflow": {
                            "type": "string",
                            "enum": [w.value for w in FOLLOWUP_WORKFLOWS],
                        },
                        "topic": text,
                        "reason": text,
                    },
                    "required": ["workflow", "reason"],
                },
                self._propose_followup,
            ),
        ]

    def briefing_tool(self) -> Tool:
        text = {"type": "string"}
        return Tool(
            "set_briefing",
            "Write the stock's briefing: a headline, a few bullets, the panel to open first.",
            {
                "type": "object",
                "properties": {
                    "headline": text,
                    "bullets": {"type": "array", "items": text},
                    "focus": {"type": "string", "enum": list(PANELS)},
                },
                "required": ["headline", "bullets"],
            },
            self._set_briefing,
        )

    def result(self, summary: str, data: dict[str, Any]) -> WorkflowResult:
        insights = list(self.insights)
        if self.goal:
            insights.insert(0, InsightDraft(InsightCategory.GOAL, self.goal))
        return WorkflowResult(
            summary=summary.strip() or "Analyse abgeschlossen (ohne Zusammenfassung).",
            insights=insights,
            thesis=self.thesis,
            followups=list(self.followups),
            datapoints=list(self.datapoints),
            relations=list(self.relations),
            intel=list(self.intel),
            profile=self.profile,
            briefing=self.briefing,
            data=data,
        )
