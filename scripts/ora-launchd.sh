#!/usr/bin/env bash
# Install and manage Ora's per-user macOS launchd service.

set -euo pipefail

# Bash 5 can treat '&' specially inside ${value//pattern/replacement}; disable
# that optional behavior so XML-escaped ampersands remain literal when paths
# are substituted into the plist. macOS Bash 3.2 simply ignores this option.
shopt -u patsub_replacement 2>/dev/null || true

LABEL="com.ora.server"
ACTION="${1:-status}"
if (( $# > 0 )); then shift; fi

SOURCE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ -z "${HOME:-}" ]]; then
  HOME="$(cd ~ && pwd -P)"
  export HOME
fi
ORA_HOME="${ORA_HOME:-$HOME/ora}"
FORCE_TARGET_MISMATCH=0

while (( $# > 0 )); do
  case "$1" in
    --ora-home)
      [[ $# -ge 2 ]] || { echo "ERROR: --ora-home requires a path." >&2; exit 2; }
      ORA_HOME="$2"
      shift 2
      ;;
    --force-target-mismatch)
      FORCE_TARGET_MISMATCH=1
      shift
      ;;
    -h|--help)
      ACTION="help"
      shift
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

usage() {
  cat <<'EOF'
Usage: ./scripts/ora-launchd.sh ACTION [--ora-home PATH] [--force-target-mismatch]

Actions:
  install       Render, install, and start the per-user launchd service.
                Also updates an existing ignored Ora.app to delegate to start.sh.
  uninstall     Stop the service and remove its installed plist.
  start         Load or restart the installed service.
  stop          Stop the service but leave its plist installed.
  restart       Restart the installed service.
  status        Show launchd's current service status.
  install-app   Update only an existing Ora.app launcher.

The default target is ~/ora. The service runs run-ora-server.sh in the
foreground with RunAtLoad and KeepAlive enabled.

The service label is global within the user's GUI session. Stop, uninstall,
start, and status refuse to manage a plist owned by another checkout. The
--force-target-mismatch flag is reserved for deliberate recovery/teardown.
EOF
}

if [[ "$ACTION" == "help" ]]; then
  usage
  exit 0
fi

if (( FORCE_TARGET_MISMATCH )) \
  && [[ "$ACTION" != "stop" && "$ACTION" != "uninstall" && "$ACTION" != "status" ]]; then
  echo "ERROR: --force-target-mismatch is allowed only for stop, uninstall, or status." >&2
  exit 2
fi

if [[ -d "$ORA_HOME" ]]; then
  # launchd ProgramArguments and WorkingDirectory must be absolute. Resolve
  # both relative inputs and symlinks before rendering or matching processes.
  ORA_HOME="$(cd -- "$ORA_HOME" && pwd -P)"
elif [[ "$ACTION" == "stop" || "$ACTION" == "uninstall" || "$ACTION" == "status" ]] \
  && [[ "$ORA_HOME" == /* ]]; then
  # Keep teardown/status usable after a checkout has been removed. No process
  # can legitimately own a missing target; the loaded label remains stoppable.
  ORA_HOME="${ORA_HOME%/}"
else
  echo "ERROR: ORA_HOME is not an existing directory: $ORA_HOME" >&2
  exit 1
fi

HEALTH_TIMEOUT="${ORA_LAUNCHD_HEALTH_TIMEOUT:-30}"
case "$HEALTH_TIMEOUT" in
  ''|*[!0-9]*|0)
    echo "ERROR: ORA_LAUNCHD_HEALTH_TIMEOUT must be a positive integer." >&2
    exit 2
    ;;
esac

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: launchd service management is supported only on macOS." >&2
  exit 1
fi

UID_VALUE="$(id -u)"
DOMAIN="gui/$UID_VALUE"
TARGET="$DOMAIN/$LABEL"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$LABEL.plist"
TEMPLATE="$SOURCE_ROOT/installer/macos/$LABEL.plist.template"
APP_TEMPLATE="$SOURCE_ROOT/installer/macos/ora-app-launcher.sh"
TMP_PLIST=""

cleanup() {
  if [[ -n "$TMP_PLIST" ]]; then
    rm -f "$TMP_PLIST"
  fi
}
trap cleanup EXIT

xml_escape() {
  local value="$1"
  value=${value//&/&amp;}
  value=${value//</&lt;}
  value=${value//>/&gt;}
  value=${value//\"/&quot;}
  value=${value//\'/&apos;}
  printf '%s' "$value"
}

is_loaded() {
  launchctl print "$TARGET" >/dev/null 2>&1
}

owned_server_pids() {
  # Match a Python interpreter whose next argv is the exact canonical server
  # path. A substring search can kill an editor, a tail/test process, or a
  # similarly-prefixed backup merely because its command mentions server.py.
  # Pass the target through the environment so the awk process itself never
  # carries the needle in its argv.
  local ORA_LAUNCHD_SERVER_TARGET="$ORA_HOME/server/server.py"
  export ORA_LAUNCHD_SERVER_TARGET
  ps -axww -o pid=,command= | awk '
    {
      pid = $1
      line = $0
      sub(/^[[:space:]]*[0-9]+[[:space:]]+/, "", line)
      target = ENVIRON["ORA_LAUNCHD_SERVER_TARGET"]
      pos = index(line, target)
      if (!pos) next
      before = substr(line, 1, pos - 1)
      after = substr(line, pos + length(target))
      if (after != "" && substr(after, 1, 1) != " ") next
      sub(/[[:space:]]+$/, "", before)
      count = split(before, parts, "/")
      exe = parts[count]
      if (exe ~ /^[Pp]ython([0-9]+([.][0-9]+)*)?([[:space:]]+-[^[:space:]]+)*$/) print pid
    }'
}

wait_for_service_exit() {
  local attempt
  # Server shutdown runs session_end hooks with a configured timeout up to
  # ten seconds; allow a bounded margin before declaring the process stuck.
  for attempt in {1..150}; do
    [[ -z "$(owned_server_pids)" ]] && return 0
    sleep 0.1
  done
  return 1
}

health_port_for_home() {
  local port payload reported_home
  for port in {5000..5010}; do
    payload="$(curl -sf --max-time 2 "http://localhost:$port/health" 2>/dev/null)" \
      || continue
    reported_home="$(printf '%s' "$payload" \
      | plutil -extract ora_home raw -o - - 2>/dev/null || true)"
    if [[ "$reported_home" == "$ORA_HOME" ]]; then
      printf '%s\n' "$port"
      return 0
    fi
  done
  return 1
}

wait_for_service_health() {
  local attempt port
  for ((attempt = 0; attempt < HEALTH_TIMEOUT; attempt++)); do
    if is_loaded && port="$(health_port_for_home)"; then
      SERVICE_HEALTH_PORT="$port"
      return 0
    fi
    if (( attempt + 1 < HEALTH_TIMEOUT )); then
      sleep 1
    fi
  done
  return 1
}

report_health_failure() {
  local stderr_log="$ORA_HOME/logs/ora-server.stderr.log"
  echo "ERROR: $LABEL did not become healthy for $ORA_HOME within ${HEALTH_TIMEOUT}s." >&2
  if [[ -s "$stderr_log" ]]; then
    echo "Last 30 lines of $stderr_log:" >&2
    tail -n 30 "$stderr_log" >&2
  else
    echo "No stderr output was captured at $stderr_log." >&2
  fi
}

stop_failed_service() {
  if is_loaded; then
    launchctl bootout "$TARGET" >/dev/null 2>&1 || true
    wait_for_service_exit || \
      echo "WARNING: Failed service process is still exiting." >&2
  fi
}

verify_installed_target() {
  local installed_runner expected_runner
  if (( FORCE_TARGET_MISMATCH )); then
    return 0
  fi
  expected_runner="$ORA_HOME/run-ora-server.sh"
  installed_runner="$(plutil -extract ProgramArguments.0 raw -o - "$PLIST_PATH" 2>/dev/null || true)"
  if [[ "$installed_runner" != "$expected_runner" ]]; then
    cat >&2 <<EOF
ERROR: The installed $LABEL service targets a different checkout:
  installed: ${installed_runner:-<unreadable>}
  requested: $expected_runner
Run this to reconcile the installed service:
  $0 install --ora-home "$ORA_HOME"
EOF
    if [[ "$ACTION" == "stop" || "$ACTION" == "uninstall" || "$ACTION" == "status" ]]; then
      cat >&2 <<EOF
Or, after verifying the installed target, force this recovery/teardown action:
  $0 $ACTION --ora-home "$ORA_HOME" --force-target-mismatch
EOF
    fi
    return 1
  fi
}

install_app_launcher() {
  local app_launcher="$ORA_HOME/Ora.app/Contents/MacOS/ai"
  if [[ ! -d "$ORA_HOME/Ora.app/Contents/MacOS" ]]; then
    echo "Ora.app is not present; skipping generated app launcher update."
    return 0
  fi
  [[ -f "$APP_TEMPLATE" ]] || {
    echo "ERROR: App launcher source is missing: $APP_TEMPLATE" >&2
    return 1
  }
  if [[ -f "$app_launcher" && ! -f "$app_launcher.pre-supervision" ]]; then
    cp -p "$app_launcher" "$app_launcher.pre-supervision"
  fi
  install -m 0755 "$APP_TEMPLATE" "$app_launcher"
  echo "Updated Ora.app launcher to delegate to $ORA_HOME/start.sh"
}

install_service() {
  [[ -x "$ORA_HOME/run-ora-server.sh" ]] || {
    echo "ERROR: Canonical foreground launcher is missing or not executable:" >&2
    echo "  $ORA_HOME/run-ora-server.sh" >&2
    exit 1
  }
  [[ -f "$TEMPLATE" ]] || {
    echo "ERROR: launchd template is missing: $TEMPLATE" >&2
    exit 1
  }

  mkdir -p "$PLIST_DIR" "$ORA_HOME/logs"
  local escaped_ora escaped_home rendered
  escaped_ora="$(xml_escape "$ORA_HOME")"
  escaped_home="$(xml_escape "$HOME")"
  rendered="$(<"$TEMPLATE")"
  rendered="${rendered//__ORA_HOME__/$escaped_ora}"
  rendered="${rendered//__USER_HOME__/$escaped_home}"
  TMP_PLIST="$(mktemp "${TMPDIR:-/tmp}/ora-launchd.XXXXXX")"
  printf '%s\n' "$rendered" >"$TMP_PLIST"
  plutil -lint "$TMP_PLIST" >/dev/null

  if is_loaded; then
    launchctl bootout "$TARGET"
    if ! wait_for_service_exit; then
      echo "ERROR: Existing supervised server did not stop cleanly." >&2
      exit 1
    fi
  fi

  assert_no_unmanaged_server

  install -m 0644 "$TMP_PLIST" "$PLIST_PATH"
  install_app_launcher
  launchctl enable "$TARGET"
  launchctl bootstrap "$DOMAIN" "$PLIST_PATH"
  if ! wait_for_service_health; then
    report_health_failure
    stop_failed_service
    return 1
  fi
  echo "Installed and started $LABEL"
  echo "Plist: $PLIST_PATH"
  echo "Logs:  $ORA_HOME/logs/ora-server.stdout.log"
  echo "Health: http://localhost:$SERVICE_HEALTH_PORT/health"
}

assert_no_unmanaged_server() {
  local unmanaged
  unmanaged="$(owned_server_pids)"
  if [[ -n "$unmanaged" ]]; then
    cat >&2 <<EOF
ERROR: An unmanaged Ora server is already running (PID(s): $unmanaged).
Stop it first with:
  $ORA_HOME/stop.sh
Then rerun this install command. This guard prevents a second server from
silently starting on another port.
EOF
    exit 1
  fi
}

start_service() {
  [[ -f "$PLIST_PATH" ]] || {
    echo "ERROR: $LABEL is not installed. Run: $0 install" >&2
    exit 1
  }
  verify_installed_target
  launchctl enable "$TARGET"
  if is_loaded; then
    launchctl kickstart -k "$TARGET"
  else
    assert_no_unmanaged_server
    launchctl bootstrap "$DOMAIN" "$PLIST_PATH"
  fi
  if ! wait_for_service_health; then
    report_health_failure
    stop_failed_service
    return 1
  fi
  echo "Started $LABEL at http://localhost:$SERVICE_HEALTH_PORT"
}

stop_service() {
  if is_loaded; then
    verify_installed_target
    launchctl bootout "$TARGET"
    wait_for_service_exit || {
      echo "WARNING: The Ora process is still exiting." >&2
      return 1
    }
    echo "Stopped $LABEL (plist remains installed)."
  else
    local unmanaged
    unmanaged="$(owned_server_pids)"
    if [[ -n "$unmanaged" ]]; then
      # shellcheck disable=SC2086  # owned_server_pids emits PID words only.
      kill $unmanaged
      if ! wait_for_service_exit; then
        echo "WARNING: The unmanaged Ora process is still exiting." >&2
        return 1
      fi
      echo "Stopped unmanaged Ora server (plist remains installed)."
    else
      echo "$LABEL is already stopped."
    fi
  fi
}

uninstall_service() {
  if is_loaded || [[ -f "$PLIST_PATH" ]]; then
    verify_installed_target
  fi
  stop_service
  if [[ -f "$PLIST_PATH" ]]; then
    rm -f "$PLIST_PATH"
    echo "Removed $PLIST_PATH"
  else
    echo "$LABEL was already uninstalled."
  fi
}

case "$ACTION" in
  install)
    install_service
    ;;
  uninstall)
    uninstall_service
    ;;
  start)
    start_service
    ;;
  stop)
    stop_service
    ;;
  restart)
    start_service
    ;;
  status)
    if is_loaded; then
      verify_installed_target
      launchctl print "$TARGET"
    else
      echo "$LABEL is not loaded."
      exit 1
    fi
    ;;
  install-app)
    install_app_launcher
    ;;
  *)
    echo "ERROR: Unknown action: $ACTION" >&2
    usage >&2
    exit 2
    ;;
esac
