#!/usr/bin/env bash
# Stop Ora without fighting launchd KeepAlive or killing developer worktrees.

set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
WORKSPACE="${ORA_HOME:-$SCRIPT_DIR}"
if [[ ! -d "$WORKSPACE" ]]; then
  echo "ERROR: ORA_HOME is not a directory: $WORKSPACE" >&2
  exit 1
fi
WORKSPACE="$(cd -- "$WORKSPACE" && pwd -P)"
if [[ -z "${HOME:-}" ]]; then
  HOME="$(cd ~ && pwd -P)"
  export HOME
fi
SERVICE_MANAGER="$WORKSPACE/scripts/ora-launchd.sh"

if command -v launchctl >/dev/null 2>&1; then
  if [[ ! -x "$SERVICE_MANAGER" ]]; then
    echo "ERROR: Service manager is missing: $SERVICE_MANAGER" >&2
    exit 1
  fi
  exec "$SERVICE_MANAGER" stop --ora-home "$WORKSPACE"
fi

# Unsupervised cross-platform fallback. Match only a Python interpreter whose
# next argv is this checkout's exact server file. A plain substring match can
# kill an editor, tail process, test command, or similarly-prefixed backup.
ORA_STOP_SERVER_TARGET="$WORKSPACE/server/app.py"
export ORA_STOP_SERVER_TARGET
pids="$(ps -axww -o pid=,command= | awk '
  {
    pid = $1
    line = $0
    sub(/^[[:space:]]*[0-9]+[[:space:]]+/, "", line)
    target = ENVIRON["ORA_STOP_SERVER_TARGET"]
    pos = index(line, target)
    if (!pos) next
    before = substr(line, 1, pos - 1)
    after = substr(line, pos + length(target))
    if (after != "" && substr(after, 1, 1) != " ") next
    sub(/[[:space:]]+$/, "", before)
    count = split(before, parts, "/")
    exe = parts[count]
    if (exe ~ /^[Pp]ython([0-9]+([.][0-9]+)*)?([[:space:]]+-[^[:space:]]+)*$/) print pid
  }')"
if [[ -n "$pids" ]]; then
  # shellcheck disable=SC2086  # ps output is a whitespace-separated PID set.
  kill $pids
  for _attempt in {1..150}; do
    remaining=""
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then
        remaining="$remaining $pid"
      fi
    done
    if [[ -z "$remaining" ]]; then
      echo "Ora server stopped."
      exit 0
    fi
    sleep 0.1
  done
  echo "ERROR: Ora server is still exiting (PID(s):$remaining)." >&2
  exit 1
else
  echo "Ora server was not running."
fi
