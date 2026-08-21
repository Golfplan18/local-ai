#!/usr/bin/env bash
# Interactive Ora launcher. The actual server environment and command live in
# run-ora-server.sh so manual, app-bundle, and launchd starts cannot drift.

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
SERVER_LAUNCHER="$WORKSPACE/run-ora-server.sh"
SERVER_LOG="$WORKSPACE/server.log"
LAUNCHD_LABEL="com.ora.server"
LAUNCHD_TARGET="gui/$(id -u)/$LAUNCHD_LABEL"
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/$LAUNCHD_LABEL.plist"
SERVICE_MANAGER="$WORKSPACE/scripts/ora-launchd.sh"
START_TIMEOUT="${ORA_START_TIMEOUT:-30}"

case "$START_TIMEOUT" in
  ''|*[!0-9]*|0)
    echo "ERROR: ORA_START_TIMEOUT must be a positive integer." >&2
    exit 2
    ;;
esac

if [[ "${PORT+x}" == "x" ]]; then
  case "$PORT" in
    ''|*[!0-9]*|0*)
      echo "ERROR: PORT must be a canonical integer from 1 to 65535; got '$PORT'." >&2
      exit 2
      ;;
  esac
  if (( ${#PORT} > 5 || PORT > 65535 )); then
    echo "ERROR: PORT must be a canonical integer from 1 to 65535; got '$PORT'." >&2
    exit 2
  fi
fi

if [[ ! -x "$SERVER_LAUNCHER" ]]; then
  echo "ERROR: Foreground launcher is missing or not executable: $SERVER_LAUNCHER" >&2
  exit 1
fi

find_ora_port() {
  local port payload reported_home python
  local ports=( {5000..5010} )
  # A direct foreground/background launch inherits PORT and the server treats it
  # as exact intent. Supervised launches with an ambient PORT are rejected below
  # because launchd cannot inherit a one-shot caller environment safely.
  if [[ "${PORT+x}" == "x" ]]; then
    ports=( "$PORT" )
  fi
  for port in "${ports[@]}"; do
    payload="$(curl -sf --max-time 2 "http://localhost:$port/health" 2>/dev/null)" || continue
    reported_home=""
    if command -v plutil >/dev/null 2>&1; then
      reported_home="$(printf '%s' "$payload" \
        | plutil -extract ora_home raw -o - - 2>/dev/null || true)"
    else
      python="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
      if [[ -n "$python" ]]; then
        reported_home="$(ORA_HEALTH_PAYLOAD="$payload" "$python" -c \
          'import json, os; v=json.loads(os.environ["ORA_HEALTH_PAYLOAD"]).get("ora_home", ""); print(os.path.realpath(v) if v else "")' \
          2>/dev/null || true)"
      fi
    fi
    if [[ "$reported_home" == "$WORKSPACE" ]]; then
      printf '%s\n' "$port"
      return 0
    fi
  done
  return 1
}

owned_server_pids() {
  # Match only a Python interpreter whose next argv is this checkout's exact
  # server file. This catches a still-running pre-identity server (whose
  # /health response has no ora_home) without treating path mentions in an
  # editor, test, or similarly-prefixed backup as an Ora process.
  ORA_START_SERVER_TARGET="$WORKSPACE/server/app.py"
  export ORA_START_SERVER_TARGET
  ps -axww -o pid=,command= | awk '
    {
      pid = $1
      line = $0
      sub(/^[[:space:]]*[0-9]+[[:space:]]+/, "", line)
      target = ENVIRON["ORA_START_SERVER_TARGET"]
      pos = index(line, target)
      if (!pos) next
      before = substr(line, 1, pos - 1)
      after = substr(line, pos + length(target))
      if (after != "" && substr(after, 1, 1) != " ") next
      sub(/[[:space:]]+$/, "", before)
      count = split(before, parts, "/")
      exe = parts[count]
      # Legacy launchers sometimes inserted interpreter flags (notably -u)
      # before the script path. Permit flag tokens, but never another script
      # argument, between the Python executable and the exact target.
      if (exe ~ /^[Pp]ython([0-9]+([.][0-9]+)*)?([[:space:]]+-[^[:space:]]+)*$/) print pid
    }'
}

open_ora() {
  local url="$1"
  [[ "${ORA_NO_BROWSER:-0}" == "1" ]] && return 0
  if command -v open >/dev/null 2>&1; then
    open "$url"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url"
  elif command -v start >/dev/null 2>&1; then
    start "$url"
  fi
}

launchd_state="none"
if command -v launchctl >/dev/null 2>&1; then
  if launchctl print "$LAUNCHD_TARGET" >/dev/null 2>&1; then
    launchd_state="loaded"
  elif [[ -f "$LAUNCHD_PLIST" ]]; then
    launchd_state="stopped"
  fi
fi

if [[ "${PORT+x}" == "x" && "$launchd_state" != "none" ]]; then
  cat >&2 <<EOF
ERROR: PORT=$PORT cannot be applied while Ora is managed by launchd.
Run ./scripts/ora-launchd.sh uninstall before using a one-shot PORT, or
configure the supervised launcher explicitly. Refusing to start on another port.
EOF
  exit 2
fi

if port="$(find_ora_port)"; then
  if [[ "$launchd_state" == "stopped" ]]; then
    cat >&2 <<EOF
ERROR: Ora is responding, but its installed launchd service is stopped.
This usually means an unmanaged server is running. Run ./stop.sh once to
stop that process, then run ./start.sh again to restore supervision.
EOF
    exit 1
  fi
  echo "Ora is already ready at http://localhost:$port"
  open_ora "http://localhost:$port"
  exit 0
fi

started_pid=""
if [[ "$launchd_state" != "none" ]]; then
  if (( $# > 0 )); then
    cat >&2 <<EOF
ERROR: Ora is managed by launchd, so per-run server arguments cannot be
forwarded. Use ./scripts/ora-launchd.sh uninstall before running manually
with arguments, or configure the supervised launcher itself.
EOF
    exit 2
  fi
  echo "Starting supervised Ora service ($LAUNCHD_LABEL)..."
  if [[ ! -x "$SERVICE_MANAGER" ]] \
    || ! "$SERVICE_MANAGER" start --ora-home "$WORKSPACE"; then
    echo "ERROR: launchd could not start $LAUNCHD_LABEL." >&2
    exit 1
  fi
else
  legacy_pids="$(owned_server_pids)"
  if [[ -n "$legacy_pids" ]]; then
    cat >&2 <<EOF
ERROR: An unsupervised Ora server from this checkout is already running
(PID(s): $legacy_pids), but it did not report this checkout identity.
It may be a pre-upgrade server. Run ./stop.sh once, then run ./start.sh
again so only one process can write to this Ora installation.
EOF
    exit 1
  fi
  echo "Starting Ora in the background..."
  nohup "$SERVER_LAUNCHER" "$@" >>"$SERVER_LOG" 2>&1 &
  started_pid=$!
fi

for ((attempt = 0; attempt < START_TIMEOUT; attempt++)); do
  if port="$(find_ora_port)"; then
    echo "Ora ready at http://localhost:$port"
    open_ora "http://localhost:$port"
    exit 0
  fi
  if [[ -n "$started_pid" ]] && ! kill -0 "$started_pid" 2>/dev/null; then
    echo "ERROR: Ora exited before becoming healthy. Check $SERVER_LOG" >&2
    exit 1
  fi
  sleep 1
done

echo "ERROR: Ora did not become healthy within ${START_TIMEOUT}s." >&2
if [[ -n "$started_pid" ]]; then
  echo "Check $SERVER_LOG for startup errors." >&2
else
  echo "Inspect with: ./scripts/ora-launchd.sh status" >&2
fi
exit 1
