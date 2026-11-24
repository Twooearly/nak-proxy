"""Abruf der NAK-Dateien (upstream.py) mit gefälschten HTTP-Antworten, ohne Netzwerk."""
from datetime import date

import pytest

import store
import upstream
from conftest import make_event, tage

BASE = upstream.STUNDENPLAN_BASE


@pytest.mark.parametrize("heute, sem", [
    (date(2025, 8, 1), 1), (date(2026, 1, 15), 2), (date(2026, 7, 1), 3),
    (date(2026, 11, 24), 3), (date(2027, 3, 1), 4), (date(2025, 3, 1), 0),
])
def test_semester(heute, sem):
    assert upstream.semester("A25a", heute) == sem


def test_candidate_urls():
    assert upstream.candidate_urls("A25a", date(2026, 11, 24)) == [
        f"{BASE}/A25a_2.ics", f"{BASE}/A25a_3.ics", f"{BASE}/A25a_4.ics"]
    # vor Studienbeginn: nur Semester 1
    assert upstream.candidate_urls("A26a", date(2026, 3, 1)) == [f"{BASE}/A26a_1.ics"]


def nak_datei(events, name="A25 2025 - Angewandte Informatik A25a"):
    """Datei wie von sked.de: UTF-8, mit Sync-Fenster und Kalendername."""
    body = "".join(e.to_ical().decode() for e in events)
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//www.sked.de//EN\r\n"
        f"X-WR-CALNAME:{name}\r\n"
        f"X-SKED-SYNC-DTSTART:{tage(-30):%Y%m%dT000000}\r\nX-SKED-SYNC-DTEND:{tage(30):%Y%m%dT000000}\r\n"
        f"{body}END:VCALENDAR\r\n"
    ).encode("utf-8")


class FakeResponse:
    def __init__(self, status, content=b"", headers=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}


class FakeSession:
    """Liefert pro URL eine feste Antwort und merkt sich die Request-Header."""
    def __init__(self, antworten):
        self.antworten = antworten
        self.requests = []

    def get(self, url, timeout=None, headers=None):
        self.requests.append((url, dict(headers or {})))
        return self.antworten.get(url, FakeResponse(404))

    def head(self, url, timeout=None):
        return FakeResponse(200 if url in self.antworten else 404)


@pytest.fixture
def fake(monkeypatch):
    def install(antworten):
        session = FakeSession(antworten)
        monkeypatch.setattr(upstream, "_session", session)
        monkeypatch.setattr(upstream, "REQUEST_PAUSE", 0)
        return session
    return install


def test_fetch_zenturie(db, fake, monkeypatch):
    monkeypatch.setattr(upstream, "candidate_urls", lambda code, today=None: [f"{BASE}/{code}_3.ics", f"{BASE}/{code}_4.ics"])
    datei = nak_datei([make_event("a", tage(2), veranstaltung="V S011 Digitale Geschäftsprozesse"),
                       make_event("b", tage(3))])
    session = fake({f"{BASE}/A25a_3.ics": FakeResponse(200, datei, {"Last-Modified": "Fri, 20 Nov 2026 10:17:25 GMT"})})
    store.ensure_zenturie("A25a")

    assert upstream.fetch_zenturie("A25a") == 2
    z = store.zenturie("A25a")
    assert z["studiengang"] == "Angewandte Informatik"
    assert store.connect().execute("SELECT titel FROM events WHERE uid='a'").fetchone()[0] == "Digitale Geschäftsprozesse"

    # zweiter Abruf schickt If-Modified-Since; 304 ändert nichts
    session.antworten[f"{BASE}/A25a_3.ics"] = FakeResponse(304)
    assert upstream.fetch_zenturie("A25a") == 0
    sent = [h for url, h in session.requests if url.endswith("_3.ics")]
    assert sent[-1]["If-Modified-Since"] == "Fri, 20 Nov 2026 10:17:25 GMT"
    status = dict(store.connect().execute("SELECT url, status FROM quellen").fetchall())
    assert status == {f"{BASE}/A25a_3.ics": 304, f"{BASE}/A25a_4.ics": 404}


def test_fetch_kaputte_datei_loescht_nichts(db, fake, monkeypatch):
    monkeypatch.setattr(upstream, "candidate_urls", lambda code, today=None: [f"{BASE}/{code}_3.ics"])
    store.ensure_zenturie("A25a")
    fake({f"{BASE}/A25a_3.ics": FakeResponse(200, nak_datei([make_event("a", tage(2))]))})
    upstream.fetch_zenturie("A25a")
    fake({f"{BASE}/A25a_3.ics": FakeResponse(200, b"<html>Wartungsarbeiten</html>")})
    upstream.fetch_zenturie("A25a")
    assert store.connect().execute("SELECT count(*) FROM events").fetchone()[0] == 1


def test_discover(db, fake, monkeypatch):
    heute = date(2026, 11, 24)
    vorhanden = ["A25a", "A25b", "W25a", "W25c", "B24a"]  # W25b fehlt -> W25c wird nicht gefunden
    fake({f"{BASE}/{z}_{upstream.semester(z, heute)}.ics": FakeResponse(200) for z in vorhanden})
    monkeypatch.setenv("ZUSATZ_ZENTURIEN", "Q26a, ungültig")
    assert upstream.discover(heute) == ["B24a", "A25a", "A25b", "W25a"]
    assert {z["code"] for z in store.list_zenturien()} == {"B24a", "A25a", "A25b", "W25a", "Q26a"}
