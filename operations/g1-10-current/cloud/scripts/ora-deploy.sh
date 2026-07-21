#!/usr/bin/env bash
# Deploy one exact accepted Ora release. No branch default and no clock retry.
set -euo pipefail

REPO="${ORA_CLOUD_REPO:-$HOME/ora}"
LOG="$HOME/ora-deploy.log"
RECEIPTS="$HOME/.local/state/ora/release-deployments.jsonl"
LOCK="$HOME/ora-deploy.lock"
BRANCH=""
COMMIT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="$2"; shift 2 ;;
    --commit) COMMIT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$BRANCH" =~ ^[A-Za-z0-9._/-]+$ ]] || {
  echo "--branch with a safe exact remote branch is required" >&2; exit 2; }
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  echo "--commit with a full SHA-1 is required" >&2; exit 2; }

mkdir -p "$(dirname "$RECEIPTS")"
exec >>"$LOG" 2>&1
exec 9>"$LOCK"
flock -n 9 || { echo "[$(date -Iseconds)] deployment already in progress"; exit 75; }
cd "$REPO"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "[$(date -Iseconds)] tracked worktree is dirty; refusing deployment"
  exit 1
fi
BEFORE="$(git rev-parse HEAD)"
git fetch origin "$BRANCH" --quiet
REMOTE="$(git rev-parse FETCH_HEAD)"
[[ "$REMOTE" == "$COMMIT" ]] || {
  echo "[$(date -Iseconds)] remote branch identity mismatch: $REMOTE != $COMMIT"
  exit 1
}

# A detached exact commit avoids silently following a mutable branch after the
# accepted release event. Untracked runtime state is preserved; Git refuses
# the switch if any path would be overwritten.
git switch --detach "$COMMIT"

if [[ -x .venv/bin/python && -f scripts/migrate.py ]]; then
  .venv/bin/python scripts/migrate.py
fi

python3 - "$RECEIPTS" "$BEFORE" "$COMMIT" "$BRANCH" <<'PY'
import datetime, json, pathlib, sys
path = pathlib.Path(sys.argv[1])
record = {
    "kind": "accepted_release_deployed",
    "before": sys.argv[2], "after": sys.argv[3], "remote_branch": sys.argv[4],
    "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
PY
echo "[$(date -Iseconds)] deployed exact accepted release $COMMIT from $BRANCH"
