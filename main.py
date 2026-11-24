from flask import Flask, Response
import requests
import os
import re
from datetime import date
from icalendar import Calendar, Timezone
from archive import merge_with_archive

app = Flask(__name__)

STUNDENPLAN_BASE = "https://cis.nordakademie.de/fileadmin/Infos/Stundenplaene"
ZENTURIE = os.environ.get("ZENTURIE", "A25a")
# Startjahr aus der Zenturie (A25a -> 2025), überschreibbar
START_JAHR = int(os.environ.get("START_JAHR", 2000 + int(re.search(r"\d{2}", ZENTURIE).group())))


def current_semester(today=None):
    """Semester (1-basiert) seit Studienstart; Studium beginnt im August (Quartal III)."""
    today = today or date.today()
    return 2 * (today.year - START_JAHR) + (1 if today.month >= 7 else 0)


def candidate_urls(today=None):
    """Berechnetes Semester zuerst, dann Nachbarn als Fallback (Wechsel-Zeitraum)."""
    sem = current_semester(today)
    return [f"{STUNDENPLAN_BASE}/{ZENTURIE}_{n}.ics" for n in (sem, sem + 1, sem - 1) if n >= 1]


def fetch_upstream():
    """Erste erreichbare Kandidaten-URL; None, wenn keine antwortet."""
    for url in candidate_urls():
        try:
            response = requests.get(url, timeout=15)
        except requests.RequestException:
            continue
        if response.status_code == 200:
            response.encoding = 'windows-1252'
            return Calendar.from_ical(response.text.encode('utf-8'))
    return None

# --- HELFER FUNKTION ---
def clean_event(event):
    """
    Nimmt ein Event entgegen, manipuliert es und gibt es zurück.
    Gibt None zurück, wenn das Event gelöscht werden soll.
    """
    summary = str(event.get('summary', ''))
    description = str(event.get('description', ''))

    if "Spanisch" in summary:
        return None

    # andere Englischkurse filtern
    # if "Pirie" in description or "Bulloch" in description:
    #     return None
    
    # # zweite Laborgruppe
    # if "Gruppe 2" in description:
    #     return None

    if ',' in summary:
        summary = summary.split(',', 1)[0].strip()
    parts = summary.split(' ', 2)
    if len(parts) >= 3:
        cleaned_summary = parts[2].strip()
    else:
        cleaned_summary = summary.strip()

    # Remove leading one-letter markers like "Z Zenturienbetreuung" -> "Zenturienbetreuung"
    cleaned_summary = re.sub(r'^[A-Z]\s+(?=\S)', '', cleaned_summary)

    # If description contains an explicit online note line, mark title as online.
    has_online_note = re.search(r'^\s*Anmerkung:\s*.*\bonline\b.*$', description, flags=re.IGNORECASE | re.MULTILINE)
    if has_online_note and not re.search(r'\bonline\b', cleaned_summary, flags=re.IGNORECASE):
        cleaned_summary = f"{cleaned_summary} (online)"

    event['summary'] = cleaned_summary

    return event

@app.route('/stundenplan.ics')
def get_stundenplan():
    try:
        cal = fetch_upstream()
        new_cal = Calendar()
        events = []

        if cal is not None:
            for key, value in cal.items():
                new_cal.add(key, value)
            for component in cal.walk():
                if component.name == "VTIMEZONE":
                    new_cal.add_component(component)
                elif component.name == "VEVENT":
                    processed_event = clean_event(component)
                    if processed_event:
                        events.append(processed_event)
        else:
            # Upstream nicht erreichbar: nur Archiv ausliefern
            new_cal.add('prodid', '-//calendar-proxy//EN')
            new_cal.add('version', '2.0')
            new_cal.add_component(Timezone.from_tzid('Europe/Berlin'))

        for event in merge_with_archive(events):
            new_cal.add_component(event)

        return Response(new_cal.to_ical(), mimetype='text/calendar')

    except Exception as e:
        return Response(f"Server Error: {str(e)}", status=500)


@app.get("/healthz")
def health():
    return "ok"


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'dev'
    app.run(debug=debug, port=port, host='0.0.0.0')
