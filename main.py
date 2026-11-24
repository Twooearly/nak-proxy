"""Öffentlicher NAK-Stundenplan: Auswahlseite, JSON-API und gefilterte Kalender-Abos.

Web-Requests lesen nur aus SQLite. Die NAK wird ausschließlich vom Poller abgerufen (poller.py),
deshalb kann kein Aufruf von außen Requests an die NAK auslösen.
"""
import hashlib
import logging
import os
import re

from flask import Flask, Response, abort, jsonify, request, send_from_directory

import poller
import render
import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("nak-proxy")

STATIC_DIR = os.path.abspath(os.getenv("STATIC_DIR", "frontend/build"))
GRUPPE_RE = re.compile(r"^[A-Za-z0-9]{1,10}$")
MAX_KEYS = 200

app = Flask(__name__, static_folder=None)
app.json.ensure_ascii = False
app.json.sort_keys = False

store.init()
poller.start()


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


@app.errorhandler(Exception)
def server_error(e):
    if hasattr(e, "code") and hasattr(e, "get_response"):  # HTTP-Fehler (404 usw.) durchreichen
        return e
    log.exception("Fehler bei %s", request.path)
    return Response("Interner Fehler", status=500, mimetype="text/plain")


def _zenturie_or_404(code):
    if not store.ZENTURIE_RE.match(code):
        abort(404)
    z = store.zenturie(code)
    if z is None:
        abort(404)
    return z


def parse_key(key):
    return bool(re.fullmatch(r"[A-Za-z0-9-]{1,60}", key))


def _split(param):
    values = [v for v in request.args.get(param, "").split(",") if v]
    if len(values) > MAX_KEYS:
        abort(400, "Zu viele Werte")
    return values


def _cached(resp, max_age):
    resp.headers["Cache-Control"] = f"public, max-age={max_age}"
    return resp


# --- Kalender -------------------------------------------------------------

def _ics_response(code, ohne, gruppen):
    z = _zenturie_or_404(code)
    # Unbekannte Schlüssel verwerfen: gleiche Wirkung = gleicher Cache-Eintrag und gleiches ETag,
    # zufällige Parameter können so den Cache nicht verdrängen
    keys = render.module_keys(code, z["version"])
    ohne = frozenset(ohne) & keys
    gruppen = tuple(sorted((k, g) for k, g in gruppen.items() if k in keys and k not in ohne))
    etag = hashlib.sha256(repr((code, z["version"], sorted(ohne), gruppen)).encode()).hexdigest()[:32]
    if request.if_none_match.contains(etag):
        return _cached(Response(status=304, headers={"ETag": f'"{etag}"'}), 900)
    body = render.render(code, z["version"], ohne, gruppen)
    resp = Response(body, mimetype="text/calendar")
    resp.headers["Content-Disposition"] = f'inline; filename="{code}.ics"'
    resp.set_etag(etag)
    return _cached(resp, 900)


@app.get("/z/<code>.ics")
def kalender(code):
    """Abo-Feed. ?ohne=A205,spanisch-b1 blendet Module aus, ?gruppe=W213.2 wählt die Laborgruppe."""
    ohne = [k for k in _split("ohne") if parse_key(k)]
    gruppen = {}
    for item in _split("gruppe"):
        key, _, g = item.partition(".")
        if parse_key(key) and GRUPPE_RE.match(g):
            gruppen[key] = g
    return _ics_response(code, ohne, gruppen)


# --- API für die Auswahlseite ----------------------------------------------

@app.get("/api/zenturien")
def api_zenturien():
    return _cached(jsonify(store.list_zenturien(nur_mit_terminen=True)), 300)


@app.get("/api/zenturien/<code>/module")
def api_module(code):
    _zenturie_or_404(code)
    return _cached(jsonify(store.list_module(code)), 300)


@app.get("/healthz")
def health():
    return "ok"


# --- Frontend (statischer SvelteKit-Build) ---------------------------------

@app.get("/")
@app.get("/<path:path>")
def frontend(path="index.html"):
    # .ics nie mit der HTML-Seite beantworten, sonst bekommen veraltete Abos 200 statt 404
    if path.startswith(("api/", "z/")) or path.endswith(".ics") or not os.path.isdir(STATIC_DIR):
        abort(404)
    if not os.path.isfile(os.path.join(STATIC_DIR, path)):
        path = "index.html"
    resp = send_from_directory(STATIC_DIR, path)
    if path.startswith("_app/immutable/"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "dev"
    app.run(debug=debug, port=port, host="0.0.0.0")
