#!/usr/bin/env python3
"""Importiert alte .ics-Dateien einer Zenturie ins Archiv.

Übernommen werden nur echte NAK-Termine (sked.de, mit "Veranstaltung:"-Zeile), egal ob roh oder
schon vom alten Proxy bereinigt. Fremde Kalender werden übersprungen, weil der Feed öffentlich ist.
Es wird nie etwas gelöscht; bestehende Archiv-Einträge bleiben unangetastet (außer mit --overwrite).

Beispiele:
  python import_ics.py --zenturie A25a --dry-run ~/Downloads/stundenplan.ics
  python import_ics.py --zenturie A25a ~/alte-kalender/            # Ordner, rekursiv
  docker compose run --rm -v "$PWD/alt:/in:ro" nak-proxy python import_ics.py --zenturie A25a /in
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import parse
import store


def read_calendar(path):
    cal = parse.decode_ics(path.read_bytes())
    for ev in cal.walk("VEVENT"):
        for key in ("summary", "description", "location"):
            if key in ev:
                ev[key] = type(ev[key])(parse.repair_mojibake(str(ev[key])))
    return cal


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
    ap.add_argument("--zenturie", required=True, help="Zenturie, z.B. A25a")
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts schreiben")
    ap.add_argument("--overwrite", action="store_true", help="bestehende Archiv-Einträge ersetzen")
    ap.add_argument("--include-future", action="store_true",
                    help="auch zukünftige Termine importieren (werden vom Poller bei Nichtvorkommen upstream wieder entfernt)")
    ap.add_argument("--db", help="Archiv-Pfad (Default: ARCHIVE_PATH bzw. archive.db)")
    args = ap.parse_args()
    if not store.ZENTURIE_RE.match(args.zenturie):
        ap.error("Zenturie muss die Form A25a haben")
    if args.db:
        store.ARCHIVE_PATH = args.db

    now = datetime.now(timezone.utc).isoformat()
    seen, to_import = set(), []
    stats = dict(nak=0, fremd=0, future=0, dup=0, broken=0)

    for f in collect_files(args.paths):
        try:
            cal = read_calendar(f)
        except Exception as e:
            print(f"! {f}: {e}", file=sys.stderr)
            continue
        n_before = len(to_import)
        for ev in cal.walk("VEVENT"):
            try:
                if not ev.get("dtstart") or not ev.get("uid"):
                    raise ValueError("kein DTSTART/UID")
                if not parse.is_nak_event(ev):
                    stats["fremd"] += 1
                    continue
                stats["nak"] += 1
                if not args.include_future and store.to_utc_iso(ev.decoded("dtstart")) >= now:
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

    print(f"\nNAK-Termine: {stats['nak']}, fremde übersprungen: {stats['fremd']}, "
          f"zukünftig übersprungen: {stats['future']}, Duplikate: {stats['dup']}, defekt: {stats['broken']}")
    if args.dry_run:
        print(f"[dry-run] {len(to_import)} Events würden ins Archiv von {args.zenturie} geschrieben.")
        return
    store.init()
    store.ensure_zenturie(args.zenturie)
    added, updated, skipped = store.import_events(args.zenturie, to_import, overwrite=args.overwrite)
    print(f"Archiv ({store.ARCHIVE_PATH}): {added} neu, {updated} aktualisiert, {skipped} bereits vorhanden.")


if __name__ == "__main__":
    main_cli()
