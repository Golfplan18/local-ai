#!/bin/bash
# Diagnose the shared WSJ profile for both the existing timer and fetch preflight.
# Only explicit authentication failure permits the existing setup/alert routine.
set -uo pipefail
ORA_ROOT=${ORA_HOME:-/home/oracle/ora}
USER_ROOT=$(dirname "$ORA_ROOT")
LOG=$USER_ROOT/wsj-reauth-guard.log
MARKER=$USER_ROOT/WSJ_REAUTH_NEEDED.txt
PROJ=${ORA_PROJECT_ROOT:-/home/oracle/sites/mainstreetindependent/ora-project}
VENV=$ORA_ROOT/.venv/bin/python3
SETUP_OUTPUT=$USER_ROOT/wsj-guard-setup.txt
export PYTHONPATH=$ORA_ROOT:$PROJ/scripts:$PROJ/tools
set -a; . "$USER_ROOT/.config/msi/wsj.env" 2>/dev/null || true; set +a
ts(){ date -u +%FT%TZ; }
cd "$PROJ" || exit 75
scratch=$(mktemp -d) || exit 75
child_pid=
cleanup(){ rm -rf "$scratch"; }
cancel(){
  trap '' TERM INT
  if [ -n "$child_pid" ]; then
    # GNU timeout owns this process group, including Firefox/xvfb descendants.
    kill -TERM -- "-$child_pid" 2>/dev/null || true
    # timeout escalates after its bounded --kill-after grace, then reaps.
    wait "$child_pid" 2>/dev/null || true
    child_pid=
  fi
  echo "$(ts) operation cancelled; retryable" >> "$LOG"
  exit 75
}
trap cleanup EXIT
trap cancel TERM INT
run_timed(){
  local limit=$1 output=$2 rc
  shift 2
  timeout --kill-after=5 "$limit" "$@" > "$output" 2>&1 &
  child_pid=$!
  wait "$child_pid"; rc=$?
  child_pid=
  return "$rc"
}
classify(){
  "$VENV" - "$1" "$2" <<'PY'
import json
import sys

# Timeout/cancellation wins over any incomplete or stale JSON output.
if int(sys.argv[2]) in (124, 137, 143):
    print("timeout")
    raise SystemExit
try:
    with open(sys.argv[1]) as stream:
        result = json.load(stream)
    status = result.get("status")
    reason = str(result.get("reason") or "")
    data = result.get("data") or {}
    fetch = data.get("fetch_result") or data
    paywall = fetch.get("paywall_state")
except (OSError, ValueError, TypeError, AttributeError):
    print("operational")
    raise SystemExit
# Recognize the existing fetcher envelopes too during coordinated deployment.
if reason in ("profile_busy", "fetch_profile_busy") or (
    "firefox_launch_failed" in reason and any(text in reason.lower() for text in (
        "profile locked", "profile is in use", "profile in use", "already running"))
):
    print("busy")
elif status == "ok" and paywall == "free" and int(sys.argv[2]) == 0:
    print("healthy")
elif reason in {
    "no_authenticated_profile", "fetch_no_authenticated_profile",
    "paywall_blocks_body", "fetch_paywall_blocks_body",
    "paywall_truncated_body", "fetch_paywall_truncated_body",
} or (status in ("partial", "blocked") and paywall in ("full", "partial")):
    print("authentication")
else:
    print("operational")
PY
}
retry(){
  echo "$(ts) $1; retryable operational outcome" >> "$LOG"
  exit 75
}

# Child allowances remain 120 + 180 + 120 seconds; unified allows 450 seconds.
run_timed 120 "$scratch/diagnose.json" "$VENV" tools/wsj_editorial_fetcher.py diagnose
rc=$?
state=$(classify "$scratch/diagnose.json" "$rc")
case "$state" in
  healthy) echo "$(ts) session OK" >> "$LOG"; rm -f "$MARKER"; exit 0 ;;
  authentication) echo "$(ts) explicit authentication failure; attempting autonomous re-auth" >> "$LOG" ;;
  *) retry "diagnosis $state" ;;
esac

run_timed 180 "$SETUP_OUTPUT" xvfb-run -a "$VENV" tools/wsj_editorial_fetcher.py setup
rc=$?
case "$rc" in 124|137|143) retry "setup timeout or cancellation" ;; esac
# Busy/setup transport failures are not evidence that credentials are invalid.
setup_state=$(classify "$SETUP_OUTPUT" "$rc")
if [ "$setup_state" = busy ]; then retry "setup profile busy"; fi

run_timed 120 "$scratch/verify.json" "$VENV" tools/wsj_editorial_fetcher.py diagnose
rc=$?
state=$(classify "$scratch/verify.json" "$rc")
case "$state" in
  healthy) echo "$(ts) autonomous re-auth SUCCEEDED" >> "$LOG"; rm -f "$MARKER"; exit 0 ;;
  authentication) ;;
  *) retry "verification $state" ;;
esac

# Existing authentication alert, only after another explicit auth failure.
echo "$(ts) AUTONOMOUS RE-AUTH FAILED — one manual WSJ login needed (see wsj-guard-setup.txt)" | tee -a "$LOG" > "$MARKER"
if [ -n "${WSJ_ALERT_WEBHOOK:-}" ]; then
  curl -s -m 15 -d "MSI cloud-ora: WSJ auto re-auth failed - manual login needed" "$WSJ_ALERT_WEBHOOK" >/dev/null 2>&1 || true
fi
exit 1
