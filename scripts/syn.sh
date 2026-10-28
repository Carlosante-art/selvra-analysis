#!/usr/bin/env bash
# Visuell regression: rendera morgonvyn och selvra.ai i mobil- och desktopbredd.
# Layoutbrott ska upptäckas av Claude i data/syn/ innan de upptäcks av en människa
# på sin telefon. Kör efter varje ändring som rör HTML/CSS: make syn.
set -euo pipefail
cd "$(dirname "$0")/.."

PW=/tmp/node_modules/.bin/playwright
if [ ! -x "$PW" ]; then
  echo "playwright saknas i /tmp/node_modules — kör: npm i --prefix /tmp playwright" >&2
  exit 1
fi

mkdir -p data/syn
skott() { # url, namn, bredd, höjd
  "$PW" screenshot --browser=chromium --viewport-size="$3,$4" --full-page "$1" "data/syn/$2.png" \
    && echo "data/syn/$2.png"
}

[ -f dashboard/index.html ] && {
  skott "file://$PWD/dashboard/index.html" morgonvy-mobil 390 844
  skott "file://$PWD/dashboard/index.html" morgonvy-desktop 1280 900
}
skott "https://selvra.ai" sajt-mobil 390 844
skott "https://selvra.ai" sajt-desktop 1280 900
skott "https://selvra.ai/studier.html" studier-mobil 390 844
