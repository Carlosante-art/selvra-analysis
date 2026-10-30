#!/usr/bin/env bash
# Sätter SELVRA_BACKUP_LOSEN i .env. Frasen skrivs dold, hamnar aldrig i
# terminalhistoriken. Kör i en vanlig WSL-terminal (inte via Claude Code).
set -euo pipefail
cd "$(dirname "$0")/.."
if grep -q '^SELVRA_BACKUP_LOSEN=' .env 2>/dev/null; then
    echo "SELVRA_BACKUP_LOSEN finns redan i .env — inget gjort."; exit 0
fi
read -rsp "Lösenfras (syns inte): " F; echo
[ -n "$F" ] || { echo "tom fras — avbryter"; exit 1; }
printf 'SELVRA_BACKUP_LOSEN=%s\n' "$F" >> .env
unset F
echo "Klart. Rader med frasen: $(grep -c '^SELVRA_BACKUP_LOSEN=' .env)"
