"""USGS earthquake feed (GeoJSON, free, no key)."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from watchstreet.intel.fetch import Fetcher, FetchError

FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
MS_PER_S = 1000


@dataclass(frozen=True)
class Quake:
    event_id: str
    magnitude: float
    place: str
    lat: float
    lon: float
    time: datetime
    url: str


def recent_quakes(fetcher: Fetcher) -> list[Quake]:
    fetched = fetcher.fetch(FEED)
    try:
        features = json.loads(fetched.text).get("features", [])
    except json.JSONDecodeError as exc:
        msg = "USGS returned invalid JSON"
        raise FetchError(msg) from exc
    quakes: list[Quake] = []
    for feature in features:
        props, coords = (
            feature.get("properties", {}),
            feature.get("geometry", {}).get("coordinates"),
        )
        if not coords or props.get("mag") is None:
            continue
        quakes.append(
            Quake(
                str(feature.get("id", "")),
                float(props["mag"]),
                props.get("place", ""),
                float(coords[1]),
                float(coords[0]),
                datetime.fromtimestamp(props.get("time", 0) / MS_PER_S, UTC),
                props.get("url", ""),
            ),
        )
    return quakes
