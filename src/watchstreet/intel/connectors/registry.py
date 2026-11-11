"""Public mine registers: Wikidata (world-wide, with operators) and USGS MRDS (deposit records).

Both are read through the guarded :class:`Fetcher`. A registry tells where something is and what
it is called; it is not a source for production, cost or current status.
"""

import json
import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode

from defusedxml import ElementTree

from watchstreet.constants import REGISTRY_MAX_RESULTS
from watchstreet.intel.fetch import Fetcher, FetchError

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
MRDS_ENDPOINT = "https://mrdata.usgs.gov/services/wfs/mrds"
MINE_CLASS = "wd:Q820477"  # Wikidata: mine
POINT = re.compile(r"Point\(([-\d.]+) ([-\d.]+)\)")
NAMESPACES = {"gml": "http://www.opengis.net/gml", "ms": "http://mapserver.gis.umn.edu/mapserver"}
# words in a Wikidata product label -> our commodity key
PRODUCT_WORDS = {
    "copper": "copper", "chalcopyrite": "copper", "gold": "gold", "silver": "silver",
    "uranium": "uranium", "uraninite": "uranium",
}  # fmt: skip
MRDS_CODES = {"CU": "copper", "AU": "gold", "AG": "silver", "U": "uranium"}
MRDS_KEPT_STATUS = ("Producer", "Past Producer", "Prospect")


@dataclass(frozen=True)
class Box:
    south: float
    west: float
    north: float
    east: float


@dataclass
class RegistryMine:
    source: str
    external_id: str
    name: str
    lat: float
    lon: float
    url: str
    country: str = ""
    operators: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    commodities: list[str] = field(default_factory=list)
    status_hint: str = ""


def _commodity(label: str) -> str | None:
    lowered = label.lower()
    return next((key for word, key in PRODUCT_WORDS.items() if word in lowered), None)


def _add(values: list[str], value: str | None) -> None:
    if value and value not in values:
        values.append(value)


def _sparql(fetcher: Fetcher, where: str) -> list[dict[str, str]]:
    query = (
        "SELECT ?m ?mLabel ?coord ?countryLabel ?opLabel ?ownLabel ?prodLabel WHERE { "
        f"{where} ?m wdt:P625 ?coord . ?m wdt:P31/wdt:P279* {MINE_CLASS} . "
        "OPTIONAL { ?m wdt:P17 ?country } OPTIONAL { ?m wdt:P137 ?op } "
        "OPTIONAL { ?m wdt:P127 ?own } OPTIONAL { ?m wdt:P1056 ?prod } "
        'SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } } '
        f"LIMIT {REGISTRY_MAX_RESULTS * 4}"  # one mine yields a row per operator/product
    )
    fetched = fetcher.fetch(f"{WIKIDATA_ENDPOINT}?{urlencode({'query': query, 'format': 'json'})}")
    try:
        bindings = json.loads(fetched.text)["results"]["bindings"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        msg = "Wikidata returned an unexpected answer"
        raise FetchError(msg) from exc
    return [{key: cell.get("value", "") for key, cell in row.items()} for row in bindings]


def _merge_wikidata(rows: list[dict[str, str]]) -> list[RegistryMine]:
    """Wikidata returns one row per combination of operator, owner and product."""
    mines: dict[str, RegistryMine] = {}
    for row in rows:
        point = POINT.search(row.get("coord", ""))
        entity = row.get("m", "")
        name = row.get("mLabel", "")
        qid = entity.rsplit("/", 1)[-1]
        if not point or not qid or not name or name == qid:  # unlabelled entries are useless
            continue
        mine = mines.setdefault(
            qid,
            RegistryMine(
                "wikidata", qid, name, float(point.group(2)), float(point.group(1)), entity,
                country=row.get("countryLabel", ""),
            ),
        )  # fmt: skip
        _add(mine.operators, row.get("opLabel"))
        _add(mine.owners, row.get("ownLabel"))
        _add(mine.commodities, _commodity(row.get("prodLabel", "")))
    return list(mines.values())[:REGISTRY_MAX_RESULTS]


def wikidata_in_box(fetcher: Fetcher, box: Box) -> list[RegistryMine]:
    where = (
        "SERVICE wikibase:box { ?m wdt:P625 ?coord . "
        f'bd:serviceParam wikibase:cornerSouthWest "Point({box.west} {box.south})"^^geo:wktLiteral . '
        f'bd:serviceParam wikibase:cornerNorthEast "Point({box.east} {box.north})"^^geo:wktLiteral . }} '
    )
    return _merge_wikidata(_sparql(fetcher, where))


def wikidata_by_company(fetcher: Fetcher, company: str) -> list[RegistryMine]:
    """Mines whose operator or owner carries exactly this English label."""
    label = company.replace("\\", "").replace('"', "")
    where = f'?c rdfs:label "{label}"@en . {{ ?m wdt:P137 ?c }} UNION {{ ?m wdt:P127 ?c }} '
    return _merge_wikidata(_sparql(fetcher, where))


def mrds_in_box(fetcher: Fetcher, box: Box) -> list[RegistryMine]:
    """USGS Mineral Resources Data System: producers, past producers and prospects in the box."""
    params = {
        "service": "WFS", "version": "1.1.0", "request": "GetFeature", "typeName": "mrds",
        "maxFeatures": str(REGISTRY_MAX_RESULTS * 4),
        "bbox": f"{box.west},{box.south},{box.east},{box.north}",
    }  # fmt: skip
    fetched = fetcher.fetch(f"{MRDS_ENDPOINT}?{urlencode(params, quote_via=quote)}")
    try:
        root = ElementTree.fromstring(fetched.text)
    except ElementTree.ParseError as exc:
        msg = "USGS MRDS returned invalid XML"
        raise FetchError(msg) from exc
    mines: list[RegistryMine] = []
    for record in root.iterfind(".//ms:mrds", NAMESPACES):

        def text(tag: str, node: object = record) -> str:
            return (node.findtext(tag, "", NAMESPACES) or "").strip()  # type: ignore[attr-defined]

        position = text(".//gml:pos").split()
        codes = [MRDS_CODES[c] for c in text("ms:code_list").split() if c in MRDS_CODES]
        status = text("ms:dev_stat")
        if len(position) != 2 or not codes or status not in MRDS_KEPT_STATUS:  # noqa: PLR2004
            continue
        mines.append(
            RegistryMine(
                "mrds", text("ms:dep_id"), text("ms:site_name"), float(position[0]),
                float(position[1]), text("ms:url"), commodities=list(dict.fromkeys(codes)),
                status_hint=status,
            )
        )  # fmt: skip
    return mines[:REGISTRY_MAX_RESULTS]
