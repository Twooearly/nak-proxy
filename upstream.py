"""Abruf der NAK-Stundenpläne und Suche nach existierenden Zenturien.

Wird nur vom Poller aufgerufen, nie direkt durch einen Web-Request.
"""
import logging
import os
import re
import string
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

import parse
import store

log = logging.getLogger(__name__)

STUNDENPLAN_BASE = "https://cis.nordakademie.de/fileadmin/Infos/Stundenplaene"
BERLIN = ZoneInfo("Europe/Berlin")
# Pause zwischen zwei Requests an die NAK (Sekunden)
REQUEST_PAUSE = float(os.getenv("UPSTREAM_PAUSE", "0.5"))
# So viele Jahrgänge rückwärts sucht die Discovery
JAHRGAENGE = int(os.getenv("DISCOVERY_JAHRGAENGE", "5"))

_session = requests.Session()
_session.headers["User-Agent"] = os.getenv("UPSTREAM_USER_AGENT", "nak-stundenplan-proxy")


def semester(code, today=None):
    """Semester (1-basiert) seit Studienstart; Studium beginnt im August (Wechsel jeweils Jan/Jul)."""
    today = today or date.today()
    start = 2000 + int(code[1:3])
    return 2 * (today.year - start) + (1 if today.month >= 7 else 0)


def candidate_urls(code, today=None):
    """Vorheriges, aktuelles und nächstes Semester, weil um den Wechsel herum mehrere online sind."""
    sem = semester(code, today)
    return [f"{STUNDENPLAN_BASE}/{code}_{n}.ics" for n in (sem - 1, sem, sem + 1) if n >= 1]


def _sync_window(cal):
    """Zeitfenster der Datei (X-SKED-SYNC-DTSTART/-DTEND, Ortszeit) als UTC-ISO-Strings."""
    try:
        lo, hi = (
            datetime.strptime(str(cal[k]), "%Y%m%dT%H%M%S").replace(tzinfo=BERLIN)
            for k in ("X-SKED-SYNC-DTSTART", "X-SKED-SYNC-DTEND")
        )
    except (KeyError, ValueError):
        return None
    return store.to_utc_iso(lo), store.to_utc_iso(hi)


def _studiengang(cal):
    """"A25 2025 - Angewandte Informatik A25a" -> "Angewandte Informatik"."""
    name = str(cal.get("X-WR-CALNAME", ""))
    m = re.match(r"^\S+\s+\d{4}\s+-\s+(.+?)\s+\S+$", name)
    return m.group(1) if m else None


def fetch_zenturie(code):
    """Holt alle Kandidaten-Dateien einer Zenturie und gleicht sie mit dem Archiv ab."""
    known = dict(store.connect().execute(
        "SELECT url, last_modified FROM quellen WHERE zenturie = ?", (code,)
    ).fetchall())
    changed = 0
    for url in candidate_urls(code):
        headers = {}
        if known.get(url):
            headers["If-Modified-Since"] = known[url]
        try:
            resp = _session.get(url, timeout=20, headers=headers)
        except requests.RequestException as e:
            log.warning("%s: %s", url, e)
            store.mark_source(url, code, 0)
            continue
        finally:
            time.sleep(REQUEST_PAUSE)
        if resp.status_code != 200:
            store.mark_source(url, code, resp.status_code)
            continue
        try:
            cal = parse.decode_ics(resp.content)
        except ValueError as e:
            log.warning("%s: nicht lesbar (%s)", url, e)
            store.mark_source(url, code, -1)
            continue
        store.ensure_zenturie(code, _studiengang(cal))
        changed += store.sync_source(
            code, url, cal.walk("VEVENT"), _sync_window(cal), resp.headers.get("Last-Modified")
        )
    return changed


def _exists(code):
    for url in candidate_urls(code):
        try:
            ok = _session.head(url, timeout=10).status_code == 200
        except requests.RequestException:
            ok = False
        time.sleep(REQUEST_PAUSE)
        if ok:
            return True
    return False


def discover(today=None):
    """Sucht Zenturien per HEAD-Request: Buchstaben A-Z, letzte Jahrgänge, Suffixe a, b, c, ...

    Suffixe sind lückenlos vergeben (W25a-d), daher endet die Suche je Studiengang/Jahrgang
    beim ersten fehlenden Suffix. Bekannte Zenturien bleiben immer gespeichert (Archiv).
    Zusätzliche Codes lassen sich über ZUSATZ_ZENTURIEN (kommagetrennt) erzwingen.
    """
    today = today or date.today()
    found = []
    extra = [z.strip() for z in os.getenv("ZUSATZ_ZENTURIEN", "").split(",") if store.ZENTURIE_RE.match(z.strip())]
    for code in extra:
        store.ensure_zenturie(code)
    for year in range(today.year - JAHRGAENGE, today.year + 1):
        yy = year % 100
        for letter in string.ascii_uppercase:
            for suffix in string.ascii_lowercase:
                code = f"{letter}{yy:02d}{suffix}"
                if not _exists(code):
                    break
                store.ensure_zenturie(code)
                found.append(code)
    log.info("Discovery: %d Zenturien gefunden: %s", len(found), ", ".join(found))
    return found
