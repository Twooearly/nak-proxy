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

def _wanted(module_key, gruppe, ohne, gruppen):
    if module_key in ohne:
        return False
    # Laborgruppe gewählt: Termine anderer Gruppen dieses Moduls ausblenden
    want = gruppen.get(module_key)
    return not (want and gruppe and gruppe != want)


@lru_cache(maxsize=256)
def module_keys(code, version):
    """Alle Modul-Schlüssel einer Zenturie (zum Kanonisieren der Filter)."""
    return frozenset(k for k, *_ in store.events_for(code))


@lru_cache(maxsize=512)
def render(code, version, ohne: frozenset, gruppen: tuple):
    """ICS-Bytes. `version` ist Teil des Cache-Keys und ändert sich bei jeder Datenänderung."""
    z = store.zenturie(code)
    gruppen = dict(gruppen)

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

    for module_key, gruppe, ical, updated_at in store.events_for(code):
        if not _wanted(module_key, gruppe, ohne, gruppen):
            continue
        ev = Event.from_ical(ical)
        title = parse.display_title(ev)
        ev.pop("summary", None)
        ev.add("summary", title)
        ev.pop("dtstamp", None)
        ev.add("dtstamp", store.parse_iso(updated_at))
        cal.add_component(ev)
    return cal.to_ical()
