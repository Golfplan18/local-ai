#!/bin/bash
# msi-repo-pullsync.sh — keep the Mac's MSI checkout an up-to-date READ-ONLY
# mirror of origin/main. Fast-forward pull only; never commits, never pushes,
# never touches local work.
#
# Installed 2026-07-08 as part of the Mac production decommission (all content
# generation moved to cloud-ora). Loaded by ~/Library/LaunchAgents/
# com.msi.repo-pullsync.plist every 30 minutes.
#
# Skips (silently, logged) when:
#   - another sync is already running (lock dir)
#   - the checkout is not on main (a session is doing branch work)
#   - tracked files have local modifications (a session is mid-edit;
#     untracked files alone do not block a fast-forward pull)
#   - the pull cannot fast-forward (never merges, never rebases)

REPO="/Users/oracle/sites/mainstreetindependent"
LOG="$HOME/Library/Logs/msi-repo-pullsync.log"
LOCK="/tmp/msi-repo-pullsync.lock"

log() { echo "$(date '+%Y-%m-%dT%H:%M:%S%z') $*" >> "$LOG"; }

if ! mkdir "$LOCK" 2>/dev/null; then
  log "skip: another sync holds $LOCK"
  exit 0
fi
trap 'rmdir "$LOCK"' EXIT

cd "$REPO" || { log "ERROR: repo missing at $REPO"; exit 1; }

branch=$(git symbolic-ref --short -q HEAD)
if [ "$branch" != "main" ]; then
  log "skip: checkout is on '$branch', not main"
  exit 0
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  log "skip: tracked files have local modifications"
  exit 0
fi

before=$(git rev-parse --short HEAD)
if out=$(git pull --ff-only origin main 2>&1); then
  after=$(git rev-parse --short HEAD)
  if [ "$before" = "$after" ]; then
    log "up to date at $after"
  else
    log "fast-forwarded $before -> $after"
  fi
else
  log "skip: pull could not fast-forward: $(echo "$out" | tail -1)"
fi
