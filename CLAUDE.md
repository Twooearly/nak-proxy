# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A small Flask app that serves the Nordakademie timetable for one Zenturie as a cleaned-up iCalendar feed at `/stundenplan.ics`. Titles are shortened, some events are filtered out, and past events are kept in a SQLite archive.

Code comments, README, log and CLI output are in German. Keep new user-facing strings and comments in German too.

## Commands

```bash
uv sync && uv run main.py              # dev server on :5000 (FLASK_ENV=dev enables debug)
docker compose up --build              # gunicorn on :8000, archive at /data/archive.db
python import_ics.py --dry-run <file-or-dir>   # import old .ics files into the archive (--db, --overwrite, --include-future)
```

There are no tests, linter or formatter configured. To check changes, run the app and request the feed with `curl localhost:5000/stundenplan.ics`.

CI (`.github/workflows/docker-image.yml`) only builds and pushes a multi-arch Docker image (amd64/arm64/armv7) to GHCR on every push to `main` and on `v*` tags.

## Architecture

- **`main.py`** creates the Flask `app` (gunicorn entry point `main:app`).
  - The upstream URL is computed, not configured: `{STUNDENPLAN_BASE}/{ZENTURIE}_{semester}.ics`, where semester = `2*(year-START_JAHR) + (1 if month >= 7)`. `fetch_upstream()` tries the computed semester first, then `+1`, then `-1`, to cover the changeover between semesters. Upstream is decoded as windows-1252.
  - `clean_event()` contains the filtering and title rules (drop "Spanisch", cut the course code prefix, add "(online)" based on the `Anmerkung:` line). It returns `None` to drop an event. `import_ics.py` reuses it.
  - If no upstream URL answers, the endpoint still returns a feed made only from the archive.
- **`archive.py`**: `merge_with_archive()` upserts all current events by UID into SQLite. Archived events missing upstream are kept if they are in the past and deleted if they are in the future, because a missing future event means it was cancelled. `dtstart` is stored as a UTC ISO string so it can be compared as text. The schema is created on every connection.
- **`import_ics.py`**: CLI that backfills the archive from old `.ics` files. Raw NAK exports (detected by `is_raw_nak()`) go through `clean_event()`; other events are imported unchanged. It never deletes anything.

## Gotchas

- When adding a module, add it to `py-modules` in `pyproject.toml` and to both `COPY` lines in the `Dockerfile`.
- Gunicorn runs 2 workers, so SQLite runs in WAL mode for concurrent access.
- The compose volume has the fixed name `calendar-proxy_calendar-data` so the archive survives renaming the project directory. Do not change it.
- `*.ics` is gitignored; do not commit sample feeds.
- `.python-version` is 3.14, but the Docker image uses 3.11.
