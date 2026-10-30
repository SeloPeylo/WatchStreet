"""Shared machinery for workflows whose analysis step is performed by an agent."""

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from watchstreet.agents.base import AgentError, AgentRequest
from watchstreet.constants import MAX_LLM_ATTEMPTS
from watchstreet.domain import InsightCategory, ThesisStatus, WorkflowKey
from watchstreet.workflows.base import (
    FollowUp,
    InsightDraft,
    ThesisDraft,
    Workflow,
    WorkflowContext,
    WorkflowResult,
)
from watchstreet.workflows.facts import Facts, gather_facts

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
  "followups": [{"workflow": "<einer der erlaubten>", "topic": "...", "reason": "..."}]
}
Erlaubte Folge-Workflows: %(followups)s. Schlage nur Folgetickets vor, die echten Mehrwert bringen.
"""
FOLLOWUP_WORKFLOWS = (
    WorkflowKey.TOPIC_ANALYSIS,
    WorkflowKey.THESIS_CHECK,
    WorkflowKey.VALUATION_SCORE,
    WorkflowKey.TECHNICAL_SNAPSHOT,
)
JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class InsightModel(BaseModel):
    category: str = InsightCategory.NOTE
    text: str


class FollowUpModel(BaseModel):
    workflow: str
    topic: str = ""
    reason: str = ""


class Analysis(BaseModel):
    """The JSON document an agent must return."""

    summary: str
    goal: str | None = None
    thesis: str | None = None
    thesis_status: str | None = None
    insights: list[InsightModel] = Field(default_factory=list)
    followups: list[FollowUpModel] = Field(default_factory=list)


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
        analysis = self._ask(ctx, facts)
        return self._to_result(analysis, facts, ctx)

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
            data={"runner": ctx.runner.name},
        )
