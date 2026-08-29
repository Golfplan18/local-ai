#!/bin/sh
# Install Documentation-Code Parity Git hooks in five explicit repositories.
#
# Required configuration (there are deliberately no live-root defaults):
#   DCP_ORA_ROOT, DCP_VAULT_ROOT, DCP_APP_ROOT, DCP_ORG_ROOT, DCP_MSI_ROOT
#
# Every repository receives the verification-only, blocking pre-push hook.
# Ora and the vault additionally retain the existing fail-open post-commit
# framework-pair queue audit. Re-runnable and foreign-hook safe.
#
#   sh scripts/install-dcp-hooks.sh            # install/update our hooks
#   sh scripts/install-dcp-hooks.sh --check    # exact report, no writes
#   sh scripts/install-dcp-hooks.sh --uninstall

set -u

MODE="${1:-install}"
case "$MODE" in
    install|--check|--uninstall) : ;;
    *) echo "usage: $0 [install|--check|--uninstall]" >&2; exit 2 ;;
esac

missing=""
for variable in DCP_ORA_ROOT DCP_VAULT_ROOT DCP_APP_ROOT DCP_ORG_ROOT DCP_MSI_ROOT
do
    eval "value=\${$variable:-}"
    if [ -z "$value" ]; then
        missing="${missing}${missing:+, }$variable"
    fi
done
if [ -n "$missing" ]; then
    echo "DCP hook configuration incomplete; missing: $missing" >&2
    exit 2
fi

POST_SOURCE="$DCP_ORA_ROOT/scripts/dcp-commit-hook.sh"
PRE_SOURCE="$DCP_ORA_ROOT/scripts/dcp-pre-push-hook.sh"
if [ ! -f "$POST_SOURCE" ] || [ ! -f "$PRE_SOURCE" ]; then
    echo "DCP hook sources are missing below explicit Ora root $DCP_ORA_ROOT" >&2
    exit 2
fi

hooks_dir() {
    (cd "$1" 2>/dev/null && git rev-parse --git-path hooks 2>/dev/null) || return 1
}

repository_common_dir() {
    repository=$1
    directory=$(cd "$repository" 2>/dev/null && git rev-parse --git-common-dir 2>/dev/null) \
        || return 1
    case "$directory" in
        /*) : ;;
        *) directory="$repository/$directory" ;;
    esac
    (cd "$directory" 2>/dev/null && pwd -P) || return 1
}

target_path() {
    repository="$1"
    hook_name="$2"
    directory=$(hooks_dir "$repository") || return 1
    case "$directory" in
        /*) : ;;
        *) directory="$repository/$directory" ;;
    esac
    printf '%s/%s\n' "$directory" "$hook_name"
}

preflight_repository() {
    repository_name=$1
    repository=$2
    if [ ! -d "$repository" ]; then
        echo "DCP hook configuration invalid: $repository_name repository is missing at $repository" >&2
        return 1
    fi
    common_directory=$(repository_common_dir "$repository") || {
        echo "DCP hook configuration invalid: $repository_name is not a resolvable Git repository at $repository" >&2
        return 1
    }
    printf '%s\n' "$common_directory"
}

reject_duplicate_repository_identity() {
    first_name=$1
    first_directory=$2
    second_name=$3
    second_directory=$4
    if [ "$first_directory" = "$second_directory" ]; then
        echo "DCP hook configuration invalid: $first_name and $second_name resolve to the same Git repository/common directory: $first_directory" >&2
        return 1
    fi
}

# Validate the complete five-repository target set before any hook is created,
# replaced, or removed. Linked worktrees share a common Git directory, so this
# also rejects one repository supplied under two different labels.
ORA_COMMON_DIR=$(preflight_repository ora "$DCP_ORA_ROOT") || exit 2
VAULT_COMMON_DIR=$(preflight_repository vault "$DCP_VAULT_ROOT") || exit 2
APP_COMMON_DIR=$(preflight_repository app "$DCP_APP_ROOT") || exit 2
ORG_COMMON_DIR=$(preflight_repository org "$DCP_ORG_ROOT") || exit 2
MSI_COMMON_DIR=$(preflight_repository msi "$DCP_MSI_ROOT") || exit 2

reject_duplicate_repository_identity ora "$ORA_COMMON_DIR" vault "$VAULT_COMMON_DIR" || exit 2
reject_duplicate_repository_identity ora "$ORA_COMMON_DIR" app "$APP_COMMON_DIR" || exit 2
reject_duplicate_repository_identity ora "$ORA_COMMON_DIR" org "$ORG_COMMON_DIR" || exit 2
reject_duplicate_repository_identity ora "$ORA_COMMON_DIR" msi "$MSI_COMMON_DIR" || exit 2
reject_duplicate_repository_identity vault "$VAULT_COMMON_DIR" app "$APP_COMMON_DIR" || exit 2
reject_duplicate_repository_identity vault "$VAULT_COMMON_DIR" org "$ORG_COMMON_DIR" || exit 2
reject_duplicate_repository_identity vault "$VAULT_COMMON_DIR" msi "$MSI_COMMON_DIR" || exit 2
reject_duplicate_repository_identity app "$APP_COMMON_DIR" org "$ORG_COMMON_DIR" || exit 2
reject_duplicate_repository_identity app "$APP_COMMON_DIR" msi "$MSI_COMMON_DIR" || exit 2
reject_duplicate_repository_identity org "$ORG_COMMON_DIR" msi "$MSI_COMMON_DIR" || exit 2

result=0
active_temp=""

cleanup_active_temp() {
    if [ -n "$active_temp" ]; then
        rm -f "$active_temp" 2>/dev/null || :
        active_temp=""
    fi
}

trap cleanup_active_temp EXIT
trap 'cleanup_active_temp; exit 1' HUP INT TERM

render_wrapper() {
    if [ "$1" = "post-commit" ]; then
        cat <<EOF
#!/bin/sh
$4 — installed by $DCP_ORA_ROOT/scripts/install-dcp-hooks.sh
# Edit the tracked source and re-run the installer; do not edit this copy.
export ORA_HOME="$DCP_ORA_ROOT"
export ORA_VAULT="$DCP_VAULT_ROOT"
exec "$5"
EOF
    else
        cat <<EOF
#!/bin/sh
$4 — installed by $DCP_ORA_ROOT/scripts/install-dcp-hooks.sh
# The task coordinator supplies DCP_*_ROOT and DCP_*_BASE for each push.
# Edit the tracked source and re-run the installer; do not edit this copy.
export DCP_HOOK_REPOSITORY="$2"
export DCP_HOOK_COMMON_DIR="$3"
exec "$5"
EOF
    fi
}

discard_active_temp() {
    temporary=$active_temp
    if rm -f "$temporary"; then
        active_temp=""
        return 0
    fi
    return 1
}

is_managed_hook() {
    [ -f "$1" ] && grep -Fq "$2 — installed by " "$1" 2>/dev/null
}

path_exists() {
    [ -e "$1" ] || [ -L "$1" ]
}

manage_hook() {
    repository="$1"
    repository_name="$2"
    hook_name="$3"
    marker="$4"
    source="$5"

    if [ ! -d "$repository" ]; then
        echo "ERROR  $repository_name/$hook_name — repository missing at $repository"
        result=1
        return
    fi
    target=$(target_path "$repository" "$hook_name") || {
        echo "ERROR  $repository_name/$hook_name — not a Git repository"
        result=1
        return
    }
    common_directory=""
    if [ "$hook_name" = "pre-push" ]; then
        common_directory=$(repository_common_dir "$repository") || {
            echo "ERROR  $repository_name/$hook_name — Git common directory could not be resolved"
            result=1
            return
        }
    fi

    case "$MODE" in
        --check)
            active_temp=$(mktemp "${TMPDIR:-/tmp}/dcp-hook-check.XXXXXX") || {
                echo "ERROR  $repository_name/$hook_name — expected-wrapper temporary file could not be created"
                result=1
                active_temp=""
                return
            }
            if ! render_wrapper \
                "$hook_name" "$repository_name" "$common_directory" \
                "$marker" "$source" > "$active_temp"
            then
                echo "ERROR  $repository_name/$hook_name — expected wrapper could not be generated"
                result=1
                cleanup_active_temp
                return
            fi
            if [ -f "$target" ] && [ -x "$target" ] \
                && cmp -s "$active_temp" "$target"
            then
                echo "ok     $repository_name/$hook_name — installed at $target"
            elif path_exists "$target"; then
                echo "STALE  $repository_name/$hook_name — not the configured DCP hook at $target"
                result=1
            else
                echo "ABSENT $repository_name/$hook_name — no DCP hook at $target"
                result=1
            fi
            if ! discard_active_temp; then
                echo "ERROR  $repository_name/$hook_name — expected-wrapper temporary file could not be removed"
                result=1
            fi
            ;;
        --uninstall)
            if is_managed_hook "$target" "$marker"; then
                if rm -f "$target"; then
                    echo "removed $repository_name/$hook_name — $target"
                else
                    echo "ERROR  $repository_name/$hook_name — managed hook could not be removed at $target"
                    result=1
                fi
            elif path_exists "$target"; then
                echo "REFUSE $repository_name/$hook_name — foreign hook left untouched at $target"
                result=1
            else
                echo "skip   $repository_name/$hook_name — no DCP hook to remove"
            fi
            ;;
        install)
            if path_exists "$target" && ! is_managed_hook "$target" "$marker"; then
                echo "REFUSE $repository_name/$hook_name — foreign hook exists at $target; not overwriting"
                result=1
                return
            fi
            target_directory=$(dirname "$target") || {
                echo "ERROR  $repository_name/$hook_name — hook directory could not be identified"
                result=1
                return
            }
            if ! mkdir -p "$target_directory"; then
                echo "ERROR  $repository_name/$hook_name — hook directory could not be created at $target_directory"
                result=1
                return
            fi
            active_temp=$(mktemp "$target.dcp.XXXXXX") || {
                echo "ERROR  $repository_name/$hook_name — installation temporary file could not be created beside $target"
                result=1
                active_temp=""
                return
            }
            if ! render_wrapper \
                "$hook_name" "$repository_name" "$common_directory" \
                "$marker" "$source" > "$active_temp"
            then
                echo "ERROR  $repository_name/$hook_name — wrapper could not be written"
                result=1
                cleanup_active_temp
                return
            fi
            if ! chmod +x "$active_temp"; then
                echo "ERROR  $repository_name/$hook_name — wrapper permissions could not be installed"
                result=1
                cleanup_active_temp
                return
            fi
            if [ -f "$target" ] && [ -x "$target" ] \
                && cmp -s "$active_temp" "$target"
            then
                if ! discard_active_temp; then
                    echo "ERROR  $repository_name/$hook_name — installation temporary file could not be removed"
                    result=1
                    return
                fi
                echo "ok     $repository_name/$hook_name — installed at $target"
                return
            fi
            staged=$active_temp
            if ! mv -f "$staged" "$target"; then
                echo "ERROR  $repository_name/$hook_name — wrapper could not be moved into place at $target"
                result=1
                cleanup_active_temp
                return
            fi
            active_temp=""
            echo "ok     $repository_name/$hook_name — installed at $target"
            ;;
    esac
}

manage_hook "$DCP_ORA_ROOT" ora pre-push "# dcp-pre-push-trigger" "$PRE_SOURCE"
manage_hook "$DCP_VAULT_ROOT" vault pre-push "# dcp-pre-push-trigger" "$PRE_SOURCE"
manage_hook "$DCP_APP_ROOT" app pre-push "# dcp-pre-push-trigger" "$PRE_SOURCE"
manage_hook "$DCP_ORG_ROOT" org pre-push "# dcp-pre-push-trigger" "$PRE_SOURCE"
manage_hook "$DCP_MSI_ROOT" msi pre-push "# dcp-pre-push-trigger" "$PRE_SOURCE"

# The queue-writing audit is intentionally not installed in the three sites.
manage_hook "$DCP_ORA_ROOT" ora post-commit "# dcp-commit-trigger" "$POST_SOURCE"
manage_hook "$DCP_VAULT_ROOT" vault post-commit "# dcp-commit-trigger" "$POST_SOURCE"

exit "$result"
