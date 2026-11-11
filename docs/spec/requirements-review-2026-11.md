# Requirements-Review aus zwei Investorensichten (11. November 2026)

Zwei Unteragenten haben die Demo-Anwendung im Browser und über die API bedient: einer mit der Brille
eines Rohstoff-Spekulanten in der Art von Rick Rule (Kostenposition, Menschen, Bilanz, Verwässerung,
Royalties), einer mit der Brille eines Makro-Investors in der Art von Ray Dalio (prüfbare Thesen,
Szenarien, Entscheidungsprotokoll). Es sind keine Aussagen dieser Personen, sondern Ableitungen aus
ihrem öffentlich bekannten Vorgehen.

## Sofort behoben

| Befund | Korrektur |
|---|---|
| „Wie damals bekannt“ zeigte Erkenntnisse und Recherchen, die erst später entstanden | Objektansicht filtert sie am Stichtag aus |
| Demo: Vorjahreswert zitierte den Bericht des Folgejahres | eigener Demo-Bericht 2024 mit eigenem Veröffentlichungsdatum |
| Erfolglose Suche machte ein Objekt „vertieft untersucht“ und hiess „Begründete Hypothese“ | „vertieft“ nur bei belegtem Ergebnis oder Agentenbewertung; neuer Belegstatus „Nicht belegt“ |
| Recherchierte Kennzahl trug das Veröffentlichungsdatum als Berichtszeitraum | Zeitraum bleibt leer; Anzeige „veröffentlicht JJJJ, Zeitraum unbekannt“ |
| Demo-Projekte führten ein Reserven-Zitat als Ressourcen | eigener Satz für Ressourcen |
| Keine Rangliste der Kostenposition | Übersicht sortiert nach Stückkosten, mit Marge in der aktuellen Ansicht |
| Szenario ohne Gesamtaussage | Banner: Minen mit negativer Marge, Produktionsanteil, Minen ohne Kostendaten |
| Evidenz erschien als „Erkenntnis #n“ | Text, Belegstatus und Sprung zum Objekt |
| Neue These wurde nicht aktiv; Horizont und Rohstoff nicht setzbar | behoben |
| Aktive These war nur in der Adresse sichtbar | Hinweis beim Vormerken einer Frage |
| Thesen- und Annahmeänderungen fehlten im Lagebericht | werden protokolliert |
| `/changes?since=<Datum>` lieferte Fehler 500 | Datum wird akzeptiert, Ungültiges ergibt 422 |
| Vergleich nummerierte anders als die Auswahlleiste | Reihenfolge der Auswahl |
| Englische Rohstoffnamen in Karte und Banner | deutsch |

## Offen – Unternehmens- und Finanzierungssicht (Rule)

| Prio | Anforderung | Datenmodell |
|---|---|---|
| MUSS | Unternehmenskarte mit Kasse, Schulden, Burn-Rate, Reichweite in Monaten | Fact auf Company; Ansicht fehlt |
| MUSS | Aktienzahl, Optionen/Warrants, Finanzierungshistorie (Verwässerung) | Fact, Milestone auf Company |
| MUSS | Management, Insiderbesitz, Erfolgsbilanz | Person fehlt |
| MUSS | Royalties, Streams, JV-Bedingungen sichtbar und in der Marge netto gerechnet | Stake vorhanden; Rechnung und Anzeige fehlen |
| MUSS | Fragenkatalog je Unternehmen mit Status und Belegverweis | Proposal-Vorlagen, Finding |
| MUSS | Kennzahlen direkt als Evidenz einer These zuordnen | `thesis_links` um `fact` erweitern |
| SOLL | Jurisdiktionsrisiko je Region, eigener Farbmodus | Fact auf Region |
| SOLL | Ressourcen nach Kategorie, Gehalt, Ausbringung, Studienstand mit Datum | neue Kennzahlen |
| SOLL | Börsenwert/EV gegen Summe der Asset-NAV, EV je Einheit Ressource | Company↔Stock |
| SOLL | Sensitivitätstabelle ±30/50 %, Capex gegen Kasse, Zyklusposition gegen Grenzkosten | berechnet |
| KANN | Prospect-Generator-Sicht; freier Cashflow statt Marge × Produktion | Stake, Fact |

## Offen – Thesen, Szenarien, Portfolio (Dalio)

| Prio | Anforderung | Datenmodell |
|---|---|---|
| MUSS | Je Annahme ein messbares Falsifikationskriterium mit Prüfdatum; Statuswechsel mit Begründung | Annahme erweitern |
| MUSS | Evidenz und Gegenevidenz je Annahme; „0 Gegenargumente geprüft“ ausweisen | Link braucht Annahme-Bezug |
| MUSS | Positionen mit Unternehmen, Minen und Thesen verknüpfen | Holding→Company/Thesis |
| SOLL | Mehrrohstoff-Szenarien mit Kosten und Diskontsatz speichern und benennen | Scenario |
| SOLL | Makrogrössen (Realzins, Dollar, Inflation) als Objekte mit Herkunft | Indikator oder neues Fact-Subjekt |
| SOLL | Wachstums-/Inflationsregime als Szenariovorlagen | baut auf Szenarien auf |
| SOLL | Portfolio-Stresstest und Konzentration je Rohstoff, Land, These | nach Verknüpfung |
| SOLL | These am Stichtag ansehen | nach Protokollierung möglich |
| SOLL | Nebenproduktpreise im Szenario berücksichtigen | Mengen als Fact |
| KANN | Quellen nach Trefferhistorie gewichten; Stilllegungslogik im NAV | Bewertung am Dokument |

## Wo die Anwendung weiterhin zu falscher Sicherheit verleiten kann

* **NAV und Cashflow** lesen sich wie Bewertungen, enthalten aber weder Steuern, Royalties,
  Investitionen, Schulden, Eigentumsanteil noch Länderabschlag; Diskontsatz (8 %) und konstante
  Produktion sind nicht sichtbar; negative NAVs unterstellen Weiterbetrieb mit Verlust.
* **Zeichen „B“ mit hohem Vertrauen** bestätigt nur, dass das Zitat wörtlich im Dokument steht.
* **Szenario ändert nur den Preis** eines Rohstoffs; Kosten, Währung, Nebenprodukte und
  Zusammenhänge zwischen Rohstoffen bleiben fest.
* **Marge aus einem einzigen Jahr**; ein Kostentrend wird nicht fortgeschrieben.
* **Annahmestatus „gestützt“** ist ein Klick ohne Belegpflicht.
* **Nutzenwert** mit zwei Nachkommastellen wirkt wie eine Wahrscheinlichkeit.
* **Asset-Sicht blendet das Unternehmensrisiko aus** (Bilanz, Verwässerung).
* Marker in dicht besetzten Regionen überlappen; die Margenlegende nennt keine Zwischenwerte.
