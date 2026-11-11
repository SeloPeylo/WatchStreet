# Import-API: Analysen und Listen einspielen

Über diese Schnittstelle bringen du, ein Skript oder ein Research-Agent ausserhalb von WatchStreet
Daten in die Anwendung. Alles Importierte ist sofort sichtbar und als **ungeprüft** markiert. Es
ersetzt nie eine Angabe aus einer Primärquelle und nie deinen eigenen Eintrag.

Die vollständige technische Beschreibung aller Endpunkte liefert der Server unter `/openapi.json`.

## Anmeldung

| Betrieb | Vorgehen |
|---|---|
| Ohne Passwort (nur lokal) | keine Anmeldung nötig |
| Mit Passwort | `WATCHSTREET_API_TOKEN` in `.env` setzen (langer Zufallswert, `openssl rand -hex 32`) und bei jedem Aufruf `Authorization: Bearer <Token>` senden |

Das Token gibt vollen Zugriff auf die API. Es gehört nur in die Umgebung des Skripts oder Agenten,
nie in ein Repository.

## Importieren

`POST /api/v1/imports` mit JSON. Entweder `text` (eine Tabelle) oder `rows` (strukturierte Zeilen).

```bash
curl -X POST https://watchstreet.example.org/api/v1/imports \
  -H "Authorization: Bearer $WATCHSTREET_API_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "title": "Kupferliste November",
    "source": "eigene Recherche",
    "rows": [
      {"name": "Mina Ejemplo", "company": "Ejemplo Mining", "commodity": "copper",
       "country": "Chile", "lat": -23.5, "lon": -69.1, "status": "production",
       "production": 120000000, "aisc": 1.85, "reserves": 2400000000}
    ]
  }'
```

Als Tabelle (CSV, TSV, mit `;` getrennt oder als Markdown-Tabelle); in der Oberfläche unter
**Quellen → Analyse importieren** auch per Datei-Upload:

```
name;company;commodity;country;lat;lon;status;production;aisc;reserves
Mina Ejemplo;Ejemplo Mining;copper;Chile;-23.5;-69.1;production;120000000;1.85;2400000000
```

### Spalten

Die Reihenfolge ist frei; unbekannte Spalten werden ignoriert. Deutsche Bezeichnungen (z. B.
`Unternehmen`, `Rohstoff`, `Land`, `Produktion`, `Reserven`) und ein Einheitenzusatz in Klammern
(`AISC (USD/lb)`) werden erkannt.

| Spalte | Bedeutung |
|---|---|
| `name` | Pflicht. Ein bekanntes Objekt wird über den Namen gefunden |
| `lat`, `lon`, `commodity` | Pflicht für ein **neues** Objekt (`gold`, `silver`, `copper`, `uranium`) |
| `company`, `share` | Betreiber; mit `share` (Prozent) als Eigentümer |
| `country`, `region`, `status` | Status: `production`, `development`, `exploration`, `care_maintenance`, `closed` |
| `production`, `aisc`, `cash_cost`, `reserves`, `grade` | Kennzahlen produzierender Minen |
| `resources`, `resources_mi`, `resources_inferred`, `recovery` | Ressourcen und Ausbringung |
| `capex`, `expected_production`, `expected_aisc`, `study_npv`, `study_price` | Studienwerte von Projekten |
| `study_stage`, `study_date`, `first_production`, `permit_status` | Textangaben |

Zahlen dürfen `1,234`, `1.234,5`, `4.0e9` oder `190 Mio` lauten. Mengen stehen in der Einheit des
Rohstoffs (Unzen bei Gold und Silber, Pfund bei Kupfer und Uran), Kosten in USD je Einheit.

### Antwort

```json
{"rows": 1, "created": 1, "matched": 0, "facts": 3, "unchanged": 0,
 "conflicts": [], "skipped": [], "asset_ids": [20], "fact_ids": [101, 102, 103],
 "document_id": 31, "ticket_id": null}
```

* `conflicts`: Die Analyse nennt einen anderen Wert als eine belegte oder eigene Angabe. Der
  vorhandene Wert bleibt.
* `skipped`: Zeilen oder Zellen, die nicht übernommen wurden, mit Grund.
* `ticket_id`: Enthielt `text` keine Tabelle und ist ein Agent konfiguriert, zerlegt er den Text in
  einer Recherche. Jede Zeile braucht dann ein wörtliches Zitat aus dem Text, sonst wird sie
  verworfen. Ohne Agent wird Fliesstext nur gespeichert.

Ein erneuter Import derselben Liste ändert nichts. Geänderte Werte ersetzen den früheren Import.

## Prüfen

| Aufruf | Wirkung |
|---|---|
| `GET /api/v1/imports/unverified` | alle noch ungeprüften Angaben |
| `POST /api/v1/facts/{id}/confirm` | du bestätigst die Angabe; sie gilt danach als dein Eintrag |
| `POST /api/v1/facts/{id}/retract` | storniert eine importierte oder eigene Angabe; sie bleibt in der Historie |
| `POST /api/v1/imports/verify` | merkt je Angabe eine Prüfung gegen Primärquellen vor |

Vorgemerkte Prüfungen stehen im Research-Backlog und laufen erst, wenn du sie startest. Jede Prüfung
sucht die Zahl zuerst ohne Sprachmodell in den gespeicherten Primärdokumenten des Objekts. Findet sie
einen Wert, gilt dieser mit Zitat; weicht er ab, nennt das Ergebnis beide Zahlen. Findet sie nichts
und ist ein Agent eingestellt, versucht er es; sonst bleibt die Angabe ungeprüft.

## Agent einstellen

Unter **System → Agent** oder per API:

```bash
curl -X PUT .../api/v1/system/agent -H "Authorization: Bearer $WATCHSTREET_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"runner": "openai", "model": "qwen2.5:7b", "base_url": "http://host.docker.internal:11434/v1"}'
```

`runner` ist `offline`, `anthropic` (Schlüssel in `api_key`) oder `openai` (jeder
OpenAI-kompatible Dienst, auch ein Modell auf eigener Hardware). Der Schlüssel wird in der Datenbank
des Servers gespeichert und nie zurückgegeben. `POST /api/v1/system/agent/test` prüft die Verbindung.
