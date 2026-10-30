"""Shared machinery for workflows whose analysis step is performed by an agent."""

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from watchstreet.agents.base import AgentError, AgentRequest
from watchstreet.agents.tools import ToolCapableRunner
from watchstreet.constants import MAX_LLM_ATTEMPTS
from watchstreet.domain import InsightCategory, ThesisStatus
from watchstreet.workflows.base import (
    DatapointDraft,
    FollowUp,
    InsightDraft,
    ProfileDraft,
    ThesisDraft,
    Workflow,
    WorkflowContext,
    WorkflowResult,
)
from watchstreet.workflows.facts import Facts, gather_facts
from watchstreet.workflows.tools import FOLLOWUP_WORKFLOWS, ToolBox

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

SYSTEM_PROMPT = """\
Du bist ein sorgfältiger Aktien-Analyst in einem Ticket-System. Du gibst keine Anlageberatung,
sondern strukturierte Analysen für den Eigengebrauch. Regeln:
- Stütze dich ausschließlich auf die gelieferten Fakten; nenne Unsicherheit ausdrücklich.
- Erfinde keine Zahlen. Fehlt etwas, sage es.
- Antworte NUR mit einem JSON-Objekt, ohne Text davor oder danach, auf Deutsch.

Schema:
{
  "summary": "kurze Zusammenfassung (2-5 Sätze)",
  "goal": "Ziel/Absicht für diese Aktie oder null",
  "thesis": "Investmentthese oder null",
  "thesis_status": "active|confirmed|weakened|invalidated oder null",
  "insights": [{"category": "goal|risk|catalyst|valuation|technical|action|note", "text": "..."}],
  "followups": [{"workflow": "<einer der erlaubten>", "topic": "...", "reason": "..."}],
  "profile": "Profilschlüssel oder null",
  "datapoints": [{"key": "...", "subject": "...", "value": 0, "source": "...",
                  "confidence": "high|medium|low"}]
}
Erlaubte Folge-Workflows: %(followups)s. Schlage nur Folgetickets vor, die echten Mehrwert bringen.
"""
JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class InsightModel(BaseModel):
    category: str = InsightCategory.NOTE
    text: str


class FollowUpModel(BaseModel):
    workflow: str
    topic: str = ""
    reason: str = ""


class DatapointModel(BaseModel):
    key: str
    subject: str = ""
    value: float | None = None
    text: str = ""
    unit: str = ""
    source: str = ""
    confidence: str = "medium"


class Analysis(BaseModel):
    """The JSON document an agent must return."""

    summary: str
    goal: str | None = None
    thesis: str | None = None
    thesis_status: str | None = None
    insights: list[InsightModel] = Field(default_factory=list)
    followups: list[FollowUpModel] = Field(default_factory=list)
    profile: str | None = None
    profile_reason: str = ""
    datapoints: list[DatapointModel] = Field(default_factory=list)


def parse_analysis(raw: str) -> Analysis:
    """Extract and validate the JSON object from a model answer."""
    match = JSON_OBJECT.search(raw)
    if not match:
        msg = "No JSON object in agent answer"
        raise AgentError(msg)
    try:
        return Analysis.model_validate(json.loads(match.group(0)))
    except (json.JSONDecodeError, ValidationError) as exc:
        msg = f"Agent answer does not match schema: {exc}"
        raise AgentError(msg) from exc


def _category(value: str) -> InsightCategory:
    try:
        return InsightCategory(value)
    except ValueError:
        return InsightCategory.NOTE


def _status(value: str | None) -> ThesisStatus:
    try:
        return ThesisStatus(value or ThesisStatus.ACTIVE)
    except ValueError:
        return ThesisStatus.ACTIVE


class LlmWorkflow(Workflow):
    """Collect facts, ask the agent, validate, translate into a ``WorkflowResult``."""

    task: str = ""
    persist_scores: bool = False

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
        box = ToolBox(ctx)
        run = runner.run_with_tools(TOOL_SYSTEM_PROMPT, prompt, box.tools())
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

    def _to_result(
        self,
        analysis: Analysis,
        facts: Facts,
        ctx: WorkflowContext,
    ) -> WorkflowResult:
        insights = [InsightDraft(_category(i.category), i.text) for i in analysis.insights]
        if analysis.goal:
            insights.insert(0, InsightDraft(InsightCategory.GOAL, analysis.goal))
        thesis = None
        if analysis.thesis or analysis.thesis_status:
            old = ctx.stock.theses[0].text if ctx.stock.theses else ""
            thesis = ThesisDraft(analysis.thesis or old, _status(analysis.thesis_status))
            if not thesis.text:
                thesis = None
        return WorkflowResult(
            summary=analysis.summary,
            insights=insights,
            scores=facts.fresh_scores if self.persist_scores else [],
            thesis=thesis,
            followups=[FollowUp(f.workflow, f.topic, f.reason) for f in analysis.followups],
            datapoints=[DatapointDraft(**d.model_dump()) for d in analysis.datapoints],
            profile=ProfileDraft(analysis.profile, analysis.profile_reason)
            if analysis.profile
            else None,
            data={"runner": ctx.runner.name, "mode": "json"},
        )
