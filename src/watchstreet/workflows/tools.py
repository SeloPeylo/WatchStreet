"""Tool handlers for LLM workflows on one stock.

Division of labour: the harness computes everything deterministic up front (quote, scores,
holding P/L) and hands over a compact fact sheet. The agent pulls *details* on demand through
read tools and records its conclusions through write tools. Write tools only fill drafts; the
harness persists them after the run, and follow-ups still pass the guardrails, which are also
previewed to the model so it can correct itself immediately instead of wasting a ticket.

Layout: schemas are in ``tool_schemas.py``, argument parsing in ``tool_args.py`` and the read
payloads in ``tool_payloads.py``; this module wires them to the run's drafts.
"""

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
)
from watchstreet.domain import DataOrigin, InsightCategory, ProfileSource, ThesisStatus
from watchstreet.drafts import (
    BriefingDraft,
    DatapointDraft,
    FollowUp,
    InsightDraft,
    IntelDraft,
    ProfileDraft,
    RelationDraft,
    ThesisDraft,
    WorkflowResult,
)
from watchstreet.intel.documents import verify_quote
from watchstreet.market.base import MarketDataError
from watchstreet.models import Document
from watchstreet.profiles.registry import PANELS, PROFILES, get_profile
from watchstreet.services.datapoints import (
    DatapointError,
    DatapointInput,
    is_user_protected,
    validate,
)
from watchstreet.workflows import tool_payloads, tool_schemas
from watchstreet.workflows.base import WorkflowContext
from watchstreet.workflows.tool_args import (
    choice_arg,
    enum_arg,
    int_arg,
    number_arg,
    text_arg,
    to_json,
)
from watchstreet.workflows.tool_schemas import FOLLOWUP_WORKFLOWS

RECORDED = "recorded"


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
        return to_json(tool_payloads.price_summary(candles, interval))

    def _fundamentals(self, _args: dict[str, Any]) -> str:
        try:
            return to_json(self._ctx.market.fundamentals(self._ctx.stock.symbol).values)
        except MarketDataError as exc:
            raise ToolError(str(exc)) from exc

    def _news(self, args: dict[str, Any]) -> str:
        limit = int_arg(args, "limit", DEFAULT_NEWS_LIMIT)
        return to_json(tool_payloads.news_headlines(self._ctx.stock.events[:limit]))

    def _knowledge(self, _args: dict[str, Any]) -> str:
        return to_json(tool_payloads.knowledge_summary(self._ctx.stock))

    def _datapoint_specs(self, _args: dict[str, Any]) -> str:
        stock = self._ctx.stock
        return to_json(tool_payloads.datapoint_specs(stock, get_profile(stock.profile)))

    # ---- write tools: evidence --------------------------------------------
    def _record_datapoint(self, args: dict[str, Any]) -> str:
        if len(self.datapoints) >= MAX_DATAPOINTS_PER_TICKET:
            msg = f"datapoint limit ({MAX_DATAPOINTS_PER_TICKET}) reached"
            raise ToolError(msg)
        value = number_arg(args, "value")
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
        return RECORDED

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
        category = enum_arg(args, "category", InsightCategory)
        document_id, _quote = self._grounding(args)
        self.insights.append(InsightDraft(category, text_arg(args, "text"), document_id))
        return RECORDED

    # ---- write tools: conclusions -----------------------------------------
    def _set_profile(self, args: dict[str, Any]) -> str:
        key = choice_arg(args, "profile", list(PROFILES))
        if self._ctx.stock.profile_source == ProfileSource.USER:
            msg = "the user fixed the profile; do not change it"
            raise ToolError(msg)
        self.profile = ProfileDraft(key, str(args.get("reason", "")))
        return RECORDED

    def _set_briefing(self, args: dict[str, Any]) -> str:
        bullets = [str(b).strip() for b in args.get("bullets", []) if str(b).strip()]
        focus = str(args.get("focus", ""))
        if focus:
            choice_arg(args, "focus", list(PANELS))
        self.briefing = BriefingDraft(
            text_arg(args, "headline"),
            bullets[:MAX_BRIEFING_BULLETS],
            focus,
            DataOrigin.AGENT,
        )
        return RECORDED

    def _set_goal(self, args: dict[str, Any]) -> str:
        self.goal = text_arg(args, "text")
        return RECORDED

    def _set_thesis(self, args: dict[str, Any]) -> str:
        status = enum_arg(args, "status", ThesisStatus)
        previous = self._ctx.stock.theses[0].text if self._ctx.stock.theses else ""
        text = str(args.get("text") or previous).strip()
        if not text:
            msg = "'text' is required when no thesis exists yet"
            raise ToolError(msg)
        self.thesis = ThesisDraft(text, status)
        return RECORDED

    def _propose_followup(self, args: dict[str, Any]) -> str:
        proposal = FollowUp(
            str(args.get("workflow", "")),
            str(args.get("topic", "")).strip(),
            str(args.get("reason", "")).strip(),
        )
        rejection = self._followup_rejection(proposal)
        if rejection:
            msg = f"rejected by guardrails: {rejection}"
            raise ToolError(msg)
        self.followups.append(proposal)
        return "accepted; the ticket is created after this run"

    def _followup_rejection(self, proposal: FollowUp) -> str | None:
        """Reason the proposal is not acceptable, or ``None`` when it passes the guardrails."""
        if proposal.workflow not in FOLLOWUP_WORKFLOWS:
            return f"workflow must be one of: {', '.join(FOLLOWUP_WORKFLOWS)}"
        key = (proposal.workflow, proposal.topic.casefold())
        if any((f.workflow, f.topic.casefold()) == key for f in self.followups):
            return "duplicate"
        check = self._ctx.followup_check
        return check(proposal, len(self.followups)) if check else None

    # ---- assembly ---------------------------------------------------------
    def tools(self) -> list[Tool]:
        """The tools offered to the model: name, description, schema, handler."""
        return [
            Tool(
                "get_price_summary",
                "Compact price statistics (high/low, SMA, RSI, momentum, last closes).",
                tool_schemas.PRICE_SUMMARY,
                self._price_summary,
            ),
            Tool(
                "get_fundamentals",
                "Key figures (P/E, P/B, margins, growth, ...).",
                tool_schemas.NO_ARGS,
                self._fundamentals,
            ),
            Tool(
                "get_news",
                "Recent stored headlines for this stock.",
                tool_schemas.NEWS,
                self._news,
            ),
            Tool(
                "get_knowledge",
                "Earlier theses, score history and insights.",
                tool_schemas.NO_ARGS,
                self._knowledge,
            ),
            Tool(
                "get_datapoint_specs",
                "Inputs the stock's valuation profile needs and which are already recorded.",
                tool_schemas.NO_ARGS,
                self._datapoint_specs,
            ),
            Tool(
                "record_datapoint",
                "Record a sourced input (e.g. a mine's AISC). Give a source and honest "
                "confidence; never guess. Per-subject keys need 'subject'.",
                tool_schemas.RECORD_DATAPOINT,
                self._record_datapoint,
            ),
            Tool(
                "set_profile",
                "Set the valuation profile (stock type) if the current one is wrong.",
                tool_schemas.SET_PROFILE,
                self._set_profile,
            ),
            Tool(
                "add_insight",
                "Record one durable finding. With document_id + a verbatim quote it becomes "
                "a cited, verified finding.",
                tool_schemas.ADD_INSIGHT,
                self._add_insight,
            ),
            Tool("set_goal", "Set the goal for this stock.", tool_schemas.SET_GOAL, self._set_goal),
            Tool(
                "set_thesis",
                "Write a new thesis version or re-rate the current one.",
                tool_schemas.SET_THESIS,
                self._set_thesis,
            ),
            Tool(
                "propose_followup",
                "Propose a follow-up ticket. Guardrails apply and answer immediately.",
                tool_schemas.PROPOSE_FOLLOWUP,
                self._propose_followup,
            ),
        ]

    def briefing_tool(self) -> Tool:
        """The extra tool of the briefing workflow."""
        return Tool(
            "set_briefing",
            "Write the stock's briefing: a headline, a few bullets, the panel to open first.",
            tool_schemas.SET_BRIEFING,
            self._set_briefing,
        )

    def result(self, summary: str, data: dict[str, Any]) -> WorkflowResult:
        """Bundle everything the agent recorded into the workflow result."""
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
