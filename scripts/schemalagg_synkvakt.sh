#!/usr/bin/env bash
# Synkvakten för en person, tre gånger om dagen (12, 17, 21).
# Användning: scripts/schemalagg_synkvakt.sh PERSON
set -euo pipefail
PERSON="${1:?ange person, t.ex. testare-1}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOGG="$REPO/data/personer/$PERSON/synkvakt.log"
RAD="0 12,17,21 * * * cd $REPO && uv run python -m selvra_analysis.synkvakt $PERSON >> $LOGG 2>&1"
if crontab -l 2>/dev/null | grep -qF "synkvakt $PERSON"; then
  echo "synkvakt för $PERSON finns redan i crontab"; exit 0
fi
(crontab -l 2>/dev/null || true; echo "$RAD") | crontab -
echo "Installerad: synkvakt för $PERSON kl 12, 17 och 21."
