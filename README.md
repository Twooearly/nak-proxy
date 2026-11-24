# NAK Stundenplan-Abo

Dein Nordakademie-Stundenplan als Kalender-Abo, nur mit den Modulen, die du wirklich belegst.

**→ [cal.kopflosertruthahn.de](https://cal.kopflosertruthahn.de)**

1. Studiengang, Studienbeginn und Zenturie wählen.
2. Module abwählen, die du nicht belegst, und bei Laboren deine Gruppe auswählen.
3. Abo-Link kopieren und in Google Kalender, Apple Kalender, Outlook oder Thunderbird als Abo (Internetkalender) hinzufügen.

Der Kalender aktualisiert sich danach von selbst. Raumänderungen und Absagen der NAK kommen innerhalb von etwa 30 Minuten an, wie schnell dein Kalender-Programm sie abholt, hängt von ihm ab (Google braucht teils mehrere Stunden).

Vergangene Termine bleiben im Abo erhalten, auch wenn die NAK die alte Semesterdatei längst entfernt hat.

> Inoffizielles Projekt, nicht von der Nordakademie. Die Daten stammen aus den öffentlichen Stundenplan-Dateien der NAK und können Fehler enthalten. Im Zweifel gilt der offizielle Stundenplan.

## Wie es funktioniert

- **Poller** (Hintergrund-Thread): sucht täglich per HEAD-Request nach existierenden Zenturien (`{Buchstabe}{JJ}{a,b,…}`) und holt alle 30 Minuten jede bekannte Zenturie (Semesterdatei davor, aktuell und danach, mit `If-Modified-Since`).
- **Archiv** (SQLite): Jeder Termin wird pro Zenturie gespeichert. Vergangene Termine bleiben erhalten, auch wenn die NAK sie oder die ganze Semesterdatei entfernt. Fehlt ein zukünftiger Termin innerhalb des Zeitfensters der Datei, gilt er als abgesagt und wird gelöscht. Eine leere Datei löscht nie etwas.
- **Feeds** lesen nur aus SQLite und lösen nie einen Request an die NAK aus. Sie werden pro Filter gecacht und mit ETag und `Cache-Control` ausgeliefert.
- **Frontend** (SvelteKit + shadcn-svelte, `frontend/`): baut nur die Abo-URL zusammen. Der ganze Filter steckt in der URL, es gibt keine Accounts und keine gespeicherten Einstellungen.

## Endpoints

| Route | Beschreibung |
|---|---|
| `GET /` | Auswahlseite |
| `GET /z/<Zenturie>.ics` | Abo-Feed, z. B. `/z/A25a.ics` |
| `  ?ohne=A205,spanisch-b1` | diese Module ausblenden (Kurscode bzw. Slug) |
| `  ?gruppe=W213.2` | bei Modul W213 nur Laborgruppe 2 |
| `GET /api/zenturien` | bekannte Zenturien mit Studiengang und Jahrgang |
| `GET /api/zenturien/<Zenturie>/module` | Module mit Terminanzahl und Laborgruppen |
| `GET /healthz` | Healthcheck |

## Selbst betreiben

```bash
docker compose up --build   # http://localhost:8000
```

Das Archiv liegt unter `/data/archive.db` im Volume. Der Container startet kurz als root, übergibt `/data` an den User `app` (UID 1000) und läuft dann ohne Root-Rechte. Ist in Compose `user:` gesetzt, läuft er direkt als dieser User und ändert keine Besitzrechte; `/data` muss dann für ihn beschreibbar sein.

Gunicorn läuft mit einem Worker und 8 Threads, damit es genau einen Poller gibt. Bitte nicht hochskalieren, sonst fragen mehrere Poller parallel bei der NAK an.

### Umgebungsvariablen

| Variable | Default | |
|---|---|---|
| `ARCHIVE_PATH` | `archive.db` (Docker: `/data/archive.db`) | SQLite-Datei |
| `POLL_MINUTEN` | `30` | Abrufintervall |
| `DISCOVERY_STUNDEN` | `24` | Intervall der Zenturien-Suche |
| `DISCOVERY_JAHRGAENGE` | `5` | so viele Jahrgänge rückwärts suchen |
| `ZUSATZ_ZENTURIEN` | – | zusätzliche Codes, z. B. `A26a,W26b` |
| `UPSTREAM_PAUSE` | `0.5` | Sekunden zwischen zwei Requests an die NAK |
| `UPSTREAM_USER_AGENT` | `nak-stundenplan-proxy` | User-Agent für Requests an die NAK |
| `POLLER` | `1` | `0` schaltet den Poller ab (z. B. für Tests) |
| `STATIC_DIR` | `frontend/build` | statischer Frontend-Build |

### Alte Kalender importieren

Termine aus früheren Semestern, die die NAK nicht mehr anbietet, lassen sich aus alten `.ics`-Dateien nachtragen:

```bash
uv run import_ics.py --zenturie A25a --dry-run ~/Downloads/stundenplan.ics
docker compose run --rm -v "$PWD/alt:/in:ro" nak-proxy python import_ics.py --zenturie A25a /in
```

Übernommen werden nur NAK-Termine (mit `Veranstaltung:`-Zeile), weil die Feeds öffentlich sind.

## Entwickeln

```bash
uv sync && uv run main.py                 # Backend auf :5000 (FLASK_ENV=dev für Debug, POLLER=0 ohne Poller)
cd frontend && npm install && npm run dev # Frontend auf :5173, /api und /z gehen an :5000
```

Ohne `npm run dev` liefert Flask den letzten `npm run build` aus `frontend/build` aus.

```bash
uv run pytest                             # Backend-Tests, offline, eigene Temp-DB pro Test
cd frontend && npm run check              # Typprüfung Frontend
```

GitHub Actions führt beide bei jedem Pull Request und bei Pushes auf `main` aus. Das Docker-Image wird nur gebaut, wenn beide grün sind.

Fehler und Ideen gern als Issue oder Pull Request.
