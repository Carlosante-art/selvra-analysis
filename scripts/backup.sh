#!/usr/bin/env bash
# Krypterad backup av det oersättliga: händelseloggar, personmappar (domar,
# studiehistorik, telefonkopplingar, tokens), push-nyckeln och .env.
# Duckdb-filerna tas INTE med — de är cache som `make build-live` återskapar.
#
# Kräver SELVRA_BACKUP_LOSEN i .env (sätts av Carl, aldrig i chatt/git).
# Arkivet AES-256-krypteras; utan lösenfrasen är backupen oläslig — förlorad
# lösenfras = förlorad backup, så den ska även ligga i Carls lösenordshanterare.
#
# Återställning:
#   SELVRA_BACKUP_LOSEN=... openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
#     -pass env:SELVRA_BACKUP_LOSEN -in selvra-backup-DATUM.tar.gz.enc | tar xzf - -C ~/selvra-analysis
#
# Varje körning verifierar arkivet (dekryptera + lista) innan gamla rensas.
set -euo pipefail
cd "$(dirname "$0")/.."

DEST="${SELVRA_BACKUP_DIR:-/mnt/c/Users/karik/SelvraBackup}"
BEHALL=14

SELVRA_BACKUP_LOSEN="$(grep -s '^SELVRA_BACKUP_LOSEN=' .env | head -1 | cut -d= -f2- | sed "s/^[\"']//; s/[\"']\$//" || true)"
if [ -z "$SELVRA_BACKUP_LOSEN" ]; then
    echo "backup: SELVRA_BACKUP_LOSEN saknas i .env — ingen backup tagen" >&2
    exit 1
fi
export SELVRA_BACKUP_LOSEN

mkdir -p "$DEST"
UT="$DEST/selvra-backup-$(date +%F).tar.gz.enc"

tar czf - \
    --exclude='*.duckdb' --exclude='*.log' \
    data/raw data/personer data/push data/snapshots .env \
    | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
        -pass env:SELVRA_BACKUP_LOSEN -out "$UT"

# Verifiera att arkivet går att dekryptera och läsa — en backup som inte
# provats är en förhoppning, inte en backup.
ANTAL=$(openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -pass env:SELVRA_BACKUP_LOSEN -in "$UT" | tar tzf - | wc -l)
[ "$ANTAL" -ge 10 ] || { echo "backup: verifiering misslyckades ($ANTAL filer)" >&2; exit 1; }

ls -1t "$DEST"/selvra-backup-*.tar.gz.enc 2>/dev/null | tail -n +$((BEHALL + 1)) | xargs -r rm --
echo "backup: $UT ($ANTAL filer, $(du -h "$UT" | cut -f1)) verifierad"
