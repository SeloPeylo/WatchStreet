"""Base class for workflows whose analysis step is performed by an agent.

Two modes: with a tool-capable runner the agent calls tools (``tools.py``) and fills drafts;
otherwise it must answer with one JSON document (``analysis.py``) that is validated here.
"""

import json
import logging
from typing import Any

from watchstreet.agents.base import AgentError, AgentRequest
from watchstreet.agents.tools import ToolCapableRunner
from watchstreet.constants import MAX_INTEL_PER_TICKET, MAX_LLM_ATTEMPTS
from watchstreet.domain import InsightCategory
from watchstreet.drafts import (
    DatapointDraft,
    FollowUp,
    InsightDraft,
    IntelDraft,
    ProfileDraft,
    ThesisDraft,
    WorkflowResult,
)
from watchstreet.intel.documents import verify_quote
from watchstreet.models import Document
from watchstreet.workflows.analysis import (
    SYSTEM_PROMPT,
    Analysis,
    category_or_note,
    parse_analysis,
    status_or_active,
)
from watchstreet.workflows.base import Workflow, WorkflowContext
from watchstreet.workflows.facts import Facts, gather_facts
from watchstreet.workflows.tool_schemas import FOLLOWUP_WORKFLOWS
from watchstreet.workflows.tools import ToolBox

logger = logging.getLogger(__name__)

TOOL_SYSTEM_PROMPT = """\
Du bist ein sorgfältiger Aktien-Analyst in einem Ticket-System (keine Anlageberatung).
Vorgehen:
- Die Fakten im Prompt sind bereits berechnet. Rufe Lese-Tools (get_*) nur auf, wenn du Details
  brauchst; jeder Aufruf kostet Zeit.
- Halte Erkenntnisse mit add_insight fest, Ziel mit set_goal, These mit set_thesis,
  sinnvolle Folgetickets mit propose_followup. Lehnt ein Tool ab, korrigiere oder lass es.
- Erfinde keine Zahlen. Nenne Unsicherheit.
- Beende mit einer Zusammenfassung in 2-5 deutschen Sätzen als normale Textantwort.
"""
COMPACT_DROP = ("fundamentals", "headlines", "recent_insights")
SEPARATORS = (",", ":")


class LlmWorkflow(Workflow):
    """Collect facts, ask the agent, validate, translate into a ``WorkflowResult``."""

    task: str = ""
    persist_scores: bool = False
    tool_system_prompt: str = TOOL_SYSTEM_PROMPT

    def make_toolbox(self, ctx: WorkflowContext) -> ToolBox:
        return ToolBox(ctx)

    def extra_facts(self, ctx: WorkflowContext) -> dict[str, Any]:
        return {"topic": ctx.ticket.params.get("topic", "")}

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        facts = gather_facts(ctx, self.extra_facts(ctx))
        runner = ctx.runner
        if getattr(runner, "supports_tools", False):
            try:
                return self._run_with_tools(ctx, facts, runner)  # type: ignore[arg-type]
            except AgentError as exc:
                logger.warning("Tool mode failed (%s); falling back to JSON mode", exc)
        analysis = self._ask(ctx, facts)
        return self._to_result(analysis, facts, ctx)

    def _run_with_tools(
        self,
        ctx: WorkflowContext,
        facts: Facts,
        runner: ToolCapableRunner,
    ) -> WorkflowResult:
        compact = {k: v for k, v in facts.data.items() if k not in COMPACT_DROP}
        prompt = f"AUFGABE: {self.task}\n\nFAKTEN (JSON):\n" + json.dumps(
            compact,
            ensure_ascii=False,
            default=str,
            separators=SEPARATORS,
        )
        box = self.make_toolbox(ctx)
        run = runner.run_with_tools(self.tool_system_prompt, prompt, box.tools())
        result = box.result(
            run.text,
            {
                "runner": runner.name,
                "mode": "tools",
                "steps": run.steps,
                "tool_calls": run.tool_calls,
                "prompt_tokens": run.prompt_tokens,
                "completion_tokens": run.completion_tokens,
            },
        )
        if self.persist_scores:
            result.scores = facts.fresh_scores
        return result

    def _ask(self, ctx: WorkflowContext, facts: Facts) -> Analysis:
        system = SYSTEM_PROMPT % {"followups": ", ".join(FOLLOWUP_WORKFLOWS)}
        prompt = f"AUFGABE: {self.task}\n\nFAKTEN (JSON):\n" + json.dumps(
            facts.data,
            ensure_ascii=False,
            default=str,
            indent=2,
        )
        last_error: AgentError | None = None
        for _ in range(MAX_LLM_ATTEMPTS):
            request = AgentRequest(
                self.key,
                system,
                prompt,
                task=self.task,
                facts=facts.data,
            )
            try:
                return parse_analysis(ctx.runner.complete(request))
            except AgentError as exc:
                last_error = exc
                prompt += f"\n\nDeine letzte Antwort war ungültig ({exc}). Nur gültiges JSON."
        raise last_error or AgentError("Agent returned nothing")

    def _intel_drafts(self, analysis: Analysis, ctx: WorkflowContext) -> list[IntelDraft]:
        """Intel items from a JSON answer; items whose quote cannot be verified are dropped."""
        drafts: list[IntelDraft] = []
        for entry in analysis.intel[:MAX_INTEL_PER_TICKET]:
            doc = ctx.session.get(Document, entry.document_id)
            if doc is None or not verify_quote(doc, entry.quote):
                logger.warning(
                    "Dropped intel for document %s: quote not verifiable", entry.document_id
                )
                continue
            drafts.append(
                IntelDraft(
                    headline=entry.headline,
                    summary=entry.summary,
                    why_it_matters=entry.why_it_matters,
                    category=entry.category,
                    severity=entry.severity,
                    document_id=doc.id,
                    quote=entry.quote,
                    country=entry.country,
                    commodities=tuple(entry.commodities),
                    impacts=((ctx.stock.id, entry.direction, entry.why_it_matters),),
                ),
            )
        return drafts

    @staticmethod
    def _thesis_draft(analysis: Analysis, ctx: WorkflowContext) -> ThesisDraft | None:
        """A new thesis, or the old text re-rated; ``None`` if the agent said nothing usable."""
        if not (analysis.thesis or analysis.thesis_status):
            return None
        previous = ctx.stock.theses[0].text if ctx.stock.theses else ""
        text = analysis.thesis or previous
        if not text:
            return None
        return ThesisDraft(text, status_or_active(analysis.thesis_status))

    def _to_result(
        self,
        analysis: Analysis,
        facts: Facts,
        ctx: WorkflowContext,
    ) -> WorkflowResult:
        insights = [
            InsightDraft(category_or_note(entry.category), entry.text)
            for entry in analysis.insights
        ]
        if analysis.goal:
            insights.insert(0, InsightDraft(InsightCategory.GOAL, analysis.goal))
        return WorkflowResult(
            summary=analysis.summary,
            insights=insights,
            scores=facts.fresh_scores if self.persist_scores else [],
            thesis=self._thesis_draft(analysis, ctx),
            followups=[FollowUp(f.workflow, f.topic, f.reason) for f in analysis.followups],
            datapoints=[DatapointDraft(**point.model_dump()) for point in analysis.datapoints],
            intel=self._intel_drafts(analysis, ctx),
            profile=ProfileDraft(analysis.profile, analysis.profile_reason)
            if analysis.profile
            else None,
            data={"runner": ctx.runner.name, "mode": "json"},
        )
