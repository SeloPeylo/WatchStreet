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
