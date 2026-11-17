"""Purchasing-power band: pure logic, the gold connector, the service and the API."""

import math
from datetime import date

import httpx
import pytest
from sqlalchemy import event

from watchstreet.analysis import purchasing as pp
from watchstreet.intel.connectors import gold_monthly
from watchstreet.intel.demo import DemoTransport, demo_resolver, macro_history
from watchstreet.intel.fetch import Fetcher, FetchError

API = "/api/v1"
START = date(2010, 1, 1)


def months(count: int, start: date = START) -> list[date]:
    return [pp.shift_months(start, i) for i in range(count)]


def growing(rate: float, count: int = 36, start: date = START) -> pp.Monthly:
    """A series that grows by ``rate`` (log) per month, starting at 100."""
    return {m: 100 * math.exp(rate * i) for i, m in enumerate(months(count, start))}


def stick(key: str, rate: float, count: int = 36) -> pp.Yardstick:
    return pp.Yardstick(key, key, key, growing(rate, count))


# ---------------------------------------------------------------- pure logic


def test_monthly_means_average_each_calendar_month():
    points = [(date(2020, 1, 2), 1.0), (date(2020, 1, 30), 3.0), (date(2020, 2, 5), 10.0)]
    assert pp.monthly_means(points) == {date(2020, 1, 1): 2.0, date(2020, 2, 1): 10.0}
    assert pp.shift_months(date(2020, 11, 1), 3) == date(2021, 2, 1)
    assert pp.shift_months(date(2020, 1, 1), -12) == date(2019, 1, 1)
    assert pp.to_pct(100 * math.log(2)) == pytest.approx(100)


def test_band_since_start_has_the_known_changes():
    """Value grows 2 %/month (log); yardsticks 0, 1, 3, 4 %: changes are (2 - g) × months."""
    rates = {"a": 0.0, "b": 0.01, "c": 0.03, "d": 0.04}
    sticks = [stick(k, r) for k, r in rates.items()]
    band = pp.band(growing(0.02), sticks)
    assert band.months[0] == START and len(band.months) == 36
    last = 35
    for key, rate in rates.items():
        assert band.changes[key][0] == pytest.approx(0)
        assert band.changes[key][last] == pytest.approx(100 * (0.02 - rate) * last)
    assert band.high[last] == pytest.approx(70) and band.low[last] == pytest.approx(-70)
    # four yardsticks: the inner band drops one at each end, the median is the middle pair's mean
    assert band.inner_high[last] == pytest.approx(35) and band.inner_low[last] == pytest.approx(-35)
    assert band.median[last] == pytest.approx(0)
    assert (band.up[last], band.down[last]) == (2, 2)
    assert pp.verdict(band.up[last], band.down[last], 4) == pp.SPLIT


def test_the_dollar_cancels_out():
    """Debasing the dollar along any path (every price times the same factor) changes nothing."""
    sticks = [stick("a", 0.002), stick("b", 0.005), stick("c", -0.001)]
    subject = growing(0.004)
    factor = {m: 1 + 0.5 * math.sin(i) + i * 0.1 for i, m in enumerate(months(36))}
    debased_sticks = [
        pp.Yardstick(y.key, y.label, y.unit, {m: v * factor[m] for m, v in y.values.items()})
        for y in sticks
    ]
    debased = {m: v * factor[m] for m, v in subject.items()}
    for mode in pp.MODES:
        plain, moved = pp.band(subject, sticks, mode), pp.band(debased, debased_sticks, mode)
        for key in plain.changes:
            assert moved.changes[key] == pytest.approx(plain.changes[key])


def test_band_width_depends_on_the_yardsticks_only():
    sticks = [stick("a", 0.0), stick("b", 0.01), stick("c", 0.02)]
    first, second = pp.band(growing(0.05), sticks), pp.band(growing(-0.03), sticks)
    widths = [h - lo for h, lo in zip(first.high, first.low, strict=True)]
    assert widths == pytest.approx([h - lo for h, lo in zip(second.high, second.low, strict=True)])
    dollar = pp.band(None, sticks)  # one US dollar: the band of the yardsticks alone
    assert dollar.changes["b"][-1] == pytest.approx(-100 * 0.01 * 35)
    assert [h - lo for h, lo in zip(dollar.high, dollar.low, strict=True)] == pytest.approx(widths)


def test_rolling_mode_compares_with_twelve_months_earlier():
    band = pp.band(growing(0.01), [stick("a", 0.0), stick("b", 0.02)], pp.ROLLING)
    assert band.months[0] == pp.shift_months(START, 12) and len(band.months) == 24
    assert band.changes["a"] == pytest.approx([12.0] * 24)
    assert band.changes["b"] == pytest.approx([-12.0] * 24)
    later = pp.band(growing(0.01), [stick("a", 0.0)], pp.ROLLING, date(2012, 1, 15))
    assert later.months[0] == date(2012, 1, 1)


def test_missing_months_are_skipped_not_filled():
    gappy = growing(0.0)
    del gappy[date(2010, 6, 1)]
    band = pp.band(growing(0.01), [pp.Yardstick("a", "a", "a", gappy), stick("b", 0.0)])
    assert date(2010, 6, 1) not in band.months and len(band.months) == 35
    rolling = pp.band(growing(0.01), [pp.Yardstick("a", "a", "a", gappy)], pp.ROLLING)
    assert date(2011, 6, 1) not in rolling.months  # its year-ago month is missing


def test_start_month_and_errors():
    sticks = [stick("a", 0.0)]
    assert pp.band(growing(0.01), sticks, start=date(2011, 3, 20)).months[0] == date(2011, 3, 1)
    assert pp.band(growing(0.01), sticks, start=date(1990, 1, 1)).months[0] == START
    assert pp.band(growing(0.01), sticks, start=date(2011, 3, 1)).first == START
    with pytest.raises(pp.BandError):
        pp.band(growing(0.01), sticks, start=date(2012, 6, 1))  # too few months left
    with pytest.raises(pp.BandError):
        pp.band(growing(0.01), [])
    with pytest.raises(pp.BandError):
        pp.band(growing(0.01, count=5), [stick("a", 0.0, count=5)])


def test_verdict_classes():
    assert pp.verdict(5, 0, 5) == pp.ALL_UP
    assert pp.verdict(0, 5, 5) == pp.ALL_DOWN
    assert pp.verdict(3, 2, 5) == pp.MOST_UP
    assert pp.verdict(1, 3, 5) == pp.MOST_DOWN
    assert pp.verdict(2, 2, 5) == pp.SPLIT


def test_summary_finds_the_lone_dissenter():
    """Two yardsticks fall a little, the 'gold' one rises fast: gold disagrees alone."""
    sticks = [stick("cpi", 0.002), stick("wage", 0.003), stick("gold", 0.05)]
    band = pp.band(growing(0.02), sticks)
    info = pp.summarize(band)
    assert info.verdict == pp.MOST_UP
    assert info.alone["gold"] > 0 and info.alone["cpi"] == 0
    assert 0 <= info.unanimous_share < 1
    assert info.widest_month == band.months[-1]
    assert info.widest_points == pytest.approx(100 * (0.05 - 0.002) * 35)


def test_sentences_follow_the_numbers():
    labels = {"cpi": "Warenkörben", "wage": "Arbeitsstunden", "gold": "Gold"}
    rising = pp.band(growing(0.03), [stick("cpi", 0.0), stick("wage", 0.01)])
    text = pp.sentence("Kupfer", rising, labels)
    assert text.startswith("Seit Januar 2010 gewann Kupfer nach allen 2 Massstäben")
    assert "In 100 % der Monate" in text and "allein" not in text
    majority = pp.band(growing(0.02), [stick("cpi", 0.0), stick("wage", 0.0), stick("gold", 0.05)])
    text = pp.sentence("Kupfer", majority, labels)
    assert "nach 2 von 3 Massstäben" in text and "dagegen gemessen in Gold −" in text
    assert "allein die Messung in Gold" in text
    split = pp.band(growing(0.01), [stick("cpi", 0.0), stick("gold", 0.02)], pp.ROLLING)
    text = pp.sentence("Öl", split, labels)
    assert text.startswith("In den 12 Monaten bis Dezember 2012 hängt das Urteil über Öl")
    assert "gewonnen in Warenkörben, verloren in Gold" in text
    falling = pp.band(growing(-0.02), [stick("cpi", 0.0), stick("gold", 0.0)])
    assert "verlor Öl nach allen 2 Massstäben" in pp.sentence("Öl", falling, labels)


# ---------------------------------------------------------------- monthly gold connector


def test_gold_connector_parses_and_refuses():
    body = "Date,Price\n2003-01,357.0\n2003-02,\n2003-03,340.5\n"
    assert gold_monthly.parse(body) == [(date(2003, 1, 1), 357.0), (date(2003, 3, 1), 340.5)]
    with pytest.raises(FetchError):
        gold_monthly.parse("Day,Value\n2003-01,1\n")
    with pytest.raises(FetchError):
        gold_monthly.parse("Date,Price\nJanuar,357\n")


def test_demo_serves_the_bundled_gold_history():
    fetch = Fetcher(httpx.Client(transport=DemoTransport()), demo_resolver, min_interval_s=0)
    rows = gold_monthly.observations(fetch, gold_monthly.SERIES, date(2003, 1, 1))
    bundled = macro_history()[gold_monthly.SERIES.key]
    assert len(rows) == len(bundled) and rows[0][0] == date(2003, 1, 1)
    assert 200 < rows[0][1] < 500  # US dollars per ounce in 2003
    recent = gold_monthly.observations(fetch, gold_monthly.SERIES, date(2025, 1, 1))
    assert recent and min(day for day, _ in recent) >= date(2025, 1, 1)


# ---------------------------------------------------------------- service and API


@pytest.fixture
def synced(container, session):
    from watchstreet.services import macro

    macro.sync(session, container.fetcher)
    session.commit()
    return session


def test_api_band_on_the_real_bundled_history(client, synced):
    data = client.get(f"{API}/charts/purchasing", params={"key": "copper"}).json()
    assert data["subject"] == {"key": "PCOPPUSDM", "label": "Kupfer (IMF, Monatsmittel)",
                               "synthetic": False}  # fmt: skip
    assert [y["key"] for y in data["yardsticks"]] == [
        "CPIAUCSL", "AHETPI", "M2SL", "GOLDWB", "DCOILWTICO",
    ]  # fmt: skip
    assert data["start"] == "2003-01-01" and data["first"] == "2003-01-01"
    assert len(data["months"]) == len(data["median"]) == len(data["lines"]["GOLDWB"])
    bounds = zip(data["low"], data["median"], data["high"], strict=True)
    assert all(lo <= m <= hi for lo, m, hi in bounds)
    assert data["plain"].startswith("Seit Januar 2003") and "Kupfer" in data["plain"]
    # the 2008 crash: copper lost against goods, wages and money within twelve months
    rolling = client.get(f"{API}/charts/purchasing", params={"key": "PCOPPUSDM", "mode": "rolling"})
    year = rolling.json()
    crash = year["months"].index("2008-12-01")
    assert all(year["lines"][k][crash] < -40 for k in ("CPIAUCSL", "AHETPI", "M2SL", "GOLDWB"))


def test_api_gold_drops_itself_and_keeps_colours(client, synced):
    data = client.get(f"{API}/charts/purchasing", params={"key": "gold", "start": "2011-08"}).json()
    assert data["subject"]["key"] == "GOLDWB" and data["start"] == "2011-08-01"
    assert [s["label"] for s in data["skipped"]] == ["Gold"]
    assert {y["key"]: y["slot"] for y in data["yardsticks"]}["DCOILWTICO"] == 4


def test_api_dollar_synthetic_and_fallbacks(client, synced):
    dollar = client.get(f"{API}/charts/purchasing", params={"key": "USD"}).json()
    assert dollar["summary"]["verdict"] == pp.ALL_DOWN  # the dollar lost against every yardstick
    objects = {o["key"]: o for o in dollar["objects"]}
    assert objects["USD"]["synthetic"] is False and "gold" not in objects  # long history instead
    assert objects["silver"]["synthetic"] and objects["S:DACC"]["synthetic"]
    share = client.get(f"{API}/charts/purchasing", params={"key": "S:DACC"}).json()
    assert share["subject"]["synthetic"] and share["plain"].startswith("Achtung")
    rate = client.get(f"{API}/charts/purchasing", params={"key": "DFII10"}).json()
    assert rate["subject"]["key"] == "GOLDWB" and "kein Preis" in rate["notice"]
    for params in ({"mode": "weekly"}, {"start": "letztes Jahr"}, {"start": "2026-01"}):
        assert client.get(f"{API}/charts/purchasing", params=params).status_code == 400


def test_band_queries_do_not_grow_with_the_number_of_shares(container, synced):
    from watchstreet.models import SharePrice, Stock
    from watchstreet.services import purchasing

    def selects() -> int:
        count = 0

        def listen(_conn, _cursor, statement, *_args):
            nonlocal count
            count += statement.lstrip().upper().startswith("SELECT")

        event.listen(container.engine, "before_cursor_execute", listen)
        try:
            purchasing.band(synced, "PCOPPUSDM")
        finally:
            event.remove(container.engine, "before_cursor_execute", listen)
        return count

    before = selects()
    for i in range(3):
        synced.add(Stock(symbol=f"ZZ{i}", name=f"Test {i}", currency="USD"))
        synced.add(SharePrice(symbol=f"ZZ{i}", day=date(2024, 1, 5), close=1.0, source="demo"))
    synced.flush()
    assert selects() == before
