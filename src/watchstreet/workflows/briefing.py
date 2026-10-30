"""The briefing layer: deterministic draft first, optional agent polish.

The draft costs no tokens and works offline. If the runner supports tools, the agent gets the
draft plus the facts and may rewrite it via ``set_briefing``; otherwise the draft is stored.
"""

import json
from typing import Any

from watchstreet.agents.base import AgentError
from watchstreet.constants import MAX_BRIEFING_BULLETS, SCORE_BAD, SCORE_GOOD
from watchstreet.domain import InsightCategory, ThesisStatus, WorkflowKey
from watchstreet.models import Stock
from watchstreet.profiles.registry import get_profile
from watchstreet.workflows.base import BriefingDraft, Workflow, WorkflowContext, WorkflowResult
from watchstreet.workflows.facts import gather_facts
from watchstreet.workflows.tools import ToolBox

BRIEFING_SYSTEM = (
    "Du schreibst das Briefing zu einer Aktie: eine Schlagzeile und höchstens vier Stichpunkte "
    "darüber, worauf es JETZT ankommt (Änderungen, Risiken, Datenlücken). Keine Anlageberatung, "
    "keine erfundenen Zahlen. Nutze set_briefing genau einmal; lass dem Entwurf treu, was stimmt."
)
RISK_CATEGORIES = (InsightCategory.RISK, InsightCategory.CATALYST)


def build_draft(stock: Stock, facts: dict[str, Any]) -> BriefingDraft:
    """Rule-based briefing from stored knowledge and fresh scores."""
    profile = get_profile(stock.profile)
    scores = facts.get("scores", {})
    valuation = scores.get(profile.scheme)
    parts = [f"{stock.symbol} ({profile.label})"]
    if valuation:
        provisional = " – vorläufig" if valuation.get("provisional") else ""
        parts.append(f"Bewertung {valuation['label']} ({valuation['value']}){provisional}")
    thesis = facts.get("thesis")
    if thesis and thesis["status"] != ThesisStatus.ACTIVE:
        parts.append(f"These {thesis['status']}")
    holding = facts.get("holding")
    if holding and holding.get("pnl_pct") is not None:
        parts.append(f"Position {holding['pnl_pct']:+.1f} %")
    bullets: list[str] = []
    missing = facts.get("missing_inputs", [])
    if missing:
        bullets.append(f"Datenlücken ({len(missing)}): {', '.join(missing[:2])}")
    bullets += [
        i["text"] for i in facts.get("recent_insights", []) if i["category"] in RISK_CATEGORIES
    ][:2]
    tech = scores.get("technical_v1")
    if tech and tech["value"] <= SCORE_BAD:
        bullets.append("Technik bärisch: Trend zeigt nach unten")
    elif tech and tech["value"] >= SCORE_GOOD:
        bullets.append("Technik bullisch: Trend zeigt nach oben")
    focus = "evidence" if missing else ("valuation" if valuation else "chart")
    return BriefingDraft(" · ".join(parts), bullets[:MAX_BRIEFING_BULLETS], focus)


class Briefing(Workflow):
    key = WorkflowKey.BRIEFING
    label = "Briefing"
    description = (
        "Fasst zusammen, worauf es jetzt ankommt (Regeln, optional vom Agenten verfeinert)."
    )
    user_creatable = False

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        facts = gather_facts(ctx)
        draft = build_draft(ctx.stock, facts.data)
        data: dict[str, Any] = {"runner": ctx.runner.name, "mode": "rules"}
        result = WorkflowResult(summary=draft.headline, briefing=draft, data=data)
        runner = ctx.runner
        if not getattr(runner, "supports_tools", False):
            return result
        box = ToolBox(ctx)
        prompt = (
            "ENTWURF:\n"
            + json.dumps(draft.__dict__, ensure_ascii=False)
            + "\n\nFAKTEN:\n"
            + json.dumps(
                {
                    k: v
                    for k, v in facts.data.items()
                    if k in ("scores", "thesis", "holding", "missing_inputs", "profile")
                },
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            )
        )
        try:
            run = runner.run_with_tools(  # type: ignore[attr-defined]
                BRIEFING_SYSTEM,
                prompt,
                [box.briefing_tool()],
            )
        except AgentError:
            return result
        if box.briefing:
            result.briefing = box.briefing
            result.summary = box.briefing.headline
            data.update(
                mode="tools",
                steps=run.steps,
                tool_calls=run.tool_calls,
                prompt_tokens=run.prompt_tokens,
                completion_tokens=run.completion_tokens,
            )
        return result
