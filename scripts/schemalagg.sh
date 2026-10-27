#!/usr/bin/env bash
# Installera en cron-rad som kör analysloopen varje morgon.
# Användning: scripts/schemalagg.sh [HH:MM]   (default 07:00)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TID="${1:-07:00}"
HH="${TID%%:*}"
MM="${TID##*:}"
RAD="$MM $HH * * * cd $REPO && /usr/bin/make loop >> $REPO/data/rapporter/cron.log 2>&1"

if crontab -l 2>/dev/null | grep -qF "make loop"; then
    echo "En loop-rad finns redan i crontab:"
    crontab -l | grep -F "make loop"
    echo "Ta bort den med 'crontab -e' om du vill byta tid."
    exit 0
fi

(crontab -l 2>/dev/null || true; echo "$RAD") | crontab -
echo "Installerad: loopen körs varje dag $TID."
echo "  $RAD"

if ! pgrep -x cron >/dev/null 2>&1; then
    echo ""
    echo "OBS: cron-tjänsten kör inte. Starta den:"
    echo "  sudo service cron start"
    echo "Och för att den ska starta med WSL, lägg i /etc/wsl.conf:"
    echo "  [boot]"
    echo "  command=\"service cron start\""
fi
