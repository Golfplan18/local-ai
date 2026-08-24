#!/bin/bash
set -euo pipefail

# Explicit PULL-ONLY update command for the MSI image/asset disaster-recovery
# mirror. G1.10 retired the nightly LaunchAgent; this command is never scheduled.

ORA_ROOT="${ORA_HOME:-$HOME/ora}"
MIRROR_ROOT="$ORA_ROOT/data/msi-image-mirror"
DEST="$MIRROR_ROOT/public"
SRC="cloud-ora:sites/mainstreetindependent/public/"
LOG="$HOME/Library/Logs/msi-image-mirror.log"
LOCK="/tmp/msi-image-mirror.lock"
BWLIMIT_KBPS=5000

usage() {
  cat <<'EOF'
Usage: msi-image-mirror.sh --verify-local
       msi-image-mirror.sh pull

  --verify-local  Read and summarize the local recovery copy; makes no changes.
  pull            Add/update files from cloud-ora without deleting local files.
EOF
}

verify_local() {
  if [[ ! -d "$MIRROR_ROOT" || ! -d "$DEST" ]]; then
    echo "MSI image mirror is unavailable at $MIRROR_ROOT" >&2
    return 1
  fi

  local files directories logical_bytes symlinks last_success
  files="$(find "$MIRROR_ROOT" -type f | wc -l | tr -d ' ')"
  directories="$(find "$MIRROR_ROOT" -type d | wc -l | tr -d ' ')"
  logical_bytes="$(find "$MIRROR_ROOT" -type f -exec stat -f '%z' {} + | awk '{sum += $1} END {print sum + 0}')"
  symlinks="$(find "$MIRROR_ROOT" -type l | wc -l | tr -d ' ')"
  if [[ -r "$MIRROR_ROOT/last-success" ]]; then
    last_success="$(tr -d '\r\n' < "$MIRROR_ROOT/last-success")"
  else
    last_success="unavailable"
  fi

  printf 'mirror_root=%s\n' "$MIRROR_ROOT"
  printf 'files=%s\n' "$files"
  printf 'directories=%s\n' "$directories"
  printf 'logical_bytes=%s\n' "$logical_bytes"
  printf 'symlinks=%s\n' "$symlinks"
  printf 'last_success=%s\n' "$last_success"
}

if [[ "$#" -ne 1 ]]; then
  usage >&2
  exit 2
fi

case "$1" in
  --verify-local)
    verify_local
    exit 0
    ;;
  pull)
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

log() { echo "$(date '+%Y-%m-%dT%H:%M:%S%z') $*" >> "$LOG"; }

mkdir -p "$DEST" "$(dirname "$LOG")"
if ! mkdir "$LOCK" 2>/dev/null; then
  log "skip: another mirror run holds $LOCK"
  exit 0
fi
trap 'rmdir "$LOCK"' EXIT

run_rsync() {
  rsync -a --partial --partial-dir=.rsync-partial --exclude='.rsync-partial' \
    --timeout=600 --bwlimit="$BWLIMIT_KBPS" \
    -e "ssh -o ServerAliveInterval=15 -o ServerAliveCountMax=40" \
    "$SRC" "$DEST/" >> "$LOG" 2>&1
}

log "start: explicit pull $SRC -> $DEST (bwlimit ${BWLIMIT_KBPS} KB/s)"
start_ts="$(date +%s)"
attempt=0
rc=1
while :; do
  attempt=$((attempt + 1))
  if run_rsync; then
    rc=0
  else
    rc=$?
  fi
  # 24 = source files vanished mid-transfer during live-site publication.
  if [[ "$rc" -eq 0 || "$rc" -eq 24 ]]; then
    break
  fi
  if [[ "$attempt" -ge 4 ]]; then
    break
  fi
  log "rsync failed (rc=$rc, attempt $attempt/4); retrying in 120s"
  sleep 120
done

elapsed=$(( $(date +%s) - start_ts ))
if [[ "$rc" -eq 0 || "$rc" -eq 24 ]]; then
  files="$(find "$DEST" -type f ! -path '*/.rsync-partial/*' | wc -l | tr -d ' ')"
  size="$(du -sh "$DEST" 2>/dev/null | cut -f1)"
  log "ok: mirror holds $files public files, $size (rc=$rc, ${elapsed}s)"
  date '+%Y-%m-%dT%H:%M:%S%z' > "$MIRROR_ROOT/last-success"
else
  log "ERROR: rsync failed after retry (rc=$rc, ${elapsed}s) — mirror is stale"
  exit 1
fi
