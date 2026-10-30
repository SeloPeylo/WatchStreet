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


def dt(value: datetime | None) -> str:
    return EMPTY if value is None else value.strftime("%d.%m.%Y %H:%M")


def sign_class(value: float | None) -> str:
    if value is None or value == 0:
        return ""
    return "pos" if value > 0 else "neg"


def preview(text: str) -> str:
    return text if len(text) <= TEXT_PREVIEW_CHARS else text[: TEXT_PREVIEW_CHARS - 1] + "…"


def register_filters(env: Environment) -> None:
    filters: dict[str, Any] = {
        "money": money,
        "pct": pct,
        "number": number,
        "dt": dt,
        "sign": sign_class,
        "preview": preview,
    }
    env.filters.update(filters)
