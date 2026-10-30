"""Jinja filters for numbers, dates and status badges."""

from datetime import datetime
from typing import Any

from jinja2 import Environment

from watchstreet.constants import TEXT_PREVIEW_CHARS

EMPTY = "–"


def money(value: float | None, currency: str = "") -> str:
    if value is None:
        return EMPTY
    return f"{value:,.2f} {currency}".strip().replace(",", " ")


def pct(value: float | None) -> str:
    return EMPTY if value is None else f"{value:+.2f} %"


def number(value: float | None) -> str:
    return EMPTY if value is None else f"{value:,.4f}".rstrip("0").rstrip(".").replace(",", " ")


BILLION = 1e9
MILLION = 1e6


def price(value: float | None) -> str:
    return EMPTY if value is None else f"{value:,.2f}".replace(",", "\u202f")


def compact(value: float | None) -> str:
    """Large amounts as 'Mrd'/'Mio' for tables; small ones via ``number``."""
    if value is None:
        return EMPTY
    magnitude = abs(value)
    if magnitude >= BILLION:
        return f"{value / BILLION:.2f} Mrd".replace(".", ",")
    if magnitude >= MILLION:
        return f"{value / MILLION:.1f} Mio".replace(".", ",")
    return number(value)


def dt(value: datetime | None) -> str:
    return EMPTY if value is None else value.strftime("%d.%m.%Y %H:%M")


def sign_class(value: float | None) -> str:
    if value is None or value == 0:
        return ""
    return "pos" if value > 0 else "neg"


def safe_url(url: str) -> str:
    """Only http(s) links are ever rendered as hrefs."""
    return url if url.startswith(("http://", "https://")) else "#"


def preview(text: str) -> str:
    return text if len(text) <= TEXT_PREVIEW_CHARS else text[: TEXT_PREVIEW_CHARS - 1] + "…"


def register_filters(env: Environment) -> None:
    filters: dict[str, Any] = {
        "money": money,
        "pct": pct,
        "number": number,
        "compact": compact,
        "price": price,
        "dt": dt,
        "sign": sign_class,
        "preview": preview,
        "safe_url": safe_url,
    }
    env.filters.update(filters)
