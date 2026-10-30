"""Populate a demo database through the real services and harness (for docs and screenshots).

Run with  WATCHSTREET_MARKET_PROVIDER=demo WATCHSTREET_DATABASE_URL=sqlite:///./data/demo.db \
          python scripts/seed_demo.py

Everything is synthetic: demo market data, demo documents (news.demo.example), and a scripted
"agent" that reads the demo filing and quotes it verbatim. The grounding checks are the real ones.
"""

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from watchstreet.agents.tools import Tool, ToolRun
from watchstreet.config import load_settings
from watchstreet.container import Container, build_container
from watchstreet.domain import WorkflowKey
from watchstreet.harness.executor import execute_ticket
from watchstreet.intel.documents import store_document
from watchstreet.intel.ingest import run_ingest
from watchstreet.models import Document, Stock
from watchstreet.services import datapoints as dps
from watchstreet.services import entities, portfolio, tickets
from watchstreet.services.intel import create_intel
from watchstreet.timeutil import utcnow
from watchstreet.worker import drain_queue
from watchstreet.workflows.base import IntelDraft

CARLIN = "Our Carlin operations in Nevada, United States produced 900,000 ounces of gold in 2025"
CADIA = "Our Cadia operations in New South Wales, Australia produced 500,000 ounces of gold in 2025"
ORICA = (
    "Orica Limited supplies substantially all of the explosives used at our Australian operations"
)
CAT = "Caterpillar Inc. supplies the majority of our haul trucks and mining equipment"
METALOR = "Metalor Technologies accounted for approximately 30% of our gold sales in 2025"
RISK = "We rely on a limited number of suppliers, which exposes us to supply interruptions."


class ScriptedFilingReader:
    """Stands in for an LLM: performs the tool calls a good agent would, quoting the filing."""

    name = "demo-agent"
    supports_tools = True

    def complete(self, request: Any) -> str:  # pragma: no cover - not used
        raise NotImplementedError

    def run_with_tools(self, _system: str, _prompt: str, tools: Sequence[Tool]) -> ToolRun:
        by_name = {t.name: t.handler for t in tools}
        calls = [
            (
                "record_asset",
                {
                    "name": "Carlin",
                    "kind": "mine",
                    "country": "United States",
                    "lat": 40.9,
                    "lon": -116.2,
                    "ownership": 1.0,
                    "quote": CARLIN,
                },
            ),
            (
                "record_asset",
                {
                    "name": "Cadia",
                    "kind": "mine",
                    "country": "Australia",
                    "lat": -33.4,
                    "lon": 149.0,
                    "ownership": 1.0,
                    "quote": CADIA,
                },
            ),
            (
                "record_relation",
                {
                    "from": "Orica Limited",
                    "from_kind": "supplier",
                    "to": "SELF",
                    "relation": "supplies",
                    "country": "Australia",
                    "quote": ORICA,
                },
            ),
            (
                "record_relation",
                {
                    "from": "Caterpillar Inc.",
                    "from_kind": "supplier",
                    "to": "SELF",
                    "relation": "supplies",
                    "country": "United States",
                    "strength": 0.4,
                    "quote": CAT,
                },
            ),
            (
                "record_relation",
                {
                    "from": "SELF",
                    "to": "Metalor Technologies",
                    "to_kind": "customer",
                    "relation": "supplies",
                    "country": "Switzerland",
                    "strength": 0.3,
                    "quote": METALOR,
                },
            ),
            (
                "add_insight",
                {
                    "category": "risk",
                    "quote": RISK,
                    "text": "Konzentriertes Zulieferer-Risiko laut Risikofaktoren.",
                },
            ),
        ]
        for tool, args in calls:
            by_name[tool](args)
        return ToolRun(
            "Standorte, Zulieferer und Kunden aus dem Demo-Dokument belegt extrahiert.",
            2,
            len(calls),
        )


def add_stocks(container: Container) -> None:
    with container.session_factory() as s:
        for symbol, qty, price, intent in (
            ("AAPL", 25, 142.3, "Langfristig halten, Dividende reinvestieren"),
            ("NEM", 60, 38.5, "Goldpreis-Hebel, Nachkauf unter NAV"),
            ("XOM", 15, 104.0, ""),
            ("NVDA", 8, 95.5, ""),
            ("SAP.DE", 40, 118.0, ""),
        ):
            portfolio.add_holding(
                s, container.market, portfolio.NewHolding(symbol, qty, price, intent=intent)
            )
        portfolio.add_watch(s, container.market, "MSFT", "Cloud")
        portfolio.add_watch(s, container.market, "NEE", "Versorger, Dividende")
        s.commit()


def nem_inputs(container: Container) -> None:
    rows: list[tuple[str, str, float | str]] = [
        ("commodity_symbol", "", "GC=F"),
        ("commodity_price", "", 2400.0),
        ("net_debt", "", 6e9),
        ("shares_outstanding", "", 55e6),
        ("mine_production", "Carlin", 900_000.0),
        ("mine_aisc", "Carlin", 1500.0),
        ("mine_reserves", "Carlin", 12e6),
        ("mine_production", "Cadia", 500_000.0),
        ("mine_aisc", "Cadia", 1100.0),
        ("mine_reserves", "Cadia", 9e6),
        ("mine_production", "Boddington", 700_000.0),
        ("mine_aisc", "Boddington", 1650.0),
        ("mine_reserves", "Boddington", 6e6),
        ("mine_ownership", "Boddington", 0.5),
    ]
    with container.session_factory() as s:
        nem = s.scalar(select(Stock).where(Stock.symbol == "NEM"))
        xom = s.scalar(select(Stock).where(Stock.symbol == "XOM"))
        for key, subject, value in rows:
            entry = (
                dps.DatapointInput(key, subject, text=str(value), source="Demo")
                if isinstance(value, str)
                else dps.DatapointInput(key, subject, value, source="Demo")
            )
            dps.add_datapoint(s, nem, entry, origin="user")
        for key, value in (("commodity_price", 80.0), ("breakeven_price", 55.0)):
            dps.add_datapoint(
                s, xom, dps.DatapointInput(key, value=value, source="Demo"), origin="user"
            )
        dps.add_datapoint(
            s,
            xom,
            dps.DatapointInput("commodity_symbol", text="CL=F", source="Demo"),
            origin="user",
        )
        mines = {m.name: m for m in entities.sync_mine_entities(s, nem)}
        entities.set_location(mines["Boddington"], -32.8, 116.4, "Australia")
        s.commit()


def run_ticket(
    container: Container, symbol: str, workflow: WorkflowKey, runner: Any = None
) -> None:
    previous = container.runner
    if runner is not None:
        container.runner = runner
    with container.session_factory() as s:
        stock = s.scalar(select(Stock).where(Stock.symbol == symbol))
        ticket = tickets.create_ticket(
            s,
            stock,
            workflow,
            topic=f"doc:{_filing_id(s)}" if workflow == WorkflowKey.READ_FILING else "",
        )
        s.commit()
        ticket_id = ticket.id
    execute_ticket(container, ticket_id)
    container.runner = previous


def _filing_id(session: Any) -> int:
    return int(session.scalar(select(Document.id).where(Document.url.like("%demo-10k.htm"))))


def extra_intel(container: Container) -> None:
    """A few hand-written demo items with countries so the map has more than the quake."""
    items = [
        (
            "Streik an australischem Standort",
            "geopolitics",
            4,
            "Australia",
            "NEM",
            "bearish",
            "Cadia und Boddington liefern zusammen rund 60 % der Produktion.",
        ),
        (
            "Chile prüft höhere Rohstoffabgaben",
            "regulatory",
            3,
            "Chile",
            "NEM",
            "bearish",
            "Politisches Signal für Bergbau-Regime in Südamerika; Newmont ist dort nicht aktiv.",
        ),
        (
            "OPEC+ verlängert Förderkürzung",
            "commodity",
            3,
            "Saudi Arabia",
            "XOM",
            "bullish",
            "Stützt den Ölpreis über dem Break-even.",
        ),
    ]
    with container.session_factory() as s:
        for idx, (headline, category, severity, country, symbol, direction, why) in enumerate(
            items
        ):
            stock = s.scalar(select(Stock).where(Stock.symbol == symbol))
            doc, _ = store_document(
                s,
                url=f"https://news.demo.example/seed/{idx}",
                kind="news",
                publisher="Demo Wire",
                title=headline,
                text=f"{headline}\nSynthetische Demo-Meldung.",
                published_at=utcnow() - timedelta(days=idx + 1),
            )
            create_intel(
                s,
                IntelDraft(
                    headline=headline,
                    category=category,
                    severity=severity,
                    why_it_matters=why,
                    document_id=doc.id,
                    country=country,
                    impacts=((stock.id, direction, why),),
                    dedupe_key=f"seed:{idx}",
                ),
                author="rules",
            )
        s.commit()


def main() -> None:
    container = build_container(load_settings())
    add_stocks(container)
    nem_inputs(container)
    drain_queue(container)
    run_ticket(container, "NEM", WorkflowKey.SEC_SYNC)
    run_ticket(container, "NEM", WorkflowKey.READ_FILING, ScriptedFilingReader())
    run_ingest(container)
    extra_intel(container)
    drain_queue(container)


if __name__ == "__main__":
    main()
