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

## Seit dem Review umgesetzt

| Sicht | Anforderung |
|---|---|
| Rule | Unternehmensansicht: Kasse, Schulden, Mittelabfluss, Reichweite, Aktienzahl, Verwässerungsüberhang, Finanzierungen |
| Rule | Menschen mit Erfolgsbilanz, Insiderbesitz |
| Rule | Royalties und Streams sichtbar und in der Marge netto gerechnet |
| Rule | Prüfkatalog je Unternehmen mit zehn Fragen und Recherche-Vorlagen |
| Rule | Kennzahlen direkt als Evidenz einer These |
| Rule | Börsenwert gegen Summe der Asset-NAV, Preishebel ±30/50 % |
| Rule | Engine-Regel „Reichweite unter zwölf Monaten“ |
| Rule | Unternehmenswert, Capex gegen Kasse (Finanzierungslücke), Erfassung von Personen und Finanzierungen |
| Rule | Ressourcen nach Kategorie, Gehalt, Ausbringung, Datum der Studie als Kennzahlen |
| Rule/Dalio | NAV rechnet Verlustbetrieb als Stilllegung |
| Dalio | Kriterium und Prüfdatum je Annahme, Statuswechsel nur mit Begründung |
| Dalio | Evidenz und Gegenevidenz je Annahme, mit Zählung |
| Dalio | Positionen mit Unternehmen, Objekten und Thesen verknüpft |

## Offen – Unternehmens- und Finanzierungssicht (Rule)

| Prio | Anforderung | Datenmodell |
|---|---|---|
| SOLL | Jurisdiktionsrisiko je Region, eigener Farbmodus | Fact auf Region |
| SOLL | Zyklusposition gegen Grenzkosten | berechnet |
| KANN | Prospect-Generator-Sicht; freier Cashflow statt Marge × Produktion | Stake, Fact |

## Offen – Thesen, Szenarien, Portfolio (Dalio)

| Prio | Anforderung | Datenmodell |
|---|---|---|
| SOLL | Mehrrohstoff-Szenarien mit Kosten und Diskontsatz speichern und benennen | Scenario |
| SOLL | Makrogrössen (Realzins, Dollar, Inflation) als Objekte mit Herkunft | Indikator oder neues Fact-Subjekt |
| SOLL | Wachstums-/Inflationsregime als Szenariovorlagen | baut auf Szenarien auf |
| SOLL | Portfolio-Stresstest und Konzentration je Rohstoff, Land, These | Verknüpfung vorhanden |
| SOLL | These am Stichtag ansehen | Protokoll vorhanden |
| SOLL | Nebenproduktpreise im Szenario berücksichtigen | Mengen als Fact |
| KANN | Quellen nach Trefferhistorie gewichten | Bewertung am Dokument |

## Zweiter Durchlauf (Rule-Sicht, nach Umsetzung der Unternehmensansicht)

Behoben: Datum „Kasse rechnerisch leer“, Stichtag wirkt auch auf Kurs und Finanzierungen, Prüfung des
Finanzierungsformulars (Betrag Pflicht, kein Zukunftsdatum, Art wählbar), keine doppelten eigenen
Vorschläge, Preishebel „nicht anwendbar“ statt Nullen und ohne Verlustminen, NAV-Summe nennt ihre
Abdeckung und zählt nur Objekte mit Eigentumsanteil, Börsenwert voll verwässert, Lücke als Vielfaches
des Börsenwerts, Formeltexte nennen die Royalty, Zahlen im Lagebericht ohne Exponentialschreibweise.

| Prio | Offen | Begründung |
|---|---|---|
| MUSS | Finanzierungen strukturiert (Warrants, Abschlag, Zeichner) mit Pro-forma-Wirkung auf Kasse und Aktienzahl | die Konditionen sind die eigentliche Verwässerung |
| MUSS | Projektbewertung nach Capex: Studien-NPV/IRR gegen Börsenwert | „Preis gegen Wert“ für Entwickler |
| MUSS | Eigene Einträge korrigieren und stornieren | Tippfehler dürfen nicht bleiben |
| SOLL | Personen mit früheren Unternehmen, Aktienbesitz, Insiderkäufen | Menschen zuerst |
| SOLL | Genehmigungs- und Jurisdiktionsstatus je Projekt | entscheidet, ob gebaut wird |
| SOLL | Wertmodell für Royalty-Halter; Preishebel für Entwickler | Optionalität |
| SOLL | Rechercheergebnis „nicht belegt“ statt „abgeschlossen“; Prüfkatalog strenger (Kosten aller Minen) | falsche Sicherheit |
| KANN | Unternehmensvergleich, Zyklusindikator | |

## Dritter Durchlauf (Dalio-Sicht) und Umsetzung der Rule-Liste

Aus der Rule-Liste umgesetzt: Finanzierungen mit Warrants, Zeichnern und Pro-forma-Wirkung;
Studien-NPV gegen Börsenwert; Stornieren von Kennzahlen und Löschen eigener Personen und
Finanzierungen; Personen mit früheren Unternehmen und Aktienbesitz; Kennzahl „Genehmigungen und
Jurisdiktion“; Wert für Royalty-Halter; Ergebnis „Abgeschlossen – nicht belegt“; Prüfkatalog verlangt
Kosten aller produzierenden Minen.

Aus dem Dalio-Durchlauf behoben: Stress-Banner zählt nur Minen mit dem gewählten Hauptrohstoff;
Stichtag und Kaufdatum in der Zukunft werden abgelehnt; Änderungen an Kriterium, Prüfdatum und
Evidenz stehen im Lagebericht, Status deutsch mit neuem Wert; Rückkehr auf „offen“ braucht eine
Begründung; Verknüpfung auf nicht vorhandene Objekte wird abgelehnt; Warnhinweise bei „gestützt trotz
Gegenevidenz“, „ohne Evidenz“ und „ohne Kriterium“; Portfolio zeigt widerlegte Annahmen und fällige
Prüfungen je These.

| Prio | Offen | Begründung |
|---|---|---|
| erledigt | Position mit These und Ausstiegsbedingung; Entscheidungsprotokoll mit damaligem Wissensstand | |
| erledigt | Wissensstatus, Quellen und Vorschläge am Stichtag gefiltert | |
| SOLL | Thesenstatus aus Annahmen ableiten; fällige Prüfungen in Glocke und Lagebericht | |
| SOLL | Preis und berechnete Grössen als Evidenz; Knopf „Objekt der These zuordnen“ | |
| SOLL | Portfolio-Stresstest, Mehrrohstoff-Szenarien, Kosteninflation, Kostentrend | |
| SOLL | Preishebel für Entwickler; Unternehmensvergleich | Rule |
| KANN | Überzeugungsgrad je Annahme, Ursache-Wirkungs-Kette, Korrelation | |

## Vierter Durchlauf (Inversion, in der Art von Charlie Munger)

Leitfrage: Wie bringt das Werkzeug seinen Nutzer dazu, sich etwas vorzumachen? Testfall war eine
Newsletter-Liste mit zu günstigen Zahlen.

Behoben: „ungeprüft“ vererbt sich auf Marge, Cashflow, NAV, Unternehmenssummen, Kostenrangliste und
Szenario-Banner; ein Import allein macht ein Objekt nicht „bekannt“ und erfüllt den Prüfkatalog nicht;
Selbstbestätigung nur mit Begründung, bleibt als „eigene Annahme“ mit niedrigem Vertrauen markiert;
Abweichungen zwischen Analyse und belegter Zahl bleiben als Auffälligkeit am Objekt; Plausibilitätsgrenzen
im Import; Storno stellt den Vorwert wieder her; Kauf nur mit Absicht und Ausstiegsbedingung;
Änderungseintrag nennt alt und neu; Entfernen wird protokolliert; Begründungen brauchen mindestens zehn
Zeichen; der Wissensstand im Protokoll enthält die Objektzahlen mit Prüfstatus; Restlaufzeit nennt ihre
Kappung bei 30 Jahren; Prüfdatum und Kriterium einer Annahme lassen sich einzeln ändern; „Verbindung
testen“ prüft die Eingabe im Formular.

| Prio | Offen | Begründung |
|---|---|---|
| erledigt | Schalter „nur Belegtes“; durchgängige Basis „Kasse heute (geschätzt)“ und „Aktien heute“ inkl. Warrants; gerundete abgeleitete Werte; Nutzenwert ausgeblendet | |
| SOLL | Je Quelle „Wer verdient daran?“ und eine Bilanz bestätigt/widerlegt/offen | Anreize und Trefferquote |
| SOLL | Markierung „zu schwierig“ je Objekt oder Unternehmen | bewusst nicht investieren |
| SOLL | Hinweis beim Kauf bei leerer Kasse oder Lücke über dem Börsenwert; Zähler „Ausstieg n-mal geändert“ | |
| SOLL | Realisiertes Ergebnis geschlossener Positionen; Nachkäufe | |
| Entscheidung | Weglassen oder entschärfen: Börsenwert/Studien-NPV und Börsenwert/Asset-NAV, Nachkommastellen, Nutzenwert im Backlog, „Kasse pro forma“ ohne Ausgaben, Übernahme-Vorschläge aus blosser Nähe, Zählung im Prüfkatalog | täuschen Präzision vor oder nähren Spekulation |

## Fünfter Durchlauf: Handelsnutzen (Rule-Sicht) und Privatanleger für Junior-Minen

Leitfrage: Was fehlt, um Minen-, Royalty- und Rohstoffaktien damit zu handeln? Zweite Sicht: der
eigentliche Zielnutzer, technisch versiert, wenig Zeit, kein Analyst, auch am Handy.

Umgesetzt: Seite „Unternehmen“ zum Sichten; Import von Unternehmenszahlen, Nennung ignorierter
Spalten; Nachkauf, Teilverkauf, realisiertes Ergebnis, Depotwert und Gewichte; Kursschwelle und
Mindestreichweite mit Hinweis an der Position; angekündigte Finanzierungen als Was-wäre-wenn; Abschlag
der letzten Finanzierung und Preisfolge; Royalty-Halter folgt der Stilllegung des Betreibers, eigene
Royalties zählen nicht als Belastung; Wissensstand im Protokoll auf heutiger Basis; Formulare behalten
Eingaben nach einer Ablehnung; eigenes Zeichen für importierte und selbst bestätigte Zahlen; Glossar;
Layout für schmale Bildschirme.

| Prio | Offen | Für wen |
|---|---|---|
| 1 | Termine und Katalysatoren mit Datum, Kalender über alle Werte | alle |
| 2 | Benachrichtigungen in der Glocke: Schwelle berührt, Reichweite unter sechs Monaten, Termin fällig | alle |
| 3 | Unternehmensvergleich mit Bewertungsverhältnissen (EV je Cashflow, je Reserve, je Jahresproduktion) | Betreiber |
| 4 | Eigenes Datenmodell für Royalties: Art, Fläche, Rückkauf, Stadium, Gegenpartei, Konzentration, Wachstum je Aktie | Royalty |
| 5 | Kursverlauf der Aktie gegen Rohstoff und gegen die eigenen Finanzierungspreise | alle |
| 6 | Warrants als eigene Position; Kapitalgeschichte (Aktienzahl über die Zeit) | Junior |
| 7 | Pressemitteilung einordnen: was ist neu gegenüber dem Bekannten | Junior |
| 8 | Freier Cashflow: Erhaltungsinvestitionen, Steuern, Schuldenfälligkeiten | Betreiber |
| 9 | Watchlist mit Kaufbedingung; Lagebericht nur für eigene Werte | alle |
| 10 | Menschen prüfbar: Insiderkäufe, Teilnahme an Platzierungen | Junior |

Bewusst nicht bauen: Kursziele und „fairer Wert“ je Aktie, Kauf-/Verkaufsampel, Warrant-Bewertung nach
Black-Scholes, wahrscheinlichkeitsgewichtete NAV für Explorer, Intraday-Kurse und Chartsignale,
automatische Positionsgrössen.

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
