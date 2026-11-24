"""HTTP-Routen (main.py) mit dem Flask-Testclient."""
import pytest
from icalendar import Calendar

import main
import store
from conftest import fenster, make_event, tage


@pytest.fixture
def client(db):
    store.ensure_zenturie("A25a", "Angewandte Informatik")
    store.ensure_zenturie("W25a", "Wirtschaftsingenieurwesen")
    store.ensure_zenturie("B24a")  # ohne Termine
    store.sync_source("A25a", "a", [
        make_event("algo", tage(2)),
        make_event("db", tage(3), veranstaltung="V A249 Datenbanksysteme", anmerkung="ONLINE"),
        make_event("spa", tage(4), veranstaltung="S Spanisch B1+"),
        make_event("spa2", tage(5), veranstaltung="S Spanisch A1.3"),
        make_event("vorbei", tage(-40)),
    ], fenster(-30, 30))
    store.sync_source("W25a", "w", [
        make_event(f"lab{g}", tage(2 + g), veranstaltung="L W213 MSR (Labor)", anmerkung=f"Gruppe {g}")
        for g in (1, 2, 3)
    ] + [make_event("thermo", tage(2), veranstaltung="V W207 Thermodynamik")], fenster(-30, 30))
    return main.app.test_client()


def titel(resp):
    return sorted(str(e["summary"]) for e in Calendar.from_ical(resp.data).walk("VEVENT"))


def test_healthz(client):
    assert client.get("/healthz").data == b"ok"


def test_api_zenturien(client):
    resp = client.get("/api/zenturien")
    assert resp.headers["Cache-Control"].startswith("public")
    codes = {z["code"]: z for z in resp.json}
    assert set(codes) == {"A25a", "W25a"}  # B24a ohne Termine fehlt
    assert codes["A25a"]["studiengang"] == "Angewandte Informatik"
    assert codes["A25a"]["jahrgang"] == 2025


def test_api_module(client):
    keys = [m["key"] for m in client.get("/api/zenturien/W25a/module").json]
    assert keys == ["W207", "W213"]
    assert client.get("/api/zenturien/X99z/module").status_code == 404
    assert client.get("/api/zenturien/kaputt/module").status_code == 404


def test_feed_komplett(client):
    resp = client.get("/z/A25a.ics")
    assert resp.status_code == 200
    assert resp.mimetype == "text/calendar"
    assert titel(resp) == ["Algorithmen und Datenstrukturen", "Algorithmen und Datenstrukturen",
                           "Datenbanksysteme (online)", "Spanisch A1.3", "Spanisch B1+"]
    cal = Calendar.from_ical(resp.data)
    assert str(cal["X-WR-CALNAME"]) == "Stundenplan A25a"
    assert all(e.get("dtstamp") for e in cal.walk("VEVENT"))
    assert len(cal.walk("VTIMEZONE")) == 1


def test_feed_ohne_module(client):
    resp = client.get("/z/A25a.ics?ohne=A205,spanisch-b1")
    assert titel(resp) == ["Datenbanksysteme (online)", "Spanisch A1.3"]


def test_feed_laborgruppe(client):
    resp = client.get("/z/W25a.ics?gruppe=W213.2")
    assert titel(resp) == ["MSR (Labor) (Gruppe 2)", "Thermodynamik"]


def test_unbekannte_parameter_landen_im_selben_cache(client):
    etags = {client.get(u).headers["ETag"] for u in (
        "/z/A25a.ics", "/z/A25a.ics?ohne=gibtsnicht", "/z/A25a.ics?ohne=x,y&gruppe=Q1.2",
        "/z/A25a.ics?gruppe=A205.<script>")}
    assert len(etags) == 1
    assert client.get("/z/A25a.ics?ohne=A205").headers["ETag"] not in etags


def test_etag_304_und_neue_version(client):
    resp = client.get("/z/A25a.ics")
    etag = resp.headers["ETag"]
    assert resp.headers["Cache-Control"] == "public, max-age=900"
    assert client.get("/z/A25a.ics", headers={"If-None-Match": etag}).status_code == 304
    # Datenänderung -> neue Version -> neues ETag und neuer Inhalt
    store.sync_source("A25a", "a", [make_event("algo", tage(2)), make_event("db", tage(3)),
                                    make_event("spa", tage(4), veranstaltung="S Spanisch B1+"),
                                    make_event("spa2", tage(5), veranstaltung="S Spanisch A1.3"),
                                    make_event("neu", tage(6))], fenster(-30, 30))
    resp2 = client.get("/z/A25a.ics", headers={"If-None-Match": etag})
    assert resp2.status_code == 200
    assert len(titel(resp2)) == 6


@pytest.mark.parametrize("url, status", [
    ("/z/X99z.ics", 404),
    ("/z/a25a.ics", 404),
    ("/z/A25.ics", 404),
    ("/z/..%2Fetc.ics", 404),
    ("/z/A25a.ics?ohne=" + ",".join(["x"] * 300), 400),
])
def test_ungueltige_anfragen(client, url, status):
    assert client.get(url).status_code == status


def test_legacy_stundenplan_ohne_spanisch(client):
    resp = client.get("/stundenplan.ics")
    assert resp.status_code == 200
    assert titel(resp) == ["Algorithmen und Datenstrukturen", "Algorithmen und Datenstrukturen",
                           "Datenbanksysteme (online)"]


def test_fehler_verraten_keine_details(client, monkeypatch):
    def kaputt(*a, **k):
        raise RuntimeError("geheimer Pfad /data/archive.db")
    monkeypatch.setattr(main.render, "render", kaputt)
    resp = client.get("/z/A25a.ics?ohne=A249")
    assert resp.status_code == 500
    assert b"geheim" not in resp.data


def test_sicherheitsheader(client):
    resp = client.get("/healthz")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_frontend(client, tmp_path, monkeypatch):
    static = tmp_path / "static"
    (static / "_app" / "immutable").mkdir(parents=True)
    (static / "index.html").write_text("<html>start</html>")
    (static / "_app" / "immutable" / "app.js").write_text("js")
    (tmp_path / "geheim.txt").write_text("geheim")
    monkeypatch.setattr(main, "STATIC_DIR", str(static))

    assert client.get("/").data == b"<html>start</html>"
    assert client.get("/irgendwas").data == b"<html>start</html>"  # SPA-Fallback
    js = client.get("/_app/immutable/app.js")
    assert "immutable" in js.headers["Cache-Control"]
    for url in ("/../geheim.txt", "/..%2fgeheim.txt", "/_app/../../geheim.txt"):
        assert b"geheim" not in client.get(url).data
    assert client.get("/api/gibtsnicht").status_code == 404
