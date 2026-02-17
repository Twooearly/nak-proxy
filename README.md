 # Stundenplan Proxy

Ein kleiner Flask-Proxy, der einen iCalendar-Stundenplan abruft, bereinigt
und als eigene `*.ics`-Datei bereitstellt.

## Features

- Holt den Original-Stundenplan von einer festen URL.
- Filtert unerwuenschte Termine (z.B. bestimmte Sprachkurse, andere Gruppen).
- Kuetzt Titel auf das fachliche Kurzformat.
- Gibt eine saubere iCalendar-Antwort zurueck.

## Endpoint

- `GET /stundenplan.ics` -> bereinigter iCalendar Feed

## Konfiguration

- `PORT` (Default: `5000` in dev, `8000` im Docker-Setup)
- `FLASK_ENV=dev` aktiviert Debug-Modus beim lokalen Start

Die Upstream-URL ist in [main.py](main.py) als `STUNDENPLAN_URL` hinterlegt.

## Lokales Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python main.py
```

Dann ist der Feed unter `http://localhost:5000/stundenplan.ics` verfuegbar.

## Docker

### Docker Compose

```bash
docker compose up --build
```

Der Feed ist dann unter `http://localhost:8000/stundenplan.ics` erreichbar.

### Docker ohne Compose

```bash
docker build -t stundenplan-proxy .
docker run --rm -p 8000:8000 stundenplan-proxy
```

## Hinweise

- Der Proxy konvertiert die Upstream-ICS-Datei sauber nach UTF-8.
- Eine Beispiel-Datei liegt in [preview_stundenplan.ics](preview_stundenplan.ics).
