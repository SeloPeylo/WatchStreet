"""Holdings and watchlist use cases."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from watchstreet.constants import MIN_REASON_CHARS, PERCENT
from watchstreet.domain import SubjectType
from watchstreet.errors import WatchStreetError
from watchstreet.market.base import MarketDataError
from watchstreet.market.service import MarketService
from watchstreet.metrics import METRICS
from watchstreet.models import (
    Asset,
    Company,
    Decision,
    Fact,
    Holding,
    Stake,
    Stock,
    Thesis,
    WatchEntry,
)
from watchstreet.services.companies import company_view
from watchstreet.services.facts import display_value
from watchstreet.services.viewing import build_view
from watchstreet.services.world import is_unproven
from watchstreet.timeutil import utcnow

SYMBOL_MAX_LEN = 32
SNAPSHOT_DERIVED = ("cash_today", "runway_months", "shares_pro_forma", "market_cap", "funding_gap")
SNAPSHOT_METRICS = ("aisc", "cash_cost", "production", "capex", "study_npv", "expected_aisc")


class PortfolioError(WatchStreetError, ValueError):
    """Invalid user input for a portfolio operation."""


def normalize_symbol(raw: str) -> str:
    symbol = raw.strip().upper()
    if not symbol or len(symbol) > SYMBOL_MAX_LEN or " " in symbol:
        msg = "Ungültiges Symbol"
        raise PortfolioError(msg)
    return symbol


def get_or_create_stock(session: Session, market: MarketService, raw_symbol: str) -> Stock:
    """Find the stock or create it, enriching name/currency from the provider."""
    symbol = normalize_symbol(raw_symbol)
    stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock:
        return stock
    try:
        quote = market.quote(symbol)
    except MarketDataError as exc:
        msg = f"Symbol '{symbol}' wurde beim Datenanbieter nicht gefunden: {exc}"
        raise PortfolioError(msg) from exc
    info = market.company_info(symbol)
    stock = Stock(
        symbol=symbol,
        name=quote.name,
        currency=quote.currency,
        exchange=quote.exchange,
        sector=info.sector,
        industry=info.industry,
    )
    session.add(stock)
    session.flush()
    return stock


@dataclass(frozen=True)
class NewHolding:
    symbol: str
    quantity: float
    avg_price: float
    bought_at: date | None = None
    intent: str = ""
    thesis_id: int | None = None
    exit_condition: str = ""
    reason: str = ""
    stop_price: float | None = None
    min_runway_months: float | None = None


def snapshot(
    session: Session, stock: Stock, thesis_id: int | None, price: float | None
) -> dict[str, Any]:
    """What was known when a decision was taken; the journal must not be rewritten by hindsight."""
    thesis = session.get(Thesis, thesis_id) if thesis_id else None
    company = session.scalars(select(Company).where(Company.stock_id == stock.id)).first()
    facts: list[Fact] = (
        list(
            session.scalars(
                select(Fact).where(
                    Fact.subject_type == SubjectType.COMPANY,
                    Fact.subject_id == company.id,
                    Fact.superseded_by.is_(None),
                )
            )
        )
        if company
        else []
    )
    return {
        "price": price,
        "thesis": {
            "title": thesis.title,
            "assumptions": [
                {"text": a.text, "status": a.status, "criterion": a.criterion}
                for a in thesis.assumptions
            ],
        }
        if thesis
        else None,
        "figures": {METRICS[f.metric_key].label: display_value(f) for f in facts},
        "assets": _asset_figures(session, company) if company else {},
    }


def _asset_figures(session: Session, company: Company) -> dict[str, dict[str, str]]:
    """Cost, production and study figures of the company's assets, each with how sure it is."""
    asset_ids = set(session.scalars(select(Stake.asset_id).where(Stake.company_id == company.id)))
    out: dict[str, dict[str, str]] = {}
    for fact in session.scalars(
        select(Fact).where(
            Fact.subject_type == SubjectType.ASSET,
            Fact.subject_id.in_(asset_ids),
            Fact.metric_key.in_(SNAPSHOT_METRICS),
            Fact.superseded_by.is_(None),
        )
    ):
        asset = session.get(Asset, fact.subject_id)
        mark = " (ungeprüft)" if is_unproven(fact) else ""
        out.setdefault(asset.name if asset else "?", {})[METRICS[fact.metric_key].label] = (
            display_value(fact) + mark
        )
    return out


def record_decision(  # noqa: PLR0913
    session: Session,
    market: MarketService,
    stock: Stock,
    kind: str,
    reason: str,
    *,
    thesis_id: int | None = None,
    quantity: float | None = None,
    price: float | None = None,
    day: date | None = None,
) -> Decision:
    quote = market.try_quote(stock.symbol)
    known = snapshot(session, stock, thesis_id, quote.price if quote else None)
    company = session.scalars(select(Company).where(Company.stock_id == stock.id)).first()
    if company is not None:  # the derived state then: cash today, runway, share count, value
        view = company_view(session, company, build_view(session, market), market)
        known["derived"] = {
            m["label"]: f"{m['value']:,.0f} {m.get('unit', '')}".replace(",", ".").strip()
            for m in view["derived"]
            if m["metric"] in SNAPSHOT_DERIVED and m.get("value") is not None
        }
    decision = Decision(
        stock_id=stock.id, kind=kind, day=day or utcnow().date(), quantity=quantity,
        price=price, reason=reason.strip(), thesis_id=thesis_id,
        snapshot=known,
    )  # fmt: skip
    session.add(decision)
    session.flush()
    return decision


def _check_thesis(session: Session, thesis_id: int | None) -> None:
    if thesis_id is not None and session.get(Thesis, thesis_id) is None:
        msg = "Die gewählte These existiert nicht"
        raise PortfolioError(msg)


def add_holding(session: Session, market: MarketService, data: NewHolding) -> Holding:
    if data.quantity <= 0 or data.avg_price <= 0:
        msg = "Menge und Durchschnittspreis müssen größer als 0 sein"
        raise PortfolioError(msg)
    stock = get_or_create_stock(session, market, data.symbol)
    if stock.holding:
        msg = f"{stock.symbol} ist bereits in den Beständen"
        raise PortfolioError(msg)
    _check_thesis(session, data.thesis_id)
    if (
        len(data.exit_condition.strip()) < MIN_REASON_CHARS
        or len(data.intent.strip()) < MIN_REASON_CHARS
    ):
        msg = "Ein Kauf braucht eine Absicht und eine Ausstiegsbedingung (je mindestens 10 Zeichen)"
        raise PortfolioError(msg)
    record_decision(
        session, market, stock, "buy", data.reason or data.intent, thesis_id=data.thesis_id,
        quantity=data.quantity, price=data.avg_price, day=data.bought_at,
    )  # fmt: skip
    holding = Holding(
        stock_id=stock.id,
        quantity=data.quantity,
        avg_price=data.avg_price,
        bought_at=data.bought_at,
        intent=data.intent.strip(),
        thesis_id=data.thesis_id,
        exit_condition=data.exit_condition.strip(),
        stop_price=data.stop_price,
        min_runway_months=data.min_runway_months,
    )
    session.add(holding)
    session.flush()
    session.refresh(stock)
    return holding


def adjust_holding(  # noqa: PLR0913
    session: Session,
    market: MarketService,
    holding: Holding,
    reason: str,
    *,
    intent: str | None = None,
    exit_condition: str | None = None,
    thesis_id: int | None = None,
    clear_thesis: bool = False,
    stop_price: float | None = None,
    min_runway_months: float | None = None,
) -> None:
    """Change why a position is held. Needs a reason, so the journal shows the bar being moved."""
    if len(reason.strip()) < MIN_REASON_CHARS:
        msg = "Bitte begründen, warum Absicht, These oder Ausstiegsbedingung geändert werden"
        raise PortfolioError(msg)
    _check_thesis(session, thesis_id)

    def state() -> str:
        return (
            f"{holding.intent} | Ausstieg: {holding.exit_condition} | Kursschwelle: "
            f"{holding.stop_price or '–'} | Mindestreichweite: {holding.min_runway_months or '–'}"
        )

    before = state()
    if stop_price is not None:
        holding.stop_price = stop_price or None  # 0 clears the threshold
    if min_runway_months is not None:
        holding.min_runway_months = min_runway_months or None
    if intent is not None:
        holding.intent = intent.strip()
    if exit_condition is not None:
        holding.exit_condition = exit_condition.strip()
    if thesis_id is not None or clear_thesis:
        holding.thesis_id = thesis_id
    after = state()
    record_decision(
        session, market, holding.stock, "adjust",
        f"{reason.strip()} (vorher: {before} → neu: {after})",
        thesis_id=holding.thesis_id,
    )  # fmt: skip


def buy_more(
    session: Session,
    market: MarketService,
    holding: Holding,
    quantity: float,
    price: float,
    reason: str,
) -> None:
    """Add to a position; the average price moves, and the journal says why you bought again."""
    if quantity <= 0 or price <= 0:
        msg = "Menge und Preis müssen größer als 0 sein"
        raise PortfolioError(msg)
    if len(reason.strip()) < MIN_REASON_CHARS:
        msg = "Bitte begründen, warum du nachkaufst"
        raise PortfolioError(msg)
    total = holding.quantity + quantity
    holding.avg_price = (holding.avg_price * holding.quantity + price * quantity) / total
    holding.quantity = total
    record_decision(
        session, market, holding.stock, "buy", reason, thesis_id=holding.thesis_id,
        quantity=quantity, price=price,
    )  # fmt: skip


def sell_holding(
    session: Session,
    market: MarketService,
    holding: Holding,
    reason: str,
    price: float | None,
    quantity: float | None = None,
) -> None:
    """Sell all or part of a position; reason, result and the knowledge then stay in the journal."""
    if len(reason.strip()) < MIN_REASON_CHARS:
        msg = "Bitte begründen, warum verkauft wird"
        raise PortfolioError(msg)
    sold = holding.quantity if quantity is None else quantity
    if sold <= 0 or sold > holding.quantity:
        msg = "Die Verkaufsmenge passt nicht zum Bestand"
        raise PortfolioError(msg)
    decision = record_decision(
        session, market, holding.stock, "sell", reason, thesis_id=holding.thesis_id,
        quantity=sold, price=price,
    )  # fmt: skip
    if price is not None:
        decision.snapshot = {
            **decision.snapshot,
            "realized": (price - holding.avg_price) * sold,
            "avg_price": holding.avg_price,
        }
    if sold == holding.quantity:
        session.delete(holding)
    else:
        holding.quantity -= sold
    session.flush()


def decisions(session: Session) -> list[Decision]:
    return list(
        session.scalars(
            select(Decision).options(joinedload(Decision.stock)).order_by(Decision.id.desc())
        )
    )


def add_watch(session: Session, market: MarketService, symbol: str, note: str = "") -> WatchEntry:
    stock = get_or_create_stock(session, market, symbol)
    if stock.watch:
        msg = f"{stock.symbol} ist bereits auf der Watchlist"
        raise PortfolioError(msg)
    entry = WatchEntry(stock_id=stock.id, note=note.strip())
    session.add(entry)
    session.flush()
    session.refresh(stock)
    return entry


@dataclass(frozen=True)
class HoldingRow:
    holding: Holding
    price: float | None
    market_value: float | None
    pnl_abs: float | None
    pnl_pct: float | None
    day_change_pct: float | None


def holding_rows(session: Session, market: MarketService) -> list[HoldingRow]:
    rows: list[HoldingRow] = []
    for holding in session.scalars(
        select(Holding).options(joinedload(Holding.stock)).order_by(Holding.id)
    ):
        quote = market.try_quote(holding.stock.symbol)
        if quote is None:
            rows.append(HoldingRow(holding, None, None, None, None, None))
            continue
        cost = holding.avg_price * holding.quantity
        value = quote.price * holding.quantity
        rows.append(
            HoldingRow(
                holding,
                quote.price,
                value,
                value - cost,
                (value / cost - 1) * PERCENT,
                quote.change_pct,
            )
        )
    return rows


def watch_entries(session: Session) -> list[WatchEntry]:
    return list(
        session.scalars(
            select(WatchEntry).options(joinedload(WatchEntry.stock)).order_by(WatchEntry.id)
        )
    )
