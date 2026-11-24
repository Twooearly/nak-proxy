# --- Frontend (SvelteKit, statischer Build) ---------------------------------
# Läuft auf der Build-Plattform: das Ergebnis ist reines HTML/JS/CSS
FROM --platform=$BUILDPLATFORM node:26-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Python-Abhängigkeiten ----------------------------------------------------
FROM --platform=$BUILDPLATFORM python:3.13-slim AS builder
WORKDIR /app
# Abhängigkeiten sind reines Python; MarkupSafe ohne C-Erweiterung,
# damit die kopierten site-packages architekturunabhängig bleiben
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MARKUPSAFE_NO_SPEEDUPS=1
COPY pyproject.toml README.md main.py parse.py store.py upstream.py poller.py render.py import_ics.py ./
RUN pip install --prefix=/install .

# --- Laufzeit -------------------------------------------------------------------
FROM python:3.13-slim AS runtime
WORKDIR /app

RUN useradd --system --uid 1000 --home /app app
COPY --from=builder /install /usr/local
COPY main.py parse.py store.py upstream.py poller.py render.py import_ics.py entrypoint.sh ./
COPY --from=frontend /frontend/build ./static

ENV PYTHONUNBUFFERED=1 \
    ARCHIVE_PATH=/data/archive.db \
    STATIC_DIR=/app/static

VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]

# Ein Prozess mit Threads: genau ein Poller, Requests lesen parallel aus SQLite
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "--timeout", "30", "--no-control-socket", "main:app"]
