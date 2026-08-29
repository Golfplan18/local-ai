#!/bin/sh
# Documentation-Code Parity — blocking, verification-only pre-push gate.
#
# Complete coordinated task context is ten explicit environment variables:
# DCP_{VAULT,ORA,APP,ORG,MSI}_{ROOT,BASE}. With that context this hook forwards
# the exact five-worktree contract to the focused verifier. It never generates
# files and never substitutes a live checkout for a missing task worktree.
#
# Without complete context, a pushed code-bearing, machine-consumed control,
# or unfamiliar path blocks and directs the user to the task coordinator. A
# genuinely prose-only range may pass, but the message explicitly withholds
# cross-repository certification.

set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)
VERIFY="$SCRIPT_DIR/verify-implementation.py"
PYTHON="${ORA_PYTHON:-python3}"

repository_label=${DCP_HOOK_REPOSITORY:-}
configured_common_dir=${DCP_HOOK_COMMON_DIR:-}
case "$repository_label" in
    vault|ora|app|org|msi) : ;;
    *)
        echo "DCP pre-push BLOCKED: installed repository label is missing or invalid." >&2
        exit 1
        ;;
esac
if [ -z "$configured_common_dir" ] || [ ! -d "$configured_common_dir" ]; then
    echo "DCP pre-push BLOCKED: installed repository identity is missing or invalid." >&2
    exit 1
fi
current_root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "DCP pre-push BLOCKED: current repository identity could not be read." >&2
    exit 1
}
current_root=$(CDPATH= cd -- "$current_root" 2>/dev/null && pwd -P) || {
    echo "DCP pre-push BLOCKED: current repository root could not be resolved." >&2
    exit 1
}
current_common_dir=$(git rev-parse --git-common-dir 2>/dev/null) || {
    echo "DCP pre-push BLOCKED: current repository identity could not be read." >&2
    exit 1
}
case "$current_common_dir" in
    /*) : ;;
    *) current_common_dir="$current_root/$current_common_dir" ;;
esac
current_common_dir=$(CDPATH= cd -- "$current_common_dir" 2>/dev/null && pwd -P) || {
    echo "DCP pre-push BLOCKED: current repository identity could not be resolved." >&2
    exit 1
}
configured_common_dir=$(CDPATH= cd -- "$configured_common_dir" 2>/dev/null && pwd -P) || {
    echo "DCP pre-push BLOCKED: configured repository identity could not be resolved." >&2
    exit 1
}
if [ "$current_common_dir" != "$configured_common_dir" ]; then
    echo "DCP pre-push BLOCKED: current repository does not match the installed $repository_label hook identity." >&2
    exit 1
fi

# Git exports repository-local variables to hooks. They are useful for finding
# the pushing worktree above, but would override every later `git -C <root>`
# and could silently redirect an explicit task root back to this repository.
git_local_environment=$(git rev-parse --local-env-vars 2>/dev/null) || {
    echo "DCP pre-push BLOCKED: Git hook-local environment could not be identified." >&2
    exit 1
}
for variable in $git_local_environment
do
    unset "$variable"
done

range_file=$(mktemp "${TMPDIR:-/tmp}/dcp-pre-push-range.XXXXXX") || {
    echo "DCP pre-push BLOCKED: could not create bounded range scratch." >&2
    exit 1
}
changed_file=""
cleanup_scratch() {
    cleanup_status=0
    rm -f "$range_file" 2>/dev/null || cleanup_status=1
    if [ -n "$changed_file" ]; then
        rm -f "$changed_file" 2>/dev/null || cleanup_status=1
    fi
    return "$cleanup_status"
}
trap 'cleanup_scratch >/dev/null 2>&1 || :' EXIT
trap 'exit 1' HUP INT TERM

if ! cat > "$range_file"; then
    echo "DCP pre-push BLOCKED: pushed-ref input could not be captured." >&2
    exit 1
fi
range_sentinel="/__DCP_RANGE_END_$$_${range_file##*.}__"
if ! printf '\n%s\n' "$range_sentinel" >> "$range_file"; then
    echo "DCP pre-push BLOCKED: pushed-ref capture could not be completed." >&2
    exit 1
fi

zero=0000000000000000000000000000000000000000
is_full_sha() {
    candidate=$1
    [ "${#candidate}" -eq 40 ] || return 1
    case "$candidate" in
        *[!0-9a-f]*) return 1 ;;
        *) return 0 ;;
    esac
}

missing_context=""
for variable in \
    DCP_VAULT_ROOT DCP_VAULT_BASE \
    DCP_ORA_ROOT DCP_ORA_BASE \
    DCP_APP_ROOT DCP_APP_BASE \
    DCP_ORG_ROOT DCP_ORG_BASE \
    DCP_MSI_ROOT DCP_MSI_BASE
do
    eval "value=\${$variable:-}"
    if [ -z "$value" ]; then
        missing_context="${missing_context}${missing_context:+, }$variable"
    fi
done

if [ -z "$missing_context" ]; then
    case "$repository_label" in
        vault) task_root=$DCP_VAULT_ROOT ;;
        ora) task_root=$DCP_ORA_ROOT ;;
        app) task_root=$DCP_APP_ROOT ;;
        org) task_root=$DCP_ORG_ROOT ;;
        msi) task_root=$DCP_MSI_ROOT ;;
    esac
    task_root=$(CDPATH= cd -- "$task_root" 2>/dev/null && pwd -P) || {
        echo "DCP pre-push BLOCKED: supplied $repository_label task root could not be resolved." >&2
        exit 1
    }
    if [ "$task_root" != "$current_root" ]; then
        echo "DCP pre-push BLOCKED: supplied $repository_label task root does not match the repository being pushed." >&2
        exit 1
    fi
    current_head=$(git -C "$current_root" rev-parse --verify 'HEAD^{commit}' 2>/dev/null) || {
        echo "DCP pre-push BLOCKED: current repository HEAD could not be resolved." >&2
        exit 1
    }
    task_head=$(git -C "$task_root" rev-parse --verify 'HEAD^{commit}' 2>/dev/null) || {
        echo "DCP pre-push BLOCKED: supplied task-root HEAD could not be resolved." >&2
        exit 1
    }
    if [ "$current_head" != "$task_head" ]; then
        echo "DCP pre-push BLOCKED: current repository HEAD and supplied task-root HEAD differ." >&2
        exit 1
    fi

    ref_failed=0
    range_read_complete=0
    while read -r local_ref local_sha remote_ref remote_sha extra
    do
        if [ "${local_ref:-}" = "$range_sentinel" ] \
            && [ -z "${local_sha:-}${remote_ref:-}${remote_sha:-}${extra:-}" ]
        then
            range_read_complete=1
            break
        fi
        [ -n "${local_ref:-}${local_sha:-}${remote_ref:-}${remote_sha:-}${extra:-}" ] || continue
        if [ -z "${local_ref:-}" ] || [ -z "${local_sha:-}" ] \
            || [ -z "${remote_ref:-}" ] || [ -z "${remote_sha:-}" ] \
            || [ -n "${extra:-}" ] \
            || ! is_full_sha "$local_sha" \
            || ! is_full_sha "$remote_sha"
        then
            ref_failed=1
            continue
        fi
        [ "$local_sha" != "$zero" ] || continue
        resolved_local=$(git -C "$task_root" rev-parse --verify "$local_sha^{commit}" 2>/dev/null) || {
            ref_failed=1
            continue
        }
        if [ "$resolved_local" != "$local_sha" ] || [ "$local_sha" != "$task_head" ]; then
            ref_failed=1
        fi
    done < "$range_file"
    if [ "$range_read_complete" -ne 1 ]; then
        echo "DCP pre-push BLOCKED: pushed-ref capture could not be read completely." >&2
        exit 1
    fi
    if [ "$ref_failed" -ne 0 ]; then
        echo "DCP pre-push BLOCKED: every non-deletion pushed SHA must equal the configured task-root HEAD." >&2
        exit 1
    fi
    if [ ! -f "$VERIFY" ]; then
        echo "DCP pre-push BLOCKED: focused verifier is missing at $VERIFY." >&2
        exit 1
    fi
    if ! cleanup_scratch; then
        echo "DCP pre-push BLOCKED: bounded range scratch could not be removed." >&2
        exit 1
    fi
    trap - EXIT HUP INT TERM
    exec "$PYTHON" "$VERIFY" \
        --check documentation-integrity \
        --vault-root "$DCP_VAULT_ROOT" --vault-base "$DCP_VAULT_BASE" \
        --ora-root "$DCP_ORA_ROOT" --ora-base "$DCP_ORA_BASE" \
        --app-root "$DCP_APP_ROOT" --app-base "$DCP_APP_BASE" \
        --org-root "$DCP_ORG_ROOT" --org-base "$DCP_ORG_BASE" \
        --msi-root "$DCP_MSI_ROOT" --msi-base "$DCP_MSI_BASE"
fi

changed_file=$(mktemp "${TMPDIR:-/tmp}/dcp-pre-push-changed.XXXXXX") || {
    echo "DCP pre-push BLOCKED: could not create changed-path scratch." >&2
    exit 1
}
if ! : > "$changed_file"; then
    echo "DCP pre-push BLOCKED: changed-path scratch could not be initialized." >&2
    exit 1
fi
range_failed=0
range_read_complete=0
while read -r local_ref local_sha remote_ref remote_sha extra
do
    if [ "${local_ref:-}" = "$range_sentinel" ] \
        && [ -z "${local_sha:-}${remote_ref:-}${remote_sha:-}${extra:-}" ]
    then
        range_read_complete=1
        break
    fi
    [ -n "${local_ref:-}${local_sha:-}${remote_ref:-}${remote_sha:-}${extra:-}" ] || continue
    if [ -z "${local_ref:-}" ] || [ -z "${local_sha:-}" ] \
        || [ -z "${remote_ref:-}" ] || [ -z "${remote_sha:-}" ] \
        || [ -n "${extra:-}" ] \
        || ! is_full_sha "$local_sha" \
        || ! is_full_sha "$remote_sha"
    then
        range_failed=1
        continue
    fi
    [ "$local_sha" != "$zero" ] || continue
    if [ "${remote_sha:-$zero}" = "$zero" ]; then
        empty_tree=$(git -C "$current_root" hash-object -t tree /dev/null 2>/dev/null) || {
            range_failed=1
            continue
        }
        git -C "$current_root" -c core.quotepath=false diff --no-renames --name-only "$empty_tree" "$local_sha" -- \
            >> "$changed_file" 2>/dev/null || range_failed=1
    else
        git -C "$current_root" -c core.quotepath=false diff --no-renames --name-only "$remote_sha" "$local_sha" -- \
            >> "$changed_file" 2>/dev/null || range_failed=1
    fi
done < "$range_file"

if [ "$range_read_complete" -ne 1 ] || [ "$range_failed" -ne 0 ]; then
    echo "DCP pre-push BLOCKED: the pushed range could not be read without complete task context." >&2
    echo "Push through the task coordinator with all five explicit worktree roots and base commits." >&2
    exit 1
fi

changed_sentinel="/__DCP_CHANGED_END_$$_${changed_file##*.}__"
if [ ! -f "$changed_file" ] \
    || ! printf '%s\n' "$changed_sentinel" >> "$changed_file"
then
    echo "DCP pre-push BLOCKED: changed-path scratch could not be completed." >&2
    exit 1
fi

documentation_only=1
changed_read_complete=0
while IFS= read -r path
do
    if [ "$path" = "$changed_sentinel" ]; then
        changed_read_complete=1
        break
    fi
    [ -n "$path" ] || continue
    case "$repository_label:$path" in
        # These exact top-level files are repository prose by convention. A
        # nested docs/help path or arbitrary Markdown suffix is not enough:
        # Ora's installed mirrors, site content collections, and vault
        # controls are all machine-consumed Markdown surfaces.
        *:README.md|*:CONTRIBUTING.md|*:SECURITY.md|*:CODE_OF_CONDUCT.md|*:SUPPORT.md|*:GOVERNANCE.md)
            continue
            ;;
        *)
            documentation_only=0
            ;;
    esac
done < "$changed_file"

if [ "$changed_read_complete" -ne 1 ]; then
    echo "DCP pre-push BLOCKED: changed-path scratch could not be read completely." >&2
    exit 1
fi

if [ "$documentation_only" -eq 1 ]; then
    echo "DCP pre-push: documentation-only range allowed without coordinated task context; cross-repository documentation integrity was NOT certified." >&2
    exit 0
fi

echo "DCP pre-push BLOCKED: the range contains code-bearing or unmapped changes, but complete coordinated task context is absent." >&2
echo "Missing context: $missing_context" >&2
echo "Push through the task coordinator with all five explicit worktree roots and base commits." >&2
exit 1
