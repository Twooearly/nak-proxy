# NAK Stundenplan-Abo

Öffentliche Seite, auf der Studierende der Nordakademie ihren Studiengang, ihren Jahrgang und ihre Zenturie wählen, einzelne Module ab- oder anwählen und dafür einen Kalender-Abo-Link bekommen. Läuft unter `https://cal.kopflosertruthahn.de`.

## Funktionsweise

- **Poller** (Hintergrund-Thread): sucht täglich per HEAD-Request nach existierenden Zenturien (`{Buchstabe}{JJ}{a,b,…}`) und holt alle 30 Minuten jede bekannte Zenturie (Semester-Datei vorher/aktuell/nachher, mit `If-Modified-Since`).
- **Archiv** (SQLite): Jeder Termin wird pro Zenturie gespeichert. Vergangene Termine bleiben auch dann erhalten, wenn die NAK sie oder die ganze Semesterdatei entfernt. Fehlt ein zukünftiger Termin innerhalb des Zeitfensters der Datei, gilt er als abgesagt und wird gelöscht.
- **Web-Requests** lesen nur aus SQLite und lösen nie einen Request an die NAK aus. Die Feeds werden pro Filter gecacht und mit ETag/`Cache-Control` ausgeliefert.
- **Frontend** (SvelteKit + shadcn-svelte, `frontend/`): baut nur die Abo-URL zusammen und wird statisch vom selben Container ausgeliefert.

## Endpoints

| Route | Beschreibung |
|---|---|
| `GET /` | Auswahlseite |
| `GET /z/<Zenturie>.ics` | Abo-Feed, z. B. `/z/A25a.ics` |
| `  ?ohne=A205,spanisch-b1` | diese Module ausblenden (Kurscode bzw. Slug) |
| `  ?gruppe=W213.2` | bei Modul W213 nur Laborgruppe 2 |
| `GET /api/zenturien` | bekannte Zenturien mit Studiengang und Jahrgang |
| `GET /api/zenturien/<Zenturie>/module` | Module mit Terminanzahl und Laborgruppen |
| `GET /stundenplan.ics` | alter Feed (A25a ohne Spanisch) für bestehende Abos |
| `GET /healthz` | Healthcheck |

## Konfiguration (Umgebungsvariablen)

| Variable | Default | |
|---|---|---|
| `ARCHIVE_PATH` | `archive.db` (Docker: `/data/archive.db`) | SQLite-Datei |
| `POLL_MINUTEN` | `30` | Abrufintervall |
| `DISCOVERY_STUNDEN` | `24` | Intervall der Zenturien-Suche |
| `DISCOVERY_JAHRGAENGE` | `5` | so viele Jahrgänge rückwärts suchen |
| `ZUSATZ_ZENTURIEN` | – | zusätzliche Codes, z. B. `A26a,W26b` |
| `UPSTREAM_PAUSE` | `0.5` | Sekunden zwischen zwei Requests an die NAK |
| `POLLER` | `1` | `0` schaltet den Poller ab (z. B. für Tests) |
| `LEGACY_ZENTURIE` | `A25a` | Zenturie für `/stundenplan.ics` und die Migration der alten DB |
| `STATIC_DIR` | `frontend/build` | statischer Frontend-Build |

## Lokal entwickeln

```bash
uv sync && uv run main.py                 # Backend auf :5000 (FLASK_ENV=dev für Debug)
cd frontend && npm install && npm run dev # Frontend auf :5173, /api und /z gehen an :5000
```

Ohne `npm run dev` liefert Flask den letzten `npm run build` aus `frontend/build` aus.

## Tests

```bash
uv run pytest                                   # Backend, offline, eigene Temp-DB pro Test
cd frontend && npm run check                    # Typprüfung Frontend
```

In GitHub Actions laufen beide bei jedem Pull Request und bei Pushes auf `main`. Das Docker-Image wird nur gebaut und gepusht (nur `main` und Tags), wenn beide grün sind.

## Alte Kalender importieren

```bash
uv run import_ics.py --zenturie A25a --dry-run ~/Downloads/stundenplan.ics
docker compose run --rm -v "$PWD/alt:/in:ro" nak-proxy python import_ics.py --zenturie A25a /in
```

Übernommen werden nur NAK-Termine (mit `Veranstaltung:`-Zeile), weil die Feeds öffentlich sind.

## Docker

```bash
docker compose up --build   # http://localhost:8000
```

Der Container startet kurz als root, übergibt `/data` an den User `app` (UID 1000) und läuft dann ohne Root-Rechte. Ist in Compose `user:` gesetzt, läuft er direkt als dieser User und ändert keine Besitzrechte; `/data` muss dann für ihn beschreibbar sein. Eine alte Archiv-DB (Tabelle `events(uid, dtstart, ical)`) wird beim ersten Start automatisch der Zenturie `LEGACY_ZENTURIE` zugeordnet. Die alte Tabelle bleibt als `events_legacy_migriert` erhalten.
