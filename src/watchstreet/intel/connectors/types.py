"""Shared connector types."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RawItem:
    url: str
    title: str
    text: str
    published_at: datetime | None
    publisher: str
    kind: str = "news"
