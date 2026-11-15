"""Official mineral-tenure registers (claims, leases) published as ArcGIS map services.

Each register is one row in ``REGISTERS``: where it is valid, where its map service lives and how
its columns are called. The browser draws the register's own map image over the base map; a click
asks ``claims_at`` who holds the ground at that point. Answers are shown, never stored as facts.
"""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import urlencode, urlparse

from watchstreet.constants import CLAIM_TEXT_CHARS, MAX_CLAIMS_PER_POINT
from watchstreet.intel.fetch import Fetcher, FetchError

MS_PER_S = 1000
HECTARES_PER_ACRE = 0.404686


@dataclass(frozen=True)
class Register:
    key: str
    label: str
    authority: str
    south: float
    west: float
    north: float
    east: float
    service: str  # ArcGIS MapServer base URL
    layer: int
    min_zoom: int  # the service draws nothing when zoomed out further
    number: str
    kind: str
    holder: str = ""  # some registers publish the holder only in their own case system
    expires: str = ""
    area: str = ""
    area_factor: float = 1.0  # converts the register's area unit to hectares
    show: tuple[int, ...] = ()  # layers drawn on the map; default is the queried layer
    name: str = ""
    status: str = ""
    holders: str = ""  # column with the number of holders, if the register has one

    def covers(self, lat: float, lon: float) -> bool:
        return self.south <= lat <= self.north and self.west <= lon <= self.east

    @property
    def host(self) -> str:
        return urlparse(self.service).hostname or ""

    @property
    def tiles(self) -> str:
        """Tile URL template for the map (the map library fills in the bounding box)."""
        layers = ",".join(str(layer) for layer in self.show or (self.layer,))
        return (
            f"{self.service}/export?bbox={{bbox-epsg-3857}}&bboxSR=3857&imageSR=3857"
            f"&size=256,256&format=png32&transparent=true&layers=show:{layers}&f=image"
        )

    @property
    def columns(self) -> list[str]:
        optional = (self.holder, self.expires, self.area, self.name, self.status, self.holders)
        return [self.number, self.kind] + [column for column in optional if column]


REGISTERS: tuple[Register, ...] = (
    Register(
        key="bc",
        label="British Columbia (Kanada)",
        authority="Mineral Titles Online, Province of British Columbia",
        south=48.2,
        west=-139.1,
        north=60.1,
        east=-114.0,
        service="https://delivery.maps.gov.bc.ca/arcgis/rest/services/mpcm/bcgwpub/MapServer",
        layer=213,
        min_zoom=8,
        number="TENURE_NUMBER_ID",
        holder="OWNER_NAME",
        kind="TITLE_TYPE_DESCRIPTION",
        expires="GOOD_TO_DATE",
        area="AREA_IN_HECTARES",
        name="CLAIM_NAME",
        holders="NUMBER_OF_OWNERS",
    ),
    Register(
        key="wa",
        label="Westaustralien",
        authority="Mining Tenements (DMIRS-003), Government of Western Australia",
        south=-35.5,
        west=112.5,
        north=-13.5,
        east=129.1,
        service=(
            "https://public-services.slip.wa.gov.au/public/rest/services/"
            "SLIP_Public_Services/Industry_and_Mining/MapServer"
        ),
        layer=3,
        min_zoom=7,
        number="fmt_tenid",
        holder="holder1",
        kind="type",
        expires="enddate",
        area="legal_area",
        status="tenstatus",
        holders="holdercnt",
    ),
    Register(
        key="on",
        label="Ontario (Kanada)",
        authority="Mining Lands Administration System, Province of Ontario",
        south=41.6,
        west=-95.2,
        north=56.9,
        east=-74.3,
        service="https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/MLAS/mlas_op/MapServer",
        layer=1,
        show=(1, 3, 5),  # claims, leases, patents; the holder is published for claims only
        min_zoom=9,
        number="TENURE_NUMBER_ID",
        holder="HOLDER",
        kind="TITLE_TYPE_DESC",
        expires="CLAIM_DUE_DATE",
        status="TENURE_STATUS_DESC",
    ),
    Register(
        key="us",
        label="USA (Bundesland, v. a. Weststaaten)",
        authority="BLM Mineral & Land Records System (MLRS), U.S. Bureau of Land Management",
        south=31.0,
        west=-125.0,
        north=49.0,
        east=-102.0,
        service=(
            "https://nlsdbpubgis.blm.gov/arcgis/rest/services/Mining_Claims/MiningClaims/MapServer"
        ),
        layer=1,
        min_zoom=11,
        number="CSE_NR",
        kind="BLM_PROD",
        area="RCRD_ACRS",
        area_factor=HECTARES_PER_ACRE,
        name="CSE_NAME",
        status="CSE_DISP",
    ),
)
HOSTS = tuple(sorted({register.host for register in REGISTERS}))


@dataclass(frozen=True)
class Claim:
    register: str
    number: str
    name: str
    holder: str
    other_holders: int
    kind: str
    status: str
    expires: date | None
    area_ha: float | None


def registers_at(lat: float, lon: float) -> list[Register]:
    """Registers whose area contains the point; near a border more than one can apply."""
    return [r for r in REGISTERS if r.covers(lat, lon)]


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()[:CLAIM_TEXT_CHARS]


def _day(value: object) -> date | None:
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value / MS_PER_S, UTC).date()
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _area(register: Register, row: dict[str, object]) -> float | None:
    raw = _number(row.get(register.area)) if register.area else None
    return None if raw is None else round(raw * register.area_factor, 2)


def parse(register: Register, body: str) -> list[Claim]:
    """Read one ArcGIS query answer. Untrusted: wrong shapes raise, texts are cut to length."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        msg = "register returned invalid JSON"
        raise FetchError(msg) from exc
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        msg = "register returned an unexpected answer"
        raise FetchError(msg)
    claims: list[Claim] = []
    for feature in data["features"][:MAX_CLAIMS_PER_POINT]:
        row = feature.get("attributes") if isinstance(feature, dict) else None
        if not isinstance(row, dict):
            continue
        count = _number(row.get(register.holders)) if register.holders else None
        claims.append(
            Claim(
                register=register.key,
                number=_text(row.get(register.number)),
                name=_text(row.get(register.name)) if register.name else "",
                holder=_text(row.get(register.holder)) if register.holder else "",
                other_holders=max(int(count) - 1, 0) if count else 0,
                kind=_text(row.get(register.kind)),
                status=_text(row.get(register.status)) if register.status else "",
                expires=_day(row.get(register.expires)) if register.expires else None,
                area_ha=_area(register, row),
            )
        )
    return claims


def claims_at(fetcher: Fetcher, register: Register, lat: float, lon: float) -> list[Claim]:
    query = urlencode(
        {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": ",".join(register.columns),
            "returnGeometry": "false",
            "f": "json",
        }
    )
    return parse(register, fetcher.fetch(f"{register.service}/{register.layer}/query?{query}").text)
