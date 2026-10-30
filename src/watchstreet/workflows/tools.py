"""Tools the agent can call during an LLM workflow.

Division of labour: the harness computes everything deterministic up front (quote, scores,
holding P/L) and hands over a compact fact sheet. The agent pulls *details* on demand through
read tools and records its conclusions through write tools. Write tools only fill drafts; the
harness persists them after the run, and follow-ups still pass the guardrails, which are also
previewed to the model so it can correct itself immediately instead of wasting a ticket.
"""

import json
from typing import Any

from watchstreet.agents.tools import Tool, ToolError
from watchstreet.constants import (
    DEFAULT_INTERVAL,
    DEFAULT_NEWS_LIMIT,
    INTERVAL_RANGES,
    MAX_INSIGHTS_PER_TICKET,
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
from watchstreet.market.base import MarketDataError
from watchstreet.market.indicators import pct_change, rsi, sma
from watchstreet.workflows.base import (
    FollowUp,
    InsightDraft,
    ThesisDraft,
    WorkflowContext,
    WorkflowResult,
)

FOLLOWUP_WORKFLOWS = (
    WorkflowKey.TOPIC_ANALYSIS,
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

    # ---- write tools ------------------------------------------------------
    def _add_insight(self, args: dict[str, Any]) -> str:
        if len(self.insights) >= MAX_INSIGHTS_PER_TICKET:
            msg = f"insight limit ({MAX_INSIGHTS_PER_TICKET}) reached; summarise instead"
            raise ToolError(msg)
        category = _enum_arg(args, "category", InsightCategory)
        self.insights.append(InsightDraft(category, _text_arg(args, "text")))
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
                "add_insight",
                "Record one durable finding.",
                {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "enum": categories},
                        "text": text,
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

    def result(self, summary: str, data: dict[str, Any]) -> WorkflowResult:
        insights = list(self.insights)
        if self.goal:
            insights.insert(0, InsightDraft(InsightCategory.GOAL, self.goal))
        return WorkflowResult(
            summary=summary.strip() or "Analyse abgeschlossen (ohne Zusammenfassung).",
            insights=insights,
            thesis=self.thesis,
            followups=list(self.followups),
            data=data,
        )
