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


## Sechster Durchlauf: Makro-Ebene (Rollenspiel im Stil einer Makro-Analystin, Lyn-Alden-Schule)

Auftrag: Was braucht eine Makro-Ebene, damit sie nicht in die Irre führt?

**Umgesetzt**

* Reihen als gespeicherte Objekte mit Einheit, Frequenz, Beobachtungstag und Hinweis auf Verzug.
* Nettoliquidität mit Einheitenumrechnung, nur an Bilanzstichtagen, ohne Auffüllen.
* Zinsblock mit marktbasiertem Realzins und Zinskurve; Dollar-Index mit Hinweis „nicht der DXY“.
* Nenner-Umschalter (Dollar, Gold, inflationsbereinigt) in der Makro-Ansicht und am Preisverlauf.
* Feste Verhältnis-Charts; logarithmische Skala; Zerlegung der Dollar-Änderung, als Rechnung beschriftet.
* Makro-Stand im Entscheidungsprotokoll.

**Offen (Muss laut Review)**

1. Veröffentlichungsdatum und Vintage (ALFRED) je Beobachtung, damit „wie damals bekannt“ stimmt.
2. Maschinenlesbares Kriterium einer Annahme (Reihe, Operator, Schwelle, Dauer) mit Hinweis „Prüfen“.
3. Nenner für Aktienkurs und Depotwert (braucht gespeicherte Kursverläufe).
4. AISC in Landeswährung an der Charakterkarte; Diskontsatz und Energiekosten im Szenario.

**Offen (Soll)**: Fiskalblock (Schulden/BIP, Zinsausgaben), benannte Makro-Szenarien, frei
überlagerbare Charts mit Basis 100, Heimwährung des Nutzers als Nenner.

**Nicht bauen**: Signale, Ampeln, Liquiditäts-Score, Prognosen, Überlagerung mit frei skalierter
zweiter Achse, vorwärts gefüllte Monatswerte, „fairer Wert“ von Gold aus M2.


## Siebter Durchlauf: öffentliche Plattform, Öl und Gas, Holz, neue Charts (alle vier Sichten)

Rollenspiel im Stil von vier bekannten Denkweisen (Rohstoff-Finanzierer, Prinzipien-Investor,
Inversion, Makro) – keine Aussagen der realen Personen. Auftrag: Was fehlt, damit jede dieser
Sichten das System empfehlen würde, wenn es öffentlich wird? Das Zielbild dazu steht in
[`product-vision.md`](product-vision.md).

**Worin sich alle vier einig sind**

* Der Prüfmassstab („keine Quelle, kein Fakt“) ist in allen Stufen gleich; bezahlt wird Tiefe, nicht Nachsicht.
* Werbende und Emittenten haben keinen Zugang zum Inhalt.
* Die Entscheidungsebene stützt die eigene Überlegung des Nutzers und gibt nie ein Urteil ab.
* Landeigentümer und Royalty-Halter brauchen ein eigenes Modell neben den Betreibern.
* Energie verbindet alle Rohstoffe.

**Rangfolge der Anforderungen**

1. Werbe-Firewall: kein Geld von Emittenten, Brokern oder aus dem Handel; die Werbeanfrage trägt keine Nutzerdaten. Prüfbar an der Anfrage und an einer Sperrliste in der Konfiguration.
2. Lizenzregister je Datenquelle; nicht lizenzierte Reihen sind im öffentlichen Betrieb verborgen.
3. Eigentümer/Betreiber-Modell mit Verlauf je Aktie (ein Unternehmen, das seine Aktienzahl verdoppelt, zeigt halbierte Fläche je Aktie).
4. Gleiche Prüfung in allen Stufen, dazu eine veröffentlichte, stichprobenartig von Hand ermittelte Fehlerquote der Agenten-Fakten.
5. Kennzahlensätze für Öl und Gas sowie Holz (siehe Zielbild, Abschnitt 6); Gas wird nie in Barrel umgerechnet.
6. Hebel-Chart als exakte Zerlegung in jedem Nenner, Rest immer sichtbar; keine angepasste Korrelation.
7. Entscheidungsebene = eigene Prinzipien als prüfbare Regeln + „so verliere ich hier Geld“ vor dem Kauf + getrennt bewertetes Protokoll (Überlegung / Ergebnis).
8. Diskussion nur an Objekt oder Fakt, mit Offenlegung, ohne Zustimmungsknöpfe; Gewicht nach aufgelösten eigenen Annahmen.

**Weitere Muss-Punkte einzelner Sichten**

* Schuldenplan aus Berichten: Fälligkeiten, Auflagen, Absicherungen, je mit Zitat.
* Treiber-Tabelle über das Depot (Realzins, Dollar, Öl, Baubeginne): Wie viele wirklich verschiedene Wetten halte ich?
* Ein Energieszenario rechnet die Kosten von Minen und Sägewerken und die Margen der Förderer gemeinsam neu.
* Kapitalzyklus je Rohstoff: Investitionen gegen Abschreibungen, Bohranlagen, Lager, eröffnete und geschlossene Kapazität – je mit Veröffentlichungsdatum.

**Widersprüche (Entscheidung offen)**

* Diskussion: gewichtet einführen – oder ganz lassen, weil Privatanleger-Foren selten helfen.
* Anzeige „Kapitalmangel“ (eingeworbenes Geld je Rohstoff gegen Preis und Grenzkosten): gewünscht als Werkzeug für antizyklisches Handeln, aber nahe an einem Signal, das die sechste Runde ausschliesst.
* Korrelationen über das Depot gewünscht; im Hebel-Chart verboten.
* Eine Sperre „ausserhalb meines Kompetenzkreises“ vor einem Kauf bremst das Wachstum der Plattform.

**Nicht bauen**: bezahlte Profile oder Recherche für Emittenten; Vermittlungsprovisionen von
Brokern; Benachrichtigungen, die auf Verweildauer optimiert sind; Zustimmungsknöpfe,
„meistgehalten“-Listen, Ranglisten nach Rendite; ein Hebel-Finder, der Fenster und Reihen nach
der besten Übereinstimmung absucht.

**Voraussetzung, die keine der vier Sichten nannte**: Die Anwendung ist für eine Person gebaut.
Vor jedem öffentlichen Schritt steht die Trennung von Depot, Thesen, Protokoll, eigenen Einträgen
und Importen je Nutzer.

**In diesem Durchlauf umgesetzt**: Rohöl, Erdgas und Holz im Rohstoffkatalog; Makro-Reihen für
Erdgas, Baubeginne und Hypothekenzins; Verhältnis Holz ÷ Gold; Umschalter Hell/Dunkel.


## Achter Durchlauf: Pilot der Charts mit fünf Personas (17. November 2026)

Fünf Unteragenten haben die Anwendung im Browser bedient (Demo-Daten): Anfängerin,
Junior-Minen-Spekulant, Makro-Traderin, Profi-Analyst, langfristige Sparerin.

| Ansicht | Urteil | Begründung |
|---|---|---|
| Massstab-Matrix | behalten (5 von 5) | beantwortet „echt oder nur der Dollar?“ auf einen Blick |
| Hebelkette | behalten (4), ändern (1) | Summen stimmen; Kette ist fest, nicht wählbar |
| Eigenwert | behalten (2), ändern (3) | trifft die Frage „Metall oder Firma?“; Sprache zu fachlich, bei schwacher Schätzung Rauschen |
| Ganze Leiter | behalten (3), ändern (2) | zeigt, was sich bewegt; reihte Treiber auch ohne belastbaren Zusammenhang auf |
| Weg | behalten (1), ändern (4) | ohne Zeitmarken schwer lesbar, auf dem Telefon unbrauchbar |
| Raum (3-D) | ändern (1), Spielerei (1) | Drehung funktioniert, bringt gegenüber dem Weg keine zusätzliche Information |
| Zyklusuhr | ändern (2), rauswerfen (3) | Beschriftung zu klein, wenige Umläufe, Zeiträume mit einem Wert |
| Linse | behalten/ausbauen (1), nichts für Laien (1) | Einheitenprüfung besser als TradingView; Monats- gegen Tagesreihe ergibt fast nichts |
| Regimekarte | behalten (1), ändern (2) | „Kauf/Verkauf“ in der Legende wirkte wie ein Signal |

**Sofort umgesetzt**: schwache Schätzungen grau mit t-Wert statt „hängt an“; Hinweis bei
überlappenden Jahresraten; „Punkte“ erklärt und der Eigenwert in einem Satz mit Prozent; Hebelkette
und Matrix nutzen denselben Ausgangstag; die Auswahl bleibt beim Wechsel des Reiters; die Leiter
endet, wo sich der Kreis schliesst; grössere Schrift an der Zyklusuhr, Zeiträume unter drei Werten
nicht aufgeführt; Legende der Regimekarte spricht von „deinem“ Kauf; Auswahlfelder laufen auf dem
Telefon nicht mehr aus dem Bildschirm.

**Offen – Muss**

1. Einfache Sprache: ein Satz „Was bewegt meine Aktie?“ oben und „Was heisst das?“ an jeder Zahl (3 Personas).
2. Linse: Monatsreihen gegen Tages- und Wochenreihen verrechnen (letzter veröffentlichter Wert, gekennzeichnet), Frequenzwahl.
3. Mehrere Treiber zugleich (Regression auf zwei bis drei Faktoren) und eine eigene Treibertabelle des Nutzers.
4. Unternehmensseite: „Kasse heute 0“ neben „Kasse 9 Mio.“ und „Reichweite 0 Monate“ neben „8 Monate“ erklären oder abgleichen; Kursverlauf und Bohrergebnisse mit Datum.
5. Nenner-Umschalter in der Makro-Ansicht ist nicht auffindbar (2 Personas).
6. Monatszusammenfassung „Was hat sich für mein Depot geändert?“.

**Offen – Soll**: Überlagerung zweier Reihen; weitere Funktionen (Korrelation, z-Wert, Vergleiche);
Aliase und Vorschläge beim Tippen; Unsicherheitsband an der Steigung; CSV-Export; Regime mit
Schwellen beschriften; Weg auf dem Telefon; Jahreszahlen überlagern Achsentitel im Weg und im Raum.

**Entscheidung offen**: Zyklusuhr und Raum behalten oder entfernen. Drei von fünf würden die
Zyklusuhr streichen; ein belastbares Urteil braucht echte Daten mit mehreren Umläufen.


## Neunter Durchlauf: Kaufkraft statt Dollar – the yardstick problem (17. November 2026)

*Design note, in English.* Owner's requirements after the demo: the 3-D view has the dollar inside
every notation; time must be a dimension; values need an inflation-neutral notation, and gold
ounces still carry a regime factor; the macro series must be real history.

**The yardstick problem.** Every "real" price is a ratio, price ÷ numeraire, and every candidate
numeraire is biased in a known direction. CPI is a contested basket (hedonics, owners' rent).
Wages rise faster than prices by productivity, so everything drifts cheaper in working hours. M2
grows with the real economy and financial deepening and jumped in 2020. Oil is the master
resource but is the noisiest series in the set (12-month moves of −77 % and +400 % in 2020). Gold
has its own regime. That last point was checked on the bundled data instead of assumed: monthly
changes of gold/CPI against changes of the 10-year TIPS yield give a stable slope of about −0.10
log per percentage point (2003–21: −0.107, 2022–26: −0.090), but the *level* relationship broke
(R² 0.67 for 2003–21, 0.13 for 2003–26; the slope even turns positive after 2022). Removing the
real-rate component from gold changes its 2003–26 real rise of +188 points (100 × log) by three
points. It explains almost all of gold's real loss in 2020–22 (−23 of −25 points) and none of the
+83 points since October 2022. A "regime-free gold" built from real rates is therefore still not a
neutral yardstick; its regime is mostly something else (central-bank buying, fear, monetary trust),
and no fitted model of that would survive a sceptic.

**Chosen answer: the purchasing-power band ("Kaufkraft").** Measure the value in five yardsticks at
once (basket, working hour, share of M2, ounce of gold, barrel of oil), month by month, and draw
time on the x-axis and yardstick disagreement as the vertical extent of a band: the median as a
bold line, the inner band without the most extreme yardstick at each end, the outer band from the
lowest to the highest, and below it a strip that says per month whether all, most or no majority
of the yardsticks show a gain. Every line is a ratio of two dollar prices, so the dollar cancels
exactly (tested: debasing every price by the same arbitrary path changes nothing). Gold's regime is
handled without a model: it is one vote of five, the median ignores a single dissenter, the table
counts how often each yardstick disagreed alone, and choosing gold as the value shows its regime
against the other four. One sentence for a non-expert: *if the whole band lies above zero, the
value gained purchasing power whatever you measure it in; if it crosses zero, the verdict depends
on the yardstick.* A useful by-product: the band's width does not depend on the value at all, only
on how far the yardsticks drift apart; choosing "US-Dollar (Bargeld)" shows the bare band.

**What it showed on real data (2003–Sept 2026).** The dollar lost against all five (−46 % in
baskets to −92 % in gold). Copper gained in four of five (median +197 %), lost only in gold (−28 %);
gold was the lone dissenter in 101 months. Oil since 2003: the verdict depends on the yardstick
(up in baskets and hours, down in M2 and gold); since August 2011 it lost in all four. The gold and
silver miners (PHLX XAU, from September 2004): +133 % in baskets but −61 % in gold, and from 2013 to
2019 below their 2004 level in every yardstick – the miners' bear market reads as one solid red
stretch. Rolling 12 months: in December 2008 gold held its purchasing power (median 0 %) while
copper (−54 %) and oil (−56 %) lost in every yardstick except, for copper, oil itself; to August
2011 gold gained 28–42 % in all four; in the twelve months to June 2013 it lost 17–28 % in all four;
in 2022 it lost 5–6 % against baskets and hours but nothing against M2, which shrank. A dollar
chart shows none of this: in 2022 it shows gold flat.

**Alternatives rejected.** *One "best" numeraire* (CPI, gold, M2): each answers one question and
hides the others; the owner's own objection to gold applies to all of them. *A fitted basket*
(weights by inverse volatility or regression): turns a measurement into an estimate and invites
tuning. *Regime-adjusted gold via real rates*: see above; the level fit broke after 2022. *Drift
removal* (detrending wages, M2): also a fit, and the drift is information (things really get
cheaper in hours of work). *User-chosen yardstick sets*: invites cherry-picking until the band says
what one hoped; the set is a fixed, declarative table with each bias written next to it. *A 3-D
surface* (time × yardstick × change): harder to read than a band and adds nothing that the table of
yardsticks does not. *Equities and nominal GDP as yardsticks*: wanted (ownership of productive
capital, share of the economy), but FRED serves the S&P 500 only for a rolling year and GDP is
quarterly; forward-filling is excluded.

**What the view cannot show.** Causes: "measured in" is not "because of". Total return: dividends,
royalties and carry are missing (the XAU index is price-only), so equities look worse than they
were. Non-US purchasing power: all yardsticks are US quantities. Short episodes: monthly means hide
intramonth crashes, and the band ends at the latest common publication (M2, about six weeks old).
Silver and lumber: no free long monthly series was found, so in the demo they stay synthetic and are
marked as such, as are all share prices. The median is still a choice of five; a sixth yardstick
would move it. The 1 % flat zone and the inner-band trim are conventions, stated in `constants.py`.

**Recommendation for the existing views.** *Raum (3-D)*: remove. Its axes are a dollar price
against a driver, the dollar is inside both, and the eighth round found no information beyond the
Weg. *Zyklusuhr*: remove as a separate view, or – if kept – re-base its radius on the band's median
instead of the dollar price and require at least four completed phases on the real history; its
useful part, the table of earlier stretches in the same phase, can move under the Weg. *Matrix,
Hebelkette, Treiberleiter*: keep, but in the demo they still read the synthetic weekly commodity
prices (160 weeks) against real macro series. They should use the long real monthly series that
now exist (`GOLDWB`, `PCOPPUSDM`, `PURANUSDM`, `DCOILWTICO`, `DHHNGSP`), as `LONG_HISTORY` in
`services/purchasing.py` does; that change belongs in `services/charts.py`.

**Data added.** FRED: `AHETPI` (hourly earnings, BLS), `PCOPPUSDM`, `PURANUSDM` (IMF primary
commodity prices), `NASDAQXAU` (© Nasdaq, from 2004). World Bank monthly gold (`GOLDWB`) via the
public-domain package `datasets/gold-prices` (ODC-PDDL-1.0; World Bank data CC BY 4.0), because
FRED dropped the London gold price in 2022 and the BLS import price index for gold (`IR14270`)
tracks it badly (correlation of monthly changes 0.40). The snapshot script now keeps bundled rows
that a source stopped serving (FRED cut the S&P 500 to a rolling year on the day of this snapshot).
