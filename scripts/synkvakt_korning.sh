#!/usr/bin/env bash
# Synkvakten för ALLA vaktbara personer (garmin-nyckel + kopplad telefon).
# Startad av Windows Task Scheduler (12/17/21, kör ikapp vid sömn).
# Vakten har egen en-påminnelse-per-dag-spärr, så ikappkörningar är ofarliga.
export PATH="/home/kari/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd /home/kari/selvra-analysis
uv run python -m selvra_analysis.synkvakt >> data/rapporter/synkvakt.log 2>&1
