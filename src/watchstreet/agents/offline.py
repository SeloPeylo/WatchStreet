"""Rule-based stand-in for an LLM.

It needs no network and no API key and is fully deterministic. It does not understand free
text; it turns the structured facts a workflow collected into the same JSON schema a real
model must return. Every summary says so, so nobody mistakes it for LLM output.
"""

import json
from typing import Any

from watchstreet.agents.base import AgentRequest
from watchstreet.constants import (
    SCORE_BAD,
    SCORE_DROP_WEAKENS_THESIS,
    SCORE_GOOD,
    TECHNICAL_SCHEME,
)
from watchstreet.profiles.classify import classify

OFFLINE_NOTE = "(Offline-Modus: regelbasiert, kein LLM)"
NEGATIVE_WORDS = (
    "klage",
    "verlust",
    "warnung",
    "rückruf",
    "betrug",
    "lawsuit",
    "probe",
    "downgrade",
    "miss",
    "recall",
    "fraud",
    "cuts",
    "plunge",
    "investigation",
)
POSITIVE_WORDS = (
    "übertrifft",
    "über den erwartungen",
    "rückkauf",
    "rekord",
    "upgrade",
    "beat",
    "buyback",
    "record",
    "raises",
    "surge",
)
RISK_TOPIC = "Risiken und Katalysatoren"
ENTRY_TOPIC = "Einstiegszeitpunkt und Kaufargumente"


def _fmt(value: float | None, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value:.1f}{suffix}"


def _score(facts: dict[str, Any], scheme: str) -> dict[str, Any] | None:
    found: dict[str, Any] | None = facts.get("scores", {}).get(scheme)
    return found


def _valuation(facts: dict[str, Any]) -> dict[str, Any] | None:
    """The profile-specific valuation score, whatever its scheme key is."""
    return next((v for k, v in facts.get("scores", {}).items() if k.startswith("valuation")), None)


def _facts_line(facts: dict[str, Any]) -> str:
    val = _valuation(facts)
    tech = _score(facts, TECHNICAL_SCHEME)
    parts = [
        f"Kurs {_fmt(facts.get('price'))} {facts.get('currency', '')}".strip(),
        f"30-Bar-Trend {_fmt(facts.get('change_20_bars_pct'), ' %')}",
        f"Bewertung {val['label'] if val else 'n/a'} ({_fmt(val['value']) if val else 'n/a'})",
        f"Technik {tech['label'] if tech else 'n/a'} ({_fmt(tech['value']) if tech else 'n/a'})",
    ]
    holding = facts.get("holding")
    if holding:
        parts.append(f"Position {_fmt(holding.get('pnl_pct'), ' %')} P/L")
    return "; ".join(parts)


def _stance(facts: dict[str, Any]) -> str:
    val = _valuation(facts)
    tech = _score(facts, TECHNICAL_SCHEME)
    avg = [s["value"] for s in (val, tech) if s]
    if not avg:
        return "neutral"
    mean = sum(avg) / len(avg)
    if mean >= SCORE_GOOD:
        return "positiv"
    if mean <= SCORE_BAD:
        return "kritisch"
    return "neutral"


def _initial_holding(facts: dict[str, Any]) -> dict[str, Any]:
    stance = _stance(facts)
    intent = facts.get("intent")
    goals = {
        "positiv": "Position halten, Gewinne laufen lassen, Nachkauf bei Rücksetzern prüfen",
        "neutral": "Position beobachten und die Investmentthese durch Folgeanalysen validieren",
        "kritisch": "Bewertung und Risiken kritisch prüfen, Teilverkauf erwägen falls These fehlt",
    }
    return {
        "summary": f"Bestandsaufnahme {facts['symbol']}: Lage {stance}. "
        f"{_facts_line(facts)} {OFFLINE_NOTE}",
        "goal": intent or goals[stance],
        "thesis": f"Die Position in {facts['name'] or facts['symbol']} wird gehalten, solange "
        f"Bewertung und Trend nicht deutlich kippen (Ausgangslage: {stance}).",
        "thesis_status": "active",
        "insights": [{"category": "action", "text": goals[stance]}],
        "followups": [
            {
                "workflow": "topic_analysis",
                "topic": RISK_TOPIC,
                "reason": "Bestandsaufnahme abgeschlossen; Risiken und Katalysatoren klären.",
            },
        ],
    }


def _initial_watch(facts: dict[str, Any]) -> dict[str, Any]:
    stance = _stance(facts)
    verdicts = {
        "positiv": "Kaufkandidat: Bewertung und Technik sprechen aktuell dafür.",
        "neutral": "Beobachten: keine klare Kaufgelegenheit erkennbar.",
        "kritisch": "Abwarten: Bewertung oder Technik sprechen aktuell dagegen.",
    }
    return {
        "summary": f"Kaufprüfung {facts['symbol']}: {verdicts[stance]} "
        f"{_facts_line(facts)} {OFFLINE_NOTE}",
        "goal": "Entscheiden, ob und zu welchem Preis ein Einstieg sinnvoll ist",
        "thesis": f"{facts['name'] or facts['symbol']} ist interessant, wenn Bewertung und Trend "
        f"zusammenpassen (Ausgangslage: {stance}).",
        "thesis_status": "active",
        "insights": [{"category": "action", "text": verdicts[stance]}],
        "followups": [
            {
                "workflow": "topic_analysis",
                "topic": ENTRY_TOPIC,
                "reason": "Kaufprüfung abgeschlossen; Einstieg konkretisieren.",
            },
        ],
    }


def _classify(facts: dict[str, Any]) -> dict[str, Any]:
    info = facts.get("company_info", {})
    key = classify(info.get("sector", ""), info.get("industry", ""))
    text = f"Sektor '{info.get('sector', '')}', Branche '{info.get('industry', '')}'"
    return {
        "summary": f"Profil für {facts['symbol']}: {key or 'kein Treffer'} ({text}). "
        f"{OFFLINE_NOTE}",
        "profile": key,
        "profile_reason": text,
        "insights": [],
        "followups": [],
    }


def _research(facts: dict[str, Any]) -> dict[str, Any]:
    missing = facts.get("missing_inputs", [])
    return {
        "summary": f"Der Offline-Modus kann nicht recherchieren. Fehlende Eingaben: "
        f"{', '.join(missing) or 'keine'}. Bitte manuell erfassen. {OFFLINE_NOTE}",
        "insights": [{"category": "note", "text": f"Datenlücke: {m}"} for m in missing],
        "followups": [],
    }


def _topic(facts: dict[str, Any]) -> dict[str, Any]:
    topic = facts.get("topic") or "Allgemein"
    return {
        "summary": f"Thema '{topic}' für {facts['symbol']}: Der Offline-Modus kann Freitext nicht "
        f"inhaltlich analysieren. Faktenlage: {_facts_line(facts)} {OFFLINE_NOTE}",
        "insights": [{"category": "note", "text": f"Thema '{topic}' benötigt einen LLM-Agenten."}],
        "followups": [],
    }


def _event_review(facts: dict[str, Any]) -> dict[str, Any]:
    insights: list[dict[str, str]] = []
    negative = False
    for title in facts.get("events", []):
        lowered = title.lower()
        if any(word in lowered for word in NEGATIVE_WORDS):
            negative = True
            insights.append({"category": "risk", "text": f"Mögliches Risiko-Signal: {title}"})
        elif any(word in lowered for word in POSITIVE_WORDS):
            insights.append({"category": "catalyst", "text": f"Mögliches Plus-Signal: {title}"})
    followups = (
        [
            {
                "workflow": "thesis_check",
                "topic": "",
                "reason": "Negatives Ereignis erkannt; These prüfen.",
            }
        ]
        if negative
        else []
    )
    count = len(facts.get("events", []))
    return {
        "summary": f"{count} neue Meldung(en) für {facts['symbol']} geprüft, "
        f"{len(insights)} mit Signal. {OFFLINE_NOTE}",
        "insights": insights,
        "followups": followups,
    }


def _thesis_check(facts: dict[str, Any]) -> dict[str, Any]:
    status = "active"
    reasons: list[str] = []
    for scheme, fresh in facts.get("scores", {}).items():
        previous = facts.get("previous_scores", {}).get(scheme)
        if previous is None:
            continue
        delta = fresh["value"] - previous
        reasons.append(f"{scheme}: {delta:+.1f}")
        if delta <= -SCORE_DROP_WEAKENS_THESIS:
            status = "weakened"
        elif delta >= SCORE_DROP_WEAKENS_THESIS and status != "weakened":
            status = "confirmed"
    old = (facts.get("thesis") or {}).get("text", "")
    return {
        "summary": f"These für {facts['symbol']} geprüft: Status {status}. "
        f"Veränderungen: {', '.join(reasons) or 'keine Vergleichswerte'}. {OFFLINE_NOTE}",
        "thesis": old or None,
        "thesis_status": status,
        "insights": [],
        "followups": [],
    }


HANDLERS = {
    "initial_holding": _initial_holding,
    "initial_watch": _initial_watch,
    "topic_analysis": _topic,
    "event_review": _event_review,
    "thesis_check": _thesis_check,
    "classify_stock": _classify,
    "research_datapoints": _research,
}


class OfflineRunner:
    name = "offline"

    def complete(self, request: AgentRequest) -> str:
        handler = HANDLERS.get(request.workflow, _topic)
        return json.dumps(handler(request.facts), ensure_ascii=False)
