"""Reading a pasted or uploaded analysis table into rows (pure).

The first line that names a "name" column is the header; every later line is one mine or project.
Columns are matched by their label, so the order is free and unknown columns are ignored.
"""

import re
from dataclasses import dataclass

from watchstreet.domain import AssetStatus

# canonical field -> accepted column labels (lower case)
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("asset", "mine", "projekt", "project", "objekt", "deposit", "lagerstätte"),
    "company": ("unternehmen", "operator", "betreiber", "owner", "eigentümer", "firma"),
    "commodity": ("rohstoff", "metal", "metall"),
    "country": ("land",),
    "region": ("provinz", "state"),
    "lat": ("latitude", "breite", "breitengrad"),
    "lon": ("lng", "long", "longitude", "länge", "längengrad"),
    "status": ("stage", "stand", "phase"),
    "share": ("anteil", "ownership", "stake", "share_pct"),
    "production": ("produktion", "jahresproduktion", "annual production"),
    "aisc": ("all-in sustaining cost", "all-in sustaining costs"),
    "cash_cost": ("cash cost", "cash costs", "c1"),
    "reserves": ("reserven", "p&p", "2p"),
    "resources": ("ressourcen",),
    "resources_mi": ("m&i", "measured and indicated"),
    "resources_inferred": ("inferred",),
    "grade": ("gehalt",),
    "recovery": ("ausbringung",),
    "capex": ("initial capex", "investition"),
    "expected_production": ("erwartete produktion", "planned production"),
    "expected_aisc": ("erwartete aisc", "planned aisc"),
    "study_npv": ("npv",),
    "study_price": ("preisannahme", "price assumption"),
    "study_stage": ("studie", "study", "studienstand"),
    "study_date": ("studiendatum", "study date"),
    "first_production": ("inbetriebnahme", "first production"),
    "permit_status": ("genehmigung", "genehmigungsstatus", "permit", "permits"),
}
STATUS_ALIASES: dict[str, AssetStatus] = {
    "production": AssetStatus.PRODUCTION,
    "producing": AssetStatus.PRODUCTION,
    "produktion": AssetStatus.PRODUCTION,
    "in produktion": AssetStatus.PRODUCTION,
    "development": AssetStatus.DEVELOPMENT,
    "entwicklung": AssetStatus.DEVELOPMENT,
    "construction": AssetStatus.DEVELOPMENT,
    "bau": AssetStatus.DEVELOPMENT,
    "exploration": AssetStatus.EXPLORATION,
    "care and maintenance": AssetStatus.CARE,
    "care_maintenance": AssetStatus.CARE,
    "ruhend": AssetStatus.CARE,
    "closed": AssetStatus.CLOSED,
    "geschlossen": AssetStatus.CLOSED,
}
DELIMITERS = ("\t", ";", "|", ",")
MIN_COLUMNS = 2
SEPARATOR_CHARS = set("|-: \t")
UNIT_SUFFIX = re.compile(r"\s*[\(\[].*$")
NUMBER = re.compile(r"-?\d[\d.,']*(?:[eE]\d+)?")
THOUSANDS = re.compile(r"-?\d{1,3}(,\d{3})+")
SCALES = {"k": 1e3, "tsd": 1e3, "m": 1e6, "mio": 1e6, "million": 1e6}
SCALES |= {"mrd": 1e9, "bn": 1e9, "billion": 1e9}
SCALE_WORD = re.compile(r"\s*([a-zA-Z]+)")


@dataclass(frozen=True)
class ImportRow:
    line: str  # the row as written: the verbatim quote behind everything taken from it
    fields: dict[str, str]


def canonical(label: str) -> str | None:
    """'AISC (USD/lb)' -> 'aisc'; an unknown label gives ``None``."""
    cleaned = UNIT_SUFFIX.sub("", label).strip(" *_`").lower()
    for key, aliases in FIELD_ALIASES.items():
        if cleaned == key or cleaned in aliases:
            return key
    return None


def _cells(line: str, delimiter: str) -> list[str]:
    text = line.strip()
    if delimiter == "|":
        text = text.strip("|")
    return [cell.strip().strip('"') for cell in text.split(delimiter)]


def _header(line: str) -> tuple[str, dict[int, str]] | None:
    for delimiter in DELIMITERS:
        if delimiter not in line:
            continue
        columns = {
            index: key
            for index, cell in enumerate(_cells(line, delimiter))
            if (key := canonical(cell)) is not None
        }
        if "name" in columns.values() and len(columns) >= MIN_COLUMNS:
            return delimiter, columns
    return None


def parse_table(text: str) -> list[ImportRow]:
    """Rows of the first table found; free text without a table gives an empty list."""
    lines = [line for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        header = _header(line)
        if header is None:
            continue
        delimiter, columns = header
        rows = []
        for raw in lines[index + 1 :]:
            if set(raw) <= SEPARATOR_CHARS:
                continue  # the |---|---| line of a Markdown table
            cells = _cells(raw, delimiter)
            fields = {columns[i]: cell for i, cell in enumerate(cells) if i in columns and cell}
            if fields.get("name"):
                rows.append(ImportRow(raw.strip(), fields))
        return rows
    return []


def number(raw: str) -> float | None:
    """'1,234', '1.234,5', '4.0e9', '190 Mio' or '2.2 USD/lb' -> float; no number gives ``None``."""
    match = NUMBER.search(raw)
    if match is None:
        return None
    token = match.group().replace("'", "").rstrip(".,")
    if "," in token and "." in token:
        token = (
            token.replace(".", "").replace(",", ".")
            if token.rfind(",") > token.rfind(".")
            else token.replace(",", "")
        )
    elif THOUSANDS.fullmatch(token):
        token = token.replace(",", "")
    else:
        token = token.replace(",", ".")
    try:
        value = float(token)
    except ValueError:
        return None
    word = SCALE_WORD.match(raw[match.end() :])
    return value * SCALES.get(word.group(1).lower(), 1.0) if word else value


def status_of(raw: str) -> AssetStatus | None:
    return STATUS_ALIASES.get(raw.strip().lower())


def table_from_records(records: list[dict[str, object]]) -> str:
    """Structured rows (API clients) as a ';' table, so each row has a verbatim line to quote."""
    keys = [key for key in FIELD_ALIASES if any(r.get(key) not in (None, "") for r in records)]
    lines = [";".join(keys)]
    lines += [
        ";".join(
            str(r.get(key, "") if r.get(key) is not None else "").replace(";", ",") for key in keys
        )
        for r in records
    ]
    return "\n".join(lines)
