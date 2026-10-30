"""Parsing of untrusted tool arguments coming from the model.

Every helper either returns a clean value or raises ``ToolError`` with a message the model can
act on (the message is fed back to it as the tool result).
"""

import json
from enum import Enum
from typing import Any

from watchstreet.agents.tools import ToolError


def text_arg(args: dict[str, Any], key: str) -> str:
    """Required, non-blank text argument (stripped)."""
    value = str(args.get(key, "")).strip()
    if not value:
        msg = f"'{key}' is required"
        raise ToolError(msg)
    return value


def number_arg(args: dict[str, Any], key: str) -> float | None:
    """Optional number: ``None`` when missing or blank, ``ToolError`` when not numeric."""
    raw = args.get(key)
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        msg = f"'{key}' must be a number"
        raise ToolError(msg) from exc


def int_arg(args: dict[str, Any], key: str, default: int = 0) -> int:
    """Optional integer built on ``number_arg``; ``default`` when missing, blank or zero."""
    return int(number_arg(args, key) or default)


def enum_arg[E: Enum](args: dict[str, Any], key: str, enum: type[E]) -> E:
    """Required argument that must be one of the enum's values."""
    try:
        return enum(str(args.get(key)))
    except ValueError as exc:
        allowed = ", ".join(str(member.value) for member in enum)
        msg = f"'{key}' must be one of: {allowed}"
        raise ToolError(msg) from exc


def choice_arg(args: dict[str, Any], key: str, allowed: tuple[str, ...] | list[str]) -> str:
    """Argument that must be one of ``allowed`` (the model sees the allowed values on error)."""
    value = str(args.get(key, ""))
    if value not in allowed:
        msg = f"'{key}' must be one of: {', '.join(allowed)}"
        raise ToolError(msg)
    return value


def to_json(data: object) -> str:
    """Compact JSON for tool results (fewer tokens than pretty-printing)."""
    return json.dumps(data, ensure_ascii=False, default=str, separators=(",", ":"))
