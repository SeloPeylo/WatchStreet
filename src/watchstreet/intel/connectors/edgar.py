"""SEC EDGAR: filing index, filing text, XBRL company facts (free; needs a contact User-Agent)."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from watchstreet.intel.fetch import Fetcher, FetchError

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
EDGAR_BROWSE = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
ANNUAL_QUARTERLY_FORMS = ("10-K", "10-Q", "20-F", "40-F")


@dataclass(frozen=True)
class Filing:
    form: str
    filed: datetime
    accession: str
    document: str
    description: str
    url: str


@dataclass(frozen=True)
class Fact:
    """One reported XBRL value with its provenance."""

    key: str  # our datapoint key
    value: float
    unit: str
    period_end: str
    form: str
    concept: str


# our key -> candidate concepts in priority order; (taxonomy, concept, unit)
CASH_CONCEPTS = (
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsAndShortTermInvestments",
)
DEBT_CONCEPTS = ("LongTermDebt", "LongTermDebtNoncurrent", "DebtAndCapitalLeaseObligations")
SHARE_CONCEPTS = (("dei", "EntityCommonStockSharesOutstanding"),)
USD = "USD"


class EdgarClient:
    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher
        self._tickers: dict[str, int] | None = None

    def _json(self, url: str) -> dict[str, Any]:
        try:
            data: dict[str, Any] = json.loads(self._fetcher.fetch(url).text)
        except json.JSONDecodeError as exc:
            msg = f"invalid JSON from {url}"
            raise FetchError(msg) from exc
        return data

    def cik_for(self, ticker: str) -> int | None:
        if self._tickers is None:
            raw = self._json(TICKERS_URL)
            self._tickers = {v["ticker"].upper(): int(v["cik_str"]) for v in raw.values()}
        return self._tickers.get(ticker.upper().split(".")[0])

    def recent_filings(self, cik: int) -> list[Filing]:
        recent = self._json(SUBMISSIONS_URL.format(cik=cik)).get("filings", {}).get("recent", {})
        filings: list[Filing] = []
        for idx, form in enumerate(recent.get("form", [])):
            accession = recent["accessionNumber"][idx]
            document = recent["primaryDocument"][idx]
            filings.append(
                Filing(
                    form=form,
                    filed=datetime.fromisoformat(recent["filingDate"][idx]).replace(tzinfo=UTC),
                    accession=accession,
                    document=document,
                    description=recent.get("primaryDocDescription", [""] * (idx + 1))[idx],
                    url=ARCHIVE_URL.format(
                        cik=cik,
                        accession=accession.replace("-", ""),
                        document=document,
                    ),
                ),
            )
        return filings

    def filing_text(self, url: str) -> str:
        return self._fetcher.fetch(url).text

    def facts_url(self, cik: int) -> str:
        return FACTS_URL.format(cik=cik)

    def facts(self, cik: int) -> dict[str, Any]:
        return self._json(self.facts_url(cik))


def _latest(
    facts: dict[str, Any], taxonomy: str, concept: str, unit: str
) -> tuple[float, str, str] | None:
    """Newest reported value (by period end, then filing date) for a concept."""
    entries = (
        facts.get("facts", {}).get(taxonomy, {}).get(concept, {}).get("units", {}).get(unit, [])
    )
    if not entries:
        return None
    best = max(entries, key=lambda e: (e.get("end", ""), e.get("filed", "")))
    return float(best["val"]), best.get("end", ""), best.get("form", "")


def extract_facts(facts: dict[str, Any]) -> list[Fact]:
    """Deterministic datapoints from XBRL: share count and net debt (debt minus cash)."""
    out: list[Fact] = []
    for taxonomy, concept in SHARE_CONCEPTS:
        found = _latest(facts, taxonomy, concept, "shares")
        if found:
            out.append(Fact("shares_outstanding", found[0], "shares", found[1], found[2], concept))
            break
    debt = next(
        (r for c in DEBT_CONCEPTS if (r := _latest(facts, "us-gaap", c, USD))),
        None,
    )
    cash = next(
        (r for c in CASH_CONCEPTS if (r := _latest(facts, "us-gaap", c, USD))),
        None,
    )
    if debt and cash:
        out.append(
            Fact("net_debt", debt[0] - cash[0], USD, debt[1], debt[2], "LongTermDebt - Cash"),
        )
    return out
