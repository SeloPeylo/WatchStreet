# WatchStreet – Benutzerhandbuch

WatchStreet überwacht deine Aktien. Du trägst ein, was du besitzt (**Holdings**) und was dich interessiert (**Watchlist**). Zu jeder Aktie legt das System **Tickets** an – Analyseaufträge, die automatisch von Agenten abgearbeitet werden. Die Erkenntnisse (Ziel, These, Scores, Hinweise) bleiben an der Aktie erhalten und wachsen mit der Zeit.

> **Hinweis zu den Screenshots:** Sie wurden mit dem Demo-Modus erzeugt (synthetische Kurse, regelbasierter Offline-Agent). Kurse und Texte sind also Beispiele und keine echten Marktdaten. **WatchStreet liefert keine Anlageberatung.**

## 1. Aufruf

Nach `docker compose up --build` ist die Anwendung unter **http://localhost:8000** erreichbar. Oben befindet sich die Navigation: *Übersicht, Holdings, Watchlist, Tickets, System, Handbuch*. Dieses Handbuch ist auch in der Anwendung unter **Handbuch** abrufbar.

## 2. Grundkonzepte

| Begriff | Bedeutung |
|---|---|
| **Holding** | Eine Aktie, die du besitzt: Menge, Ø-Kaufpreis, optional Kaufdatum und Absicht. |
| **Watchlist** | Eine Aktie, die du beobachtest, mit optionaler Notiz. |
| **Ticket** | Ein Auftrag mit genau einem vordefinierten **Workflow**. Status: wartend → läuft → erledigt / fehlgeschlagen / abgebrochen. |
| **Workflow** | Festes Ablaufschema eines Tickets (siehe Abschnitt 8). |
| **Erkenntnis** | Dauerhafte Aussage aus einem Ticket (Kategorien: Ziel, Risiko, Katalysator, Bewertung, Technik, Handlung, Notiz). |
| **Score** | Zahl 0–100 nach einem festen Schema. Jede Messung wird gespeichert, so entsteht ein Verlauf. |
| **These** | Die Investmentthese. Jede Prüfung legt eine neue Version mit Status an. |
| **Folgeticket** | Ein Ticket, das ein abgeschlossenes Ticket vorgeschlagen hat. |

## 3. Übersicht (Dashboard)

![Übersicht](screenshots/01-dashboard.png)

* **Depotwert** – Einstand, aktueller Wert und Gewinn/Verlust. Je Währung eine Karte; verschiedene Währungen werden nie zusammengerechnet.
* **Positionen** – Anzahl der Holdings und Watchlist-Einträge.
* **Tickets** – offene, erledigte und fehlgeschlagene Tickets.
* **Harness** – ob der Worker läuft, welcher Agent und welche Datenquelle aktiv sind.
* **Letzte Tickets** und **Neueste Erkenntnisse** – Klick führt zum Ticket bzw. zur Aktie.

## 4. Holdings

![Holdings](screenshots/02-holdings.png)

**Position eintragen:** Symbol (z. B. `AAPL`, `SAP.DE`; beim Tippen erscheinen Vorschläge), Menge, Ø-Kaufpreis (Komma oder Punkt), optional Kaufdatum und **Absicht** (z. B. „langfristig halten“). Mit *Eintragen & Bestandsaufnahme starten* wird die Position gespeichert und automatisch ein **Bestandsaufnahme-Ticket** angelegt. Ohne Absicht leitet der Agent ein Ziel selbst ab.

**Tabelle:** Kurs, Tagesänderung, Wert und Gewinn/Verlust je Position. Ein Klick auf das Symbol öffnet die Aktie. *Entfernen* löscht nur die Position; Tickets, Erkenntnisse und Thesen bleiben erhalten.

**Fehlermeldungen:** Ungültige Eingaben (z. B. Text statt Zahl, unbekanntes Symbol, doppelte Position) werden angezeigt, deine Eingaben bleiben im Formular stehen.

![Fehlermeldung](screenshots/03-holdings-error.png)

## 5. Watchlist

![Watchlist](screenshots/04-watchlist.png)

Symbol und optional eine Notiz eintragen. Es wird eine **Kaufprüfung** gestartet: Lohnt sich ein Kauf? Das Ergebnis und Folgeanalysen erscheinen an der Aktie. Eine Aktie kann gleichzeitig Holding und Watchlist-Eintrag sein.

## 6. Aktien-Detailseite (geschichtet)

Die Seite ist in **Schichten** aufgebaut, damit viele Informationen nicht gleichzeitig erschlagen:

1. **Kopf** – Kurs, Änderung zum Vortag, **Profil** (Aktientyp) als Badge.
2. **Briefing „Worauf es jetzt ankommt“** – eine Schlagzeile und wenige Stichpunkte (Bewertung, Datenlücken, Risiken, Technik). Es wird nach jeder Änderung automatisch neu erzeugt (zuerst regelbasiert, mit LLM zusätzlich vom Agenten verfeinert), ist gespeichert und zeigt Autor und Zeit. *Aktualisieren* erzeugt es sofort neu; der Link „zum Fokus-Bereich“ springt zum wichtigsten Panel.
3. **Position** – Menge, Ø-Preis, Wert, Gewinn/Verlust; *Position bearbeiten*.
4. **Panels** – aufklappbare Bereiche. **Ihre Reihenfolge richtet sich nach dem Profil**: Bei Minen stehen *Bewertung* und *Belege* oben, bei Tech-Aktien zuerst der *Kursverlauf*. Die ersten beiden Panels sind offen, der Fokus-Bereich des Briefings ebenfalls.

| Panel | Inhalt |
|---|---|
| **Bewertung** | Score nach dem Profil-Schema, Kriterientabelle mit Gewicht und Teil-Score, Datenlücken, ggf. NAV-Aufstellung, Technik-Score, *Profil ändern*. |
| **Kursverlauf (Kerzen)** | Candlestick-Chart mit Volumen; Stunde/Tag/Woche; Mausover zeigt O/H/L/C. |
| **Belege & Datenpunkte** | Alle Eingaben mit Quelle, Konfidenz, Herkunft; Formular zum Erfassen. |
| **Ziel & Investmentthese** | Ziel, aktuelle These mit Status, Versionsverlauf. |
| **Verlauf** | Score-Verlauf, Erkenntnisse, Tickets (auch neue anlegen), Zeitleiste. |

![Tech-Aktie: Chart zuerst](screenshots/05-stock-tech.png)

![Chart täglich](screenshots/06-stock-chart-daily.png)

## 6a. Profile und Bewertungsschemata

Jede Aktie hat ein **Profil**, das bestimmt, *wie* sie bewertet wird, welche Eingaben nötig sind und wie die Seite aufgebaut ist.

| Profil | Schema (Kern) | Zusätzliche Eingaben |
|---|---|---|
| **Minen / Rohstoffförderer** | Kurs/NAV, AISC-Marge, Reservenlaufzeit | je Mine: Produktion, AISC, Reserven, Beteiligung; Rohstoffpreis, Nettoverschuldung, Aktienzahl |
| **Öl & Gas** | Marge über Break-even, FCF-Rendite, Reservenlaufzeit | Break-even-Preis, Reserven, Produktion, Free Cash Flow |
| **Technologie** | Rule of 40, erwartetes KGV, PEG, Wachstum | – |
| **Versorger** | Dividende, Verschuldung, KGV, ROE | – |
| **Banken & Finanz** | Kurs/Buchwert gegen ROE, CET1 | CET1-Quote |
| **Immobilien / REIT** | Kurs/FFO, Kurs/NAV, Ausschüttung | FFO und NAV je Aktie |
| **Gesundheit / Pharma** | KGV, Wachstum, Marge | – |
| **Allgemein** | Standardschema aus Kennzahlen | – |

**Wie das Profil entsteht:** Beim Eintragen wird es automatisch aus Sektor und Branche des Datenanbieters abgeleitet. Unklare Fälle bleiben „Allgemein“. Ein Agent darf es per Ticket *Profil bestimmen* korrigieren; **dein manuelles Setzen** (Bewertung → *Profil ändern*) hat immer Vorrang und wird nie überschrieben. Nach einer Änderung wird sofort neu bewertet.

**Rechnen kann der Code, recherchieren der Agent:** Alles, was keine kostenlose API liefert (z. B. welche Minen ein Unternehmen hat und zu welchen Kosten sie fördern), sind **Datenpunkte** mit Quelle und Konfidenz (*high/medium/low*). Du erfasst sie im Panel *Belege*; ein Agent kann sie per Ticket *Datenpunkte recherchieren* eintragen, überschreibt aber nie deine Werte. Berechnungen wie der **NAV** (Barwert der Marge jeder Mine über ihre Reservenlaufzeit, minus Nettoverschuldung, durch Aktienzahl) sind deterministisch und nachvollziehbar in der Bewertung aufgeschlüsselt.

**Datenlücken statt Raten:** Fehlen Eingaben, nennt das Panel *Bewertung* sie ausdrücklich und markiert den Score als **vorläufig**. Der Score wird erst „vollständig“, wenn die Kernkennzahlen (z. B. Kurs/NAV und AISC-Marge bei Minen) berechenbar sind. Weichen Berichtswährung und Aktienwährung ab, wird zusätzlich ein Wechselkurs verlangt.

![Minen: Bewertung mit NAV](screenshots/11-mining-valuation.png)

![Minen: Belege und Formular](screenshots/12-mining-evidence.png)

![Minen-Aktie gesamt](screenshots/10-stock-mining.png)

![Öl-&-Gas-Aktie mit Datenlücken](screenshots/13-stock-oil.png)

## 6b. Intel, Karte, Netzwerk und Rohstoff-Cockpit

Diese Bereiche bilden die „Lagezentrale“ für dein Portfolio. Leitprinzip: **Keine Quelle, kein Fakt.** Jede Meldung verweist auf die direkte Quelle, und was ein Agent behauptet, muss er wörtlich aus dem gespeicherten Dokument zitieren; das System prüft das Zitat selbst und lehnt Unbelegtes ab.

### Intel – Nachrichtenzentrale

![Intel](screenshots/14-intel.png)

Zugeschnittene Meldungen zu deinen Aktien, sortiert nach Zeit, mit **Schwere (1–5)**, Thema (*company, supply, geopolitics, macro, regulatory, commodity, hazard*) und **Auswirkung je Aktie** (▲ positiv, ▼ negativ, • unklar). Jede Karte zeigt:

* **Warum für dich relevant** und – bei Agenten-Einträgen – das **wörtliche Belegzitat** mit dem Vermerk „im Dokument gefunden“,
* **Quelle öffnen ↗** (Originaladresse) und **gespeicherte Kopie** (unveränderte Kopie samt Prüfsumme, auch wenn die Seite später verschwindet),
* das Badge **Primärquelle** für Behörden, Einreichungen und Unternehmensmitteilungen; *nur Primärquellen* filtert Medienberichte aus,
* wer die Meldung erstellt hat: **Agent** oder **Regeln**.

![Nur Primärquellen](screenshots/15-intel-primary.png)

**So entsteht eine Meldung:** Der Worker holt stündlich neue Quellen (RSS-Feeds, GDELT-Suche je Firmenname/Mine/Zulieferer, SEC EDGAR, USGS-Erdbeben, Rohstoffpreise). Ein **deterministischer Filter** bewertet, welche Quellen zu deinen Aktien passen (Firmenname, Minen, Zulieferer, Ticker); nur Treffer gehen an einen Agenten, der sie einordnet. So werden die meisten Quellen gar nicht erst an ein Modell geschickt (Token-Ersparnis). Zusätzlich lösen **Tripwires** ohne LLM Meldungen aus: ein Erdbeben ab M 5,0 im Umkreis von 300 km um eines deiner Assets, ein Tagessprung ab 3 % bei einem Rohstoff, von dem deine Aktien abhängen, und neue SEC-Einreichungen.

*Jetzt aktualisieren* stößt einen Durchlauf an. Unter **Quellen verwalten** siehst du alle Feeds mit Status und letztem Fehler, kannst Feeds aktivieren/deaktivieren, löschen und eigene RSS/Atom-Quellen ergänzen. Fünf Fehlversuche in Folge deaktivieren einen Feed.

![Quellen verwalten](screenshots/20-feeds.png)

### Karte

![Lagekarte](screenshots/16-map.png)

Weltkarte (offline, ohne Kartendienst) mit drei Ebenen, die du ein- und ausblendest:

* **Länder-Exposure:** Länder werden umso kräftiger eingefärbt, je mehr Portfoliowert an sie gebunden ist. Gerechnet wird nach Marktwert deiner Positionen, bei Minen nach Produktionsanteil und Beteiligung der Assets, bei Zulieferern/Kunden nach dem erfassten Anteil (fehlt er, gilt ein Standardwert von 10 %). Ein Klick auf ein Land nennt die Gründe je Aktie.
* **Assets:** Minen, Anlagen und Häfen mit Standort.
* **Ereignisse:** Meldungen der letzten 14 Tage mit Ort; Größe nach Schwere, Farbe nach Thema. Ein Klick zeigt Warum-relevant und die Quelle.

Mausrad zoomt, Ziehen verschiebt. Minen ohne Koordinaten erscheinen rechts unter **Assets ohne Standort**; dort trägst du Breite, Länge und Land ein. Agenten ergänzen Standorte beim Lesen von Einreichungen mit Zitat.

### Netzwerk – Abhängigkeiten

![Netzwerk](screenshots/17-graph.png)

Graph aus Aktien, Assets, **Zulieferern, Kunden**, Ländern und Rohstoffen. Auswahl *„XYZ – Umfeld“* zeigt zwei Beziehungsebenen um eine Aktie. **Durchgezogene Linien** sind belegt (geprüftes Zitat) oder von dir eingetragen, **gestrichelte** unbelegt; die Dicke steht für den Anteil (z. B. 40 % der Fahrzeugflotte). Klick auf einen Knoten oder eine Kante zeigt Art, Land, Anteil, Konfidenz, Herkunft, das **Zitat** und den Link zum Dokument. Rechts trägst du eigene Beziehungen ein (z. B. „Caterpillar → Carlin, supplies, 0,4“). Deine Einträge überschreibt kein Agent. Aus den Zulieferern und Minen entstehen automatisch Suchbegriffe für die Nachrichtenzentrale.

### Rohstoff- und Makro-Cockpit

![Cockpit](screenshots/18-commodities.png)

* **Rohstoffe** (Gold, Silber, Platin, Palladium, Kupfer, Aluminium, Öl WTI/Brent, Erdgas) und **Makro** (US-Dollar-Index, 10-Jahres-Rendite, VIX, S&P 500) mit Tages- und Monatsänderung und 60-Tage-Verlauf.
* **Verhältnisse:** Gold/Silber, Kupfer/Gold (Konjunkturbarometer), Öl/Gas.
* **Dein Rohstoff-Exposure:** welche Aktien an welchem Rohstoff hängen und wie viel Portfoliowert (setzt den Datenpunkt *Rohstoff-Symbol*, z. B. GC=F, voraus).
* **Szenario-Rechner:** Der NAV je Aktie jeder Mine wird mit −30 % bis +30 % Rohstoffpreis neu berechnet (Kosten, Reserven und Schulden unverändert). Das zeigt den **Hebel**: Eine Mine mit hohen Kosten verliert bei fallendem Preis überproportional, bei sehr niedrigem Preis kann der NAV negativ werden. Die Positionsänderung unterstellt ein gleichbleibendes Kurs/NAV-Verhältnis; das ist eine Modellannahme, keine Prognose.

### Dokumente und SEC-Einreichungen

![Dokument](screenshots/19-document.png)

Jede Quelle liegt als **Dokument** vor (Adresse, Herausgeber, Art, Abrufzeit, Prüfsumme, Text; HTML und PDF werden gelesen). Die Dokumentseite zeigt auch, **was auf ihr beruht**: Datenpunkte, Beziehungen und Erkenntnisse jeweils mit Zitat. Bei Einreichungen startet *Von einem Agenten lesen lassen* das Ticket **Einreichung lesen**.

Für US-Notierungen holt das Ticket **SEC-Abgleich** (täglich, ohne LLM) neue Einreichungen (10-K, 10-Q, 20-F, 40-F, 8-K, 6-K) von SEC EDGAR und übernimmt **Aktienanzahl** und **Nettoverschuldung** (Schulden minus Kasse) aus den strukturierten XBRL-Daten, mit Quelle und Konfidenz *high*. Das Ticket **Einreichung lesen** (Agent mit Tool-Unterstützung) liest gezielt Gliederung, Suche und Abschnitte und trägt Minen/Standorte, Zulieferer/Kunden, Eingaben und Risiken ein, jede Aussage mit wörtlichem Zitat. Unbelegte Angaben eines Agenten gelten höchstens als Konfidenz *low*.

## 7. Tickets

![Tickets](screenshots/07-tickets.png)

Die Seite **Tickets** listet alle Tickets, filterbar nach Status.

**Eigenes Ticket anlegen** (Aktien-Seite): Workflow wählen, bei *Themenanalyse* ein Thema angeben (z. B. „Wettbewerb in China“).

![Ticket-Details](screenshots/08-ticket-detail.png)

**Ticket-Detail:** Workflow, Herkunft (*user, intake, followup, event, schedule*), Priorität, Agent, Zeiten, Parameter, Ergebnis, erzeugte Erkenntnisse und Scores sowie die **Folgetickets**. Dort steht auch, welche vorgeschlagenen Folgetickets die Leitplanken **verworfen** haben und warum. Aktionen: *Erneut ausführen* (fehlgeschlagen/abgebrochen), *Abbrechen* (wartend).

**Leitplanken für Folgetickets:** nur bekannte Workflows, maximal 2 Ebenen Tiefe, maximal 4 Folgetickets je Ticket, höchstens 8 offene Tickets je Aktie, keine Duplikate innerhalb von 24 Stunden.

## 8. Workflows

| Workflow | Zweck | LLM |
|---|---|---|
| Bestandsaufnahme (Holding) | Ausgangslage, Ziel, These, Scores; schlägt Folgetickets vor. Wird beim Eintragen automatisch angelegt. | ja |
| Kaufprüfung (Watchlist) | Lohnt sich ein Kauf? Wird beim Beobachten automatisch angelegt. | ja |
| Themenanalyse | Vertiefung zu einem frei wählbaren Thema. | ja |
| Ereignis-Prüfung | Bewertet neue Meldungen auf Relevanz für die These. Wird automatisch angelegt. | ja |
| These prüfen | Testet die These gegen neue Daten und Score-Änderungen; setzt den Thesen-Status. | ja |
| Bewertungs-Score | Deterministisches, **profilabhängiges** Schema (siehe 6a) inkl. NAV/Marge-Berechnung. Wird nach jedem neuen Datenpunkt automatisch neu gestartet. | nein |
| Profil bestimmen | Ordnet die Aktie einem Typ zu. | ja |
| Datenpunkte recherchieren | Trägt fehlende Eingaben mit Quelle und Konfidenz ein; rät nicht. | ja |
| SEC-Abgleich | Neue Einreichungen und XBRL-Kennzahlen von SEC EDGAR (täglich, mit Quelle). | nein |
| Einreichung lesen | Agent liest eine Einreichung und extrahiert Datenpunkte, Beziehungen und Assets, jeweils mit geprüftem Zitat. | ja (Tools nötig) |
| Nachrichten-Zuschnitt | Ordnet neue, deterministisch vorgefilterte Quellen ein und veröffentlicht belegte Intel-Items. Läuft automatisch. | ja |
| Briefing | Erzeugt „Worauf es jetzt ankommt“ (Regeln, optional vom Agenten verfeinert). Läuft automatisch nach jeder Änderung. | optional |
| Technik-Snapshot | Deterministisch: Kurs vs. SMA50, SMA20 vs. SMA50, Momentum, RSI aus Stundenkerzen. | nein |

Scores werden aus den verfügbaren Eingaben berechnet und nur gebildet, wenn mindestens drei Kriterien vorliegen; die *Abdeckung* (z. B. 7/10) ist angegeben.

## 9. Automatik (Worker)

Der Worker läuft als eigener Container. Er

* arbeitet wartende Tickets nach Priorität ab (manuell/Intake vor Folge- und Zeitplan-Tickets),
* prüft **stündlich** (einstellbar) alle Aktien auf neue Meldungen und legt dafür eine Ereignis-Prüfung an,
* frischt Analysen auf: Technik-Snapshot täglich, Bewertungs-Score und These wöchentlich – nur für Aktien mit abgeschlossener Bestandsaufnahme,
* setzt nach einem Absturz hängende Tickets (> 30 min *läuft*) zurück in die Warteschlange.

## 10. System

![System](screenshots/09-system.png)

Zeigt Datenquelle, Agent, Worker-Status, letzten Scan und alle Workflows.

**Datenquellen:** `yahoo` (kostenlos, ohne Schlüssel, Kurse stundengenau) oder `demo` (synthetisch, offline).
**Agenten (`WATCHSTREET_AGENT_RUNNER`):** `llama` (lokales llama.cpp im Docker-Verbund), `offline` (regelbasiert, kein LLM – kann Freitext-Themen nicht inhaltlich analysieren), `anthropic` (API-Schlüssel nötig), `openai` (OpenAI-kompatibel, z. B. lokales Ollama), `cli` (externer Agent per Kommandozeile, z. B. `claude -p`). Konfiguration in `.env`, siehe `.env.example`.

## 11. Lokales LLM, Datenbank und Tool-Calling

* **Datenbank:** Postgres läuft als eigener Container, die Dateien liegen im Projektordner unter `data/postgres`.
* **Lokales Modell:** GGUF-Datei in den Ordner `models/` legen (`scripts/download_model.sh <url>`), in `.env` `LLAMA_MODEL=<datei>` und `WATCHSTREET_AGENT_RUNNER=llama` setzen und mit `docker compose --profile llm-gpu up --build` (NVIDIA-GPU) bzw. `--profile llm-cpu` starten. Grenzen für GPU-Anzahl, GPU-Schichten, Threads, Kontext und RAM stehen in `.env` (`LLAMA_*`). Empfohlen sind Instruct-Modelle mit Tool-Unterstützung.
* **Tool-Calling:** Der Harness berechnet Kurs, Kennzahlen, Scores und Gewinn/Verlust selbst und gibt dem Agenten nur ein kompaktes Faktenblatt. Details holt der Agent bei Bedarf über Tools und hält Ergebnisse (Erkenntnis, Ziel, These, Folgeticket, Datenpunkt mit Quelle, Profil) ebenfalls über Tools fest. Ablehnungen der Leitplanken (z. B. Duplikat) bekommt der Agent sofort zurückgemeldet. Im Ticket-Detail zeigt **Modus** die Schritte, Tool-Aufrufe und Tokens. Unterstützt das Modell keine Tools, wechselt der Harness automatisch auf JSON-Antworten (Modus `json`).

## 12. Grenzen und Hinweise

* Yahoo-Daten kommen aus einer inoffiziellen, kostenlosen Schnittstelle; sie kann sich ändern oder Anfragen begrenzen. Fehlende Kennzahlen führen zu weniger Kriterien, nicht zu erfundenen Werten.
* Zahlen und Texte können falsch sein. Keine Anlageberatung.
* Währungen werden nicht umgerechnet; bei Minen mit abweichender Berichtswährung ist ein Wechselkurs als Datenpunkt nötig.
* **Abrufweg:** Quellen ruft der Harness ab, nicht der Agent. Er erlaubt nur öffentliche http(s)-Adressen (keine internen Netze), begrenzt Größe und Weiterleitungen und behandelt Inhalte ausschließlich als Daten, nie als Anweisungen. Agenten lesen die gespeicherten Kopien. Das macht Belege reproduzierbar und schützt vor eingeschleusten Anweisungen in Webseiten.
* **Abdeckung:** SEC EDGAR deckt US-Notierungen ab. Kanadische (SEDAR+) und europäische Emittenten haben keine freie Schnittstelle; dort helfen RSS-Quellen der Unternehmen und manuelles Erfassen. GDELT, USGS und die Standard-Feeds sind kostenlos, aber unverbindlich; Feed-Adressen können sich ändern (unter *Quellen verwalten* anpassen). Die SEC verlangt eine Kontakt-Kennung: setze `WATCHSTREET_SEC_USER_AGENT` auf „Name e-mail“.
* Ein lokales LLM hat keinen eigenen Internetzugriff: Recherchierte Datenpunkte stammen aus dem Modellwissen und sind entsprechend mit Konfidenz zu lesen. Prüfe sie, bevor du dich auf sie verlässt.
* Beim Update von einer älteren Version fehlen neue Tabellenspalten (keine Migrationen): lokale Datenbank (`data/`) neu anlegen.
* Es gibt noch keine Benutzerverwaltung: Die Anwendung gehört in ein vertrauenswürdiges Netz.
