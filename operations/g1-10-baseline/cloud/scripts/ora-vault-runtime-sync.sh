#!/usr/bin/env bash
# Assemble the vault-synced lens registry into the Ora runtime dir.
# WHY: ~/ora/knowledge/ is .gitignored, so ora-deploy.sh (git pull) never
# carries the mental-model lenses; the vault-sync agent only lands them in
# ~/ora/vault-sync/Lenses. boot._load_mental_models reads ~/ora/knowledge/
# mental-models, which was never assembled on this host -> the entire lens
# layer (ANALYTICAL PERSPECTIVES) was silently inert. This bridges them.
# Runs on cron; guarded so a broken vault-sync can never wipe the registry.
set -euo pipefail
SRC="$HOME/ora/vault-sync/Lenses"
DST="$HOME/ora/knowledge/mental-models"
LOG="$HOME/ora-vault-runtime-sync.log"
exec >>"$LOG" 2>&1
n=$(find "$SRC" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l)
if [ "$n" -lt 100 ]; then
  echo "[$(date -Iseconds)] ABORT: source has $n lens files (<100); refusing to sync (guards against a broken vault-sync wiping the registry)"
  exit 0
fi
mkdir -p "$DST"
rsync -a --delete --include="*.md" --exclude="*" "$SRC"/ "$DST"/
echo "[$(date -Iseconds)] synced $n lenses $SRC -> $DST"

# --- modes bridge (added 2026-06-01) ---------------------------------------
# WHY: ~/ora/modes/ is the dir boot.load_mode (MODES_DIR) reads. New Ora modes
# authored in the vault land in ~/ora/vault-sync/Modes via the vault-sync agent,
# but nothing promoted them into the runtime modes/ dir (the lens bridge above
# only covers Lenses) -> e.g. market-dynamics / mechanism-design were selected
# by MSI routing then dropped at load (empty mode text). This bridges them.
# ADDITIVE + INDEX-preserving: no --delete (modes/ holds a generated INDEX.md
# and may hold files a mirror would destroy); INDEX.md excluded so the runtime
# index is never clobbered; -u so a newer runtime file is never overwritten.
# New/updated mode specs are promoted; rare removals are left to git/ora-deploy.
MSRC="$HOME/ora/vault-sync/Modes"
MDST="$HOME/ora/modes"
mn=$(find "$MSRC" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l)
if [ "$mn" -lt 40 ]; then
  echo "[$(date -Iseconds)] [modes] ABORT: source has $mn mode files (<40); refusing to sync"
else
  mkdir -p "$MDST"
  rsync -au --exclude="INDEX.md" --include="*.md" --exclude="*" "$MSRC"/ "$MDST"/
  echo "[$(date -Iseconds)] [modes] synced from $mn-file source $MSRC -> $MDST (additive, INDEX preserved)"
fi
