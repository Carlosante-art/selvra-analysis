#!/usr/bin/env bash
# Installera en cron-rad som skickar en persons morgonmejl varje dag.
# Användning: scripts/schemalagg_morgonpush.sh PERSON [HH:MM]   (default 07:00)
set -euo pipefail

PERSON="${1:?ange person, t.ex. testare-1}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
TID="${2:-07:00}"
HH="${TID%%:*}"
MM="${TID##*:}"
UV="$(command -v uv)"
LOGG="$REPO/data/personer/$PERSON/morgonpush.log"
RAD="$MM $HH * * * cd $REPO && $UV run python -m selvra_analysis.morgonpush skicka $PERSON >> $LOGG 2>&1"

if crontab -l 2>/dev/null | grep -qF "morgonpush skicka $PERSON"; then
    echo "Det finns redan en rad för $PERSON:"
    crontab -l | grep -F "morgonpush skicka $PERSON"
    exit 0
fi
(crontab -l 2>/dev/null || true; echo "$RAD") | crontab -
echo "Installerad: morgonnotis till $PERSON varje dag $TID."
if ! pgrep -x cron >/dev/null 2>&1; then
    echo "OBS: cron körs inte. Starta: sudo service cron start"
fi
