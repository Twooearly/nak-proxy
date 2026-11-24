"""Regeln für Modul-Schlüssel, Titel, Gruppen und Kodierung (parse.py)."""
import pytest

import parse
from conftest import make_event, tage


@pytest.mark.parametrize("veranstaltung, key, titel", [
    ("V A205 Algorithmen und Datenstrukturen", "A205", "Algorithmen und Datenstrukturen"),
    ("WP WP040 Arbeitsrecht", "WP040", "Arbeitsrecht"),
    ("L W213 Mess-, Steuerungs- und Regelungstechnik (MSR) (Labor)", "W213",
     "Mess-, Steuerungs- und Regelungstechnik (MSR) (Labor)"),
    ("S Spanisch B1+", "spanisch-b1", "Spanisch B1+"),
    ("S Spanisch A.2.2", "spanisch-a-2-2", "Spanisch A.2.2"),
    ("Z Zenturienbetreuung", "zenturienbetreuung", "Zenturienbetreuung"),
    ("I Studiengangsversammlung", "studiengangsversammlung", "Studiengangsversammlung"),
    ("V S011 Digitale Geschäftsprozesse", "S011", "Digitale Geschäftsprozesse"),
])
def test_modul_und_titel(veranstaltung, key, titel):
    ev = make_event("u", tage(1), veranstaltung=veranstaltung)
    assert parse.module_key(ev) == key
    assert parse.display_title(ev) == titel
    assert parse.KEY_RE.match(key)


def test_titel_aus_bereinigter_summary_ohne_beschreibung():
    """Fallback, wenn keine Veranstaltung-Zeile vorhanden ist."""
    ev = make_event("u", tage(1))
    del ev["description"]
    assert parse.module_key(ev) == "A205"
    assert parse.display_title(ev) == "Algorithmen und Datenstrukturen"


@pytest.mark.parametrize("anmerkung, status, online", [
    ("ONLINE", "-", True),
    ("-", "Onlinevorlesung", True),
    ("-", "-", False),
    ("Gruppe 1", "-", False),
])
def test_online(anmerkung, status, online):
    ev = make_event("u", tage(1), anmerkung=anmerkung, status=status)
    assert parse.is_online(ev) is online
    assert parse.display_title(ev).endswith("(online)") is online


def test_online_nicht_doppelt():
    ev = make_event("u", tage(1), veranstaltung="V A100 Online-Marketing online", anmerkung="ONLINE")
    assert parse.display_title(ev) == "Online-Marketing online"


@pytest.mark.parametrize("anmerkung, gruppe", [
    ("Gruppe 2", "2"), ("gruppe 3", "3"), ("Labor", None), ("-", None),
])
def test_gruppe(anmerkung, gruppe):
    ev = make_event("u", tage(1), veranstaltung="L W213 Labor", anmerkung=anmerkung)
    assert parse.gruppe(ev) == gruppe
    if gruppe:
        assert parse.display_title(ev) == f"Labor (Gruppe {gruppe})"


def test_is_nak_event():
    assert parse.is_nak_event(make_event("u", tage(1)))
    fremd = make_event("u", tage(1))
    fremd["description"] = "ICE 123 nach Hamburg"
    assert not parse.is_nak_event(fremd)


@pytest.mark.parametrize("kaputt, heil", [
    ("Digitale GeschÃ¤ftsprozesse", "Digitale Geschäftsprozesse"),
    ("Prof. LÃ¼cke", "Prof. Lücke"),
    ("GroÃŸe Projekte", "Große Projekte"),
    ("Fliegen â€“ verstehen", "Fliegen – verstehen"),
])
def test_repair_mojibake(kaputt, heil):
    assert parse.repair_mojibake(kaputt) == heil


@pytest.mark.parametrize("text", ["Prof. Lücke", "Geschäftsprozesse", "Ärger – Ölung", "plain ascii", "Ã allein"])
def test_repair_mojibake_laesst_korrektes_in_ruhe(text):
    assert parse.repair_mojibake(text) == text


def _ics(summary):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:x\r\nDTSTART:20260101T080000Z\r\n"
            f"SUMMARY:{summary}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


@pytest.mark.parametrize("encoding", ["utf-8", "windows-1252"])
def test_decode_ics(encoding):
    cal = parse.decode_ics(_ics("Prof. Lücke").encode(encoding))
    assert str(cal.walk("VEVENT")[0]["summary"]) == "Prof. Lücke"


def test_slug():
    assert parse.slug("Spanisch B1+") == "spanisch-b1"
    assert parse.slug("Übung für Ältere") == "ubung-fur-altere"
    assert parse.slug("+++") == "sonstiges"
