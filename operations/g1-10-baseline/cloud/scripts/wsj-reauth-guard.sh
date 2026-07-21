#!/bin/bash
# wsj-reauth-guard.sh — keep the WSJ subscriber session alive with no human.
# Daily: diagnose; if expired, auto re-auth via xvfb+setup (env creds from
# wsj.env); if that fails, drop a marker + optional webhook push.
set -uo pipefail
LOG=/home/oracle/wsj-reauth-guard.log
MARKER=/home/oracle/WSJ_REAUTH_NEEDED.txt
PROJ=/home/oracle/sites/mainstreetindependent/ora-project
VENV=/home/oracle/ora/.venv/bin/python3
export PYTHONPATH=/home/oracle/ora:$PROJ/scripts:$PROJ/tools
set -a; . /home/oracle/.config/msi/wsj.env 2>/dev/null || true; set +a
ts(){ date -u +%FT%TZ; }
cd "$PROJ" || exit 1
# 1. Is the session valid?
if timeout 120 "$VENV" tools/wsj_editorial_fetcher.py diagnose 2>/dev/null | grep -q "\"free\""; then
  echo "$(ts) session OK" >> "$LOG"; rm -f "$MARKER"; exit 0
fi
echo "$(ts) session invalid; attempting autonomous re-auth" >> "$LOG"
# 2. Auto re-auth (headed Firefox under virtual display, env creds)
timeout 180 xvfb-run -a "$VENV" tools/wsj_editorial_fetcher.py setup > /home/oracle/wsj-guard-setup.txt 2>&1 || true
# 3. Verify
if timeout 120 "$VENV" tools/wsj_editorial_fetcher.py diagnose 2>/dev/null | grep -q "\"free\""; then
  echo "$(ts) autonomous re-auth SUCCEEDED" >> "$LOG"; rm -f "$MARKER"; exit 0
fi
# 4. Failed — alert (marker always; webhook if configured)
echo "$(ts) AUTONOMOUS RE-AUTH FAILED — one manual WSJ login needed (see wsj-guard-setup.txt)" | tee -a "$LOG" > "$MARKER"
if [ -n "${WSJ_ALERT_WEBHOOK:-}" ]; then
  curl -s -m 15 -d "MSI cloud-ora: WSJ auto re-auth failed - manual login needed" "$WSJ_ALERT_WEBHOOK" >/dev/null 2>&1 || true
fi
exit 1
