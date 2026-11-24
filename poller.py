"""Hintergrund-Thread: findet Zenturien und holt regelmäßig alle Stundenpläne.

Über einen Dateilock läuft der Poller nur in einem Prozess, auch wenn gunicorn mehrere Worker
startet oder der Flask-Reloader die App doppelt lädt.
"""
import fcntl
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import store
import upstream

log = logging.getLogger(__name__)

POLL_MINUTEN = int(os.getenv("POLL_MINUTEN", "30"))
DISCOVERY_STUNDEN = int(os.getenv("DISCOVERY_STUNDEN", "24"))

_lock_file = None


def _acquire_lock():
    global _lock_file
    path = os.path.join(os.path.dirname(os.path.abspath(store.ARCHIVE_PATH)), ".poller.lock")
    _lock_file = open(path, "w")
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        _lock_file.close()
        _lock_file = None
        return False


def poll_all(nur_neue=False):
    codes = [z["code"] for z in store.list_zenturien() if not (nur_neue and z["letzter_abruf"])]
    changed = 0
    for code in codes:
        try:
            changed += upstream.fetch_zenturie(code)
        except Exception:
            log.exception("Abruf von %s fehlgeschlagen", code)
    log.info("Abruf: %d Zenturien, %d Änderungen", len(codes), changed)


def _discovery_faellig():
    last = store.get_meta("letzte_discovery")
    if not last:
        return True
    age = datetime.now(timezone.utc) - store.parse_iso(last)
    return age >= timedelta(hours=DISCOVERY_STUNDEN)


def _loop():
    while True:
        started = time.monotonic()
        try:
            # Erst bekannte Zenturien aktualisieren, damit Neustarts den Abruf nicht verzögern
            poll_all()
            if _discovery_faellig():
                upstream.discover()
                store.set_meta("letzte_discovery", store.now_iso())
                poll_all(nur_neue=True)
        except Exception:
            log.exception("Poller-Durchlauf fehlgeschlagen")
        time.sleep(max(60.0, POLL_MINUTEN * 60 - (time.monotonic() - started)))


def start():
    """Startet den Poller, falls kein anderer Prozess ihn schon betreibt."""
    if os.getenv("POLLER", "1") == "0":
        log.info("Poller deaktiviert (POLLER=0)")
        return
    if not _acquire_lock():
        log.info("Poller läuft bereits in einem anderen Prozess")
        return
    threading.Thread(target=_loop, name="poller", daemon=True).start()
    log.info("Poller gestartet (alle %d min, Discovery alle %d h)", POLL_MINUTEN, DISCOVERY_STUNDEN)
