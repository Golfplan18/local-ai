#!/usr/bin/env bash
# Cloud Ora auto-pull deploy script.
# Lives outside ~/ora/ so it is not subject to its own auto-pull.
# Run every 15 minutes via cron. Pulls origin/main with --ff-only,
# skipping if MSI publication is in flight or another deploy is already running.

set -euo pipefail

REPO="${HOME}/ora"
LOG="${HOME}/ora-deploy.log"
LOCK="${HOME}/ora-deploy.lock"

exec >>"$LOG" 2>&1

# Serialize concurrent runs
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[$(date -Iseconds)] another deploy run in progress; skipping"
    exit 0
fi

echo "[$(date -Iseconds)] === deploy run ==="

cd "$REPO"

# In-progress MSI guard. Placeholder pattern until MSI cleanup defines a
# canonical lockfile path; widens to catch likely entry points.
if pgrep -f "msi_publish|article_generator|publish_cycle" >/dev/null 2>&1; then
    echo "[$(date -Iseconds)] MSI publication in progress; skipping pull until next cron tick"
    exit 0
fi

git fetch origin main --quiet

LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u})

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[$(date -Iseconds)] already up to date (${LOCAL:0:7})"
    exit 0
fi

BASE=$(git merge-base @ @{u})
if [ "$LOCAL" != "$BASE" ]; then
    # Added 2026-06-06: ~/ora carries server-local config + patch commits, so it can be
    # AHEAD of / diverged from upstream and --ff-only would error every run. Only auto-pull
    # when strictly behind (local is an ancestor of upstream); otherwise skip cleanly and
    # leave the engine pinned for a deliberate manual reconcile.
    echo "[$(date -Iseconds)] diverged ($(git rev-list --count @{u}..@) ahead / $(git rev-list --count @..@{u}) behind) — local commits present; auto-deploy paused pending manual reconcile; skipping"
    exit 0
fi
echo "[$(date -Iseconds)] pulling ${LOCAL:0:7} -> ${REMOTE:0:7} (fast-forward)"
git pull --ff-only origin main

# Migration hook. No migrations exist today; reserved for future use.
if [ -x .venv/bin/python ] && [ -f scripts/migrate.py ]; then
    echo "[$(date -Iseconds)] running scripts/migrate.py"
    .venv/bin/python scripts/migrate.py
fi

# Service restart hook. No systemd unit for Ora yet (will land when MSI cycle
# is wired up). Uncomment when ora.service exists:
# systemctl --user restart ora.service

echo "[$(date -Iseconds)] deploy complete (now at $(git rev-parse @ | cut -c1-7))"
