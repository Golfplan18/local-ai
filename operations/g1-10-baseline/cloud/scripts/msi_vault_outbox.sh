#!/usr/bin/env bash
# msi_vault_outbox.sh — mirror MSI published news articles into
# the cloud-outbox where the Mac-side sync pulls them into the vault.
# Server-side uses dir name `msi-news` (no space, rsync-safe); Mac
# destination is ~/Documents/vault/MSI News/ for Obsidian display.
set -euo pipefail
SRC=/home/oracle/sites/mainstreetindependent/src/content/articles/
DST=/home/oracle/cloud-outbox/msi-news/
if [ ! -d "$SRC" ] || [ -z "$(ls -A "$SRC" 2>/dev/null)" ]; then
  echo "$(date -u +%FT%TZ) msi_vault_outbox: src empty/missing — skip" \
    >> /home/oracle/msi-vault-outbox.log
  exit 0
fi
mkdir -p "$DST"
rsync -a --delete --exclude="_drafts/" "$SRC" "$DST"
echo "$(date -u +%FT%TZ) msi_vault_outbox: synced $(ls "$DST" | wc -l) articles" \
  >> /home/oracle/msi-vault-outbox.log
