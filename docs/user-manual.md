# WatchStreet – Benutzerhandbuch

WatchStreet ist ein kartenzentrierter Recherche-Arbeitsplatz für Rohstoffinvestments. Die Mine bzw. das
Projekt ist die Analyseeinheit; jede Zahl zeigt, woher sie stammt. WatchStreet gibt **keine
Anlageempfehlungen** und handelt nicht.

Im Demo-Modus (`make demo`) sind alle Objekte, Werte und Ereignisse **synthetisch** und entsprechend
markiert.

[TOC]

## 1. Aufbau

![Explorer](screenshots/01_explorer.png)

| Bereich | Zweck |
|---|---|
| Kopfzeile | Rohstoffleiste mit Preis, Navigation, Suche, Glocke für Ergebnisse |
| Karte | Minen und Projekte; Form = Status, Farbe = gewählter Farbmodus |
| Rechtes Panel | Übersicht oder Charakterkarte des gewählten Objekts |
| Auswahlleiste | mehrfach ausgewählte Objekte für den Vergleich |
| Zeitleiste | Preisverlauf, Stichtag, Replay, Szenariopreis |

Der gesamte Ansichtszustand steht in der Adresse; eine Ansicht lässt sich als Link weitergeben.

**Tastatur:** `Esc` schliesst das Panel, `c` öffnet den Vergleich, `Umschalt+Klick` auf einen Marker
fügt ihn der Auswahl hinzu.

## 2. Rohstoff wählen und Karte lesen

Ein Klick auf einen Rohstoff in der Kopfzeile filtert die Karte. Ein zweiter Klick hebt den Filter auf.

* **Form** zeigt den Status: ● Produktion, ◆ Entwicklung, ▲ Exploration, ■ stillgelegt/ruhend.
* **Farbe** zeigt den Farbmodus (Auswahl links oben): Rohstoff (neutral), Marge, Änderung im Szenario,
  Wissensstatus, Datenqualität.
* **Schraffiert-grau** bedeutet: für diesen Modus fehlen Daten. „Unbekannt“ wird nie wie ein mittlerer
  Wert eingefärbt.
* **Punkt am Marker:** blau = Recherche läuft, grün = neues Ergebnis, gelb = offene Frage.
* Die Kästchen links blenden Statusgruppen und Ereignisse (rote Ringe, z. B. Erdbeben) ein und aus.

## 3. Von der These zur Mine

Ein Klick auf eine These (rechts in der Übersicht oder im Bereich Research → „Auf der Karte zeigen“)
richtet die Karte auf die verknüpften Objekte aus.

![These auf der Karte](screenshots/02_these_auf_karte.png)

## 4. Charakterkarte

Ein Klick auf einen Marker oder einen Namen öffnet die Charakterkarte.

![Charakterkarte](screenshots/03_charakterkarte.png)

Jede Kennzahl trägt ein Herkunftszeichen:

| Zeichen | Bedeutung |
|---|---|
| **B** | berichtet – aus einem gespeicherten Dokument mit wörtlichem Zitat |
| **≈** | berechnet – aus anderen Kennzahlen, Formel wird genannt |
| **~** | geschätzt – immer als Bandbreite, mit benannter Methode |
| **?** | unbekannt – es wird nichts erfunden |

Kursive Werte sind Prognosen (z. B. Studienwerte eines Projekts). Produzierende Minen zeigen
Produktion, Kosten, Reserven; Projekte zeigen Studienwerte.

**Wirtschaftlichkeit** (Marge, Cashflow, Restlaufzeit, einfacher NAV) wird nur gerechnet, wenn Preis
und Stückkosten bekannt sind. Ist eine Eingabe geschätzt, ist auch das Ergebnis geschätzt und eine
Bandbreite.

### Herleitung einer Zahl

Ein Klick auf eine Kennzahl zeigt Wert, Definition, Zeitraum, Quelle, Zitat und frühere Werte.

![Herleitung](screenshots/04_herleitung.png)

### Unternehmensansicht

Ein Klick auf den Betreiber öffnet die Unternehmensansicht. Die Objekte des Unternehmens bleiben auf
der Karte hervorgehoben, alle anderen abgedunkelt sichtbar; der Kartenausschnitt bleibt erhalten.

![Unternehmen](screenshots/05_unternehmen_hervorgehoben.png)

Die Ansicht beantwortet, ob das Unternehmen lange genug durchhält, um von seinen Objekten zu
profitieren:

| Abschnitt | Inhalt |
|---|---|
| Bilanz und Kapitalstruktur | Kasse, Finanzschulden, Mittelabfluss je Quartal, ausstehende und voll verwässerte Aktien, Insiderbesitz – jeweils mit Herkunftszeichen und Herleitung |
| Abgeleitet | Nettokasse, Reichweite in Monaten, Verwässerungsüberhang, Börsenwert, Summe der einfachen Asset-NAV (anteilig), Verhältnis Börsenwert zu Asset-NAV |
| Prüfkatalog | zehn Kernfragen mit Status „belegt“ oder offen; offene Punkte lassen sich als Recherche vormerken |
| Menschen | Führungspersonen mit Rolle und Erfolgsbilanz |
| Finanzierungen | Datum, Betrag, Preis je Aktie |
| Royalties und Streams | Belastungen auf den Objekten; sie mindern die Marge des Objekts |
| Preishebel | anteiliger Cashflow der produzierenden Objekte bei −50 % bis +50 % Rohstoffpreis |
| Eigene Angabe | eigene Werte eintragen; sie werden von Agenten nie überschrieben |

![Junior mit kurzer Reichweite](screenshots/20_junior_unternehmen.png)

Reicht die Kasse weniger als zwölf Monate, legt die Regelprüfung eine Auffälligkeit und einen
Recherchevorschlag zur Finanzierung an. „Belegt“ im Prüfkatalog heisst, dass etwas vorliegt, nicht,
dass die Antwort gut ist. Asset-NAV und das Verhältnis dazu sind einfache Modellrechnungen, keine
Bewertung.

Ist eine These aktiv, lässt sich im Herleitungsdialog jede Kennzahl der These als stützende oder
widersprechende Evidenz zuordnen.

## 5. Auswahl und Vergleich

„+ Zur Auswahl“ oder `Umschalt+Klick` legt ein Objekt in die Auswahlleiste (höchstens 8). Ausgewählte
Objekte tragen auf der Karte ihre Nummer.

![Auswahl und vorgemerkte Frage](screenshots/06_projekt_und_frage.png)

„Vergleichen“ stellt die Karten nebeneinander und zeigt die Lebensläufe ab einem gemeinsamen Anker
(„Jahr 0 = Entdeckung“ usw.). Beruhen Kosten auf unterschiedlichen Definitionen, erscheint ein Hinweis.

![Vergleich](screenshots/07_vergleich.png)

## 6. Fragen vormerken und Recherchen starten

Recherche läuft in zwei bewussten Schritten:

1. **Vormerken:** in der Charakterkarte unter „Frage vormerken“ (Vorlage wählen, optional eigene
   Formulierung) oder bei einer unbekannten Kennzahl über „Recherche vorschlagen“. Auch die
   Analyse-Engine legt Vorschläge an (fehlende Kennzahlen, Kostenausreisser, Nachbarschaft zu Minen
   anderer Betreiber).
2. **Starten:** im Bereich **Research → Backlog** oder direkt in der Charakterkarte. Erst jetzt läuft
   etwas.

![Backlog](screenshots/08_backlog.png)

Im Backlog lässt sich der Auftragstext ändern, der Nutzenwert einsehen (Maus auf ⓘ), mehrere
Vorschläge gesammelt starten oder ein Vorschlag verwerfen. Der Nutzenwert sortiert nur.

Während eine Recherche läuft, kann weiter erkundet werden. Fertige Ergebnisse meldet die Glocke; von
dort führt ein Klick zum Objekt.

### Beispiel: fehlende Kosten

![Kosten unbekannt](screenshots/09_kosten_unbekannt.png)

Nach dem Start durchsucht WatchStreet zuerst die gespeicherten Dokumente des Objekts. Wird die Zahl
gefunden, erscheint sie als berichteter Wert mit Zitat; daraus wird die Wirtschaftlichkeit berechnet.

![Ergebnis am Objekt](screenshots/10_ergebnis_am_objekt.png)
![Ergebnis mit Zitat](screenshots/11_ergebnis_mit_zitat.png)

Mögliche Ergebnisse einer Recherche: berichteter Wert mit Zitat, geschätzte Bandbreite mit Methode,
oder ausdrücklich „nicht gefunden“.

### Vorlagen

| Vorlage | Was geschieht |
|---|---|
| Fehlende Kennzahl beschaffen | Suche in gespeicherten Dokumenten, danach (falls konfiguriert) Agent |
| Kosten schätzen | Bandbreite aus belegten Kosten vergleichbarer produzierender Minen (mindestens 3) |
| Übernahmeziel? / Strategische Bedeutung / Kostenstruktur erklären / Freie Frage | Agent bewertet anhand der bekannten Daten und Dokumente. Ohne Agent entsteht nur eine Zusammenstellung, ausdrücklich ohne Bewertung |
| Dokument lesen | siehe Abschnitt 9 |

## 7. Szenario und Stichtag

**Szenario:** Mit dem Regler „Szenariopreis“ in der Zeitleiste ändert sich der angenommene Preis des
gewählten Rohstoffs. Karte und Charakterkarten rechnen neu; ein Banner zeigt den Szenariomodus.
Das Banner nennt, wie viele produzierende Minen bei diesem Preis eine negative Marge haben, welchen
Anteil der Produktion das betrifft und für wie viele Minen Kostendaten fehlen. Die Übersicht rechts
listet die Objekte nach Stückkosten sortiert (niedrigste zuerst) mit ihrer Marge in dieser Ansicht.

![Szenario](screenshots/12_szenario.png)

**Stichtag:** Ein Datum im Feld „Stichtag“ oder ein Klick in den Preisverlauf zeigt den damaligen
Stand. Die Auswahl daneben trennt zwei Sichten:

* **wie damals bekannt** – nur, was bis dahin veröffentlicht war. Kennzahlen ohne
  Veröffentlichungsdatum erscheinen hier nicht.
* **rückblickend bekannt** – alles über den Zeitraum, auch später Veröffentlichtes.

![Stichtag](screenshots/13_stichtag.png)

**Replay:** Ist ein Objekt geöffnet, springen ◀ ▶ von Meilenstein zu Meilenstein seines Lebenslaufs;
„ansehen“ im Lebenslauf setzt den Stichtag direkt.

## 8. Wissensstatus

Der Farbmodus „Wissensstatus“ zeigt je Objekt: noch nicht geprüft, bekannt, vertieft untersucht, neue
Entwicklung, veraltet. Der Status wird abgeleitet und nicht von Hand gepflegt. „Noch nicht geprüft“
heisst, dass nichts vorliegt, nicht, dass nichts existiert.

![Wissensstatus](screenshots/14_wissensstatus.png)

## 9. Research-Bereich

**Thesen:** Aussage, Zeithorizont, Annahmen mit Status (offen, gestützt, widerlegt, unklar) und
zugeordnete Evidenz. Ergebnisse von Fragen, die bei aktiver These vorgemerkt wurden, werden der These
zugeordnet und lassen sich als stützend, widersprechend oder Kontext einordnen.

**Recherchen:** Liste aller gestarteten Recherchen. Ein Klick öffnet das Ergebnis mit festen
Abschnitten: Antwort, Unsicherheiten, geprüfte Alternativen, nicht gefunden, abgelehnte Angaben des
Agenten, Folgefragen.

![Rechercheergebnis](screenshots/15_rechercheergebnis.png)

**Seit deinem letzten Besuch:** alle Änderungen (neue Kennzahlen mit altem und neuem Wert,
abgeschlossene Recherchen, Auffälligkeiten, Ereignisse). „Als gelesen markieren“ setzt den
Besuchszeitpunkt; mit „ab“ lässt sich ein anderes Vergleichsdatum wählen.

![Lagebericht](screenshots/16_lagebericht.png)

## 10. Portfolio

Bestände (Symbol, Stück, Durchschnittspreis, optional Kaufdatum und Absicht) und Watchlist.

![Portfolio](screenshots/17_portfolio.png)

## 11. Quellen

Alle gespeicherten Dokumente. Ein Bericht lässt sich in der Charakterkarte unter „Quellen“ per Adresse
hinzufügen („Dokument lesen“): WatchStreet ruft ihn geschützt ab, speichert den Text und sucht
Kennzahlen darin.

![Quellen](screenshots/18_quellen.png)

## 12. System

Datenmodus, Marktdatenquelle, konfigurierter Agent, Zustand des Workers. „Hintergrundlauf jetzt“
aktualisiert Preise und Ereignisse und führt die Regelprüfung aus; er startet nie einen Agenten.

![System](screenshots/19_system.png)

## 13. Betrieb

| Zweck | Befehl |
|---|---|
| Demo ohne Netz und Schlüssel | `make demo` → http://localhost:8000 |
| Mit Docker und PostgreSQL | `docker compose up --build` |
| Lokales Modell (llama.cpp) | `docker compose --profile llm-cpu up --build` bzw. `llm-gpu`, dazu `WATCHSTREET_AGENT_RUNNER=llama` |

Einstellungen stehen in `.env.example`. Ohne konfigurierten Agenten (`offline`) arbeitet WatchStreet
nur mit deterministischen Schritten.

**Sicherung:** bei PostgreSQL `docker compose exec db pg_dump -U watchstreet watchstreet > backup.sql`;
vor einem Update immer sichern, denn Migrationen sind nicht in jedem Fall umkehrbar.

## 14. Grenzen des aktuellen Stands

* Marge, Cashflow und NAV sind einfache Modellrechnungen (Preis minus Stückkosten, 8 % Diskontsatz,
  konstante Produktion) ohne Steuern, Royalties, Investitionen und Schulden – keine Bewertung.

* Echtdaten für Minen entstehen nur durch eigene Einträge und Recherchen; es gibt keinen mitgelieferten
  realen Bestand.
* Noch nicht vorhanden: Marker-Clustering, Standortbilder, Anmeldung, Inflations- und
  Rohstoffäquivalent-Spalten im Vergleich.
* Die Zitatprüfung stellt sicher, dass ein Zitat wörtlich im Dokument steht, nicht, dass es die Zahl
  inhaltlich richtig belegt.
