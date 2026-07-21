#!/usr/bin/env bash
# vault-derive-sync.sh — self-healing Paper -> site reconcile (WS0).
#
# Every run fetches vault origin/main into a dedicated disposable worktree,
# re-derives ALL canonical "Paper — *.md" sources into both site repos, and
# pushes whatever changed to main. The server's */15 deploy crons
# (ora-deploy.sh, msi-deploy.sh) then publish. Idempotent: a cycle with no Paper
# changes produces no commit. Resilient: a malformed Paper is skipped + logged
# (per-paper invocation) so one bad file can never block the rest — that is the
# "without fail" property.
#
# It writes into dedicated git WORKTREES of the working repos (detached on
# origin/main), so it never disturbs the working tree the user edits in sessions
# and never re-downloads the repos. The derive script + deps come from the
# working repo (which has node_modules); the worktrees are pure output + push
# targets.
#
#   vault-derive-sync.sh            # dry run: derive + show what WOULD change
#   vault-derive-sync.sh --push     # derive + commit + push to main (launchd uses this)
set -uo pipefail

export PATH="/Users/oracle/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

WORK_VAULT="${VAULT_REPO:-${VAULT_DIR:-$HOME/Documents/vault}}"
WORK_ORA="${ORA_WORKDIR:-$HOME/sites/ora-ai-app}"
WORK_MSI="${MSI_WORKDIR:-$HOME/sites/mainstreetindependent}"
SYNC_ROOT="$HOME/sites/.vault-sync"
VAULT_WT="$SYNC_ROOT/vault"
ORA_WT="$SYNC_ROOT/ora"
MSI_WT="$SYNC_ROOT/msi"
VAULT="$VAULT_WT"
LOG="$SYNC_ROOT/vault-derive-sync.log"
LOCKDIR="$SYNC_ROOT/.lock.d"
DERIVE="$WORK_ORA/scripts/derive-explainer.mjs"

PUSH=0; [[ "${1:-}" == "--push" ]] && PUSH=1

mkdir -p "$SYNC_ROOT"
exec >>"$LOG" 2>&1

# Single-instance lock (macOS has no flock). Clear a stale lock (>30 min).
[[ -d "$LOCKDIR" ]] && [[ -n "$(find "$LOCKDIR" -maxdepth 0 -mmin +30 2>/dev/null)" ]] && rmdir "$LOCKDIR" 2>/dev/null
if ! mkdir "$LOCKDIR" 2>/dev/null; then echo "$(date -u +%FT%TZ) another run in progress; skip"; exit 0; fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

echo "===== $(date -u +%FT%TZ) vault-derive-sync start (push=$PUSH) ====="

# Bring a worktree to a clean, detached origin/main (create it if absent). The
# worktree shares the working repo's object store — no download. Disposable:
# safe to hard-reset because nothing here is ever hand-edited.
prep() {
  local work="$1" wt="$2"
  git -C "$work" fetch -q origin || return 1
  if [[ ! -d "$wt/.git" && ! -f "$wt/.git" ]]; then
    echo "creating worktree $wt"
    git -C "$work" worktree prune
    git -C "$work" worktree add -q --detach "$wt" origin/main || return 1
  fi
  git -C "$wt" checkout -q --detach origin/main || return 1
  git -C "$wt" reset -q --hard origin/main || return 1
  git -C "$wt" clean -fdq || true
}
prep "$WORK_VAULT" "$VAULT_WT" || { echo "vault worktree prep failed"; exit 1; }
prep "$WORK_ORA" "$ORA_WT" || { echo "ora worktree prep failed"; exit 1; }
prep "$WORK_MSI" "$MSI_WT" || { echo "msi worktree prep failed"; exit 1; }

# Derive every Paper (per-paper so one bad file can't block the rest). Script +
# js-yaml come from the working ora repo; output goes to the worktrees.
ok=0; fail=0
while IFS= read -r -d '' paper; do
  if VAULT_DIR="$VAULT" ORA_DIR="$ORA_WT" MSI_DIR="$MSI_WT" node "$DERIVE" "$paper" --target all --write >/dev/null 2>>"$LOG"; then
    ok=$((ok + 1))
  else
    fail=$((fail + 1)); echo "DERIVE FAILED: $(basename "$paper")"
  fi
done < <(find "$VAULT" -maxdepth 1 -name 'Paper — *.md' -print0)
if VAULT_DIR="$VAULT" ORA_DIR="$ORA_WT" MSI_DIR="$MSI_WT" node "$DERIVE" --framework-mirrors --write >/dev/null 2>>"$LOG"; then
  ok=$((ok + 3))
else
  fail=$((fail + 1)); echo "DERIVE FAILED: framework mirrors"
fi
echo "derived ok=$ok failed=$fail"

# Reverse parity: a source that becomes unroutable or changes slug must remove its
# old generated page. Only prune after a failure-free pass; otherwise a malformed
# source could make a still-valid output look orphaned. The checker deliberately
# excludes MSI's independently managed public/papers/visual subtree.
if [[ "$fail" == "0" ]]; then
  if ! VAULT_DIR="$VAULT" ORA_DIR="$ORA_WT" MSI_DIR="$MSI_WT" DERIVE_SCRIPT="$DERIVE" \
    node "$WORK_ORA/scripts/assert-papers-derived.mjs" --prune; then
    echo "derived parity/prune failed; refusing to stage or push"
    exit 1
  fi
else
  echo "reverse parity skipped because $fail source derivation(s) failed"
fi

# Stage only the derived content/public paths, then commit+push if anything moved.
sync_repo() {
  local name="$1" wt="$2"; shift 2
  git -C "$wt" add -- "$@" 2>/dev/null
  if git -C "$wt" diff --cached --quiet; then echo "$name: no changes"; return 0; fi
  local n; n=$(git -C "$wt" diff --cached --name-only | wc -l | tr -d ' ')
  echo "$name: $n changed file(s):"
  git -C "$wt" diff --cached --name-only | sed 's/^/    /' | head -60
  if [[ "$PUSH" == "1" ]]; then
    git -C "$wt" -c user.name='vault-sync-bot' -c user.email='golfplan18@gmail.com' \
      commit -q -m "chore(content): auto-sync derived pages from vault ($n files)" \
      -m "Generated by vault-derive-sync.sh from canonical Paper — *.md. Do not hand-edit derived files." \
      && (git -C "$wt" push -q origin HEAD:main && echo "$name: pushed $n files" || echo "$name: PUSH FAILED (retry next cycle)")
  else
    echo "$name: DRY-RUN (pass --push to commit); unstaging"
    git -C "$wt" reset -q
  fi
}

sync_repo "ora" "$ORA_WT" src/content/modes src/content/lenses src/content/visual-outputs src/content/papers src/content/analytical-frameworks src/content/functional-frameworks public/papers
sync_repo "msi" "$MSI_WT" src/content/mode-explainers src/content/lens-explainers src/content/papers public/papers

echo "===== $(date -u +%FT%TZ) vault-derive-sync done ====="
