"""Collect the structured facts every workflow starts from.

Existing knowledge (thesis, recent insights, previous scores) is included on purpose: it is
how findings of earlier tickets reach later ones instead of getting lost.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from watchstreet.constants import (
    CHANGE_PERIOD_BARS_DAY,
    DEFAULT_INTERVAL,
    MOMENTUM_BARS,
    PERCENT,
    RECENT_LIMIT,
    TECHNICAL_SCHEME,
    VALUATION_SCHEME,
)
from watchstreet.market.base import MarketDataError
from watchstreet.market.indicators import pct_change
from watchstreet.models import Insight, MarketEvent, Score
from watchstreet.workflows.base import ScoreDraft, WorkflowContext
from watchstreet.workflows.scoring import ScoreResult, technical_score, valuation_score

RECENT_INSIGHTS = 12


@dataclass
class Facts:
    data: dict[str, Any]
    fresh_scores: list[ScoreDraft]


def _draft(result: ScoreResult) -> ScoreDraft:
    return ScoreDraft(result.scheme, result.value, result.label, result.details)


def latest_scores(ctx: WorkflowContext) -> dict[str, float]:
    """Newest persisted value per scheme."""
    out: dict[str, float] = {}
    rows = ctx.session.scalars(
        select(Score).where(Score.stock_id == ctx.stock.id).order_by(Score.id.desc()),
    )
    for row in rows:
        out.setdefault(row.scheme, row.value)
    return out


def _market_block(ctx: WorkflowContext) -> tuple[dict[str, Any], list[ScoreResult]]:
    symbol = ctx.stock.symbol
    data: dict[str, Any] = {}
    scores: list[ScoreResult] = []
    try:
        quote = ctx.market.quote(symbol)
        data.update(price=quote.price, currency=quote.currency)
        data["change_1d_pct"] = quote.change_pct
        candles = ctx.market.candles(symbol, DEFAULT_INTERVAL)
        closes = [c.close for c in candles]
        data["change_20_bars_pct"] = pct_change(closes, MOMENTUM_BARS)
        data["change_day_pct"] = pct_change(closes, CHANGE_PERIOD_BARS_DAY)
        fundamentals = ctx.market.fundamentals(symbol)
        data["fundamentals"] = dict(fundamentals.values)
        tech = technical_score(candles)
        val = valuation_score(fundamentals, quote.price)
        scores = [s for s in (val, tech) if s is not None]
    except MarketDataError as exc:
        data["market_error"] = str(exc)
    return data, scores


def _holding_block(ctx: WorkflowContext, price: float | None) -> dict[str, Any] | None:
    holding = ctx.stock.holding
    if holding is None:
        return None
    block: dict[str, Any] = {
        "quantity": holding.quantity,
        "avg_price": holding.avg_price,
        "bought_at": holding.bought_at.isoformat() if holding.bought_at else None,
        "intent": holding.intent,
    }
    if price is not None:
        block["market_value"] = price * holding.quantity
        block["pnl_abs"] = (price - holding.avg_price) * holding.quantity
        block["pnl_pct"] = (price / holding.avg_price - 1.0) * PERCENT
    return block


def gather_facts(ctx: WorkflowContext, extra: dict[str, Any] | None = None) -> Facts:
    stock = ctx.stock
    data, results = _market_block(ctx)
    data.update(symbol=stock.symbol, name=stock.name)
    data["holding"] = _holding_block(ctx, data.get("price"))
    data["watch_note"] = stock.watch.note if stock.watch else None
    data["scores"] = {
        r.scheme: {"value": r.value, "label": r.label, "coverage": r.details.get("coverage")}
        for r in results
    }
    data["previous_scores"] = latest_scores(ctx)
    thesis = stock.theses[0] if stock.theses else None
    data["thesis"] = {"text": thesis.text, "status": thesis.status} if thesis else None
    insights = ctx.session.scalars(
        select(Insight)
        .where(Insight.stock_id == stock.id)
        .order_by(Insight.id.desc())
        .limit(RECENT_INSIGHTS),
    )
    data["recent_insights"] = [{"category": i.category, "text": i.text} for i in insights]
    headlines = ctx.session.scalars(
        select(MarketEvent)
        .where(MarketEvent.stock_id == stock.id)
        .order_by(MarketEvent.published_at.desc())
        .limit(RECENT_LIMIT),
    )
    data["headlines"] = [e.title for e in headlines]
    data.update(extra or {})
    return Facts(data=data, fresh_scores=[_draft(r) for r in results])


__all__ = ["TECHNICAL_SCHEME", "VALUATION_SCHEME", "Facts", "gather_facts", "latest_scores"]
