#!/bin/zsh
# One-shot delayed launch of the rewrite. Bounded: sleeps once, runs once, exits.
# Costs zero Claude usage while waiting — the wait is a shell sleep, not a session.
DELAY="${1:-3600}"
LOG=/Users/oracle/engram-work/.migration/rewrite-run.log
echo "[delayed] $(date '+%F %T') sleeping ${DELAY}s before restart" >> "$LOG"
sleep "$DELAY"
echo "[delayed] $(date '+%F %T') starting rewrite" >> "$LOG"
exec /opt/homebrew/bin/python3 /Users/oracle/ora/scripts/engram-migration/rewrite_run.py \
  --apply --worklist /Users/oracle/engram-work/.migration/opus_worklist.json --workers 8
