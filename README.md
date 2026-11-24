# NAK Proxy

Ein Flask-Proxy fuer den Nordakademie-Stundenplan.

## Features

- Ermittelt automatisch die Stundenplan-Datei des aktuellen Semesters (`{Zenturie}_{Semester}.ics`, Fallback auf Nachbarsemester).
- Archiviert Termine in SQLite: vergangene Termine, die die NAK loescht, bleiben im Feed; zukuenftig geloeschte (abgesagte) verschwinden.
- Filtert unerwuenschte Termine (z.B. bestimmte Sprachkurse, andere Gruppen).
- Kuerzt Titel auf das fachliche Kurzformat.
- Gibt eine saubere iCalendar-Antwort zurueck.

## Endpoint

- `GET /stundenplan.ics` -> bereinigter iCalendar Feed
- `GET /healthz` -> Healthcheck

## Konfiguration

- `PORT` (Default: `5000` in dev, `8000` im Docker-Setup)
- `FLASK_ENV=dev` aktiviert Debug-Modus beim lokalen Start
- `ZENTURIE` (Default `A25a`), `START_JAHR` (Default aus Zenturie, `2025`)
- `ARCHIVE_PATH` (Default `archive.db`, im Docker-Setup `/data/archive.db` auf Volume `calendar-proxy_calendar-data`)

Die Upstream-URL wird in [main.py](main.py) aus `ZENTURIE` und dem aktuellen Datum berechnet (Semester = `2*(Jahr-Startjahr) + (1 ab Juli)`).

## Lokales Setup

```bash
uv sync
uv run main.py
```

Dann ist der Feed unter `http://localhost:5000/stundenplan.ics` verfuegbar.

## Alte Kalender importieren

```bash
python import_ics.py --dry-run ~/Downloads/stundenplan.ics
docker compose run --rm -v "$PWD/alt:/in:ro" nak-proxy python import_ics.py /in
```

## Docker

```bash
docker compose up --build
```

Der Feed ist dann unter `http://localhost:8000/stundenplan.ics` erreichbar.

## Hinweise

- Der Proxy konvertiert die Upstream-ICS-Datei (windows-1252) sauber nach UTF-8.
