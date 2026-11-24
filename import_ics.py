#!/usr/bin/env python3
"""Importiert alte .ics-Dateien ins Archiv.

Roh-Exporte der NAK (sked.de) werden durch clean_event() geschickt, bereits vom Proxy bereinigte
Dateien und fremde Kalender (z.B. Bahn) werden unverändert übernommen. Es wird nie etwas gelöscht;
bestehende Archiv-Einträge bleiben unangetastet (außer mit --overwrite).

Beispiele:
  python import_ics.py --dry-run ~/Downloads/stundenplan.ics
  python import_ics.py ~/alte-kalender/            # Ordner, rekursiv
  docker compose run --rm -v "$PWD/alt:/in:ro" calendar-proxy python import_ics.py /in
"""
import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from icalendar import Calendar

import archive
from main import clean_event


def read_calendar(path):
    data = path.read_bytes()
    for enc in ("utf-8-sig", "windows-1252"):
        try:
            return Calendar.from_ical(data.decode(enc).encode("utf-8"))
        except UnicodeDecodeError:
            continue
    raise ValueError("Kodierung nicht lesbar")


def is_raw_nak(event):
    """Roh-NAK-Event: Summary entspricht noch der 'Veranstaltung:'-Zeile der Beschreibung."""
    m = re.search(r"^Veranstaltung:\s*(.+?)\s*$", str(event.get("description", "")), re.MULTILINE)
    if not m:
        return False
    first = lambda t: t.split(",", 1)[0].strip()
    return first(str(event.get("summary", ""))) == first(m.group(1))


def ensure_uid(event):
    if event.get("uid"):
        return
    key = f"{event.get('summary','')}|{event.get('dtstart').to_ical() if event.get('dtstart') else ''}"
    event.add("uid", "import-" + hashlib.sha1(key.encode()).hexdigest()[:16])


def collect_files(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += [f for f in p.rglob("*") if f.suffix.lower() == ".ics"]
        elif p.is_file():
            files.append(p)
        else:
            print(f"! nicht gefunden: {p}", file=sys.stderr)
    # neueste zuerst: bei gleicher UID gewinnt die aktuellere Datei
    return sorted(set(files), key=lambda f: f.stat().st_mtime, reverse=True)


def main_cli():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help=".ics-Dateien oder Ordner")
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts schreiben")
    ap.add_argument("--overwrite", action="store_true", help="bestehende Archiv-Einträge ersetzen")
    ap.add_argument("--include-future", action="store_true", help="auch zukünftige Termine importieren (werden vom Proxy bei Nichtvorkommen upstream wieder entfernt)")
    ap.add_argument("--db", help="Archiv-Pfad (Default: ARCHIVE_PATH bzw. archive.db)")
    args = ap.parse_args()
    if args.db:
        archive.ARCHIVE_PATH = args.db

    now = datetime.now(timezone.utc).isoformat()
    seen, to_import = set(), []
    stats = dict(raw=0, as_is=0, filtered=0, future=0, dup=0, broken=0)

    for f in collect_files(args.paths):
        try:
            cal = read_calendar(f)
        except Exception as e:
            print(f"! {f}: {e}", file=sys.stderr)
            continue
        n_before = len(to_import)
        for ev in cal.walk("VEVENT"):
            try:
                if not ev.get("dtstart"):
                    raise ValueError("kein DTSTART")
                if is_raw_nak(ev):
                    ev = clean_event(ev)
                    stats["raw"] += 1
                    if ev is None:
                        stats["filtered"] += 1
                        continue
                else:
                    stats["as_is"] += 1
                ensure_uid(ev)
                if not args.include_future and archive._start_utc(ev) >= now:
                    stats["future"] += 1
                    continue
                uid = str(ev["uid"])
                if uid in seen:
                    stats["dup"] += 1
                    continue
                seen.add(uid)
                to_import.append(ev)
            except Exception as e:
                stats["broken"] += 1
                print(f"! {f.name}: Event übersprungen ({e})", file=sys.stderr)
        print(f"{f.name}: {len(to_import) - n_before} Events")

    print(f"\nRoh-NAK bereinigt: {stats['raw']}, unverändert: {stats['as_is']}, durch Filter entfernt: {stats['filtered']}, "
          f"zukünftig übersprungen: {stats['future']}, Duplikate: {stats['dup']}, defekt: {stats['broken']}")
    if args.dry_run:
        print(f"[dry-run] {len(to_import)} Events würden ins Archiv geschrieben.")
        return
    added, updated, skipped = archive.import_events(to_import, overwrite=args.overwrite)
    print(f"Archiv ({archive.ARCHIVE_PATH}): {added} neu, {updated} aktualisiert, {skipped} bereits vorhanden.")


if __name__ == "__main__":
    main_cli()
