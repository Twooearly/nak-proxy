"""SQLite-Speicher: bekannte Zenturien, Quell-Dateien und alle Termine (inkl. Archiv).

Schreiben tut nur der Poller (und import_ics.py), Web-Requests lesen nur.
"""
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone

import parse

log = logging.getLogger(__name__)

ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", "archive.db")
ZENTURIE_RE = re.compile(r"^[A-Z]\d{2}[a-z]$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS zenturien (
    code TEXT PRIMARY KEY,
    studiengang TEXT,
    jahrgang INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    gefunden_am TEXT NOT NULL,
    letzter_abruf TEXT
);
CREATE TABLE IF NOT EXISTS quellen (
    url TEXT PRIMARY KEY,
    zenturie TEXT NOT NULL,
    last_modified TEXT,
    letzter_abruf TEXT,
    status INTEGER
);
CREATE TABLE IF NOT EXISTS events (
    zenturie TEXT NOT NULL,
    uid TEXT NOT NULL,
    module_key TEXT NOT NULL,
    typ TEXT,
    titel TEXT NOT NULL,
    gruppe TEXT,
    dtstart_utc TEXT NOT NULL,
    dtend_utc TEXT,
    ical BLOB NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (zenturie, uid)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS events_zenturie_start ON events (zenturie, dtstart_utc);
"""

_local = threading.local()


def _new_connection():
    conn = sqlite3.connect(ARCHIVE_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def connect():
    """Eine Verbindung pro Thread (gunicorn gthread + Poller-Thread)."""
    conn = getattr(_local, "conn", None)
    if conn is None or getattr(_local, "path", None) != ARCHIVE_PATH:
        conn = _local.conn = _new_connection()
        _local.path = ARCHIVE_PATH
    return conn


def init():
    """Schema anlegen."""
    conn = connect()
    with conn:
        conn.executescript(SCHEMA)
        # Backup-Tabelle der früheren Migration vom alten Ein-Zenturien-Archiv, wird nicht mehr gebraucht
        conn.execute("DROP TABLE IF EXISTS events_legacy_migriert")


# --- Hilfen ---------------------------------------------------------------

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(text):
    return datetime.fromisoformat(text)


def to_utc_iso(value):
    """datetime/date -> UTC-ISO-String (als Text vergleichbar)."""
    if not isinstance(value, datetime):  # ganztägig
        value = datetime(value.year, value.month, value.day)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _row(zenturie, event):
    # DTSTAMP ändert sich bei jedem Export; ohne ihn erkennen wir echte Änderungen
    event.pop("dtstamp", None)
    typ, _code, name = parse.veranstaltung(event)
    end = event.get("dtend")
    return (
        zenturie,
        str(event["uid"]),
        parse.module_key(event),
        typ,
        name,
        parse.gruppe(event),
        to_utc_iso(event.decoded("dtstart")),
        to_utc_iso(end.dt) if end else None,
        event.to_ical(),
    )


def get_meta(key):
    row = connect().execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(key, value):
    conn = connect()
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


def ensure_zenturie(code, studiengang=None):
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO zenturien (code, studiengang, jahrgang, gefunden_am) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(code) DO UPDATE SET studiengang=COALESCE(excluded.studiengang, studiengang)",
            (code, studiengang, 2000 + int(code[1:3]), now_iso()),
        )


# --- Schreiben (Poller) ---------------------------------------------------

def sync_source(zenturie, url, events, window=None, last_modified=None):
    """Gleicht die Termine einer Upstream-Datei mit dem Archiv ab.

    - Alle Termine der Datei werden per (Zenturie, UID) eingefügt/aktualisiert.
    - Zukünftige Termine dieser Zenturie, die in der Datei fehlen, gelten als abgesagt und werden
      gelöscht, aber nur innerhalb des Zeitfensters der Datei (X-SKED-SYNC-DTSTART/-DTEND).
    - Vergangene Termine bleiben immer erhalten (Archiv).
    Gibt die Anzahl geänderter Zeilen zurück.
    """
    now = now_iso()
    rows = {}
    for ev in events:
        if ev.get("uid") and ev.get("dtstart"):
            row = _row(zenturie, ev)
            rows[row[1]] = row

    conn = connect()
    changed = 0
    with conn:
        stored = dict(conn.execute(
            "SELECT uid, ical FROM events WHERE zenturie = ?", (zenturie,)
        ).fetchall())
        upserts = [r + (now,) for uid, r in rows.items() if stored.get(uid) != r[8]]
        conn.executemany(
            "INSERT INTO events (zenturie, uid, module_key, typ, titel, gruppe, dtstart_utc, dtend_utc, ical, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(zenturie, uid) DO UPDATE SET "
            "module_key=excluded.module_key, typ=excluded.typ, titel=excluded.titel, gruppe=excluded.gruppe, "
            "dtstart_utc=excluded.dtstart_utc, dtend_utc=excluded.dtend_utc, ical=excluded.ical, "
            "updated_at=excluded.updated_at",
            upserts,
        )
        changed += len(upserts)

        # Absagen nur erkennen, wenn die Datei überhaupt Termine enthielt (Schutz vor leeren Exporten)
        if rows:
            lo, hi = window if window else (now, "9999")
            lo = max(lo, now)
            cur = conn.execute(
                "SELECT uid FROM events WHERE zenturie = ? AND dtstart_utc >= ? AND dtstart_utc < ?",
                (zenturie, lo, hi),
            )
            gone = [(zenturie, uid) for (uid,) in cur if uid not in rows]
            conn.executemany("DELETE FROM events WHERE zenturie = ? AND uid = ?", gone)
            changed += len(gone)
            if gone:
                log.info("%s: %d zukünftige Termine abgesagt", zenturie, len(gone))

        conn.execute(
            "INSERT INTO quellen (url, zenturie, last_modified, letzter_abruf, status) VALUES (?, ?, ?, ?, 200) "
            "ON CONFLICT(url) DO UPDATE SET last_modified=excluded.last_modified, "
            "letzter_abruf=excluded.letzter_abruf, status=200",
            (url, zenturie, last_modified, now),
        )
        conn.execute(
            "UPDATE zenturien SET letzter_abruf = ?, version = version + ? WHERE code = ?",
            (now, 1 if changed else 0, zenturie),
        )
    return changed


def mark_source(url, zenturie, status):
    """Abruf ohne neue Daten (304/404/Fehler) vermerken."""
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO quellen (url, zenturie, letzter_abruf, status) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(url) DO UPDATE SET letzter_abruf=excluded.letzter_abruf, status=excluded.status",
            (url, zenturie, now_iso(), status),
        )


def import_events(zenturie, events, overwrite=False):
    """Schreibt Events ins Archiv, ohne etwas zu löschen. Gibt (neu, aktualisiert, übersprungen) zurück."""
    conn = connect()
    added = updated = skipped = 0
    now = now_iso()
    with conn:
        for ev in events:
            row = _row(zenturie, ev) + (now,)
            exists = conn.execute(
                "SELECT 1 FROM events WHERE zenturie = ? AND uid = ?", (zenturie, row[1])
            ).fetchone()
            if exists and not overwrite:
                skipped += 1
                continue
            conn.execute(
                "INSERT OR REPLACE INTO events (zenturie, uid, module_key, typ, titel, gruppe, dtstart_utc, "
                "dtend_utc, ical, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            if exists:
                updated += 1
            else:
                added += 1
        if added or updated:
            conn.execute("UPDATE zenturien SET version = version + 1 WHERE code = ?", (zenturie,))
    return added, updated, skipped


# --- Lesen (Web) ----------------------------------------------------------

def zenturie(code):
    row = connect().execute(
        "SELECT code, studiengang, jahrgang, version, letzter_abruf FROM zenturien WHERE code = ?", (code,)
    ).fetchone()
    if not row:
        return None
    return dict(zip(("code", "studiengang", "jahrgang", "version", "letzter_abruf"), row))


def list_zenturien(nur_mit_terminen=False):
    """Alle bekannten Zenturien; für die Auswahlseite nur die, für die schon Termine vorliegen."""
    rows = connect().execute(
        "SELECT z.code, z.studiengang, z.jahrgang, z.letzter_abruf, "
        "(SELECT max(dtstart_utc) FROM events e WHERE e.zenturie = z.code) "
        "FROM zenturien z ORDER BY z.code"
    ).fetchall()
    return [
        dict(code=c, studiengang=s, jahrgang=j, letzter_abruf=a, letzter_termin=t)
        for c, s, j, a, t in rows
        if t or not nur_mit_terminen
    ]


def list_module(code):
    """Module einer Zenturie mit Anzahl Termine, Zeitraum und Laborgruppen."""
    conn = connect()
    now = now_iso()
    rows = conn.execute(
        "SELECT module_key, typ, count(*), sum(dtstart_utc >= ?), min(dtstart_utc), max(dtstart_utc), "
        "group_concat(DISTINCT gruppe) FROM events WHERE zenturie = ? GROUP BY module_key",
        (now, code),
    ).fetchall()
    # Titel/Typ vom jüngsten Termin, weil sich Bezeichnungen ändern können
    latest = dict(
        ((k, (t, ty)) for k, t, ty in conn.execute(
            "SELECT module_key, titel, typ FROM events WHERE zenturie = ? ORDER BY dtstart_utc", (code,)
        ))
    )
    result = []
    for key, _typ, n, n_future, first, last, groups in rows:
        titel, typ = latest[key]
        result.append(dict(
            key=key,
            titel=titel,
            typ=typ,
            typ_name=parse.TYPEN.get(typ or "", "Sonstiges"),
            anzahl=n,
            anzahl_zukuenftig=n_future or 0,
            erster_termin=first,
            letzter_termin=last,
            gruppen=sorted(groups.split(","), key=lambda g: (len(g), g)) if groups else [],
        ))
    order = list(parse.TYPEN)
    result.sort(key=lambda m: (
        m["anzahl_zukuenftig"] == 0,
        order.index(m["typ"]) if m["typ"] in order else len(order),
        m["titel"],
    ))
    return result


def events_for(code):
    return connect().execute(
        "SELECT module_key, gruppe, ical, updated_at FROM events WHERE zenturie = ? ORDER BY dtstart_utc",
        (code,),
    ).fetchall()
