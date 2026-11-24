"""Baut den gefilterten iCalendar-Feed einer Zenturie."""
from datetime import timedelta
from functools import lru_cache

from icalendar import Calendar, Event, Timezone, vDuration

import parse
import store

# Kompakte Zeitzone mit RRULE (wie im NAK-Export), gilt unbegrenzt
BERLIN_TZ = Timezone.from_ical(
    "BEGIN:VTIMEZONE\r\nTZID:Europe/Berlin\r\n"
    "BEGIN:DAYLIGHT\r\nTZNAME:CEST\r\nDTSTART:19960101T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU\r\n"
    "TZOFFSETFROM:+0100\r\nTZOFFSETTO:+0200\r\nEND:DAYLIGHT\r\n"
    "BEGIN:STANDARD\r\nTZNAME:CET\r\nDTSTART:19960101T030000\r\nRRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU\r\n"
    "TZOFFSETFROM:+0200\r\nTZOFFSETTO:+0100\r\nEND:STANDARD\r\nEND:VTIMEZONE\r\n"
)

_ENDE = b"END:VCALENDAR\r\n"


def _wanted(module_key, gruppe, ohne, gruppen):
    if module_key in ohne:
        return False
    # Laborgruppe gewählt: Termine anderer Gruppen dieses Moduls ausblenden
    want = gruppen.get(module_key)
    return not (want and gruppe and gruppe != want)


def _kopf(code):
    """Kalender-Eigenschaften und Zeitzone, ohne abschließendes END:VCALENDAR."""
    z = store.zenturie(code)
    cal = Calendar()
    cal.add("prodid", "-//nak-stundenplan-proxy//DE")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    name = f"Stundenplan {code}"
    cal.add("x-wr-calname", name)
    cal.add("name", name)
    if z and z["studiengang"]:
        cal.add("x-wr-caldesc", f"{z['studiengang']} {code} (Nordakademie)")
    cal.add("x-wr-timezone", "Europe/Berlin")
    cal.add("refresh-interval", timedelta(hours=1), parameters={"VALUE": "DURATION"})
    cal["X-PUBLISHED-TTL"] = vDuration(timedelta(hours=1))
    cal.add_component(BERLIN_TZ)
    return cal.to_ical().removesuffix(_ENDE)


def _termin(ical, updated_at):
    """Ein archivierter Termin als fertige VEVENT-Bytes, mit Anzeige-Titel und DTSTAMP."""
    ev = Event.from_ical(ical)
    title = parse.display_title(ev)
    ev.pop("summary", None)
    ev.add("summary", title)
    ev.pop("dtstamp", None)
    ev.add("dtstamp", store.parse_iso(updated_at))
    return ev.to_ical()


@lru_cache(maxsize=64)
def _bausteine(code, version):
    """Kopf und alle Termine einer Zenturie, einmal pro Datenstand fertig serialisiert.

    Das Parsen und Serialisieren ist der teure Teil. So kostet jede weitere Filter-Kombination
    nur noch das Zusammensetzen, und zufällige Kombinationen können den Server nicht auslasten.
    """
    termine = tuple(
        (module_key, gruppe, _termin(ical, updated_at))
        for module_key, gruppe, ical, updated_at in store.events_for(code)
    )
    return _kopf(code), termine


def module_keys(code, version):
    """Alle Modul-Schlüssel einer Zenturie (zum Kanonisieren der Filter)."""
    return frozenset(k for k, _g, _b in _bausteine(code, version)[1])


@lru_cache(maxsize=128)
def render(code, version, ohne: frozenset, gruppen: tuple):
    """ICS-Bytes. `version` ist Teil des Cache-Keys und ändert sich bei jeder Datenänderung."""
    kopf, termine = _bausteine(code, version)
    gruppen = dict(gruppen)
    teile = [kopf]
    teile += (b for k, g, b in termine if _wanted(k, g, ohne, gruppen))
    teile.append(_ENDE)
    return b"".join(teile)
