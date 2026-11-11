"""Country lookup and great-circle distance (pure)."""

import json
import math
from functools import lru_cache
from pathlib import Path

from watchstreet.constants import EARTH_RADIUS_KM

DATA = Path(__file__).parent / "data" / "countries.json"

# common names -> the name used by the world map data
ALIASES: dict[str, str] = {
    "usa": "United States of America",
    "us": "United States of America",
    "united states": "United States of America",
    "uk": "United Kingdom",
    "drc": "Dem. Rep. Congo",
    "democratic republic of the congo": "Dem. Rep. Congo",
    "congo (kinshasa)": "Dem. Rep. Congo",
    "russian federation": "Russia",
    "south korea": "South Korea",
    "czech republic": "Czechia",
    "ivory coast": "Côte d'Ivoire",
    "burma": "Myanmar",
    "turkiye": "Turkey",
    "türkiye": "Turkey",
}


@lru_cache(maxsize=1)
def countries() -> dict[str, tuple[float, float]]:
    """Map name -> (lat, lon) label point."""
    return {c["name"]: (c["lat"], c["lon"]) for c in json.loads(DATA.read_text(encoding="utf-8"))}


def normalize_country(raw: str) -> str:
    """Return the canonical map name for ``raw``, or '' if unknown."""
    text = raw.strip()
    if not text:
        return ""
    known = countries()
    if text in known:
        return text
    lowered = text.lower()
    alias = ALIASES.get(lowered)
    if alias:
        return alias
    return next((name for name in known if name.lower() == lowered), "")


def country_point(raw: str) -> tuple[float, float] | None:
    name = normalize_country(raw)
    return countries().get(name)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
