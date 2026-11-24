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
COPY --from=ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d /uv /bin/uv
# Genau die Versionen aus uv.lock, per Hash geprüft. Das Projekt selbst wird nicht installiert,
# die Module liegen in /app.
# Läuft auf der Build-Plattform: markupsafe und charset-normalizer bringen dabei C-Erweiterungen
# für die falsche Architektur mit. Beide fallen dann auf ihre reine Python-Version zurück.
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt \
    && pip install --prefix=/install --require-hashes --no-deps -r requirements.txt

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
