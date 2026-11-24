"""SQLite-Archiv: behält vergangene Stundenplan-Termine, die upstream gelöscht wurden."""
import os
import sqlite3
from datetime import date, datetime, timezone

from icalendar import Event

ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", "archive.db")


def _connect():
    conn = sqlite3.connect(ARCHIVE_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS events ("
        "uid TEXT PRIMARY KEY, dtstart TEXT NOT NULL, ical BLOB NOT NULL)"
    )
    return conn


def _start_utc(event):
    """DTSTART als UTC-ISO-String (vergleichbar, auch bei ganztägigen Terminen)."""
    dt = event.decoded("dtstart")
    if not isinstance(dt, datetime):  # ganztägig
        dt = datetime(dt.year, dt.month, dt.day)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def merge_with_archive(current_events, now=None):
    """Gibt current_events plus vergangene, upstream verschwundene Termine zurück.

    - Aktuelle Events werden per UID im Archiv gespeichert/aktualisiert.
    - Archivierte Events, die upstream fehlen: nur behalten, wenn sie in der Vergangenheit liegen.
      Zukünftige (= abgesagte) Termine werden aus dem Archiv entfernt.
    """
    now_iso = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    current_uids = set()
    rows = []
    for ev in current_events:
        uid = str(ev.get("uid", ""))
        if not uid:
            continue
        current_uids.add(uid)
        rows.append((uid, _start_utc(ev), ev.to_ical()))

    conn = _connect()
    try:
        with conn:
            conn.executemany(
                "INSERT INTO events (uid, dtstart, ical) VALUES (?, ?, ?) "
                "ON CONFLICT(uid) DO UPDATE SET dtstart=excluded.dtstart, ical=excluded.ical",
                rows,
            )
            stored = conn.execute("SELECT uid, dtstart, ical FROM events").fetchall()
            stale_future = [
                (uid,) for uid, start, _ in stored
                if uid not in current_uids and start >= now_iso
            ]
            conn.executemany("DELETE FROM events WHERE uid = ?", stale_future)
    finally:
        conn.close()

    gone_past = [
        Event.from_ical(ical)
        for uid, start, ical in stored
        if uid not in current_uids and start < now_iso
    ]
    return list(current_events) + gone_past


def import_events(events, overwrite=False):
    """Schreibt Events ins Archiv, ohne etwas zu löschen. Gibt (neu, aktualisiert, übersprungen) zurück."""
    conn = _connect()
    added = updated = skipped = 0
    try:
        with conn:
            for ev in events:
                uid = str(ev.get("uid", ""))
                row = (uid, _start_utc(ev), ev.to_ical())
                exists = conn.execute("SELECT 1 FROM events WHERE uid = ?", (uid,)).fetchone()
                if exists and not overwrite:
                    skipped += 1
                elif exists:
                    conn.execute("UPDATE events SET dtstart=?, ical=? WHERE uid=?", (row[1], row[2], uid))
                    updated += 1
                else:
                    conn.execute("INSERT INTO events (uid, dtstart, ical) VALUES (?, ?, ?)", row)
                    added += 1
    finally:
        conn.close()
    return added, updated, skipped
