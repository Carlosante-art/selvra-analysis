#!/usr/bin/env bash
# Synkvakten, startad av Windows Task Scheduler (12/17/21, kör ikapp vid sömn).
# Vakten har egen en-påminnelse-per-dag-spärr, så ikappkörningar är ofarliga.
export PATH="/home/kari/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd /home/kari/selvra-analysis
uv run python -m selvra_analysis.synkvakt testare-1 >> data/personer/testare-1/synkvakt.log 2>&1
