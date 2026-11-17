"""Snapshot the FRED history behind the demo macro view into one gzip file.

Maintenance tool, run by hand (not application code):

    python scripts/snapshot_macro_history.py

Downloads every series in ``fred.SERIES`` and the World Bank monthly gold price
(``intel/connectors/gold_monthly.py``) from ``MACRO_HISTORY_START_YEAR`` on, with the same URL
and parameters that ``services/macro.py::sync`` uses, and writes
``src/watchstreet/data/macro_history.csv.gz`` with rows ``series,day,value``. Values are kept in
the unit FRED publishes; the app applies ``Series.scale`` when it reads them, as it does for live
data. Days without a value (".") are dropped, never filled. If any series fails or has no
value, nothing is written, so the bundle is never partly stale.

The download uses httpx directly because this is a maintenance script, not an agent path; it does
not go through ``intel/fetch.py``.
"""

import gzip
import io
import sys
from datetime import date
from pathlib import Path

import httpx

from watchstreet.constants import HTTP_TIMEOUT_S, MACRO_HISTORY_FILE, MACRO_HISTORY_START_YEAR
from watchstreet.intel.connectors import fred, gold_monthly
from watchstreet.intel.fetch import FetchError

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "src/watchstreet/data" / MACRO_HISTORY_FILE
EXIT_FAILED = 1


def _get(client: httpx.Client, url: str) -> str:
    response = client.get(url)
    if response.status_code != httpx.codes.OK:
        msg = f"HTTP {response.status_code}"
        raise FetchError(msg)
    return response.text


def download(client: httpx.Client, series: fred.Series, start: date) -> list[tuple[date, float]]:
    if series.key == gold_monthly.SERIES.key:
        rows = gold_monthly.parse(_get(client, gold_monthly.CSV_URL))
        return [(day, value) for day, value in rows if day >= start]
    return fred.parse(_get(client, f"{fred.CSV_URL}?id={series.key}&cosd={start.isoformat()}"))


def keep_older(points_by_series: dict[str, list[tuple[date, float]]]) -> None:
    """Keep bundled rows older than a fresh download: some sources (S&P 500 on FRED) only serve
    a rolling window, and the past does not change."""
    if not DST.exists():
        return
    first = {key: min(rows)[0] for key, rows in points_by_series.items() if rows}
    text = gzip.decompress(DST.read_bytes()).decode("utf-8")
    for line in text.splitlines()[1:]:
        key, day_text, value = line.split(",")
        day = date.fromisoformat(day_text)
        if key in first and day < first[key]:
            points_by_series[key].append((day, float(value)))


def build(points_by_series: dict[str, list[tuple[date, float]]]) -> bytes:
    lines = ["series,day,value"]
    for key in sorted(points_by_series):
        lines.extend(
            f"{key},{day.isoformat()},{value!r}" for day, value in sorted(points_by_series[key])
        )
    raw = io.BytesIO()
    # mtime=0 and no file name in the header: the same input always gives the same bytes.
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(("\n".join(lines) + "\n").encode("utf-8"))
    return raw.getvalue()


def main() -> int:
    start = date(MACRO_HISTORY_START_YEAR, 1, 1)
    points: dict[str, list[tuple[date, float]]] = {}
    failed: list[str] = []
    with httpx.Client(timeout=HTTP_TIMEOUT_S, follow_redirects=False) as client:
        for series in (*fred.SERIES, gold_monthly.SERIES):
            try:
                rows = download(client, series, start)
            except (FetchError, httpx.HTTPError) as exc:
                print(f"{series.key:<14} FAILED: {exc}")
                failed.append(series.key)
                continue
            if not rows:
                print(f"{series.key:<14} FAILED: no values published")
                failed.append(series.key)
                continue
            points[series.key] = rows
            first, last = min(rows)[0], max(rows)[0]
            print(f"{series.key:<14} rows={len(rows):>6}  first={first}  last={last}")

    if failed:
        print(f"Nothing written: {len(failed)} series failed: {', '.join(failed)}")
        return EXIT_FAILED
    keep_older(points)
    data = build(points)
    DST.write_bytes(data)
    print(f"Wrote {DST} ({len(data)} bytes, {len(points)} series)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
