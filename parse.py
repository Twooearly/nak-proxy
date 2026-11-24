"""Zerlegt NAK-Termine (sked.de-Export) in Modul, Titel, Gruppe usw.

Alle Regeln lesen bevorzugt die DESCRIPTION-Zeilen ("Veranstaltung:", "Anmerkung:"), weil die
auch in alten, schon bereinigten Archiv-Einträgen noch unverändert enthalten sind.
"""
import re
import unicodedata

from icalendar import Calendar

# "V A205 Algorithmen und Datenstrukturen", "WP WP040 Arbeitsrecht", "S Spanisch B1+", "Z Zenturienbetreuung"
_VERANSTALTUNG = re.compile(r"^(?P<typ>[A-Z]{1,2})\s+(?:(?P<code>[A-Z]{1,2}\d{2,4}[a-z]?)\s+)?(?P<name>\S.*)$")

TYPEN = {
    "V": "Vorlesung",
    "L": "Labor",
    "WP": "Wahlpflicht",
    "S": "Sprache",
    "Z": "Zenturie",
    "I": "Information",
}

KEY_RE = re.compile(r"^[A-Za-z0-9-]{1,60}$")


def decode_ics(data: bytes) -> Calendar:
    """sked.de liefert UTF-8 (ohne BOM); ältere Dateien evtl. windows-1252."""
    for enc in ("utf-8-sig", "windows-1252"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return Calendar.from_ical(text.encode("utf-8"))


def repair_mojibake(text: str) -> str:
    """Repariert UTF-8, das fälschlich als windows-1252 gelesen wurde ("GeschÃ¤ft" -> "Geschäft").

    Der alte Proxy hat so dekodiert, deshalb enthalten Archiv-Einträge solche Fehler.
    Korrekte Texte bleiben unverändert, weil sie sich nicht zurückkodieren lassen.
    """
    if not re.search(r"[ÃÂâ]", text):
        return text
    try:
        return text.encode("windows-1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _desc_field(event, name):
    m = re.search(rf"^\s*{name}:\s*(.*?)\s*$", str(event.get("description", "")), re.MULTILINE)
    if not m or m.group(1) in ("", "-"):
        return None
    return m.group(1)


def is_nak_event(event):
    """Echter NAK-Termin (sked.de): Beschreibung enthält eine "Veranstaltung:"-Zeile."""
    return _desc_field(event, "Veranstaltung") is not None


def veranstaltung(event):
    """(typ, code, name) aus der Veranstaltung-Zeile, sonst aus der Summary."""
    raw = _desc_field(event, "Veranstaltung")
    if raw is None:
        raw = str(event.get("summary", "")).split(",", 1)[0].strip()
    m = _VERANSTALTUNG.match(raw)
    if not m:
        return None, None, raw.strip()
    return m.group("typ"), m.group("code"), m.group("name").strip()


def slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "sonstiges"


def module_key(event):
    """Stabiler Schlüssel fürs Filtern: Kurscode (A205) oder Slug des Namens (spanisch-b1)."""
    _typ, code, name = veranstaltung(event)
    return code or slug(name)


def gruppe(event):
    """Laborgruppe aus "Anmerkung: Gruppe 2" -> "2", sonst None."""
    m = re.match(r"(?i)gruppe\s*(\w+)", _desc_field(event, "Anmerkung") or "")
    return m.group(1) if m else None


def is_online(event):
    for field in ("Anmerkung", "Status"):
        if re.search(r"\bonline", _desc_field(event, field) or "", re.IGNORECASE):
            return True
    return False


def display_title(event):
    """Gekürzter Titel: ohne Typ, Kurscode, Dozent und Raum, ggf. mit "(online)"/"(Gruppe n)"."""
    _typ, _code, title = veranstaltung(event)
    if is_online(event) and not re.search(r"\bonline\b", title, re.IGNORECASE):
        title += " (online)"
    g = gruppe(event)
    if g:
        title += f" (Gruppe {g})"
    return title
