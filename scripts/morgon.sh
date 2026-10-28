#!/usr/bin/env bash
# Morgonkörningen: hämta → bygg → två brev. Startas av Windows Task Scheduler
# (Selvra morgon, 07:00, väcker datorn; kör ikapp om den var av). En markörfil
# gör en andra start samma dag till en no-op — ingen får två brev.
export PATH="/home/kari/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd /home/kari/selvra-analysis
mkdir -p data/rapporter
MARKOR=data/rapporter/morgon.datum
[ -f "$MARKOR" ] && [ "$(cat "$MARKOR")" = "$(date +%F)" ] && exit 0
{
  echo "=== morgon $(date '+%F %H:%M') ==="
  /usr/bin/make loop || echo "loop misslyckades ($?)"
  uv run python -m selvra_analysis.morgonpush skicka carl || echo "push carl misslyckades ($?)"
  uv run python -m selvra_analysis.morgonpush skicka testare-1 || echo "push testare-1 misslyckades ($?)"
  bash scripts/backup.sh || echo "backup misslyckades ($?)"
  date +%F > "$MARKOR"
} >> data/rapporter/morgon.log 2>&1
