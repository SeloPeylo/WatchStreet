# Zielbild: öffentliche Plattform (Stand 16. November 2026)

Dieses Dokument beschreibt, wohin WatchStreet sich entwickeln soll, was das für das Systemdesign
bedeutet und ob es sich rechnet. Was heute gebaut ist, steht in [`../architecture.md`](../architecture.md);
das fachliche Zielmodell in [`world-explorer-spec.md`](world-explorer-spec.md); die Anforderungen
aus den Review-Runden in [`requirements-review-2026-11.md`](requirements-review-2026-11.md).

## 1. Ziel

Eine öffentliche Website für Anleger in Sachwerten (Metalle, Uran, Öl und Gas, Holz), in drei Ebenen:

| Ebene | Inhalt | Zugang | bezahlt durch |
|---|---|---|---|
| **Information** | Karte, Objekte, Unternehmen, Konzessionen, Makro, Charts – jede Zahl mit Herkunft | ohne Anmeldung | wenig Werbung, nur zur Deckung der Infrastruktur |
| **Eigene Arbeit** | Depot, Thesen, Annahmen, Entscheidungsprotokoll, eigene Linsen und Prinzipien | Anmeldung über Google (später weitere) | kostenlos, mit Mengengrenzen |
| **Recherche und Entscheidung** | Rechercheaufträge mit Agenten, tiefere Läufe, Prüfung der eigenen Prinzipien vor einem Kauf | Abonnement | Abonnement |

Grundsätze, die in allen Ebenen gleich gelten: keine Anlageempfehlung, kein Signal, kein Handel;
„keine Quelle, kein Fakt“; nichts startet einen Agenten ausser dem Nutzer.

## 2. Was sich nicht kopieren lässt

Karte, Charts und Agenten kann jeder mit KI in Wochen nachbauen. Schutz entsteht nur dort, wo
sich mit der Zeit etwas ansammelt, das ein Nachbau nicht hat:

1. **Der geprüfte Faktenbestand mit Geschichte.** Jede Zahl mit Dokument, wörtlichem Zitat,
   Veröffentlichungsdatum und allen früheren Ständen. Ein Nachbau startet bei null und kann die
   Vergangenheit („was war am Stichtag bekannt“) nicht nachträglich erzeugen.
2. **Das eigene System of Record der Nutzer.** Entscheidungsprotokoll, Thesen mit Annahmen,
   Prinzipien und deren Trefferquote. Wer drei Jahre Protokoll hat, zieht nicht um.
3. **Korrekturen aus der Nutzerschaft.** Fehlermeldungen an einer Zahl, die geprüft in den Bestand
   eingehen, mit Gewicht nach nachweislich richtigen früheren Beiträgen.
4. **Lizenzen.** Verträge für die öffentliche Anzeige von Kursen sind eine Hürde für jeden Nachahmer.
5. **Unabhängigkeit.** Kein Geld von Emittenten, Brokern oder Börsenbriefen – nachprüfbar.

Kein Schutz: das Design, die Modelle, die Kartenebenen, die Formeln.

## 3. Wirtschaftlichkeit

Zahlen aus einer Web-Recherche vom 15.11.2026; viele Anbieterseiten waren nicht direkt lesbar,
die Werte stammen dann aus Drittquellen und sind als Grössenordnung zu lesen.

| Posten | Grössenordnung | Bemerkung |
|---|---|---|
| Server (App, PostgreSQL) | 20–40 USD/Monat bis etwa 10.000 Nutzer im Monat | ein virtueller Server genügt lange |
| Kartenkacheln | wenige USD/Monat selbst gehostet (Protomaps), sonst 20–30 USD/Monat | die Kacheln von openstreetmap.org sind keine Grundlage für einen Dienst |
| **Kursdaten mit Anzeigerecht** | **ab etwa 150 USD/Monat, je nach Anbieter bis 2.500 USD/Monat** | grösster Posten |
| Anmeldung | 0 USD (eigene OIDC-Anbindung) | verwaltete Dienste sind bis 25.000–50.000 Nutzer frei |
| Agentenlauf (200.000 Token gelesen, 5.000 geschrieben) | etwa 0,45 USD mittleres Modell, 1,80 USD Spitzenmodell | Stapelverarbeitung halbiert das |
| Werbeerlös | etwa 48 USD je 1.000 Nutzer im Monat | Annahme: 10 Seiten je Nutzer, 8 USD je 1.000 Seiten, 40 % Werbeblocker |

| Nutzer im Monat | Kosten/Monat | Werbeerlös | Abonnenten zur Deckung (15 USD, 20 Läufe inklusive) |
|---|---|---|---|
| 1.000 | ~190 USD | ~48 USD | 32 |
| 10.000 | ~230 USD | ~480 USD | 39 |
| 100.000 | ~450 USD | ~4.800 USD | 75 |

Ergebnis: Werbung deckt die Infrastruktur ab etwa 5.000 Nutzern im Monat – aber nur, wenn die
Kursdaten rund 150 USD kosten. Verlangt der Anbieter eine Unternehmenslizenz, liegt die Schwelle
bei etwa 50.000 Nutzern. Nicht die Technik entscheidet über die Wirtschaftlichkeit, sondern die
Datenlizenz. Das Abonnement trägt sich selbst, solange die Zahl der Läufe begrenzt ist.

### Voraussetzungen vor einer Veröffentlichung (hart)

| Quelle heute | Problem | Weg |
|---|---|---|
| Yahoo Finance (Kurse) | nur private Nutzung | Anbieter mit Anzeigerecht; bis dahin Kurse nur für angemeldete Einzelnutzer im Eigenbetrieb |
| FRED | Reihen mit fremdem Urheberrecht (z. B. S&P 500) dürfen nicht weitergegeben werden; die Bedingungen verbieten das Zwischenspeichern für Dritte | je Reihe prüfen; amtliche Reihen direkt bei der Behörde holen (Fed, BLS, Treasury, EIA, Census) |
| OpenTopoMap (Geländekacheln) | kein Anspruch, Sperre ohne Ankündigung; die Strassenkarte kommt seit dem 17.11. von OpenFreeMap (frei, auch gewerblich) | Kacheln selbst hosten oder kaufen |
| Register Ontario | keine offene Lizenz gefunden | bis zur Klärung nicht öffentlich zeigen |
| Register Westaustralien, British Columbia, BLM; USGS | offen bzw. gemeinfrei | Quellenangabe |

Dafür braucht es ein **Lizenzregister**: je Datenquelle Lizenz, Beleg, Datum und ein Schalter
„öffentlich zeigbar“. Im öffentlichen Betrieb werden Quellen ohne diesen Schalter nicht ausgeliefert.

### Werbung

* Höchstens eine Fläche je Seite, klar als Anzeige beschriftet, nie in Karte, Chart, Tabelle oder
  Rechercheergebnis; keine Fläche für zahlende Nutzer.
* Nur nach dem Inhalt der Seite ausgespielt. Die Werbeanfrage enthält weder Depot noch
  Beobachtungsliste noch Thesen.
* Ausgeschlossen: Emittenten, Broker, Börsenbriefe, Hebelprodukte, Krypto. Bezahlte Darstellung
  eines Emittenten wäre zudem eine Anlageempfehlung mit Offenlegungs- und Anzeigepflichten
  (Art. 20 Marktmissbrauchsverordnung, § 86 WpHG).
* Werbe-Cookies brauchen eine Einwilligung (§ 25 TDDDG). Werbung ohne Verfolgung des Nutzers
  vermeidet das Einwilligungsfenster und passt zum Grundsatz „Daten des Nutzers gehen nicht hinaus“.
* Kein Erlös, der vom Handeln abhängt (Vermittlungsprovisionen von Brokern, Orderfluss).

## 4. Systemdesign für den öffentlichen Betrieb

Heute ist die Anwendung für eine Person gebaut: ein Passwort, ein Depot, ein Protokoll, ein
gespeicherter Agentenschlüssel. Öffentlich braucht sie:

| Baustein | Entwurf |
|---|---|
| **Mandantentrennung** | Tabelle `users`; `user_id` an Depot, Protokoll, Thesen, Annahmen, eigenen Fakten, Importen, Vorschlägen, Aufträgen, Einstellungen. Jede Abfrage dieser Tabellen läuft über einen Zugriff, der den Nutzer erzwingt; ein Test prüft, dass kein Endpunkt fremde Zeilen liefert. |
| **Zwei Wissensschichten** | *Gemeinsam*: Objekte, Unternehmen, Fakten aus Dokumenten und Registern (unveränderlich, öffentlich). *Privat*: eigene Einträge und Schätzungen des Nutzers, die für ihn über der gemeinsamen Schicht liegen. Ein privater Eintrag wird nur über eine geprüfte Korrektur gemeinsam. |
| **Anmeldung** | OpenID Connect gegen Google, eigene Anbindung; gespeichert werden nur die Kennung des Anbieters, Anzeigename und E-Mail. Kein eigenes Passwort. Facebook erst bei Bedarf (zusätzliche Prüfung durch Meta). |
| **Stufen und Kontingente** | `plan` am Nutzer; Kontingent an Rechercheläufen je Monat, Zähler je Lauf mit Token und Kosten; harte Obergrenze je Lauf. Der Betreiber stellt den Agentenzugang, nicht mehr der Nutzer. |
| **Zahlung** | Zahlungsdienst mit gehosteter Bezahlseite; die Anwendung speichert nur den Status des Abonnements. |
| **Öffentliche Lese-API** | Antworten ohne Nutzerbezug zwischenspeicherbar (Karte, Objekt, Unternehmen, Makro); Begrenzung der Anfragen je Adresse. |
| **Rückmeldung** | „Fehler melden“ an jeder Zahl erzeugt einen Korrekturvorschlag mit Quelle; Wünsche als eigenes Formular. Auswertung nur zusammengefasst; private Inhalte werden nicht für andere sichtbar. |
| **Diskussion** | Beiträge hängen an einem Objekt, einem Fakt oder einer Annahme, tragen eine Offenlegung (hält die Aktie / wird vom Emittenten bezahlt / keins von beiden) und haben keine Zustimmungsknöpfe. Gewicht nach nachweislich eingetroffenen eigenen Annahmen – erst wenn es genug aufgelöste Annahmen gibt. |
| **Lizenzregister** | siehe Abschnitt 3. |
| **Betrieb** | nur PostgreSQL; Sicherung; Überwachung der Agentenkosten; Impressum, Datenschutzerklärung, Löschung des Kontos. |

### Entscheidungsebene

Sie entscheidet nie. Sie hält dem Nutzer seine eigenen Regeln vor:

1. Der Nutzer schreibt Prinzipien als prüfbare Regeln („keine Position über 5 %“, „kein Kauf bei
   Reichweite der Kasse unter 12 Monaten“, „Realzins über 2,5 % für 60 Tage → These prüfen“).
2. Vor dem Eintrag eines Kaufs zeigt die Anwendung, welche Regeln verletzt wären, verlangt einen
   Satz „so verliere ich hier Geld“ und zeigt Grundquoten aus geprüften Daten.
3. Nach dem Abschluss wird getrennt bewertet: Überlegung richtig oder falsch, Ergebnis gut oder
   schlecht. Trefferquote je Begründungsart und je Prinzip.

Das ist zugleich der Teil, der am schwersten zu kopieren ist (Abschnitt 2, Punkt 2).

## 5. Charts: der nächste Schritt nach TradingView

Drei Entwürfe aus unterschiedlicher Sicht wurden verglichen. Sie ergänzen sich zu einem Modell
mit einem gemeinsamen Kern: **Jeder Preis ist ein Verhältnis, und der Nenner ist eine Einstellung
der ganzen Anwendung** – wie heute Stichtag und Szenario.

| Baustein | Was man sieht | Frage, die er beantwortet |
|---|---|---|
| **Massstab-Matrix** | Zeilen: was man hält oder beobachtet. Spalten: Dollar, Gold, Verbraucherpreise, M2, Öl, Heimatwährung. Jede Zelle: Verlauf, Änderung über ein Jahr, Lage in der eigenen Zehnjahresspanne. Klick auf eine Spalte setzt den Massstab überall. | Worin ist das billig oder teuer? Ist mein Gewinn echt oder fällt nur der Dollar? |
| **Linse** | Eine Formel als gespeichertes Objekt mit freiem Platz (`$objekt / gold`), Einheit und Frequenz je Glied, anwendbar auf jede Aktie und das Depot. Addition von Dollar und Prozent wird abgelehnt. | Ersetzt die getippte Ticker-Formel; dieselbe Sicht für alles. |
| **Hebelkette** | Die Änderung eines Kurses als Kette von Verhältnissen, deren Beiträge sich exakt zur Gesamtänderung addieren: Währung → Gold → Rohstoff → Unternehmen. Darunter derselbe Verlauf über die Zeit. | Welcher Faktor hat den Kurs bewegt – und wann? |
| **Regimekarte** | Ebene aus zwei Makrogrössen (z. B. Realzins × Dollar), der Weg der Welt durch diese Ebene, die eigenen Käufe und Verkäufe als Punkte darauf. | Wo stand die Welt, als ich gehandelt habe? |
| **Annahme aus dem Chart** | Aus einer Linse wird eine Bedingung (`realzins > 2,5 für 60 Tage`) an einer These; der Chart schattiert die Zeiträume, in denen sie galt. | Verbindet den Chart mit der These statt ihn im Reiter sterben zu lassen. |

Regeln, damit das nicht in die Irre führt:

* Exakte Zerlegungen (Verhältnisse, Logarithmen) und Schätzungen (Regression, Korrelation) sind
  getrennt dargestellt. Exakt heisst „gemessen in“, nie „wegen“.
* Kein Hebel-Finder, der Zeitfenster und Reihen nach der besten Übereinstimmung absucht.
  Korrelation nur auf Änderungen, mit Zahl der Beobachtungen, ohne Farbe als Signal.
* Keine Lückenfüllung ohne Kennzeichnung; Monatsreihen als Stufen, mit Veröffentlichungsverzug.
* Verschiedene Einheiten nie auf einer Achse.

Stand: Kursverläufe, Hebelkette (exakt, ohne Vergleichskorb), Massstab-Matrix, Linsen mit
Einheitenprüfung und Regimekarte sind als erste Fassung gebaut (Bereich „Charts“). Offen: Massstab
als Einstellung der ganzen Anwendung, Depot als Zeile, Annahme aus dem Chart, Veröffentlichungsverzug
je Reihe, Monatsreihen als Stufen.

Ursprüngliche Reihenfolge: (1) Kursverläufe der Aktien speichern, (2) Hebelkette exakt für eine Aktie – sie
verallgemeinert die vorhandene Aufteilung „Dollar = Goldpreis × in Gold“, (3) Massstab-Matrix und
Massstab als Einstellung, (4) Linsen mit Einheiten, (5) Annahme aus dem Chart, (6) Regimekarte.

## 6. Öl und Gas, Holz

Seit diesem Stand sind Rohöl, Erdgas und Holz im Rohstoffkatalog (Preis, Szenario, Makro-Reihen:
Erdgas Henry Hub, Baubeginne, Hypothekenzins, Holz ÷ Gold). Objekte dieser Rohstoffe gibt es noch
nicht. Dafür braucht das Modell eine Erweiterung, die für alle Rohstoffe gilt:

**Eigentümer und Betreiber trennen.** Wer den Boden oder das Recht hält (Grundeigentümer,
Mineral- und Royalty-Halter, Holz-REIT), ist ein anderes Geschäft als wer fördert oder sägt.
Jede Beteiligung trägt deshalb eine Halterart, und die Unternehmensansicht zeigt Bestände je
Aktie über die Zeit (Reserven, Netto-Royalty-Fläche, Waldfläche je Aktie).

| | Objektarten | Kennzahlen | Quellen (zu prüfen) |
|---|---|---|---|
| **Öl und Gas** | Feld, Förderlizenz, Royalty-Fläche | Förderrückgang der laufenden Bohrungen, Kosten je Barrel einschliesslich Erhaltungsinvestitionen, Reservenreichweite (nur gesicherte, produzierende), Absicherung für 24 Monate, Nettoschulden zu operativem Ergebnis, Preisabschlag zum Referenzpreis | EIA, Register der Bundesstaaten und Provinzen, Geschäftsberichte |
| **Holz – Land** | Waldbesitz nach Region | Fläche, Altersklassen, Zuwachs gegen Einschlag, Preis des stehenden Holzes je Region, Landverkäufe zu höherer Nutzung je Acre, Unternehmenswert je Acre, Dividende aus Einschlag oder aus Landverkäufen | Geschäftsberichte der REITs, USDA Forest Service, Provinzstatistik |
| **Holz – Sägewerke** | Werk | Kapazität, Kosten je 1.000 Board Feet, Stillstände, Zölle, Rohholzversorgung | Geschäftsberichte, Branchenmeldungen |

Erdgas wird nie in Barrel umgerechnet; es ist ein regionaler Markt (Henry Hub, AECO, TTF).
Energie ist zugleich Kostenfaktor jeder Mine und jedes Sägewerks: ein Energieszenario soll alle
Margen gemeinsam neu rechnen.

## 7. Reihenfolge

| Schritt | Inhalt | Warum hier |
|---|---|---|
| 1 | Kursverläufe speichern; Hebelkette; Massstab-Matrix | Kern des mehrdimensionalen Modells, ohne neue Abhängigkeit |
| 2 | Eigentümer/Betreiber-Modell, Objektarten für Öl, Gas, Holz, erste Register | fachliche Breite |
| 3 | Prinzipien, Vorab-Prüfung, bewertetes Protokoll | Entscheidungsebene, schwer kopierbar |
| 4 | Mandantentrennung, Anmeldung über Google | Voraussetzung für alles Öffentliche |
| 5 | Lizenzregister, Kursanbieter mit Anzeigerecht, eigene Kacheln | harte Voraussetzung der Veröffentlichung |
| 6 | Kontingente, Zahlung, Betreiber-Agent | Abonnement |
| 7 | Rückmeldung, Korrekturen, Diskussion | braucht Nutzer |
| 8 | Werbung | zuletzt; lohnt erst ab einigen tausend Nutzern |

## 8. Offene Entscheidungen

1. Welcher Kursanbieter (Preis gegen Anzeigerecht)? Davon hängt die Wirtschaftlichkeit ab.
2. Rechtsform, Impressum, Sitz – bestimmt, welche Aufsichtsregeln gelten.
3. Diskussion ja oder nein: zwei der vier Review-Sichten halten sie für wertlos oder schädlich,
   wenn sie nicht an Fakten und Offenlegung gebunden ist.
4. Bleibt der Eigenbetrieb (eine Person, eigener Agentenschlüssel) als zweite Betriebsart erhalten?

## Quellen der Recherche

* Kachelrichtlinie: <https://operations.osmfoundation.org/policies/tiles/>
* FRED: <https://fred.stlouisfed.org/docs/api/terms_of_use.html>, <https://fred.stlouisfed.org/legal/>
* yfinance (Hinweis „personal use only“): <https://raw.githubusercontent.com/ranaroussi/yfinance/main/README.md>
* Register Westaustralien (CC BY 4.0): <https://catalogue.data.wa.gov.au/dataset/mining-tenements-dmirs-003>
* Kursdaten: <https://twelvedata.com/pricing-business>, <https://eodhd.com/commercial-pricing>
* Kacheln: <https://www.maptiler.com/cloud/pricing/>, <https://docs.protomaps.com/pmtiles/cloud-storage>
* Anlageempfehlungen: <https://bafin.de/EN/Aufsicht/BoersenMaerkte/Marktmissbrauch/Anlagestrategie/anlagestrategie_node_en.html>
* Modellpreise: <https://platform.claude.com/docs/en/about-claude/pricing>
* Anmeldung: <https://cloud.google.com/identity-platform/pricing>
