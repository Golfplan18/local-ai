#!/bin/sh
# Documentation-Code Parity — stage 1 of the commit trigger.
#
# G1.10 removed DCP's daily schedule on 2026-07-21 and specified commit,
# deploy and specification-handoff events to replace it. The replacement was
# never built, so from that day nothing ran DCP at all; the runs in the Run
# History are all a human standing in for this hook.
#
# Two stages, per Framework — Documentation-Code Parity ":79". This is stage 1:
# the deterministic framework-pair check, ~0.1s, no model, no cost. It records
# what it finds in the DCP Escalation Queue. Stage 2 — the model-driven
# DCP-Audit and DCP-Reconcile — is invoked against that queue, never per commit.
# `--check all` is deliberately NOT run here: it takes over two minutes.
#
# Fails open by construction. This runs as post-commit, so the commit is
# already made and nothing here can block it. Every failure prints and is
# logged; none is swallowed, and none is allowed to look like success.
#
# Installed by scripts/install-dcp-hooks.sh. Hooks are not tracked by git, so
# that installer is the reproducible source — not the copy in .git/hooks.

set -u

ORA_ROOT="${ORA_HOME:-$HOME/ora}"
VERIFY="$ORA_ROOT/scripts/verify-implementation.py"
LOG="$ORA_ROOT/logs/dcp-commit-hook.log"
PYTHON="${ORA_PYTHON:-python3}"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG" 2>/dev/null; }

# Re-entry guard. The enqueue writes to a vault file, whose commit fires this
# hook again. The idempotent enqueue would append nothing and the chain would
# stop after one extra pass, but relying on that is not a guard.
if [ "${DCP_COMMIT_HOOK_RUNNING:-}" = "1" ]; then
    exit 0
fi
DCP_COMMIT_HOOK_RUNNING=1
export DCP_COMMIT_HOOK_RUNNING

mkdir -p "$(dirname "$LOG")" 2>/dev/null

# Recursion guard, the commit-identity equivalent of the event dispatcher's
# .git exclusion: a commit that only touched DCP's own outputs is this hook's
# own footprint, not new subject matter.
CHANGED=$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null)
if [ -n "$CHANGED" ]; then
    OTHER=$(printf '%s\n' "$CHANGED" | grep -v '^Administration/DCP/' || true)
    if [ -z "$OTHER" ]; then
        log "skip $(git rev-parse --short HEAD 2>/dev/null): DCP outputs only"
        exit 0
    fi
fi

if [ ! -f "$VERIFY" ]; then
    log "ERROR verifier missing at $VERIFY — DCP did not run for $(git rev-parse --short HEAD 2>/dev/null)"
    echo "DCP commit hook: verifier missing at $VERIFY (see $LOG)" >&2
    exit 0
fi

SHA=$(git rev-parse --short HEAD 2>/dev/null)
OUT=$("$PYTHON" "$VERIFY" --check framework-pairs --enqueue-framework-findings 2>&1)
STATUS=$?

# Exit 1 means findings are open, which is the normal state while drift is
# queued. Exit 2 is a queue-write failure and is a real problem.
QLINE=$(printf '%s\n' "$OUT" | grep 'Queue write:' || true)
CLINE=$(printf '%s\n' "$OUT" | grep 'paired clean=' || true)
log "run $SHA exit=$STATUS ${CLINE:-no-count} ${QLINE:-no-queue-line}"

if [ "$STATUS" -ge 2 ]; then
    log "ERROR $OUT"
    echo "DCP commit hook FAILED (exit $STATUS) — drift is not being recorded. See $LOG" >&2
fi

case "$QLINE" in
    *"0 authenticated finding(s) appended"*|"") : ;;
    *) echo "DCP: $QLINE" >&2 ;;
esac

exit 0
