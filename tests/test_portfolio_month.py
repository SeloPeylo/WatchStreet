"""The monthly depot summary: pure selection first, then the portfolio payload."""

from datetime import date, timedelta

from sqlalchemy import select

from watchstreet.analysis.portfolio import (
    JournalEntry,
    PositionCheck,
    exit_breaches,
    month_summary,
)
from watchstreet.constants import MONTHS_DE, PORTFOLIO_REVIEW_DAYS
from watchstreet.models import Decision
from watchstreet.timeutil import utcnow

API = "/api/v1"
TODAY = date(2026, 11, 16)
STOP_NEVER_HIT = 1_000_000_000.0


def _entry(entry_id: int, day: date, kind: str = "buy") -> JournalEntry:
    return JournalEntry(id=entry_id, day=day, symbol="NEM", kind=kind, reason="Begründung")


def _position(position_id: int, last_logged: date, breaches: tuple[str, ...] = ()) -> PositionCheck:
    return PositionCheck(
        id=position_id,
        symbol=f"P{position_id}",
        name=f"Position {position_id}",
        last_logged=last_logged,
        breaches=breaches,
    )


def test_month_summary_counts_only_this_calendar_month():
    journal = [
        _entry(1, date(2026, 11, 2)),
        _entry(2, date(2026, 11, 16), "sell"),
        _entry(3, date(2026, 10, 31)),
        _entry(4, date(2025, 11, 5)),
    ]
    summary = month_summary(TODAY, journal, [])
    assert [d.id for d in summary.decisions] == [2, 1]
    assert (summary.year, summary.month) == (2026, 11)
    assert summary.sentence == (
        "Im November: 2 Entscheidungen, keine Position verletzt ihre Ausstiegsbedingung, "
        f"keine Position seit über {PORTFOLIO_REVIEW_DAYS} Tagen ungeprüft."
    )


def test_month_summary_flags_exits_and_positions_unreviewed_beyond_the_period():
    limit = PORTFOLIO_REVIEW_DAYS
    positions = [
        _position(1, TODAY, ("Kurs 9 liegt auf oder unter deiner Schwelle 10",)),
        _position(2, TODAY - timedelta(days=limit)),  # exactly at the limit: still reviewed
        _position(3, TODAY - timedelta(days=limit + 1)),  # one day beyond: unreviewed
        _position(4, TODAY - timedelta(days=limit + 30), ("Reichweite rund 8 Monate",)),
    ]
    summary = month_summary(TODAY, [_entry(9, TODAY)], positions)
    assert summary.review_days == PORTFOLIO_REVIEW_DAYS
    assert [p.id for p in summary.exits] == [1, 4]
    assert [p.id for p in summary.unreviewed] == [3, 4]
    assert summary.sentence == (
        "Im November: 1 Entscheidung, 2 Positionen verletzen ihre Ausstiegsbedingung, "
        f"2 Positionen seit über {limit} Tagen ungeprüft."
    )


def test_month_summary_singular_wording():
    positions = [_position(1, TODAY - timedelta(days=PORTFOLIO_REVIEW_DAYS + 1), ("x",))]
    summary = month_summary(TODAY, [_entry(1, TODAY)], positions)
    assert summary.sentence.endswith(
        f"1 Entscheidung, 1 Position verletzt ihre Ausstiegsbedingung, "
        f"1 Position seit über {PORTFOLIO_REVIEW_DAYS} Tagen ungeprüft."
    )


def test_exit_breaches_only_count_known_crossed_thresholds():
    assert exit_breaches(10.0, 10.0, None, None) == [
        "Kurs 10 liegt auf oder unter deiner Schwelle 10"
    ]
    assert exit_breaches(10.5, 10.0, None, None) == []
    assert exit_breaches(None, 10.0, None, None) == []  # no quote, no claim
    assert exit_breaches(10.0, None, None, None) == []  # no threshold set
    assert exit_breaches(10.0, 0.0, None, None) == []  # 0 clears a threshold
    assert exit_breaches(10.0, None, 7.5, 12.0) == [
        "Reichweite rund 8 Monate liegt unter deiner Schwelle 12"
    ]
    assert exit_breaches(10.0, None, None, 12.0) == []  # runway unknown
    assert exit_breaches(10.0, None, 14.0, 12.0) == []


def test_month_summary_in_portfolio_payload(client, session):
    holding = {
        "symbol": "nem",
        "quantity": 10,
        "avg_price": 40.0,
        "intent": "Goldhebel im Aufschwung",
        "exit_condition": "Verkauf bei AISC über 1500",
        "stop_price": STOP_NEVER_HIT,  # the demo quote is far below: the threshold is crossed
    }
    made = client.post(f"{API}/portfolio/holdings", json=holding).json()
    month = client.get(f"{API}/portfolio").json()["month"]
    assert [d["symbol"] for d in month["decisions"]] == ["NEM"]
    assert month["decisions"][0]["kind"] == "buy" and month["decisions"][0]["day"]
    assert [p["symbol"] for p in month["exits"]] == ["NEM"]
    assert "Kurs" in month["exits"][0]["breaches"][0]
    assert month["unreviewed"] == []
    assert month["sentence"].startswith(
        f"Im {MONTHS_DE[utcnow().date().month - 1]}: 1 Entscheidung"
    )

    # the last logged decision was long ago: the position is unreviewed, not in this month
    old = utcnow().date() - timedelta(days=PORTFOLIO_REVIEW_DAYS + 30)
    for decision in session.scalars(select(Decision)):
        decision.day = old
    session.commit()
    month = client.get(f"{API}/portfolio").json()["month"]
    assert month["decisions"] == []
    assert [p["symbol"] for p in month["unreviewed"]] == ["NEM"]
    assert month["unreviewed"][0]["last_logged"] == old.isoformat()
    assert month["review_days"] == PORTFOLIO_REVIEW_DAYS
    assert f"1 Position seit über {PORTFOLIO_REVIEW_DAYS} Tagen ungeprüft" in month["sentence"]

    client.delete(f"{API}/portfolio/holdings/{made['id']}")
    month = client.get(f"{API}/portfolio").json()["month"]
    assert month["exits"] == [] and month["unreviewed"] == []
