#!/bin/sh
# Install the DCP commit trigger into every repository DCP watches.
#
# Git hooks are not tracked by git, so this script is the reproducible source
# of the installation — a hook that exists only in someone's .git/hooks is
# exactly the "runtime by documentation" trap that Framework — Oversight
# Configuration names. Re-runnable; safe to run repeatedly.
#
#   sh scripts/install-dcp-hooks.sh            # install
#   sh scripts/install-dcp-hooks.sh --check    # report, change nothing
#   sh scripts/install-dcp-hooks.sh --uninstall

set -eu

ORA_ROOT="${ORA_HOME:-$HOME/ora}"
VAULT_ROOT="${ORA_VAULT:-$HOME/Documents/vault}"
HOOK_SRC="$ORA_ROOT/scripts/dcp-commit-hook.sh"
MARKER="# dcp-commit-trigger"
MODE="${1:-install}"

hooks_dir() {
    # Honours core.hooksPath, worktrees, and the vault's external gitdir.
    ( cd "$1" 2>/dev/null && git rev-parse --git-path hooks 2>/dev/null ) || return 1
}

for REPO in "$ORA_ROOT" "$VAULT_ROOT"; do
    NAME=$(basename "$REPO")
    if [ ! -d "$REPO" ]; then
        echo "skip   $NAME — not present at $REPO"
        continue
    fi
    DIR=$(hooks_dir "$REPO") || { echo "skip   $NAME — not a git repository"; continue; }
    case "$DIR" in /*) : ;; *) DIR="$REPO/$DIR" ;; esac
    TARGET="$DIR/post-commit"

    case "$MODE" in
      --check)
        if [ -f "$TARGET" ] && grep -q "$MARKER" "$TARGET" 2>/dev/null; then
            echo "ok     $NAME — installed at $TARGET"
        else
            echo "ABSENT $NAME — no DCP hook at $TARGET"
        fi
        ;;
      --uninstall)
        if [ -f "$TARGET" ] && grep -q "$MARKER" "$TARGET" 2>/dev/null; then
            rm -f "$TARGET"; echo "removed $NAME — $TARGET"
        else
            echo "skip   $NAME — no DCP hook to remove"
        fi
        ;;
      install)
        if [ -f "$TARGET" ] && ! grep -q "$MARKER" "$TARGET" 2>/dev/null; then
            echo "REFUSE $NAME — $TARGET exists and is not ours; not overwriting"
            continue
        fi
        mkdir -p "$DIR"
        cat > "$TARGET" <<EOF
#!/bin/sh
$MARKER — installed by $ORA_ROOT/scripts/install-dcp-hooks.sh
# Edit scripts/dcp-commit-hook.sh, not this file. Re-run the installer to update.
exec "$HOOK_SRC"
EOF
        chmod +x "$TARGET"
        echo "ok     $NAME — installed at $TARGET"
        ;;
      *)
        echo "usage: $0 [install|--check|--uninstall]" >&2; exit 2 ;;
    esac
done
