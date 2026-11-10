# WatchStreet – Spezifikation und Designplan „Investment World Explorer“

**Stand:** 10. November 2026
**Status:** Entwurf zur Freigabe. Ersetzt nach Freigabe `docs/architecture.md` als Zielbild.
**Grundlage:** Requirements-Engineering-Session (D01–D12, Szenarien A–D), Design-Briefs A (World Explorer), B (Research Cockpit), C (Strategy Explorer), Bestand im Branch `claude/stock-portfolio-tracker-zyazxn`.
**Sprache:** Oberfläche Deutsch, Code Englisch.

Kennzeichnung in diesem Dokument: **[E]** = Entscheidung aus der Session, **[V]** = Vorschlag dieses Plans (noch zu bestätigen), **[O]** = bewusst offen.

---

## 1. Zielbild

WatchStreet wird von einem aktienzentrierten Dashboard zu einem **kartenzentrierten Recherche- und Lernarbeitsplatz für Rohstoffinvestments**. Die Mine bzw. das Projekt ist die primäre Analyseeinheit; Unternehmen, Thesen, Tickets, Quellen und Ereignisse hängen daran.

### 1.1 Produktprinzipien (verbindlich)

| Prinzip | Konsequenz für das Design |
|---|---|
| Asset-first | Jede Kennzahl, jedes Ticket, jede Erkenntnis kann an einem Asset hängen, ohne dass ein Ticker existiert. |
| Map-first | Die Karte ist Startseite und bleibt bei jedem Perspektivwechsel sichtbar. |
| Evidence-first | Keine Zahl ohne Herkunftsstatus, Zeitbezug und Definition. Unbekannt bleibt unbekannt. |
| History-aware | „Damals bekannt“, „rückblickend bekannt“ und „Szenario“ sind getrennte Sichten. |
| Human-in-the-loop | Agenten-Recherche wird vorgeschlagen und bewusst gestartet. |
| Deterministic-first | Rechnen und Regelprüfung vor LLM. Ein LLM läuft erst nach Freigabe. |
| Learning-first | Wissen ist dauerhaft, verknüpft und wiederauffindbar; kein Chatverlauf als Speicher. |

### 1.2 Nicht-Ziele

* Keine Anlageempfehlungen, keine Kauf-/Verkaufssignale, keine Orderanbindung.
* Keine Echtzeitdaten; Stundengenauigkeit bei Preisen genügt.
* Keine globale Vollabdeckung aller Minen. Der Bestand wächst durch Recherche.
* Keine Mehrbenutzer-/Mandantenfähigkeit; ein Nutzer, optionaler Passwortschutz.
* Keine erfundenen Werte ausserhalb des klar gekennzeichneten Demo-Modus.

### 1.3 Rohstoffumfang

Gold, Silber, Kupfer, Uran **[E]**. Das Modell ist rohstoffneutral; rohstoffspezifisch sind nur Einheiten, Kostenbegriffe und Abbauverfahren (Abschnitt 5.4).

---

## 2. UX-Konzept: Entscheidung zwischen den drei Briefs

Die Briefs sehen drei getrennte Prototypen vor. Um nicht dreimal zu bauen, legt dieser Plan **eine kombinierte Variante [V]** fest und baut sie so, dass die offenen UX-Fragen daran geprüft werden können.

| Baustein | Herkunft | Übernommen als |
|---|---|---|
| Karte als Hauptfläche, Layer, Filter, Kontextpanel | A | Arbeitsbereich **Explorer** (Startseite) |
| These-Board, Backlog mit Freigabe, Lagebericht „seit letztem Besuch“ | B | Arbeitsbereich **Research**, mit eingebetteter Karte |
| Wissensstatus je Objekt, Scout-Sammelkorb, Ereignisleiste, Journal | C | Querschnittsfunktionen im Explorer |
| Spielmetapher (Begriffe, Animationen) | C | **nicht** übernommen; nur die Interaktionsmuster (Mehrfachauswahl, Sammeln, Status) |

Begründung: Die Session legt Map-first und Asset-first fest (spricht für A), verlangt aber Ticketvorschläge mit Freigabe und persistente Thesen (B) sowie Auswahlleiste und Wissensstatus (C). Die Metapher aus C gefährdet „seriöse Finanzinformation“; ihre Mechanik nicht.

### 2.1 Informationsarchitektur

```
┌ Kopfzeile: Rohstoffleiste (Au Ag Cu U + Preis, Δ)  │ Suche │ Stichtag │ Glocke ┐
├──────────────┬───────────────────────────────────────────────┬────────────────┤
│ Navigation   │                                               │ Kontextpanel   │
│  Explorer    │                 KARTE                         │ (Charakterkarte│
│  Research    │   Layer · Legende · Farbmodus                 │  → Detail)     │
│  Portfolio   │                                               │                │
│  Quellen     ├───────────────────────────────────────────────┤                │
│  System      │ Auswahlleiste (selektierte Assets) · Szenario │                │
├──────────────┴───────────────────────────────────────────────┴────────────────┤
│ Zeitleiste: Preisverlauf des Rohstoffs · Ereignisse · Stichtag-Regler         │
└────────────────────────────────────────────────────────────────────────────────┘
```

| Bereich | Route | Inhalt |
|---|---|---|
| Explorer | `/` | Karte, Kontextpanel, Auswahlleiste, Zeitleiste |
| Asset-Detail | `/assets/{slug}` (Panel oder Vollansicht, Karte bleibt) | Kennzahlen, Eigentum, Lebenslauf, Quellen, Tickets |
| Unternehmen | `/companies/{slug}` | Assets des Unternehmens (auf Karte hervorgehoben), Aktie, Bewertung |
| Vergleich | `/compare?ids=…` | Karten nebeneinander, synchronisierte Zeitachsen |
| Research | `/research` | These-Board, Backlog, Lagebericht, Journal |
| These | `/theses/{id}` | Annahmen, Evidenz pro/contra, offene Fragen, betroffene Assets |
| Ticket | `/tickets/{id}` | Auftrag, Verlauf, Ergebnis, Quellen |
| Portfolio | `/portfolio` | Bestände und Watchlist (bestehende Funktion, verschlankt) |
| Quellen | `/sources`, `/documents/{id}` | Dokumentenspeicher, Feeds |
| System | `/system`, `/manual` | Zustand, Agenten, Handbuch |

Perspektivwechsel (Region ↔ Asset ↔ Unternehmen ↔ These) erfolgen ohne Seiten-Reload; die Karte behält Ausschnitt, Filter und Auswahl. Der gesamte Zustand steht in der URL (`?c=cu&sel=12,15&asof=2019-06-30&color=margin`), damit Ansichten teilbar und der Zurück-Knopf verlässlich sind.

### 2.2 Karte

* **Layer** (einzeln schaltbar): produzierende Minen, Entwicklungsprojekte, Explorationsprojekte, stillgelegte Assets, Ereignisse, Länder-/Regionsflächen. Default **[V]**: Produktion + Entwicklung an, Exploration an ab Zoomstufe „Region“, stillgelegt aus.
* **Markerform = Status** (Kreis Produktion, Raute Entwicklung, Dreieck Exploration, Quadrat mit Strich stillgelegt). **Markerfarbe = gewählter Farbmodus**. Form und Farbe tragen nie dieselbe Information.
* **Farbmodus** wählbar **[V]** (löst offene Frage 1): `Status` (neutral, Default), `Marge %`, `Abstand zum Break-even`, `Δ im Szenario`, `Wissensstatus`, `Datenqualität`. Wirtschaftlichkeitsmodi nutzen eine divergierende, farbfehlsichtige Skala (Blau–Grau–Orange statt Rot/Grün) mit Legende und Zahlenwert im Tooltip. Assets ohne ausreichende Daten sind **schraffiert-grau, nie neutral eingefärbt** – „unbekannt“ darf nicht wie „Mitte der Skala“ aussehen.
* **Clustering** ab überlappenden Markern; Cluster zeigen Anzahl und Statusverteilung. Selektierte Assets werden nie geclustert.
* **Wissens-Badge** am Marker (kleiner Punkt oben rechts): offene Frage, Recherche läuft, neues Ergebnis, veraltet.
* **Interaktion:** Klick = Charakterkarte; Umschalt+Klick oder Rahmen ziehen = zur Auswahl hinzufügen; Rechtsklick/„+ Frage“ = Scout-Frage; Doppelklick auf Unternehmen im Panel = dessen Assets hervorheben, übrige abdunkeln (nicht ausblenden).
* **Highlighting:** neutral als Default, automatische Hervorhebung nur nach expliziter Wahl eines Farbmodus oder einer These **[V]** (offene Frage aus den Briefs).

### 2.3 Charakterkarte (erste Detailstufe) **[E: D03]**

Erscheint verankert am Marker bzw. im Kontextpanel. Zwei Varianten:

**Produzierendes Asset:** Name, Land/Region, Betreiber (+ Eigentumsanteile), Rohstoffe (Haupt/Neben), Status seit, Abbauverfahren, Produktion (letzte Periode), Kosten (mit Kostenbegriff), Marge beim aktuellen bzw. Szenariopreis, Reserven/Ressourcen, Restlaufzeit, Datenqualität gesamt, Bild.

**Projekt (Exploration/Entwicklung):** Name, Land/Region, Eigentümer, Rohstoffe, Phase, Studienstand (PEA/PFS/FS + Datum), Baufortschritt/geplante Inbetriebnahme, Studienwerte (Capex, erwartete Produktion, erwartete AISC, NPV/IRR **jeweils mit Preisannahme der Studie**), Ressourcen, nächster Meilenstein, Datenqualität, Bild.

Jede Kennzahl trägt ein **Herkunfts-Chip** (Abschnitt 4.2). Klick auf die Kennzahl öffnet die **Herleitung**: Quelle mit Zitat, Formel, Eingangsgrössen (selbst wieder anklickbar), Zeitraum, Definition, Unsicherheit, Aktualisierungsstand. Fehlende Kennzahl zeigt „unbekannt“ und – falls recherchierbar – den Knopf „Recherche vorschlagen“.

**Bild [O]:** Stufe 1 ohne externes Bild (Kartenausschnitt als Platzhalter). Stufe 2 optionaler Satelliten-Layer aus frei lizenzierter Quelle; Lizenzprüfung ist Voraussetzung (Abschnitt 9).

### 2.4 Auswahlleiste und Vergleich **[E: D04]**

* Leiste unter der Karte **[V]**; Einträge als Mini-Karten (Name, Status, Leitkennzahl), entfernbar, Reihenfolge ziehbar, max. 8 **[V]**.
* Selektierte Assets erhalten auf der Karte Ring + Nummer, die der Position in der Leiste entspricht.
* „Vergleichen“ öffnet Karten nebeneinander mit zeilenweise ausgerichteten Kennzahlen; Unterschiede werden hervorgehoben, unterschiedliche Kostenbegriffe mit Warnhinweis statt stiller Gleichsetzung.
* Szenario-Regler wirkt auf alle selektierten Assets gleichzeitig; ohne Auswahl auf alle sichtbaren.

### 2.5 Zeitleiste, Stichtag und Szenario **[E: D05]**

Drei strikt getrennte Modi, immer als Banner sichtbar:

| Modus | Auslöser | Anzeige |
|---|---|---|
| **Heute** | Default | letzte bekannte Werte, aktueller Preis |
| **Stichtag** | Datum auf Zeitleiste wählen | Zustand „wie damals bekannt“ (Abschnitt 4.4); Umschalter „rückblickend“ zeigt später Bekanntes daneben, nie vermischt |
| **Szenario** | Preisregler oder Preiseingabe | modellierte Werte, Chip „Szenario“, Ausgangswerte durchgestrichen daneben |

Stichtag und Szenario sind kombinierbar („Szenariopreis auf den Datenstand von 2019“), das Banner nennt dann beides.

### 2.6 Scout-Frage, Vorschläge und Backlog **[E: D07]**

1. **Sammeln:** Am Asset, an einer Region, an einer These oder an einer fehlenden Kennzahl „+ Frage“. Es entsteht ein **Vorschlag** (kein laufendes Ticket). Vorlagen: „Fehlende Kennzahl beschaffen“, „Übernahmeziel?“, „Strategische Bedeutung“, „Kostenstruktur erklären“, freie Frage.
2. **Prüfen:** Backlog zeigt Vorschläge mit Auftragstext, betroffenen Objekten, vorgeschlagenen Teilfragen, erwartetem Nutzen (Abschnitt 6.3) und geschätztem Aufwand. Text ist editierbar.
3. **Starten:** einzeln oder gesammelt. Erst jetzt läuft ein Agent.
4. **Weiterarbeiten:** Fortschritt als Badge am Marker und in der Glocke; keine Sperre der Oberfläche.
5. **Ergebnis:** Benachrichtigung mit „zum Ort springen“. Ergebnis erscheint am Asset (Kennzahlen aktualisiert, Erkenntnis im Journal, Quellen verlinkt) und kann einer These als Pro/Contra-Evidenz zugeordnet werden.

Backlog-Zustände: `Vorschlag` → `Bereit` → `Wartet` → `Läuft` → `Abgeschlossen` | `Fehlgeschlagen` | `Verworfen`; zusätzlich Kennzeichen `Aktualisierung nötig`.

### 2.7 Wissensstatus je Objekt **[E: Brief C]**

Abgeleitet, nicht manuell gepflegt:

| Status | Regel |
|---|---|
| Nicht geprüft | Stammdaten vorhanden, keine belegte Kennzahl, kein abgeschlossenes Ticket |
| Bekannt | Pflichtkennzahlen des Steckbriefs mindestens teilweise belegt |
| Vertieft | mindestens ein abgeschlossenes Agenten-Ticket mit Quellen |
| Neue Entwicklung | Ereignis/Fakt seit letztem Besuch |
| Veraltet | jüngste Leitkennzahl älter als Schwelle (Default 15 Monate, Konstante) |

„Nicht geprüft“ heisst nie „existiert nicht“: Die Legende und der leere Zustand sagen ausdrücklich „Über dieses Objekt liegt noch nichts vor“.

### 2.8 Lagebericht „Seit deinem letzten Besuch“ **[E: Brief B]**

Liste der Änderungen seit letztem Besuch oder frei wählbarem Datum, gruppiert nach These → Asset: neue/geänderte Fakten (alt → neu), Status- und Eigentümerwechsel, abgeschlossene Tickets, Ereignisse, Preisbewegungen über Schwelle. Jede Zeile springt zum Objekt auf der Karte. Der Besuchszeitpunkt wird erst beim ausdrücklichen „Als gelesen markieren“ fortgeschrieben.

### 2.9 Lebenslauf, Replay und synchronisierter Vergleich **[E: D08, D09]**

* **Lebenslauf:** Meilensteine (Entdeckung, Ressourcenschätzung, PEA, PFS, FS, Genehmigung, Finanzierung, Baubeginn, erste Produktion, kommerzielle Produktion, Erweiterung, Unterbrechung, Stilllegung, Eigentümerwechsel) auf einer Achse, darunter Rohstoffpreis und – falls vorhanden – Marktkapitalisierung des Eigentümers.
* **Replay:** Schrittweises Vorrücken von Meilenstein zu Meilenstein. Sichtbar ist nur, was bis dahin veröffentlicht war (Abschnitt 4.4). Prognosen der damaligen Studien stehen als „Prognose (Stand JJJJ)“ da; ein Umschalter blendet die tatsächliche spätere Entwicklung als zweite, klar abgesetzte Spur ein.
* **Synchronisierter Vergleich:** Zwei Assets, Anker wählbar („Jahr 0 = Entdeckung / FS / Baubeginn“). Priorität 1 strukturell (Geologie, Gehalt, Verfahren, Infrastruktur, Genehmigungs- und Bauzeiten). Priorität 2 Originalzahlen. Optionale Zusatzspalten: inflationsbereinigt, Rohstoffäquivalent. Originalwerte bleiben immer sichtbar; Zusatzspalten tragen den Hinweis, dass Rohstoffäquivalente keine Kaufkraftbereinigung sind.

### 2.10 Zustände und Bedienqualität

Jede Ansicht hat definierte Zustände leer / lädt / Fehler / Demo. Demo-Daten tragen durchgehend ein Wasserzeichen „synthetisch“. Tastatur: `/` Suche, `Esc` Panel schliessen, `Umschalt+Klick` Mehrfachauswahl, `c` Vergleich, `s` Szenario, `t` Backlog. Desktop-first, Mindestbreite 1280 px; Mobil nur lesend. Animationen nur als Zustandsübergang (≤ 200 ms), abschaltbar über `prefers-reduced-motion`.

---

## 3. Fachmodell

### 3.1 Entitäten

| Entität | Zweck | Bestand |
|---|---|---|
| `Commodity` | Rohstoff mit Einheit, Preissymbol | neu (heute Konstante in `commodities.py`) |
| `Region` | Land / Provinz / Distrikt, hierarchisch | neu (heute `countries.json`) |
| `Asset` | Mine, Projekt oder Lagerstätte mit Koordinaten | neu, ersetzt `Entity(kind=mine)` |
| `Company` | Unternehmen, optional börsennotiert (→ `Stock`) | aus `Entity(kind=company)` + `Stock` |
| `Person` | Management, Schlüsselpersonen | neu, P3 |
| `StatusPeriod` | Status eines Assets über einen Zeitraum | neu |
| `Stake` | Betreiber-, Eigentums-, Royalty-, Stream-Beziehung über einen Zeitraum | neu, ersetzt `Relation(owns)` |
| `Fact` | eine Kennzahl zu einem Subjekt, zeit- und herkunftsbezogen | ersetzt `Datapoint` |
| `Milestone` | Lebenslauf-Ereignis eines Assets | neu |
| `Thesis` | Investmentthese mit Annahmen und Evidenz | erweitert (heute an Aktie gebunden) |
| `Proposal` / `Ticket` | Recherchevorschlag und laufender Auftrag | `Ticket` erweitert |
| `Finding` | Erkenntnis aus Ticket oder Engine | aus `Insight` |
| `Document` | gespeicherte Quelle mit Hash | bleibt |
| `Event` | datiertes Ereignis mit Ort | aus `IntelItem` + `MarketEvent` |
| `Scenario`, `Selection` | gespeicherte Szenarien und Auswahlen | neu |
| `ChangeEntry` | Änderungsprotokoll für den Lagebericht | neu |

Polymorpher Bezug: Fakten, Tickets, Erkenntnisse, Ereignisse und Thesen verweisen über `(subject_type, subject_id)` auf Asset, Company, Region, Commodity oder Thesis. Erlaubte Typen stehen in einem Enum; die Integrität prüft die Service-Schicht.

### 3.2 Tabellen (Kernfelder)

```
commodities   key PK · name_de · unit (oz|lb|t) · price_symbol · color
regions       id · parent_id · kind (country|province|district) · name · iso_code · geometry_ref
assets        id · slug · name · kind (mine|project|deposit) · lat · lon · region_id
              · mining_method (open_pit|underground|isr|heap_leach|placer|mixed|unknown)
              · summary · image_document_id · is_demo · created_at
asset_commodities   asset_id · commodity_key · role (primary|co_product|by_product)
status_periods      asset_id · status (exploration|development|production|care_maintenance|closed)
                    · valid_from · valid_to · document_id · quote
companies     id · slug · name · stock_id? · country · is_demo
stakes        asset_id · company_id · role (operator|owner|royalty|stream|jv_partner)
              · share_pct? · terms? · valid_from · valid_to · document_id · quote
facts         id · subject_type · subject_id · metric_key
              · value? · value_low? · value_high? · text? · unit · currency?
              · period_start? · period_end?          -- worauf sich der Wert bezieht
              · published_at                          -- seit wann öffentlich bekannt
              · recorded_at                           -- wann WatchStreet es gelernt hat
              · provenance (reported|derived|estimated) · claim_kind (actual|guidance|hypothesis|ai_inference)
              · basis?                                -- Definition, z. B. "AISC, by-product, USD/oz"
              · formula_key? · inputs (JSON: fact-ids, Annahmen)?
              · document_id? · quote? · page?
              · confidence (high|medium|low) · origin (user|agent|api|engine)
              · ticket_id? · superseded_by? · is_demo
milestones    asset_id · kind · date · date_precision (day|month|year) · title · document_id · quote
theses        id · title · statement · horizon · status · commodity_key? · created_at
thesis_assumptions  thesis_id · text · status (open|supported|contradicted|unclear)
thesis_links        thesis_id · target_type · target_id · stance (supports|contradicts|context) · note
proposals     id · subject_type · subject_id · thesis_id? · template_key · question · sub_questions (JSON)
              · origin (user|engine|agent) · value_score · state (draft|ready|dismissed|started) · ticket_id?
tickets       (bestehend) + subject_type · subject_id · proposal_id · worker_id · heartbeat_at
findings      id · subject_type · subject_id · ticket_id? · kind (insight|pattern|anomaly|answer)
              · epistemic (correlation|hypothesis|evidenced) · text · uncertainty · created_at
events        id · kind · title · occurred_at · lat? · lon? · region_id? · severity · document_id · is_demo
event_links   event_id · subject_type · subject_id · impact_note
price_points  commodity_key · date · close · source     -- Tagesreihe, lange Historie
scenarios     id · name · prices (JSON commodity→price) · discount_rate? · created_at
selections    id · name · asset_ids (JSON) · created_at
change_log    id · at · subject_type · subject_id · kind · summary · old? · new? · ref_type · ref_id
visits        id · marked_at
```

Regeln:

* `facts` ist **append-only**. Eine Korrektur schreibt eine neue Zeile und setzt `superseded_by`. Nutzereingaben werden nie von Agent/API überschrieben (bestehende Regel bleibt).
* „Unbekannt“ ist kein Datensatz, sondern das Fehlen eines gültigen Fakts; die API liefert es explizit als `{"provenance": "unknown"}`.
* `status_periods` und `stakes` dürfen sich je Asset (und je Rolle) zeitlich nicht widersprüchlich überlappen; Summe der `owner`-Anteile ≤ 100 %.
* Jede Zeile mit `is_demo = true` wird in der Oberfläche als synthetisch markiert; Demo- und Echtdaten liegen nie in derselben Datenbank **[V]** (Start verweigert Mischbetrieb).

### 3.3 Speicherform **[V]** (offene Frage 9)

Relationale Datenbank (PostgreSQL, wie Bestand) mit expliziten Beziehungstabellen. Kein separater Graphspeicher: Die Beziehungen sind wenige, typisierte, zeitabhängige Kanten (`stakes`, `thesis_links`, `event_links`), die sich mit SQL und rekursiven CTEs abfragen lassen. Ein Graph-Export (JSON) bleibt für die Netzansicht. Neubewertung, falls Pfadabfragen über mehr als drei Kanten zum Regelfall werden.

---

## 4. Evidenz, Herkunft und Zeit

### 4.1 Zwei unabhängige Achsen je Kennzahl

| Achse | Werte | Frage |
|---|---|---|
| **Herkunft** (`provenance`) | berichtet · berechnet · geschätzt · unbekannt | Wie kam die Zahl zustande? |
| **Aussageart** (`claim_kind`) | Ist · Unternehmensprognose · eigene Hypothese · KI-Schlussfolgerung | Was behauptet sie? |

Beispiele: AISC aus Jahresbericht = berichtet/Ist. AISC aus Machbarkeitsstudie = berichtet/Prognose. Marge = berechnet/Ist. Kosten aus Diesel, Löhnen, Verfahren = geschätzt/KI-Schlussfolgerung.

### 4.2 Darstellung

* Chip an jeder Zahl: `B` berichtet (voll), `≈` berechnet (Umriss), `~` geschätzt (gestrichelt, immer als Bandbreite `1 150–1 400`), `?` unbekannt. Prognosen kursiv mit Stand-Jahr. Form und Text, nicht nur Farbe.
* Altersanzeige: „Stand GJ 2025“, ab Schwelle Warnsymbol „veraltet“.
* Herleitungsdialog mit festen Abschnitten: **Wert · Definition · Zeitraum · Quelle & Zitat · Formel · Eingangsgrössen · Annahmen · Unsicherheit · Verlauf früherer Werte**.

### 4.3 Regeln (harte Prüfungen im Service)

1. `reported` verlangt `document_id` und ein wörtliches, vom Harness im Dokument verifiziertes Zitat („no source, no fact“ – bestehende Regel).
2. `derived` verlangt `formula_key` und `inputs`; die Herkunft erbt die schwächste Herkunft der Eingaben (eine geschätzte Eingabe macht das Ergebnis geschätzt).
3. `estimated` verlangt `value_low` und `value_high`, eine benannte Methode und mindestens zwei belegte Treiber; sonst wird der Fakt abgelehnt und bleibt unbekannt.
4. Kosten- und Margenfakten verlangen `basis` (Kostenbegriff, Nebenproduktbehandlung, Währung, Zeitraum). Fakten mit verschiedener `basis` werden nie stillschweigend verglichen oder verrechnet.
5. Agentenfakten ohne Dokument sind höchstens `estimated` mit Vertrauen `low`.

### 4.4 Zeitmodell (offene Frage 4) **[V]**

Drei Zeitpunkte je Fakt: **Bezugszeitraum** (`period_*`), **Veröffentlichung** (`published_at`), **Erfassung** (`recorded_at`).

* Sicht „wie damals bekannt“ zum Stichtag *T*: Fakten mit `published_at ≤ T`, je Kennzahl der jüngste Bezugszeitraum.
* Sicht „rückblickend“: Fakten mit `period_end ≤ T`, unabhängig vom Veröffentlichungsdatum.
* Fehlt `published_at`, gilt der Fakt für die Sicht „damals bekannt“ als nicht verfügbar – lieber eine Lücke als Hindsight-Bias.
* `recorded_at` dient nur dem Lagebericht („seit letztem Besuch“), nie der fachlichen Sicht.

---

## 5. Wirtschaftlichkeitsmodell (deterministisch)

Reine Funktionen in `economics/`, ohne I/O, vollständig testbar. Bestehende Ableitungen aus `profiles/derive.py` (NAV per Annuität, AISC-Marge, Restlaufzeit) werden übernommen und auf Asset-Ebene gehoben.

### 5.1 Kennzahlen je produzierendem Asset

Mit Preis `P`, Stückkosten `C` (deklarierte Basis), Jahresproduktion `Q`, Anteil `a`:

| Kennzahl | Formel |
|---|---|
| Marge je Einheit | `P − C` |
| Marge % | `(P − C) / P` |
| Abstand zum Break-even | `(P − C) / P`; Break-even-Preis = `C` |
| Operativer Jahres-Cashflow (100 %) | `Q · (P − C)` |
| Zurechenbarer Cashflow | `a · Q · (P − C)` |
| Preissensitivität | `ΔCF = Q · ΔP`; relativer Hebel `P / (P − C)` |
| Restlaufzeit | `Reserven / Q`, gedeckelt (Konstante) |
| Einfacher Asset-NAV | Annuitätenbarwert des Cashflows über die Restlaufzeit bei Diskontsatz `r` |

Bandbreiten: Ist eine Eingabe ein Intervall, wird das Ergebnis als Intervall gerechnet (Intervallarithmetik, konservativ) und als geschätzt gekennzeichnet.

### 5.2 Nebenprodukte und Mehrrohstoffminen (offene Frage 3) **[V]**

* Kosten werden mit ihrer berichteten Basis gespeichert: `by_product` (Nebenprodukterlöse abgezogen) oder `co_product`.
* Im Szenario mit geändertem Nebenproduktpreis wird die By-product-Kostenbasis neu gerechnet, **wenn** Nebenproduktmengen bekannt sind: `C' = C + Σ Q_by · (P_by,ref − P_by') / Q`. Fehlen Mengen, bleibt `C` unverändert und die Karte zeigt den Hinweis „Nebenproduktgutschrift nicht angepasst“.
* Vergleich über Rohstoffe hinweg nur über Marge % und Break-even-Abstand, nie über absolute Stückkosten.

### 5.3 Projekte

Keine laufende Marge. Angezeigt werden Studienwerte als Prognose mit der Preisannahme der Studie. Szenario zeigt die **erwartete** Marge `P − C_Studie` ausdrücklich als „Prognose × Szenario“ und nimmt Projekte per Default aus der Kartenfärbung nach Wirtschaftlichkeit aus (Schalter).

### 5.4 Rohstoff- und verfahrensspezifische Tabelle

Deklarativ (keine Magic Numbers im Code): je Rohstoff Einheit, übliche Kostenbegriffe (AISC, Cash Cost C1, Gesamtkosten), Pflicht- und Kann-Kennzahlen des Steckbriefs; je Abbauverfahren die Kostentreiber für Schätzungen (Diesel, Strom, Reagenzien, Löhne, Abraumverhältnis; ISR: Säure/Lauge, Bohrfeldentwicklung).

### 5.5 Historische Wirtschaftlichkeit

| Sicht | Eingaben | Kennzeichnung |
|---|---|---|
| Berichtet | damalige berichtete Kosten und realisierter Preis | berichtet / Ist |
| Rückgerechnet | damalige Kosten × historischer Marktpreis | berechnet / Ist |
| Szenario | heutige oder damalige Kosten × frei gewählter Preis | Szenario |

Die drei Sichten erscheinen nie in derselben Spalte.

---

## 6. Recherchekreislauf und Analyse-Engine

### 6.1 Drei Stufen **[E: D11]**

| Stufe | Was | Wann **[V]** (offene Fragen 6, D11) | Kosten |
|---|---|---|---|
| 1 Deterministisch | Kennzahlen rechnen, Lücken finden, Regeln und Ausreisser prüfen | ereignisgetrieben bei neuem Fakt/Preis/Status + nächtlicher Gesamtlauf | keine LLM-Kosten |
| 2 Triage | Nutzen eines Rechercheauftrags bewerten, Vorschlag anlegen | direkt nach Stufe 1, regelbasiert | keine LLM-Kosten |
| 3 Agent | Quellen suchen und lesen, Fakten belegen, Schätzung ableiten, Alternativerklärungen prüfen | **nur nach Freigabe** | LLM |

Hintergrundüberwachung ist damit auf Stufe 1–2 beschränkt; Stufe 3 startet nie selbsttätig. Ausnahme, einstellbar und per Default aus: Auto-Freigabe für die Vorlage „Fehlende Kennzahl beschaffen“ mit Tagesbudget.

### 6.2 Regeln der Stufe 1 (Startumfang)

Deklarative Regeltabelle, jede Regel mit Schlüssel, Schwelle, Text:

* **Lücke:** Pflichtkennzahl des Steckbriefs fehlt oder ist veraltet.
* **Ausreisser:** Stückkosten ausserhalb des robusten Bereichs (Median ± k·MAD) der Vergleichsgruppe gleicher Rohstoff/gleiches Verfahren.
* **Sprung:** Kennzahl ändert sich gegenüber Vorperiode über Schwelle.
* **Sensitivität:** Asset kippt im aktiven Szenario über/unter Break-even.
* **Widerspruch:** zwei gültige Fakten gleicher Kennzahl und Periode weichen über Toleranz ab.
* **Relation:** Kostenentwicklung gegen Treiberreihe (z. B. Öl/Silber-Verhältnis) – Ausgabe ausdrücklich als *Korrelation*, mit Stichprobengrösse; unter Mindestgrösse keine Ausgabe.
* **Nachbarschaft:** Explorationsprojekt innerhalb Radius einer produzierenden Mine mit anderem Eigentümer (Vorlage „Übernahmeziel?“).

Jede Auffälligkeit wird `Finding(kind=anomaly|pattern)` mit epistemischem Status. Es gibt genau drei: **Korrelation**, **begründete Hypothese**, **belegter Zusammenhang** **[E: D10]**. Nur ein Agententicket mit Quellen kann den Status anheben.

### 6.3 Nutzenwert eines Vorschlags (offene Frage 5) **[V]**

`value_score` = gewichtete Summe aus fünf Teilwerten 0–1, Gewichte als Konstanten und in den Einstellungen änderbar:

| Teilwert | Bedeutung | Gewicht |
|---|---|---|
| Erkenntnisgewinn | schliesst Lücke in Leitkennzahl / erklärt Auffälligkeit | 0,30 |
| Relevanz | Bezug zu aktiver These, Auswahl, Portfolio | 0,25 |
| Neuartigkeit | keine ähnliche Recherche in den letzten n Tagen | 0,20 |
| Datenlage | Primärquelle voraussichtlich vorhanden | 0,15 |
| Investmentnutzen | Grösse der Position bzw. Hebel im Szenario | 0,10 |

Der Wert sortiert nur; er verwirft nichts. Die Zusammensetzung ist im Backlog aufklappbar.

### 6.4 Agenten-Workflows (Stufe 3)

Feste Abläufe mit möglichst vielen deterministischen Schritten; das Modell bekommt nur die Schritte, die Urteil brauchen.

| Workflow | Deterministisch | Agent |
|---|---|---|
| `fill_metric` | Quellenkandidaten aus Dokumentenspeicher/EDGAR/hinterlegten URLs, Abruf, Textextraktion, Zitatprüfung | Fundstelle wählen, Wert + Zitat + Basis melden |
| `estimate_cost` | Treiberdaten laden, Vergleichsgruppe bilden, Intervall rechnen | Methode wählen, Annahmen begründen, Grenzen benennen |
| `asset_profile` | Stammdaten-Skelett, Dublettenprüfung | Status, Eigentum, Meilensteine aus Dokumenten belegen |
| `lifecycle` | Dokumentliste chronologisch, Preisreihe zuordnen | Meilensteine und damalige Prognosen extrahieren |
| `strategic_question` | Kontextpaket (Nachbarn, Eigentümer, Kennzahlen) | Antwort mit Pro/Contra, Unsicherheiten, Alternativerklärungen |
| `explain_pattern` | Auffälligkeit, Vergleichsdaten | Hypothesen prüfen, epistemischen Status vorschlagen |
| `read_document` | Abruf, Hash, Extraktion | Einordnung, Faktenvorschläge mit Zitat |
| `situation_report` | Änderungsprotokoll gruppieren | optional sprachlich verdichten |

Werkzeuge des Agenten (alle validiert, alle über Services): `search_documents`, `read_document`, `fetch_url` (nur über `intel/fetch.py`), `record_fact`, `record_milestone`, `record_stake`, `record_status`, `propose_asset`, `record_finding`, `propose_followup`. Folgeaufträge eines Agenten landen als **Vorschlag** im Backlog, nicht als laufendes Ticket. Agentenausgabe bleibt nicht vertrauenswürdig: Schema-, Einheiten-, Bereichs- und Zitatprüfung vor jedem Schreiben.

### 6.5 Ergebnisdarstellung

Ticketergebnis mit festen Abschnitten: **Antwort · Belegte Fakten (mit Zitat) · Schätzungen (mit Bandbreite und Methode) · Unsicherheiten · Geprüfte Alternativen · Nicht gefunden · Quellen · Vorgeschlagene Folgefragen**. „Nicht gefunden“ ist ein gültiges Ergebnis.

---

## 7. Technische Architektur

### 7.1 Leitentscheidungen

| Thema | Entscheidung | Begründung |
|---|---|---|
| Backend | Python, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL – **bleibt** | trägt Harness, Provenienz, Fetcher bereits; getestet |
| Schnittstelle | versionierte JSON-API `/api/v1`, OpenAPI als Vertrag | Voraussetzung für Perspektivwechsel ohne Reload |
| Frontend **[V]** | Single-Page-Anwendung: TypeScript, React, Vite, MapLibre GL JS; Build in eigener Docker-Stufe, Auslieferung als statische Dateien durch FastAPI | Mehrfachauswahl, Vergleich, Szenario, Stichtag und Karte teilen sich Zustand – mit servergerenderten Seiten und Einzelskripten nicht wartbar. Hebt die bisherige Regel „kein Build-Schritt“ bewusst auf. |
| Karte | MapLibre mit **lokal ausgelieferten** Vektordaten (Natural Earth, bereits im Repo) – kein Kachelserver, offlinefähig; optionale Rasterquelle konfigurierbar | läuft ohne Schlüssel und ohne Netz |
| Live-Aktualisierung | Server-Sent Events `/api/v1/stream` (Ticketstatus, neue Ergebnisse), Polling als Rückfall | einfacher als WebSockets, genügt für einen Nutzer |
| Agenten | bestehende Runner (offline, llama.cpp, OpenAI-kompatibel, Anthropic, CLI) und Tool-Schleife – **bleiben** | |
| Betrieb | Docker Compose: `db`, `web`, `worker`, optional `llama-*` – **bleibt** | |

### 7.2 Schichten (import-linter erzwingt die Richtung)

```
web (api, static)  →  services  →  economics · analysis (rein)  →  domain/constants
        ↓                ↓
   harness/worker  →  workflows  →  agents (runner, tools)
                         ↓
                 intel (fetch, connectors)   market (provider)
```

Neue reine Pakete: `economics/` (Abschnitt 5), `analysis/` (Regeln Abschnitt 6.2, Nutzenwert), `temporal/` (Sichten Abschnitt 4.4). Reine Pakete importieren weder ORM noch HTTP.

### 7.3 API (Auszug)

```
GET  /api/v1/commodities                         Rohstoffleiste mit Preis
GET  /api/v1/commodities/{key}/prices?from&to    Zeitreihe
GET  /api/v1/map?commodity&status&bbox&asof&view&color&scenario
                                                 GeoJSON-Features inkl. Farbwert, Wissensstatus
GET  /api/v1/assets/{id}?asof&view&scenario      Charakterkarte
GET  /api/v1/assets/{id}/facts/{metric}          Herleitung inkl. Eingaben und Verlauf
GET  /api/v1/assets/{id}/lifecycle?asof          Meilensteine, Prognosen
GET  /api/v1/companies/{id}                      Unternehmen + Assets
POST /api/v1/compare                             {asset_ids, anchor, asof, scenario}
POST /api/v1/scenarios/evaluate                  {prices, asset_ids} → Kennzahlen je Asset
GET/POST /api/v1/proposals · POST /api/v1/proposals/{id}/start · /dismiss
GET  /api/v1/tickets · /tickets/{id}
GET/POST /api/v1/theses · /theses/{id}/links
GET  /api/v1/changes?since                       Lagebericht
POST /api/v1/visits                              „als gelesen“
POST /api/v1/facts                               Nutzereingabe
POST /api/v1/documents                           Quelle per URL hinzufügen
GET  /api/v1/search?q                            Assets, Unternehmen, Regionen, Thesen
GET  /api/v1/stream                              SSE
```

Jede Kennzahl in jeder Antwort hat dieselbe Form:

```json
{"metric": "aisc", "value": 1310, "low": null, "high": null, "unit": "USD/oz",
 "provenance": "reported", "claim_kind": "actual", "basis": "AISC, by-product",
 "period": "FY2025", "published_at": "2026-02-19", "stale": false,
 "confidence": "high", "fact_id": 4711, "is_demo": false}
```

Szenarioauswertung ist zustandslos und rechnet serverseitig mit denselben reinen Funktionen wie alle anderen Sichten; das Frontend rechnet nichts selbst nach.

### 7.4 Sicherheit und Betrieb

Optionales Passwort mit signiertem Sitzungs-Cookie; Same-Origin-Prüfung für schreibende Aufrufe; strikte Content-Security-Policy (ohne Inline-Skripte); Ports per Default an `127.0.0.1` gebunden; Fetcher mit SSRF-Schutz, Grössen- und Typgrenzen (Bestand); Worker mit Lease/Heartbeat, damit zwei Worker weder denselben Scan noch dasselbe Ticket bearbeiten; Health-Endpunkt mit Datenbank- und Worker-Prüfung; Runbook für Sicherung, Wiederherstellung, Aktualisierung.

### 7.5 Qualität

`make check` bleibt Pflicht (ruff, import-linter, mypy --strict, bandit, pytest ≥ 80 %). Neu: Frontend-Prüfung (`tsc --noEmit`, ESLint, Vitest) und ein Playwright-Durchlauf der Kupfer-Klickstrecke (Abschnitt 10) als Abnahmetest. Eigenschaftsbasierte Tests für `economics/` und `temporal/` (Monotonie in `P`, Intervall enthält Punktwert, keine später veröffentlichte Information in der „damals“-Sicht).

---

## 8. Umgang mit dem Bestand

Angaben nach Kenntnisstand des Branches; vor dem Löschen wird je Modul per Suche geprüft, dass keine Abhängigkeit übrig bleibt.

### 8.1 Bleibt (unverändert oder mit kleinen Anpassungen)

| Modul | Anmerkung |
|---|---|
| `agents/` (Runner, Tool-Schleife, Factory) | unverändert |
| `harness/executor`, `scheduler`, `worker.py` | + Lease/Heartbeat, Subjektbezug |
| `services/tickets.py`, `followups.py` | Leitplanken bleiben; Folgeaufträge werden Vorschläge |
| `intel/fetch.py`, `intel/documents.py`, Zitatprüfung | Kern von „no source, no fact“ |
| `intel/connectors/` (EDGAR, RSS, GDELT, USGS) | liefern Dokumente und Ereignisse |
| `market/` (Yahoo, Demo, Indikatoren) | Aktien- und Rohstoffpreise |
| `db.py`, `migrate.py`, `container.py`, `config.py`, `constants.py`, `errors.py`, `timeutil.py`, `geo.py` | |
| `profiles/derive.py` (NAV, Marge, Restlaufzeit) | wandert nach `economics/` |
| Docker, Compose, Makefile, CI, Sonar, pre-commit | + Frontend-Stufe |
| Holdings/Watchlist-Services | als Bereich „Portfolio“ |

### 8.2 Wird umgebaut

| Bestand | Ziel |
|---|---|
| `Datapoint` | `Fact` (Bandbreite, Zeitachsen, Herkunft, Basis, Formel) – Migration mit Datenübernahme |
| `Entity` / `Relation` | `Asset`, `Company`, `Stake`, `StatusPeriod` |
| `Thesis` (je Aktie) | eigenständige These mit Annahmen und Evidenz-Links |
| `Insight` | `Finding` mit epistemischem Status |
| `IntelItem`, `MarketEvent`, Tripwires | `Event` + `event_links`; Tripwires werden Regeln der Stufe 1 |
| `Briefing` | Lagebericht aus `change_log` |
| `Ticket` | Subjektbezug, Vorschlagsstufe davor |
| Workflows `research_datapoints`, `read_filing`, `sec_sync`, `intel_triage`, `briefing` | `fill_metric`, `read_document`, Konnektor-Job, Stufe 2, `situation_report` |
| `services/scenarios.py`, `cockpit.py`, `mapdata.py`, `exposure.py` | hinter der neuen API, auf Asset-Ebene |
| Automatische Tickets beim Anlegen einer Position | werden Vorschläge (Human-in-the-loop) |

### 8.3 Wird entfernt

| Bestand | Grund |
|---|---|
| Jinja-Seiten und Routen der Oberfläche (`routes_*`, `templates/`, `panels/`) ausser Handbuch | ersetzt durch SPA + API |
| `static/map.js`, `graph.js`, `candles.js`, `tables.js`, `live.js`, `symbols.js`, `app.css` | ersetzt durch Frontend-Komponenten |
| Profile `tech`, `utility`, `financial`, `reit`, `healthcare`, `oil_gas` samt Kriterientabellen | ausserhalb des Fokus Minenanalyse; bei Bedarf neu |
| Workflows `technical_snapshot`, `valuation_score`, `thesis_check`, `event_review`, `initial_*`, `topic_analysis`, `classify_stock` | aktienzentriert; Funktion geht in Stufe 1 bzw. neue Workflows über |
| `Score` und die Scoring-Tabellen | Bewertungspunkte passen nicht zu Evidence-first; ersetzt durch offene Kennzahlen |
| Kraftgerichtete Netzansicht | Beziehungen erscheinen auf Karte und im Panel; Rückkehr nur bei Bedarf |
| Screenshots 01–27, alte Handbuchkapitel | Neuaufnahme nach P1 |

Die Migrationen `0001`/`0002` bleiben eingefroren; der Umbau kommt als neue Revisionen. Vor dem Entfernen wird der Stand als Tag `v0-dashboard` markiert.

---

## 9. Datenquellen (offene Fragen 2 und 8)

| Bedarf | Quelle (Kandidat) | Stand |
|---|---|---|
| Rohstoffpreise, Historie | Yahoo-Futures (Bestand); lange Reihen zusätzlich aus frei verfügbaren Reihen | **[O]** Endpunkte in der Sandbox nie live geprüft |
| Unternehmensberichte USA | SEC EDGAR (Bestand) | nie live geprüft; braucht Kontakt-User-Agent |
| Berichte Kanada/Australien/andere | „Dokument per URL hinzufügen“ + Agent liest | manuell angestossen |
| Technische Berichte (NI 43-101, JORC) | wie oben | wichtigste Quelle für Projekte und Lebenslauf |
| Minenstandorte, Stammdaten | Start: Agenten-Recherche je Asset mit Beleg; Prüfung offener Lagerstättendaten | **[O]** Lizenz und Abdeckung prüfen |
| Ereignisse | GDELT, USGS, RSS (Bestand) | nie live geprüft |
| Kostentreiber (Diesel, Strom, Löhne, Wechselkurse) | öffentliche Statistikreihen | **[O]** |
| Inflation | amtlicher Verbraucherpreisindex | **[O]** |
| Standort-/Satellitenbild | frei lizenzierte Quelle | **[O]** Rechte klären, bis dahin kein Bild |

Grundsatz: Ohne geprüfte Quelle startet die Anwendung mit leerem Bestand plus getrenntem Demo-Datensatz – nicht mit unbelegten „Startdaten“.

**MVP-Pflichtfelder je Asset [V]:** Name, Koordinaten, Land, Hauptrohstoff, Status mit Datum, Betreiber. **Leitkennzahlen Produktion:** Jahresproduktion, Stückkosten mit Basis, Reserven. **Leitkennzahlen Projekt:** Studienstand, Ressource, Capex, erwartete Produktion und Kosten.

---

## 10. Abnahme: gemeinsame Klickstrecke und Szenarien

**Kupferstrecke (aus den Briefs), als automatisierter Durchlauf auf Demo-Daten:**

1. These „Kupfernachfrage wächst langfristig“ öffnen → Karte fokussiert verknüpfte Assets.
2. Rohstoff Kupfer, Region wählen → produzierende Mine anklicken → Charakterkarte mit Herkunfts-Chips.
3. Zum Betreiber wechseln → dessen Assets hervorgehoben, Kartenausschnitt unverändert → zurück zum Asset.
4. Benachbartes Explorationsprojekt per Umschalt+Klick zur Auswahl hinzufügen.
5. „+ Frage: Übernahmeziel?“ → Vorschlag im Backlog, kein laufendes Ticket.
6. Backlog öffnen, Text prüfen, starten.
7. Während das Ticket läuft, andere Region öffnen; Badge „läuft“ am Marker.
8. Benachrichtigung → Sprung zurück → Ergebnis mit Quellen und Unsicherheiten am Projekt; der These als Evidenz zuordnen.
9. Stichtag zurücksetzen bzw. „seit letztem Besuch“ → Änderungen sichtbar.

**Akzeptanzkriterien je Session-Szenario:**

* **A:** Preisregler ändert Marge der Mine und Kartenfarbe aller sichtbaren Assets in < 300 ms (bis 500 Assets); Assets ohne Kosten bleiben schraffiert.
* **B:** Fehlende Kosten → Vorschlag → Start → Ergebnis ist entweder berichteter Wert mit Zitat, geschätzte Bandbreite mit Methode oder ausdrücklich „nicht gefunden“. Nie ein Punktwert ohne Herkunft.
* **C:** Replay zeigt zu keinem Schritt einen Fakt mit späterem Veröffentlichungsdatum (automatischer Test); Vergleich mit Anker „Jahr 0“ zeigt Originalwerte immer.
* **D:** Engine erzeugt für eine Auswahl mit auffälligen Kosten ein Finding „Korrelation“ samt Stichprobengrösse und einen Vorschlag; der Status steigt erst nach Agententicket mit Quellen.

---

## 11. Umsetzungsplan

Jede Phase endet lauffähig, mit grünem `make check`, Migration und aktualisiertem Handbuch.

| Phase | Inhalt | Ergebnis |
|---|---|---|
| **0 Fundament** | Tag `v0-dashboard`; Entfernen laut 8.3; neues Schema (Abschnitt 3) mit Datenübernahme; `economics/`, `temporal/`; API-Gerüst + OpenAPI; Frontend-Gerüst, Build-Stufe, CSP, Login | leere, sichere Hülle; Backend-Tests grün |
| **P0 Karte** | Rohstoffleiste, Karte mit Layern/Clustering, Charakterkarten beider Varianten, Herkunfts-Chips, Herleitungsdialog, Suche, Demo-Datensatz (Au/Ag/Cu/U) | Schritte 2–3 der Strecke |
| **P1 Vergleich & Szenario** | Auswahlleiste, Vergleich, Preisregler, Farbmodi, Zeitleiste mit Preis | Szenario A |
| **P2 Recherchekreislauf** | Vorschläge, Backlog, Start, SSE, Workflows `fill_metric`, `estimate_cost`, `strategic_question`, `read_document`, Dokument per URL, Wissensstatus, Lagebericht, Thesen-Board | Kupferstrecke vollständig, Szenario B |
| **P3 Lebenslauf** | Meilensteine, Stichtagssicht, Replay, synchronisierter Vergleich, Inflations- und Äquivalentspalten, Workflow `lifecycle` | Szenario C |
| **P4 Engine** | Regeltabelle Stufe 1, Nutzenwert, Vergleichsgruppen, `explain_pattern`, Treiberreihen | Szenario D |
| **Betrieb** (parallel ab P0) | Worker-Lease, Health, Runbook, Live-Prüfung aller Konnektoren, Docker-Lauf, echter Modelllauf | einsatzbereit |

Reihenfolge P0–P4 folgt dem Vorschlag der Session; sie ist dort ausdrücklich noch nicht bestätigt.

---

## 12. Offene Entscheidungen mit Vorschlag

| # | Frage | Vorschlag dieses Plans |
|---|---|---|
| 1 | Kartenfarbe | wählbarer Modus, Default neutral nach Status (2.2) |
| 2 | Pflichtfelder MVP | Liste in Abschnitt 9 |
| 3 | Nebenprodukte, Kostenbegriffe | Basis je Fakt speichern, nie stillschweigend mischen (5.2) |
| 4 | Versionierung „damals/heute“ | drei Zeitpunkte je Fakt, append-only (4.4) |
| 5 | Ticket-Priorisierung | transparenter Nutzenwert aus fünf Teilwerten (6.3) |
| 6 | Zeitpunkt deterministischer Analysen | ereignisgetrieben + nächtlich; Agent nur nach Freigabe (6.1) |
| 7 | Darstellung Unsicherheit/Alter | Chips, Bandbreiten, Schraffur, Altershinweis (2.2, 4.2) |
| 8 | Externe Quellen und Rechte | offen; Start ohne Bilder, Stammdaten per belegter Recherche (9) |
| 9 | Persistenz | relational mit Beziehungstabellen, kein Graphspeicher (3.3) |
| 10 | Wiederverwendung | Abschnitt 8 |
| – | Frontend-Technik | SPA mit React/TypeScript/MapLibre, Build im Container (7.1) |
| – | Eine kombinierte Variante statt drei Prototypen | Abschnitt 2 |
| – | Position der Auswahlleiste | unter der Karte |
| – | Portfolio-Bereich | bleibt, verschlankt |

**Vor Beginn von Phase 0 zu bestätigen:** kombinierte UX-Variante, Wechsel auf SPA mit Build-Schritt, Entfernungsliste 8.3 (insbesondere Scoring und Nicht-Minen-Profile).

---

## 13. Risiken

| Risiko | Wirkung | Gegenmassnahme |
|---|---|---|
| Stammdaten für Minen sind nicht frei und vollständig verfügbar | Karte bleibt dünn | Bestand wächst über belegte Recherche; Wissensstatus macht Lücken sichtbar statt sie zu verbergen |
| Kostenbegriffe uneinheitlich | falsche Vergleiche | `basis` verpflichtend, Warnung im Vergleich |
| `published_at` historischer Dokumente unsicher | Hindsight-Bias im Replay | ohne Datum keine „damals“-Sicht |
| Lokale Modelle scheitern an langen technischen Berichten | schwache Ergebnisse | deterministische Vorauswahl von Textstellen, Zitatprüfung, „nicht gefunden“ als gültiges Ergebnis |
| Ticketflut durch Stufe 2 | Überforderung (UX-Frage Brief B) | Vorschläge gebündelt je Asset, Nutzenwert, Obergrenze offener Vorschläge |
| Umfang des Neuaufbaus der Oberfläche | lange Zeit ohne nutzbare Anwendung | Phasen einzeln lauffähig; Tag `v0-dashboard` als Rückfall |
| Externe Endpunkte und Docker-Lauf bisher ungeprüft | Überraschungen im Echtbetrieb | Live-Prüfung als eigener Punkt der Betriebsphase, nicht als Annahme |
