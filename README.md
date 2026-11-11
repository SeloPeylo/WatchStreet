# WatchStreet

Kartenzentrierter Recherche-Arbeitsplatz für Rohstoffinvestments: Minen und Projekte als eigenständige
Objekte auf einer Weltkarte, jede Kennzahl mit Herkunft, Szenarien und Stichtage, Recherche nur nach
bewusster Freigabe. Keine Anlageempfehlungen, kein Handel.

```
make install     # Python-Abhängigkeiten (Python 3.12+)
make demo        # baut die Oberfläche (Node 22) und startet mit synthetischen Daten: http://localhost:8000
make check       # ruff, import-linter, mypy --strict, bandit, pytest (>= 80 % Abdeckung)
docker compose up --build    # App + Worker + PostgreSQL
```

| Dokument | Inhalt |
|---|---|
| [`docs/user-manual.md`](docs/user-manual.md) | Benutzerhandbuch mit Screenshots (in der App unter „Handbuch“) |
| [`docs/spec/world-explorer-spec.md`](docs/spec/world-explorer-spec.md) | Spezifikation und Designplan |
| [`docs/architecture.md`](docs/architecture.md) | Was gebaut ist und wie die Schichten zusammenhängen |
| [`docs/engineering-rules.md`](docs/engineering-rules.md) | Regeln für Änderungen |

Der frühere aktienzentrierte Stand liegt unter dem Tag `v0-dashboard`.

**Stand:** Mit Demo-Daten Ende zu Ende geprüft (`scripts/capture_screenshots.mjs`). Echte Datenquellen
(Yahoo, SEC, USGS), ein echter Agentenlauf und der Docker-Build sind in der Entwicklungsumgebung nicht
geprüft worden.
