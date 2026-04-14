from flask import Flask, Response
import requests
import os
from icalendar import Calendar, Event

app = Flask(__name__)
STUNDENPLAN_URL = "https://cis.nordakademie.de/fileadmin/Infos/Stundenplaene/A25a_2.ics"

# --- HELFER FUNKTION ---
def clean_event(event):
    """
    Nimmt ein Event entgegen, manipuliert es und gibt es zurück.
    Gibt None zurück, wenn das Event gelöscht werden soll.
    """
    summary = str(event.get('summary', ''))
    description = str(event.get('description', ''))

    # if "Französisch" in summary or "Spanisch" in summary:
    #     return None

    # andere Englischkurse filtern
    if "Pirie" in description or "Bulloch" in description:
        return None
    
    # # zweite Laborgruppe
    # if "Gruppe 2" in description:
    #     return None

    if ',' in summary:
        summary = summary.split(',', 1)[0].strip()
    parts = summary.split(' ', 2)
    if len(parts) >= 3:
        event['summary'] = parts[2].strip()
    else:
        event['summary'] = summary.strip()

    return event

@app.route('/stundenplan.ics')
def get_stundenplan():
    try:
        response = requests.get(STUNDENPLAN_URL)
        
        if response.status_code == 200:
            response.encoding = 'windows-1252'
            
            cal = Calendar.from_ical(response.text.encode('utf-8'))
            
            new_cal = Calendar()
            
            for key, value in cal.items():
                new_cal.add(key, value)
            
            for component in cal.walk():
                if component.name == "VTIMEZONE":
                    new_cal.add_component(component)
                
                elif component.name == "VEVENT":
                    processed_event = clean_event(component)
                    
                    if processed_event:
                        new_cal.add_component(processed_event)
            
            return Response(new_cal.to_ical(), mimetype='text/calendar')
        
        else:
            return Response(f"Failed to fetch: {response.status_code}", status=500)
            
    except Exception as e:
        return Response(f"Server Error: {str(e)}", status=500)



if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'dev'
    app.run(debug=debug, port=port, host='0.0.0.0')
