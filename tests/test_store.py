"""Archiv-Logik (store.py): Abgleich, Absagen, Import und Migration der alten Tabelle."""
import sqlite3

import store
from conftest import fenster, make_event, tage

Z = "A25a"


def uids(zenturie=Z):
    return {r[0] for r in store.connect().execute("SELECT uid FROM events WHERE zenturie = ?", (zenturie,))}


def version(zenturie=Z):
    return store.zenturie(zenturie)["version"]


def test_sync_fuegt_ein_und_setzt_felder(db):
    store.ensure_zenturie(Z, "Angewandte Informatik")
    ev = make_event("e1", tage(3), veranstaltung="L W213 Labor", anmerkung="Gruppe 2")
    assert store.sync_source(Z, "url", [ev], fenster(-30, 30)) == 1
    row = store.connect().execute(
        "SELECT module_key, typ, titel, gruppe, ical FROM events WHERE uid = 'e1'").fetchone()
    assert row[:4] == ("W213", "L", "Labor", "2")
    assert b"DTSTAMP" not in row[4]  # ändert sich bei jedem Export
    assert store.zenturie(Z)["studiengang"] == "Angewandte Informatik"
    assert store.zenturie(Z)["jahrgang"] == 2025


def test_fehlender_zukuenftiger_termin_im_fenster_wird_geloescht(db):
    store.ensure_zenturie(Z)
    store.sync_source(Z, "url", [make_event("a", tage(5)), make_event("b", tage(6))], fenster(-30, 30))
    store.sync_source(Z, "url", [make_event("b", tage(6))], fenster(-30, 30))
    assert uids() == {"b"}


def test_vergangene_termine_bleiben_im_archiv(db):
    store.ensure_zenturie(Z)
    store.sync_source(Z, "url", [make_event("alt", tage(-5)), make_event("neu", tage(5))], fenster(-30, 30))
    store.sync_source(Z, "url", [make_event("neu", tage(5))], fenster(-30, 30))
    assert uids() == {"alt", "neu"}


def test_termine_ausserhalb_des_fensters_bleiben(db):
    """Termin aus einer anderen Semesterdatei darf nicht als abgesagt gelten."""
    store.ensure_zenturie(Z)
    store.sync_source(Z, "sem4", [make_event("spaeter", tage(60))], fenster(40, 100))
    store.sync_source(Z, "sem3", [make_event("jetzt", tage(5))], fenster(-30, 30))
    assert uids() == {"spaeter", "jetzt"}


def test_ohne_fenster_gelten_alle_zukuenftigen_fehlenden_als_abgesagt(db):
    store.ensure_zenturie(Z)
    store.sync_source(Z, "url", [make_event("a", tage(5)), make_event("b", tage(90))], None)
    store.sync_source(Z, "url", [make_event("a", tage(5))], None)
    assert uids() == {"a"}


def test_leere_datei_loescht_nichts(db):
    store.ensure_zenturie(Z)
    store.sync_source(Z, "url", [make_event("a", tage(5))], fenster(-30, 30))
    assert store.sync_source(Z, "url", [], fenster(-30, 30)) == 0
    assert uids() == {"a"}


def test_absagen_betreffen_nur_die_eigene_zenturie(db):
    store.ensure_zenturie(Z)
    store.ensure_zenturie("W25a")
    store.sync_source("W25a", "w", [make_event("w1", tage(5))], fenster(-30, 30))
    store.sync_source(Z, "a", [make_event("a1", tage(5))], fenster(-30, 30))
    assert uids("W25a") == {"w1"}


def test_gleiche_uid_in_zwei_zenturien(db):
    store.ensure_zenturie(Z)
    store.ensure_zenturie("A25b")
    store.sync_source(Z, "a", [make_event("x", tage(5))], fenster(-30, 30))
    store.sync_source("A25b", "b", [make_event("x", tage(5))], fenster(-30, 30))
    assert uids(Z) == uids("A25b") == {"x"}


def test_version_nur_bei_aenderungen(db):
    store.ensure_zenturie(Z)
    store.sync_source(Z, "url", [make_event("a", tage(5))], fenster(-30, 30))
    v = version()
    # neuer Export mit anderem DTSTAMP, sonst gleich: keine Änderung
    ev = make_event("a", tage(5))
    ev.pop("dtstamp")
    ev.add("dtstamp", tage(1))
    assert store.sync_source(Z, "url", [ev], fenster(-30, 30)) == 0
    assert version() == v
    # Raumänderung: neue Version
    ev2 = make_event("a", tage(5))
    ev2["location"] = "A105"
    assert store.sync_source(Z, "url", [ev2], fenster(-30, 30)) == 1
    assert version() == v + 1


def test_quellen_werden_vermerkt(db):
    store.ensure_zenturie(Z)
    store.sync_source(Z, "u3", [make_event("a", tage(5))], fenster(-30, 30), "Fri, 20 Nov 2026 10:17:25 GMT")
    store.mark_source("u4", Z, 404)
    rows = dict(((u, (s, lm)) for u, s, lm in store.connect().execute(
        "SELECT url, status, last_modified FROM quellen")))
    assert rows == {"u3": (200, "Fri, 20 Nov 2026 10:17:25 GMT"), "u4": (404, None)}


def test_import_ueberschreibt_nur_mit_flag(db):
    store.ensure_zenturie(Z)
    assert store.import_events(Z, [make_event("a", tage(-5))]) == (1, 0, 0)
    ev = make_event("a", tage(-5), veranstaltung="V A206 Formale Grundlagen")
    assert store.import_events(Z, [ev]) == (0, 0, 1)
    assert store.import_events(Z, [ev], overwrite=True) == (0, 1, 0)
    assert store.connect().execute("SELECT module_key FROM events").fetchone()[0] == "A206"


def test_list_module(db):
    store.ensure_zenturie(Z)
    events = [
        make_event("v1", tage(-10)), make_event("v2", tage(5)),
        make_event("l1", tage(3), veranstaltung="L W213 Labor", anmerkung="Gruppe 2"),
        make_event("l2", tage(4), veranstaltung="L W213 Labor", anmerkung="Gruppe 10"),
        make_event("l3", tage(4), veranstaltung="L W213 Labor", anmerkung="Gruppe 1"),
        make_event("s1", tage(-20), veranstaltung="S Spanisch B1+"),
    ]
    store.sync_source(Z, "url", events, fenster(-30, 30))
    module = {m["key"]: m for m in store.list_module(Z)}
    assert module["A205"]["anzahl"] == 2 and module["A205"]["anzahl_zukuenftig"] == 1
    assert module["W213"]["gruppen"] == ["1", "2", "10"]
    assert module["W213"]["typ_name"] == "Labor"
    assert module["spanisch-b1"]["anzahl_zukuenftig"] == 0
    # aktuelle Module zuerst (Vorlesung vor Labor), Archiv am Ende
    assert [m["key"] for m in store.list_module(Z)] == ["A205", "W213", "spanisch-b1"]


def test_list_zenturien_nur_mit_terminen(db):
    store.ensure_zenturie(Z)
    store.ensure_zenturie("B24a")
    store.sync_source(Z, "url", [make_event("a", tage(5))], fenster(-30, 30))
    assert [z["code"] for z in store.list_zenturien()] == [Z, "B24a"]
    assert [z["code"] for z in store.list_zenturien(nur_mit_terminen=True)] == [Z]


# --- Migration der alten Ein-Zenturien-Tabelle ------------------------------------

def _alte_db(pfad, events):
    """DB im Format des alten archive.py: events(uid, dtstart, ical), bereinigte Titel."""
    conn = sqlite3.connect(pfad)
    conn.execute("CREATE TABLE events (uid TEXT PRIMARY KEY, dtstart TEXT NOT NULL, ical BLOB NOT NULL)")
    for ev in events:
        conn.execute("INSERT INTO events VALUES (?, ?, ?)",
                     (str(ev["uid"]), store.to_utc_iso(ev.decoded("dtstart")), ev.to_ical()))
    conn.commit()
    conn.close()


def test_migration(tmp_path, monkeypatch):
    pfad = tmp_path / "alt.db"
    alt = make_event("alt", tage(-30), veranstaltung="V S011 Digitale GeschÃ¤ftsprozesse")
    alt["summary"] = "Digitale GeschÃ¤ftsprozesse"  # vom alten Proxy schon gekürzt
    bahn = make_event("bahn", tage(-3))
    bahn["description"] = "ICE 123 nach Hamburg"
    zukunft = make_event("zukunft", tage(10))
    _alte_db(pfad, [alt, bahn, zukunft])

    monkeypatch.setattr(store, "ARCHIVE_PATH", str(pfad))
    store.init()
    conn = store.connect()
    tabellen = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "events_legacy_migriert" in tabellen and "events_legacy" not in tabellen
    assert uids() == {"alt", "zukunft"}  # fremder Termin bleibt draußen
    assert conn.execute("SELECT module_key, titel FROM events WHERE uid='alt'").fetchone() == (
        "S011", "Digitale Geschäftsprozesse")
    assert conn.execute("SELECT count(*) FROM events_legacy_migriert").fetchone()[0] == 3

    # Poller sagt den zukünftigen Termin ab; ein Neustart darf ihn nicht zurückholen
    store.sync_source(Z, "url", [make_event("neu", tage(11))], fenster(-30, 30))
    store.init()
    assert uids() == {"alt", "neu"}
    conn.close()
    store._local.conn = None
