# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A public site where Nordakademie students pick Studiengang, Jahrgang and Zenturie, select modules, and get an iCalendar subscription URL. The filter lives entirely in the URL (`/z/A25a.ics?ohne=A205,spanisch-b1&gruppe=W213.2`); the frontend only builds that URL. Past events are kept in a SQLite archive.

Code comments, README, log, CLI output and UI texts are in German. Keep new user-facing strings and comments in German too.

## Commands

```bash
uv sync && uv run main.py                      # backend on :5000 (FLASK_ENV=dev enables debug, POLLER=0 disables polling)
cd frontend && npm run dev                     # frontend on :5173, proxies /api and /z to :5000
cd frontend && npm run check && npm run build  # type-check, static build into frontend/build (served by Flask)
docker compose up --build                      # gunicorn on :8000, archive at /data/archive.db
uv run import_ics.py --zenturie A25a --dry-run <file-or-dir>   # backfill archive (--db, --overwrite, --include-future)
uv run pytest                                  # backend tests (offline, temp DB per test)
```

Tests live in `tests/` (pytest, fully offline). `conftest.py` provides the `db` fixture (fresh SQLite per test, caches cleared) and `make_event()`, which builds events in the NAK sked.de format. Upstream HTTP is faked via `FakeSession` in `test_upstream.py`. Add or adjust tests with every behaviour change, especially in `store.sync_source` (archive and cancellation logic). There is no linter. Local Docker builds need buildx (`docker buildx build --load -t nak-proxy .`).

CI (`.github/workflows/ci.yml`) runs `test-backend` (pytest on Python 3.13) and `test-frontend` (`npm run check` + build) on PRs and on pushes to `main`/tags. The `docker` job (multi-arch build + push to GHCR) needs both and runs only for `main`, `v*` tags and manual dispatch, so red tests never reach the server.

## Architecture

- **Requests never hit upstream.** `poller.py` runs one background thread (guarded by an `flock` on `.poller.lock` next to the DB). Daily it runs `upstream.discover()` (HEAD probes over letters A–Z, the last 5 Jahrgänge, suffixes a, b, … until the first miss). Every 30 min it runs `upstream.fetch_zenturie()` for every known Zenturie.
- **`upstream.py`**: The URL is `{BASE}/{Zenturie}_{semester}.ics`, semester = `2*(year-start) + (1 if month >= 7)`. Only the current semester file is online, so all of sem-1/sem/sem+1 are fetched with `If-Modified-Since`. Upstream is **UTF-8** (the old proxy wrongly decoded windows-1252). The Studiengang comes from `X-WR-CALNAME`, and the cancellation window from `X-SKED-SYNC-DTSTART/-DTEND`.
- **`parse.py`**: All rules read the `Veranstaltung:` / `Anmerkung:` / `Status:` description lines:
  - `module_key()`: course code (`A205`) or a slug (`spanisch-b1`).
  - `gruppe()`: Laborgruppe.
  - `display_title()`.
  Titles are computed at render time, so rule changes apply to archived events too.
- **`store.py`**: Tables `zenturien` (with `version`, bumped on every change; used as cache key/ETag), `quellen` (per upstream URL), and `events` (PK `zenturie, uid`; raw event without DTSTAMP). `sync_source()` upserts, then deletes only *future* events missing from the file *within its sync window*, and never deletes on an empty file. `init()` migrates the old single-Zenturie table once (renamed to `events_legacy_migriert`) and skips non-NAK events.
- **`render.py`**: `lru_cache` over `(zenturie, version, ohne, gruppen)`.
- **`main.py`**: Routes, input validation (Zenturie regex + must exist in DB), legacy `/stundenplan.ics` (A25a without `spanisch*`), serving the static frontend.
- **`frontend/`**: SvelteKit 3 (adapter-static, runes, CSP hashes), shadcn-svelte (`vega` style) + Tailwind 4. Imports use `#lib/...` with explicit `.js`/`index.js` paths. The selection is mirrored into the URL hash (`#/z/A25a.ics?ohne=…`).

## Gotchas

- When adding a Python module, add it to `py-modules` in `pyproject.toml` and to both `COPY` lines in the `Dockerfile`.
- Gunicorn runs **1 worker with 8 threads** so there is exactly one poller; SQLite runs in WAL mode.
- Started as root, the entrypoint chowns `/data` to UID 1000 and drops root. With `user:` set in compose it skips that and runs directly as that user; `/data` must then be writable by it (SQLite creates `-wal`/`-shm` files next to the DB).
- The local `compose.yaml` uses the named volume `calendar-proxy_calendar-data`. A deployment may use a bind mount instead.
- `/stundenplan.ics` must keep working; existing subscriptions use it.
- Feeds are public: never import non-NAK events into the archive.
- `*.ics` is gitignored; do not commit sample feeds.
- Docker uses Python 3.13 and Node 26 (the lockfile is from npm 11). `.python-version` is 3.14.
