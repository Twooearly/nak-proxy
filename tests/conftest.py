"""Gemeinsame Fixtures: jede Testfunktion bekommt eine eigene, leere SQLite-DB.

Die Tests laufen komplett offline; NAK-Termine werden mit make_event() nachgebaut.
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

# vor dem Import von main setzen: kein Poller-Thread, kein Frontend-Build nötig
os.environ["POLLER"] = "0"
os.environ["ARCHIVE_PATH"] = os.path.join(tempfile.mkdtemp(), "import.db")

import pytest
from icalendar import Event

import render
import store

JETZT = datetime.now(timezone.utc).replace(microsecond=0)


def make_event(uid, start, veranstaltung="V A205 Algorithmen und Datenstrukturen",
               anmerkung="-", status="-", dauer=timedelta(hours=2)):
    """Termin im Format des sked.de-Exports der NAK."""
    ev = Event()
    ev.add("uid", uid)
    ev.add("summary", f"{veranstaltung},Prof. Dr. Muster,A102")
    ev.add("description", f"Veranstaltung: {veranstaltung}\nDozent: Prof. Dr. Muster\n"
                          f"Pause: -\nRaum: A102\nAnmerkung: {anmerkung}\nStatus: {status}")
    ev.add("dtstart", start)
    ev.add("dtend", start + dauer)
    ev.add("dtstamp", JETZT)
    return ev


def tage(n):
    """Zeitpunkt n Tage von jetzt (negativ = Vergangenheit)."""
    return JETZT + timedelta(days=n)


def fenster(von, bis):
    """Sync-Fenster einer NAK-Datei als UTC-ISO-Strings."""
    return store.to_utc_iso(tage(von)), store.to_utc_iso(tage(bis))


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Frische DB pro Test, Caches geleert."""
    monkeypatch.setattr(store, "ARCHIVE_PATH", str(tmp_path / "archive.db"))
    render.render.cache_clear()
    render.module_keys.cache_clear()
    store.init()
    yield tmp_path / "archive.db"
    conn = getattr(store._local, "conn", None)
    if conn is not None:
        conn.close()
        store._local.conn = None
