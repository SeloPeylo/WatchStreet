"""JSON answer contract for agents without tool support: prompt, schema and validation.

The model's answer is untrusted text. ``parse_analysis`` turns it into a validated ``Analysis``
or raises ``AgentError``; unknown categories and statuses degrade to safe defaults.
"""

import json
import re

from pydantic import BaseModel, Field, ValidationError

from watchstreet.agents.base import AgentError
from watchstreet.domain import InsightCategory, ThesisStatus

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


class IntelModel(BaseModel):
    document_id: int
    headline: str
    summary: str = ""
    why_it_matters: str = ""
    category: str = "company"
    severity: int = 2
    direction: str = "unknown"
    quote: str = ""
    country: str = ""
    commodities: list[str] = Field(default_factory=list)


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
    intel: list[IntelModel] = Field(default_factory=list)


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


def category_or_note(value: str) -> InsightCategory:
    """Unknown insight categories become plain notes."""
    try:
        return InsightCategory(value)
    except ValueError:
        return InsightCategory.NOTE


def status_or_active(value: str | None) -> ThesisStatus:
    """Missing or unknown thesis statuses mean the thesis is simply active."""
    try:
        return ThesisStatus(value or ThesisStatus.ACTIVE)
    except ValueError:
        return ThesisStatus.ACTIVE
