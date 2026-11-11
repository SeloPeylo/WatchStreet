# Betrieb als Webanwendung

WatchStreet ist eine Webanwendung für **einen** Nutzer. Sie braucht einen Rechner, auf dem Docker
läuft; gehostet wird sie nicht von uns, sondern auf einem eigenen Server.

## Empfohlene Aufstellung

| Baustein | Empfehlung | Warum |
|---|---|---|
| Server | kleiner Linux-Server (2 CPU, 4 GB RAM, 40 GB Platte) bei einem beliebigen Anbieter | App, Worker und PostgreSQL brauchen wenig |
| Zugang | eigene (Sub-)Domain, HTTPS über Caddy, Passwort-Anmeldung | im Lieferumfang (`docker-compose.public.yml`) |
| Agent | API-Schlüssel (`WATCHSTREET_AGENT_RUNNER=anthropic`) | ein gemieteter Server hat keine GPU; lange technische Berichte überfordern kleine lokale Modelle |
| Daten | `./data` regelmässig sichern | enthält PostgreSQL und Zertifikate |

Ohne Agent (`offline`) funktioniert alles Deterministische: Karte, Register-Import, Kennzahlen aus
gespeicherten Dokumenten, Szenarien, Regelprüfung. Fragen, die Urteil brauchen, bleiben dann offen.

## Alternativen für das Sprachmodell

Der Agent lässt sich im Betrieb unter **System → Agent** einstellen (Anbieter, Modell, Adresse,
Schlüssel) und dort testen; ein Neustart ist nicht nötig. Die Umgebungsvariablen unten gelten, solange
dort nichts eingestellt ist. Der Schlüssel liegt dann in der Datenbank des Servers.

| Variante | Einrichtung | Einschätzung |
|---|---|---|
| API-Schlüssel | `ANTHROPIC_API_KEY`, Runner `anthropic` – oder Runner `openai` mit beliebigem OpenAI-kompatiblen Dienst | einfachster und stärkster Weg; Kosten nur bei gestarteten Recherchen |
| Eigene GPU (8 GB) auf dem Desktop | alles lokal: `docker compose --profile llm-gpu up`, Runner `llama` | läuft ohne laufende Kosten; 8 GB reichen für kleine Modelle (etwa 7–8 Mrd. Parameter, 4-Bit), deren Qualität bei langen Berichten begrenzt ist |
| Server ohne GPU, Modell zu Hause | Runner `openai` mit `WATCHSTREET_OPENAI_BASE_URL` auf einen von aussen erreichbaren llama.cpp-Server | möglich, aber der Heimrechner muss erreichbar und abgesichert sein – nicht empfohlen |
| Colab o. Ä. | – | ungeeignet: Sitzungen enden, keine stabile Adresse |

## Einrichtung auf dem Server

```
git clone https://github.com/SeloPeylo/WatchStreet.git && cd WatchStreet
cp .env.example .env        # dann ausfüllen, siehe unten
docker compose -f docker-compose.yml -f docker-compose.public.yml up -d --build
```

Pflichtwerte in `.env`:

| Variable | Inhalt |
|---|---|
| `WATCHSTREET_DOMAIN` | z. B. `watchstreet.example.org`; der DNS-Eintrag muss auf den Server zeigen |
| `WATCHSTREET_PASSWORD` | Anmeldepasswort |
| `WATCHSTREET_SECRET_KEY` | langer Zufallswert (`openssl rand -hex 32`) |
| `WATCHSTREET_API_TOKEN` | optional: Zugang für Skripte und Research-Agenten ([Import-API](import-api.md)) |
| `POSTGRES_PASSWORD` | eigenes Datenbankpasswort |
| `WATCHSTREET_SEC_USER_AGENT` | Name und Kontakt für Abrufe bei der SEC |

Ports 80 und 443 müssen offen sein; Caddy holt das Zertifikat selbst.

## Aktualisieren und Sichern

```
docker compose exec db pg_dump -U watchstreet watchstreet > backup-$(date +%F).sql   # vorher sichern
git pull
docker compose -f docker-compose.yml -f docker-compose.public.yml up -d --build      # migriert beim Start
```

Migrationen laufen beim Start automatisch; sie sind nicht in jedem Fall umkehrbar, daher vorher sichern.

## Sicherheit

* Ohne `WATCHSTREET_PASSWORD` ist die Anwendung offen; die Standard-Aufstellung bindet sie deshalb nur
  an `127.0.0.1`. Die öffentliche Aufstellung verweigert den Start ohne Passwort.
* Nach fünf falschen Passwörtern sind Anmeldungen fünf Minuten gesperrt.
* Schreibende Anfragen fremder Herkunft werden abgelehnt; Skripte laden nur von der eigenen Adresse.
* Externe Inhalte werden nur über den abgesicherten Abruf geladen (keine internen Adressen, Grössen-
  und Typgrenzen).

## Stand der Prüfung

Der Docker-Build und die Tests auf PostgreSQL laufen in der CI. Die öffentliche Aufstellung mit Caddy
und ein Lauf mit echtem Sprachmodell sind **nicht** geprüft.
