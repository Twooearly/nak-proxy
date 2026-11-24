#!/bin/sh
# Startet als root nur, um /data dem App-User zu geben (alte Volumes gehören root),
# und läuft dann ohne Root-Rechte weiter.
set -e
if [ "$(id -u)" = "0" ]; then
    chown -R app:app /data
    exec setpriv --reuid=app --regid=app --init-groups "$@"
fi
exec "$@"
