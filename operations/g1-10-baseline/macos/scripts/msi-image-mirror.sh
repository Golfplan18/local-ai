#!/bin/bash
# msi-image-mirror.sh — nightly PULL-ONLY mirror of the MSI image/asset tree
# from cloud-ora to this Mac. The live tree at
# cloud-ora:~/sites/mainstreetindependent/public/ is the only complete copy of
# ~525 cartoon PNGs and ~2,150 article hero PNGs (the git harvest deliberately
# excludes images); this job makes the Mac the full offline disaster-recovery
# copy.
#
# Installed 2026-07-08. Loaded by ~/Library/LaunchAgents/com.msi.image-mirror.plist
# daily at 04:00 local time (off-peak — the same uplink carries the 15-minute
# vault sync, com.cloud-ora.sync).
#
# Safety properties (do not weaken):
#   - PULL only: the server is never written to and never deleted from.
#   - NO --delete on the local copy either: the archive is additive, so files
#     later pruned on the server survive here. Reclaim space manually if ever
#     needed.
#   - --bwlimit keeps the transfer polite on the shared uplink;
#     --partial/--partial-dir lets an interrupted night resume the next run.
#
# Restore (manual, deliberate — never automated):
#   rsync -a --partial ~/Archives/msi-image-mirror/public/ \
#     cloud-ora:sites/mainstreetindependent/public/

SRC="cloud-ora:sites/mainstreetindependent/public/"
DEST="$HOME/Archives/msi-image-mirror/public"
LOG="$HOME/Library/Logs/msi-image-mirror.log"
LOCK="/tmp/msi-image-mirror.lock"
BWLIMIT_KBPS=5000   # ~5 MB/s courtesy cap on the shared uplink

log() { echo "$(date '+%Y-%m-%dT%H:%M:%S%z') $*" >> "$LOG"; }

if ! mkdir "$LOCK" 2>/dev/null; then
  log "skip: another mirror run holds $LOCK"
  exit 0
fi
trap 'rmdir "$LOCK"' EXIT

mkdir -p "$DEST"

# The Mac<->cloud-ora path runs ~0.5-0.7 MB/s and stalls occasionally
# (measured 2026-07-08; two concurrent streams starved each other into
# poll timeouts). Keepalives hold the NAT mapping through stalls; the
# retry loop + --partial resume ride out drops. Never run two bulk
# transfers on this link at once.
run_rsync() {
  rsync -a --partial --partial-dir=.rsync-partial --exclude='.rsync-partial' \
    --timeout=600 --bwlimit="$BWLIMIT_KBPS" \
    -e "ssh -o ServerAliveInterval=15 -o ServerAliveCountMax=40" \
    "$SRC" "$DEST/" >> "$LOG" 2>&1
}

log "start: pull $SRC -> $DEST (bwlimit ${BWLIMIT_KBPS} KB/s)"
start_ts=$(date +%s)

attempt=0
while :; do
  attempt=$((attempt + 1))
  run_rsync
  rc=$?
  # 24 = source files vanished mid-transfer (live site publishing) — benign,
  # the next nightly run picks them up.
  [ "$rc" -eq 0 ] || [ "$rc" -eq 24 ] && break
  if [ "$attempt" -ge 4 ]; then break; fi
  log "rsync failed (rc=$rc, attempt $attempt/4); retrying in 120s"
  sleep 120
done

elapsed=$(( $(date +%s) - start_ts ))
if [ "$rc" -eq 0 ] || [ "$rc" -eq 24 ]; then
  files=$(find "$DEST" -type f ! -path '*/.rsync-partial/*' | wc -l | tr -d ' ')
  size=$(du -sh "$DEST" 2>/dev/null | cut -f1)
  log "ok: mirror holds $files files, $size (rc=$rc, ${elapsed}s)"
  date '+%Y-%m-%dT%H:%M:%S%z' > "$HOME/Archives/msi-image-mirror/last-success"
else
  log "ERROR: rsync failed after retry (rc=$rc, ${elapsed}s) — mirror is stale"
  exit 1
fi
