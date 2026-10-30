"""One-shot confirmation messages shown after a redirect (``?flash=<code>``).

Only codes from this table are ever rendered, so the query string cannot inject text.
"""

from urllib.parse import quote

FLASH_PARAM = "flash"

FLASH_MESSAGES: dict[str, str] = {
    "holding_added": "Position eingetragen. Die Bestandsaufnahme läuft im Hintergrund.",
    "holding_updated": "Position gespeichert.",
    "holding_removed": "Position entfernt. Wissen und Tickets bleiben erhalten.",
    "watch_added": "Aktie wird beobachtet. Die Kaufprüfung läuft im Hintergrund.",
    "watch_removed": "Aus der Watchlist entfernt.",
    "profile_set": "Profil gesetzt. Die Bewertung wird neu berechnet.",
    "datapoint_added": "Datenpunkt gespeichert. Die Bewertung wird neu berechnet.",
    "datapoint_removed": "Datenpunkt gelöscht. Die Bewertung wird neu berechnet.",
    "briefing_requested": "Briefing wird neu erzeugt. Die Seite aktualisiert sich selbst.",
    "ticket_created": "Ticket angelegt.",
    "ticket_retried": "Ticket erneut eingereiht.",
    "ticket_cancelled": "Ticket abgebrochen.",
    "scan_requested": "Aktualisierung angestoßen. Neue Meldungen erscheinen in Kürze.",
    "feed_added": "Quelle hinzugefügt.",
    "feed_toggled": "Quelle umgeschaltet.",
    "feed_removed": "Quelle gelöscht.",
    "relation_added": "Beziehung gespeichert.",
    "location_set": "Standort gespeichert.",
}


def with_flash(url: str, code: str | None) -> str:
    """Append ``flash=<code>`` to ``url`` (before any ``#fragment``)."""
    if code is None:
        return url
    path, hash_sep, fragment = url.partition("#")
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}{FLASH_PARAM}={quote(code)}{hash_sep}{fragment}"
