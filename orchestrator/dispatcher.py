"""Unified tool dispatcher with permission gating, path validation,
command classification, audit logging, and consecutive call limiting."""

from __future__ import annotations

import hashlib
import contextlib
import json
import os
import sys
import threading
import time
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

# CAMPAIGN-RAG-BYPASS-2026-05-26 — context-propagated flag set by the
# pipeline (boot.run_step2_context_assembly) at the start of every turn.
# When set to "web_only", any vault-touching tool dispatched on this
# thread is refused. Per-turn lifetime via Python contextvars: each Flask
# request thread reads its own value, so a parallel non-isolated request
# is unaffected. Read this via ``_get_rag_isolation()``; set via
# ``set_rag_isolation()``. Removal: delete with the rest of the bypass
# (see boot.py removal procedure under the same marker).
_RAG_ISOLATION_CTX: ContextVar[str | None] = ContextVar(
    "rag_isolation", default=None,
)

# Consecutive-tool protection is loop-local state. The ContextVar is shared
# as a definition, but each request/agentic-loop context carries its own
# immutable ``(tool_name, count)`` value, so parallel conversations cannot
# advance one another's limiter.
_CONSECUTIVE_TOOL_CTX: ContextVar[tuple[str | None, int]] = ContextVar(
    "consecutive_tool_state", default=(None, 0),
)


def set_rag_isolation(value: str | None) -> None:
    """Set the per-turn rag_isolation flag. Called by boot.py at step 2.

    Lives in dispatcher.py (not boot.py) to avoid a circular import.
    """
    _RAG_ISOLATION_CTX.set(value)


def _get_rag_isolation() -> str | None:
    return _RAG_ISOLATION_CTX.get()

# Ora roots come from the single cross-platform source (runtime_paths),
# env-overridable, no hardcoded ~/ora or ~/Documents.
try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp
WORKSPACE = _rp.WORKSPACE
VAULT = _rp.VAULT_STR
CONVERSATIONS = _rp.CONVERSATIONS_STR
LOG_DIR = str(_rp.LOGS_DIR)

# ── Tool imports ───────────────────────────────────────────────────────────
import sys
# Resolve tools/ relative to THIS file, not the ~/ora constant, so a git
# worktree checkout imports its own tools rather than the main checkout's.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))

try:
    from web_search import web_search
    from web_fetch import web_fetch
    from file_ops import file_read, file_write, _validate_path, model_read_blocked
    from knowledge_search import knowledge_search
    from credential_store import credential_store
    from bash_execute import (
        CommandPreparationError,
        PreparedCommand,
        classify_command,
        cleanup_all,
        execute_command,
        prepare_command,
        revalidate_prepared_command,
        resolve_shell_profile,
        stop_process,
    )
    from file_edit import edit_file
    from search_files import grep_files, list_directory
    from subagent import spawn_subagent
    from code_execute import code_execute as _code_execute_run, code_execute_axes
    _TOOLS_LOADED = True
except ImportError as e:
    print(f"[dispatcher] Tool import warning: {e}")
    _TOOLS_LOADED = False

# Execution Review instrumentation layer (recorder + capability gate).
try:
    import tool_events
except ImportError:
    from orchestrator import tool_events

try:
    import system_protection
except ImportError:  # pragma: no cover
    from orchestrator import system_protection

# Non-critical imports (hooks, MCP)
try:
    from hooks import fire_hooks, load_hooks as _load_hooks
    _load_hooks()
except ImportError:
    def fire_hooks(event, context=None): return []

try:
    from mcp_client import (
        BOUND_BROWSER_TOOLS, get_manager as _get_mcp_manager, shutdown as _mcp_shutdown,
    )
except ImportError:
    _get_mcp_manager = None
    _mcp_shutdown = None
    BOUND_BROWSER_TOOLS = frozenset()


# ── Tool Registry ─────────────────────────────────────────────────────────

def _wrap_web_search(params):
    # Opt the agentic-loop tool into semantic augmentation: when enabled in
    # config with the semantic provider keyed, model-initiated searches merge
    # in semantic (e.g. Exa) results alongside the keyword cascade. No-op when
    # the feature is off or the provider is unkeyed.
    return web_search(
        params.get("query", ""), params.get("max_results", 5),
        semantic_augment=True,
    )

def _wrap_web_fetch(params):
    return web_fetch(
        params.get("url", ""),
        channel=params.get("channel", "auto"),
        persist=params.get("persist", False),
    )

def _wrap_file_read(params):
    return file_read(params.get("path", ""))

def _wrap_file_write(params):
    return file_write(params.get("path", ""), params.get("content", ""))

def _wrap_file_edit(params):
    return edit_file(params.get("file_path", params.get("path", "")),
                     params.get("old_string", ""),
                     params.get("new_string", ""))

def _wrap_bash_execute(params, prepared_command=None):
    return execute_command(
        prepared_command if prepared_command is not None else params.get("command", ""),
        timeout=params.get("timeout", 60),
        cwd=params.get("cwd"),
        background=params.get("background", False),
        max_output_chars=params.get("max_output_chars", 10000),
    )

def _wrap_search_files(params):
    return grep_files(
        params.get("pattern", ""),
        params.get("directory", WORKSPACE),
        params.get("file_extension"),
        params.get("max_results", 50),
    )

def _wrap_list_directory(params):
    return list_directory(params.get("path", WORKSPACE),
                          params.get("max_depth", 2))

def _wrap_knowledge_search(params):
    # CAMPAIGN-RAG-BYPASS-2026-05-26 — refuse vault/conversation lookups
    # when the per-turn flag is "web_only". The knowledge_search tool
    # hits ChromaDB's ``knowledge`` (vault) and ``conversations``
    # collections, which a clean-install visitor would not have. Returns
    # a refusal string the model can act on (typically by emitting
    # COVERAGE GAP or by calling web_search instead).
    if _get_rag_isolation() == "web_only":
        return (
            "[knowledge_search refused — rag_isolation: web_only is active for "
            "this run. Conversation RAG and vault RAG are both off so the "
            "output remains reproducible from a clean install. Use web_search "
            "instead, or emit a COVERAGE GAP block naming the unverifiable "
            "claim.]"
        )
    return knowledge_search(
        params.get("query", ""),
        params.get("collection", "knowledge"),
        params.get("n_results", 5),
    )

def _wrap_credential_store(params):
    return credential_store(
        params.get("action", "status"),
        params.get("service", ""),
        params.get("username", ""),
        params.get("value"),
    )

def _wrap_stop_process(params):
    return stop_process(params.get("pid", 0))

def _wrap_spawn_subagent(params):
    return spawn_subagent(
        params.get("system_prompt", "You are a helpful assistant."),
        params.get("user_prompt", ""),
        params.get("model_slot"),
        params.get("timeout", 120),
    )

# Each entry carries the existing function axis ("category" — untouched)
# plus the Execution Review capability axes: "mutability" / "sensitivity" /
# "egress" (tool_events.py vocabularies). "sensitivity" is the tool default;
# path-taking tools get per-call resolution in dispatch(). This registry is
# the runtime source of truth for model-facing tools.
TOOL_REGISTRY = {
    "web_search":       {"handler": _wrap_web_search,       "permission": "auto",    "category": "read",
                         "mutability": "read", "sensitivity": "public", "egress": "external"},
    "web_fetch":        {"handler": _wrap_web_fetch,        "permission": "auto",    "category": "read",
                         "mutability": "read", "sensitivity": "public", "egress": "external"},
    "file_read":        {"handler": _wrap_file_read,        "permission": "auto",    "category": "read",
                         "mutability": "read", "sensitivity": "private", "egress": "none"},
    "file_write":       {"handler": _wrap_file_write,       "permission": "approve", "category": "write",
                         "mutability": "reversible_write", "sensitivity": "private", "egress": "none"},
    "file_edit":        {"handler": _wrap_file_edit,        "permission": "approve", "category": "write",
                         "mutability": "reversible_write", "sensitivity": "private", "egress": "none"},
    "bash_execute":     {"handler": _wrap_bash_execute,     "permission": "approve", "category": "execute",
                         "mutability": "irreversible", "sensitivity": "private", "egress": "external",
                         "enforcement": "boundary_only"},
    "search_files":     {"handler": _wrap_search_files,     "permission": "auto",    "category": "read",
                         "mutability": "read", "sensitivity": "private", "egress": "none"},
    "list_directory":   {"handler": _wrap_list_directory,   "permission": "auto",    "category": "read",
                         "mutability": "read", "sensitivity": "private", "egress": "none"},
    "knowledge_search": {"handler": _wrap_knowledge_search, "permission": "auto",    "category": "read",
                         "mutability": "read", "sensitivity": "private", "egress": "none"},
    "credential_store": {"handler": _wrap_credential_store, "permission": "approve", "category": "write",
                         "mutability": "reversible_write", "sensitivity": "secret", "egress": "none"},
    "stop_process":     {"handler": _wrap_stop_process,     "permission": "approve", "category": "execute",
                         "mutability": "reversible_write", "sensitivity": "private", "egress": "none"},
    "spawn_subagent":   {"handler": _wrap_spawn_subagent,   "permission": "approve", "category": "execute",
                         "mutability": "read", "sensitivity": "private", "egress": "external",
                         "enforcement": "boundary_only"},
}


if _TOOLS_LOADED:
    # Sandboxed compute (replaces boot.py's legacy _code_execute bypass).
    # Axes are dynamic: orchestrated when sandbox-exec is available, else
    # fail-closed so the gate blocks rather than running unsandboxed.
    TOOL_REGISTRY["code_execute"] = {
        "handler": lambda p: _code_execute_run(p.get("code", ""),
                                               p.get("timeout", 30)),
        "permission": "auto", "category": "execute",
        "mutability": "reversible_write", "sensitivity": "private",
        "egress": "none", "axes_fn": code_execute_axes,
    }


def register_tool(name: str, handler, *, permission: str, category: str,
                  mutability: str, sensitivity: str, egress: str,
                  axes_fn=None) -> None:
    """Register a tool at runtime (used by boot.py for the former legacy
    inline tools, so they route through the gate + event log instead of
    bypassing the dispatcher). ``axes_fn`` may return dynamic axes (e.g.
    code_execute's sandbox-availability-dependent classification)."""
    entry = {"handler": handler, "permission": permission,
             "category": category, "mutability": mutability,
             "sensitivity": sensitivity, "egress": egress}
    if axes_fn is not None:
        entry["axes_fn"] = axes_fn
    TOOL_REGISTRY[name] = entry

# ── Permission modes ──────────────────────────────────────────────────────

_permission_mode = "approve-each"   # approve-each | approve-by-category | auto-approve
_approved_categories = set()         # for approve-by-category mode


def set_permission_mode(mode: str):
    global _permission_mode
    if mode in ("approve-each", "approve-by-category", "auto-approve"):
        _permission_mode = mode


def request_permission(tool_name: str, parameters: dict,
                       classification: dict | None = None,
                       callback=None) -> bool:
    """Check permission for a tool call. Returns True if approved.

    Args:
        callback: Optional function(tool_name, params, classification) -> bool
                  Used by server.py for browser-based approval.
                  If None, uses terminal input.
    """
    entry = TOOL_REGISTRY.get(tool_name)
    if not entry:
        return False

    if entry["permission"] == "auto":
        return True

    # Bash execute: use classification levels
    if tool_name == "bash_execute" and classification:
        level = classification.get("level", "moderate")
        if level == "blocked":
            return False
        if level == "safe":
            return True
        if level == "dangerous":
            # Dangerous always prompts regardless of mode
            if callback:
                return callback(tool_name, parameters, classification)
            print(f"\n⚠️  WARNING — DANGEROUS COMMAND")
            print(f"Command: {parameters.get('command', '')}")
            print(f"Reason: {classification.get('reason', '')}")
            print("This command operates outside the workspace or could cause system changes.")
            resp = input("Type 'yes' to confirm, or 'n' to deny: ").strip().lower()
            return resp == "yes"

    # Mode-based checks
    if _permission_mode == "auto-approve":
        return True

    if _permission_mode == "approve-by-category":
        if entry["category"] in _approved_categories:
            return True

    # Interactive approval
    if callback:
        return callback(tool_name, parameters, classification)

    print(f"\n🔐 Permission requested: {tool_name}")
    print(f"   Parameters: {json.dumps(parameters, indent=2)[:300]}")
    if classification:
        print(f"   Risk: {classification.get('level', '?')} — {classification.get('reason', '')}")
    resp = input("   Approve? (y/n): ").strip().lower()
    return resp in ("y", "yes")


# ── Path validation ───────────────────────────────────────────────────────

ALLOWED_BASES = [WORKSPACE, VAULT, CONVERSATIONS]

DENY_LIST = [".ssh", ".gnupg", ".env", "id_rsa", "id_ed25519", ".netrc",
             "credentials", "secrets", "token", ".aws/credentials"]


def validate_path(file_path: str, operation: str = "read") -> tuple[bool, str]:
    """Validate a file path for safety."""
    resolved = os.path.realpath(os.path.expanduser(file_path))

    # Block path traversal attempts
    if ".." in file_path:
        return False, f"Path traversal not allowed: {file_path}"

    # Block deny-listed patterns. Normalize separators to '/' and case-fold so a
    # Windows backslash path (``C:\\Users\\a\\.aws\\credentials``) still matches
    # the '/'-shaped patterns (``.aws/credentials``) — a raw ``resolved.lower()``
    # substring test misses them (the W1 separator-anchoring class, §7).
    path_match = resolved.replace("\\", "/").lower()
    for pattern in DENY_LIST:
        if pattern in path_match:
            return False, f"Access denied to sensitive path: {pattern}"

    if operation == "read":
        # Reads are allowed more broadly
        return True, "allowed"

    # Writes must be within allowed bases — boundary-anchored + case-normalized
    # (runtime_paths.within_any_base), so a mere-prefix SIBLING (``ora-project``
    # next to ``ora``) can't be treated as inside, on Windows or POSIX.
    if _rp.within_any_base(resolved, ALLOWED_BASES):
        return True, "allowed"

    return False, f"Path outside allowed locations: {resolved}"


def _prepare_file_call(tool_name: str, parameters: dict) -> dict:
    """Validate one exact file-tool target and handler contract before review."""

    if tool_name == "file_edit":
        supplied = [
            parameters[key] for key in ("file_path", "path")
            if key in parameters
        ]
        if len(supplied) > 1 and supplied[0] != supplied[1]:
            raise ValueError("file edit has conflicting target paths")
        raw_path = supplied[0] if supplied else None
    else:
        raw_path = parameters.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("file path must be a non-empty string")

    operation = "read" if tool_name == "file_read" else "write"
    valid, reason = validate_path(raw_path, operation)
    if not valid:
        raise ValueError(reason)
    handler_valid, handler_reason = _validate_path(raw_path)
    if not handler_valid:
        raise ValueError(handler_reason)

    canonical = os.path.realpath(os.path.expanduser(raw_path))
    if tool_name == "file_read":
        if model_read_blocked(canonical):
            raise ValueError("archived MindSpec self-spec is not model-readable")
        if not os.path.isfile(canonical):
            raise ValueError("file read target must be an existing regular file")
        try:
            with open(canonical, "r", encoding="utf-8") as stream:
                stream.read()
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"file read target is not readable UTF-8: {exc}") from exc
        parameters["path"] = canonical
    elif tool_name == "file_write":
        if not isinstance(parameters.get("content"), str):
            raise ValueError("file content must be a string")
        if os.path.exists(canonical) and not os.path.isfile(canonical):
            raise ValueError("file write target must be absent or a regular file")
        parent = os.path.dirname(canonical)
        while not os.path.lexists(parent):
            parent = os.path.dirname(parent)
        if not os.path.isdir(parent):
            raise ValueError("file write target has a non-directory ancestor")
        parameters["path"] = canonical
    else:
        old_string = parameters.get("old_string")
        if not isinstance(old_string, str) or not old_string:
            raise ValueError("file edit old_string must be a non-empty string")
        if not isinstance(parameters.get("new_string"), str):
            raise ValueError("file edit new_string must be a string")
        if not os.path.isfile(canonical):
            raise ValueError("file edit target must be an existing regular file")
        try:
            with open(canonical, "r", encoding="utf-8") as stream:
                current_content = stream.read()
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"file edit target is not readable UTF-8: {exc}") from exc
        occurrences = current_content.count(old_string)
        if occurrences != 1:
            raise ValueError(
                "file edit old_string must occur exactly once in the target"
            )
        parameters.pop("path", None)
        parameters["file_path"] = canonical
    return system_protection.capture_path_identity(canonical)


def _prepare_credential_call(parameters: dict) -> None:
    """Validate and normalize the credential handler's exact public contract."""

    action = parameters.get("action", "status")
    service = parameters.get("service")
    username = parameters.get("username")
    if not isinstance(action, str) or action.strip().lower() not in {
        "status", "store", "delete",
    }:
        raise ValueError("credential action must be status, store, or delete")
    if service != "ora":
        raise ValueError("credential service must be 'ora'")
    if not isinstance(username, str) or not username.strip():
        raise ValueError("credential username must be a non-empty string")
    try:
        import provider_registry as _provider_registry
    except ImportError:  # pragma: no cover - package-qualified import context
        from orchestrator import provider_registry as _provider_registry
    try:
        declared_usernames = set(
            _provider_registry.keyring_username_map().values()
        )
    except Exception as exc:
        raise ValueError("provider registry is unavailable") from exc
    if username.strip() not in declared_usernames:
        raise ValueError("credential username is not declared by the provider registry")
    normalized_action = action.strip().lower()
    if normalized_action == "store":
        value = parameters.get("value")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("credential value must be a non-empty string")
    parameters["action"] = normalized_action
    parameters["service"] = "ora"
    parameters["username"] = username.strip()


# ── Audit logging ─────────────────────────────────────────────────────────

# ``tool_events`` is the canonical, conversation-correlated dispatch sink.
# The older ``logs/session-*.log`` duplicate had no reader and no ownership
# field, so neither Stealth suppression nor Delete Forever could address it
# exactly. Retire that sink at runtime and remove its legacy files once rather
# than adding a second global JSONL rewrite surface.
_dispatch_log_retire_lock = threading.Lock()
_retired_dispatch_log_roots: set[str] = set()


def retire_legacy_session_logs(log_dir: str | os.PathLike[str] | None = None) -> dict:
    """Remove the retired, uncorrelated dispatcher session-log store.

    This cleanup is intentionally corpus-wide: the legacy format has no
    conversation identity, and the repository has no consumer for it. The
    correlated ``tool_events`` store remains authoritative. Symlinks are
    unlinked without following; unexpected entries are retained and reported.
    """
    root = Path(log_dir or LOG_DIR)
    removed: list[str] = []
    errors: list[str] = []
    try:
        if not root.exists():
            return {"removed": removed, "errors": errors}
        if root.is_symlink() or not root.is_dir():
            raise ValueError(f"refusing non-directory dispatcher log root {root}")
        for path in sorted(root.glob("session-*.log")):
            try:
                if path.is_symlink() or path.is_file():
                    path.unlink()
                    removed.append(str(path))
                elif path.exists():
                    raise ValueError(f"refusing non-file dispatcher log {path}")
            except Exception as exc:
                errors.append(f"{path}: {exc}")
    except Exception as exc:
        errors.append(str(exc))
    for error in errors:
        print(f"[dispatcher] legacy session-log retirement: {error}",
              file=sys.stderr, flush=True)
    return {"removed": removed, "errors": errors}


def _retire_legacy_session_logs_once() -> None:
    root_key = _rp.norm_key(LOG_DIR)
    with _dispatch_log_retire_lock:
        if root_key in _retired_dispatch_log_roots:
            return
        result = retire_legacy_session_logs(LOG_DIR)
        if not result["errors"]:
            _retired_dispatch_log_roots.add(root_key)
        if result["removed"]:
            print(
                f"[dispatcher] retired {len(result['removed'])} legacy "
                "uncorrelated session log(s); tool_events is authoritative",
                file=sys.stderr,
                flush=True,
            )


def _log_dispatch(tool_name: str, parameters: dict, classification: dict | None,
                  permission: str, result_summary: str, duration_ms: int):
    """Compatibility seam: retire the duplicate sink; persist nothing here.

    Machine-readable dispatch logging happens through ``tool_events.record``
    below, which already carries conversation identity and suppresses Stealth.
    Keeping this call in place avoids destabilizing the dispatch control flow
    while making every old early-return call harmless.
    """
    del tool_name, parameters, classification, permission, result_summary, duration_ms
    _retire_legacy_session_logs_once()


# ── Consecutive call limiter ──────────────────────────────────────────────

@contextlib.contextmanager
def tool_loop_context():
    """Run one agentic tool loop with a fresh consecutive-call counter.

    Restoring the caller's value on exit matters for nested or sequential
    loops in the same request context, while the ContextVar itself keeps
    parallel request contexts independent.
    """
    token = _CONSECUTIVE_TOOL_CTX.set((None, 0))
    try:
        yield
    finally:
        _CONSECUTIVE_TOOL_CTX.reset(token)


def _current_consecutive_count() -> int:
    return _CONSECUTIVE_TOOL_CTX.get()[1]


def _check_consecutive(tool_name: str) -> str | None:
    """Track consecutive calls. Returns a warning message or None."""
    previous_tool, count = _CONSECUTIVE_TOOL_CTX.get()

    if tool_name == previous_tool:
        count += 1
    else:
        count = 1
    _CONSECUTIVE_TOOL_CTX.set((tool_name, count))

    if count >= 8:
        return (f"Maximum consecutive calls reached for {tool_name}. "
                "Report the current state to the user and ask for guidance.")
    if count >= 5:
        return (f"You have called {tool_name} {count} times consecutively. "
                "Pause and assess: are you making progress or repeating the same approach? "
                "State your diagnosis of the problem before making another attempt.")
    return None


def reset_consecutive():
    """Reset the consecutive call counter (called when model produces non-tool response)."""
    _CONSECUTIVE_TOOL_CTX.set((None, 0))


# ── MCP routing ───────────────────────────────────────────────────────────

_mcp_client = None


def set_mcp_client(client):
    """Set the MCP client module for routing mcp_ prefixed tool calls."""
    global _mcp_client
    _mcp_client = client


def _normalize_mcp_result(result, result_str: str) -> tuple[str, bool]:
    """Make both MCP failure result shapes explicit to downstream receipts."""

    if not isinstance(result, dict):
        return result_str, False
    failed = "error" in result or result.get("isError") is True
    if not failed:
        return result_str, False
    return f"[MCP error — {result_str}]", True


def _inject_hook_outputs(result, result_str: str,
                         hook_outputs: list[str]) -> str:
    """Add hook stdout to the model-facing result without invalidating JSON.

    ``web_fetch`` has a deterministic consumer that parses the dispatcher's
    JSON and forwards only its ``markdown`` (or ``error``) field. Put hook
    output in that field so it reaches that consumer exactly once. Other
    structured results retain their root shape and carry a reserved metadata
    member/item; scalar results keep the historical text suffix.
    """
    outputs = [str(output) for output in hook_outputs if str(output)]
    if not outputs:
        return result_str

    hook_text = "\n".join(f"[hook: {output}]" for output in outputs)
    if isinstance(result, dict):
        model_result = dict(result)
        if "markdown" in model_result:
            markdown = model_result.get("markdown")
            if isinstance(markdown, str) and markdown.strip():
                # Prepend so the deterministic formatter's content cap cannot
                # truncate the injected output off the end.
                model_result["markdown"] = f"{hook_text}\n\n{markdown}"
            else:
                error = str(model_result.get("error") or "").strip()
                model_result["error"] = (
                    f"{error}; {hook_text}" if error else hook_text
                )
        else:
            existing = model_result.get("_ora_hook_output")
            if existing is None:
                model_result["_ora_hook_output"] = outputs
            elif isinstance(existing, list):
                model_result["_ora_hook_output"] = [*existing, *outputs]
            else:
                model_result["_ora_hook_output"] = [existing, *outputs]
        return json.dumps(model_result)

    if isinstance(result, list):
        return json.dumps([
            *result,
            {"_ora_hook_output": outputs},
        ])

    return f"{result_str}\n{hook_text}"


# ── Main dispatch function ────────────────────────────────────────────────

def _resolve_call_axes(tool_name: str, entry: dict | None,
                       parameters: dict,
                       prepared_command: PreparedCommand | None = None,
                       ) -> tuple[dict, dict | None, dict | None]:
    """Resolve the capability axes for THIS call.

    Returns (axes, classification, shell_profile). Order of resolution:
    registry defaults → dynamic axes_fn → shell profile (bash) → per-path
    sensitivity → protected-config escalation. Unknown anywhere → fail
    closed ({irreversible, secret, unknown: True})."""
    classification = None
    shell_profile = None

    if tool_name.startswith("mcp_"):
        resolved = tool_events.mcp_policy(tool_name, parameters)
        parameters.clear()
        parameters.update(resolved["parameters"])
        axes = dict(resolved["axes"])
        axes["_mcp_action"] = resolved["action"]
        axes["_mcp_selectors"] = resolved["selectors"]
        axes["_mcp_destructive"] = resolved["destructive"]
        return axes, None, None

    axes = {"category": entry.get("category", "execute"),
            "mutability": entry.get("mutability", "irreversible"),
            "sensitivity": entry.get("sensitivity", "secret"),
            "egress": entry.get("egress", "external")}
    axes_fn = entry.get("axes_fn")
    if callable(axes_fn):
        try:
            axes.update(axes_fn())
        except Exception:
            axes.update(tool_events.FAIL_CLOSED)

    if tool_name == "bash_execute":
        if prepared_command is None:
            # Keep the direct inspection helper compatible for legacy callers
            # that invoke ``_resolve_call_axes`` themselves.  The production
            # dispatcher prepares once before reaching this function and
            # passes that same object through, so this branch cannot create a
            # second parse on the real execution path.
            try:
                prepared_command = prepare_command(
                    str(parameters.get("command", "")),
                    cwd=parameters.get("cwd") or WORKSPACE,
                )
            except CommandPreparationError as exc:
                # Legacy inspection callers expect a classification object
                # even when the command is refused before preparation.  The
                # real dispatch path rejects this same error before entering
                # the resolver; this compatibility branch has no execution
                # authority and never reaches a handler.
                command_text = str(parameters.get("command", ""))
                lower = command_text.casefold()
                protected_hint = (
                    "mindspec" in lower
                    and (
                        "self-spec" in lower
                        or "self-spe[cd]" in lower
                        or "mindspec/*.md" in lower
                        or "mindspec/{default,self-spec}" in lower
                        or "mindspec/**/self-spec" in lower
                        or "{mindspec,personas}" in lower
                    )
                ) or "self-spec" in lower or (
                    "/ora/*/" in lower
                    or "/ora/{" in lower
                    or ("/ora" in lower and any(
                        lower.lstrip().startswith(prefix)
                        for prefix in ("grep ", "rg ", "find ")
                    ))
                )
                axes.update(tool_events.FAIL_CLOSED)
                shell_profile = resolve_shell_profile(
                    command_text, cwd=parameters.get("cwd") or WORKSPACE,
                )
                classification = {
                    "level": "blocked" if protected_hint else "rejected",
                    "reason": (
                        "archived MindSpec self-spec is not model-readable"
                        if protected_hint else str(exc)
                    ),
                }
                return axes, classification, shell_profile
        classification = classify_command(prepared_command)
        _cwd = parameters.get("cwd") or WORKSPACE
        shell_profile = prepared_command.profile()
        axes["mutability"] = shell_profile["mutability"]
        axes["sensitivity"] = shell_profile["sensitivity"]
        axes["egress"] = shell_profile["egress"]
        # There is no shell interior: exact argv and executable identity are
        # bound, but the invoked program remains a boundary-observed process.
        axes["enforcement"] = "boundary_only"
        if shell_profile.get("unknown"):
            axes["unknown"] = True
        # Per-path escalation: a shell read of a secret path gates like
        # file_read; a shell write into protected config gates like
        # file_write. Without this, 'cat ~/.ssh/id_rsa' or
        # 'echo x > config/hooks/y' would slip past the file-tool gates. The
        # cwd itself is checked too (cd into a secret dir is a red flag).
        def _abs_target(_t):
            _e = os.path.expanduser(_t)
            return _e if os.path.isabs(_e) else os.path.join(_cwd, _e)

        for _p in (shell_profile.get("read_paths", []) +
                   shell_profile.get("write_paths", []) + [_cwd]):
            axes["sensitivity"] = tool_events.max_sensitivity(
                axes.get("sensitivity", "private"),
                tool_events.resolve_path_sensitivity(_abs_target(_p)))
        read_scopes = shell_profile.get("authority_scopes", [])
        if any(
            model_read_blocked(
                _abs_target(_read_path),
                shell_scope=True,
                recursive=any(
                    scope.get("path") == _read_path and scope.get("recursive")
                    for scope in read_scopes
                ),
            )
            for _read_path in shell_profile.get("read_paths", [])
        ):
            classification = {
                "level": "blocked",
                "reason": "archived MindSpec self-spec is not model-readable",
            }
        for _wp in shell_profile.get("write_paths", []):
            if tool_events.is_protected_config_path(_abs_target(_wp)):
                axes["mutability"] = "irreversible"
                axes["protected_config"] = True
        # A cwd inside protected config is itself a red flag.
        if tool_events.is_protected_config_path(_cwd):
            axes["mutability"] = tool_events.max_mutability(
                axes.get("mutability", "read"), "irreversible")
            axes["protected_config"] = True

    if tool_name == "credential_store":
        credential_action = str(parameters.get("action") or "status").lower()
        if credential_action == "status":
            axes.update({"category": "read", "mutability": "read",
                         "sensitivity": "private", "egress": "none"})
        elif credential_action in {"store", "delete"}:
            axes.update({"category": "write", "mutability": "reversible_write",
                         "sensitivity": "secret", "egress": "none"})
        else:
            axes.update(tool_events.FAIL_CLOSED)

    # Read-only tools that take an arbitrary directory/path argument reach
    # the filesystem just like file_read — a grep or listing of ~/.ssh
    # exposes the same content, so resolve sensitivity on their target too.
    if tool_name in ("search_files", "list_directory"):
        _target = (parameters.get("directory") if tool_name == "search_files"
                   else parameters.get("path", ""))
        if _target:
            axes["sensitivity"] = tool_events.max_sensitivity(
                axes.get("sensitivity", "private"),
                tool_events.resolve_path_sensitivity(_target))

    if tool_name in ("file_read", "file_write", "file_edit"):
        file_path = parameters.get("path", parameters.get("file_path", ""))
        if file_path:
            axes["sensitivity"] = tool_events.max_sensitivity(
                axes.get("sensitivity", "private"),
                tool_events.resolve_path_sensitivity(file_path))
            # A write into enforcement-relevant config (hooks, MCP config,
            # manifests, orchestrator code) is gated regardless of the
            # tool's own axes — one allowed reversible write must not be
            # able to install un-gated execution for later.
            if tool_name in ("file_write", "file_edit") and \
                    tool_events.is_protected_config_path(file_path):
                axes["mutability"] = "irreversible"
                axes["protected_config"] = True

    return axes, classification, shell_profile


def dispatch(tool_name: str, parameters: dict,
             permission_callback=None) -> str:
    """Dispatch a tool call through the unified permission and safety pipeline.

    Execution Review Phase 1: every call resolves capability axes, passes
    the execution gate (which runs BEFORE and independently of the
    permission mode — auto-approve cannot carry irreversible / unknown /
    secret / sensitive actions), and leaves one machine-readable record in
    the tool-event log. MCP calls now go through the same gate, consecutive
    limiter, and logging instead of returning early.

    Args:
        tool_name: Name of the tool to call.
        parameters: Dict of parameters for the tool.
        permission_callback: Optional callback for browser-based approval.

    Returns:
        String result of the tool call.
    """
    if not _TOOLS_LOADED:
        return "[Tools unavailable — import failed at startup]"

    start = time.time()
    parameters = dict(parameters or {})
    is_mcp = tool_name.startswith("mcp_")
    entry = TOOL_REGISTRY.get(tool_name)

    if entry is None and not is_mcp:
        tool_events.record({
            "event": "tool", "action": tool_name, "category": "execute",
            **tool_events.FAIL_CLOSED,
            "gate": {"decision": "blocked", "why": "unregistered tool"},
            "exit": {"ok": False, "reason": "unknown tool"},
            "enforcement_model": "in_harness",
        })
        return f"[Unknown tool: {tool_name}]"

    # Structural command and destination refusal belongs before the generic
    # gate, one-shot-token consumption, hooks, handler, or any effect.
    prepared_command = None
    if tool_name == "bash_execute":
        try:
            prepared_command = prepare_command(
                str(parameters.get("command") or ""),
                cwd=parameters.get("cwd") or WORKSPACE,
            )
        except CommandPreparationError as exc:
            tool_events.record({
                "event": "gate", "action": "bash_execute", "category": "execute",
                **tool_events.FAIL_CLOSED,
                "gate": {"decision": "blocked", "why": str(exc)},
                "exit": {"ok": False, "reason": "invalid command structure"},
                "enforcement_model": "in_harness",
            })
            return f"[SYSTEM PROTECTION — {exc}]"
    elif tool_name == "web_fetch":
        try:
            try:
                import network_policy as _network_policy
            except ImportError:  # pragma: no cover
                from orchestrator import network_policy as _network_policy
            parameters["url"] = _network_policy.validate_public_url(
                str(parameters.get("url") or ""),
            ).url
        except _network_policy.NetworkPolicyError as exc:
            refusal_event = {
                "event": "gate", "action": "web_fetch", "category": "read",
                "mutability": "read", "sensitivity": "public", "egress": "external",
                "gate": {"decision": "blocked", "why": str(exc)},
                "exit": {"ok": False, "reason": "invalid network destination"},
                "enforcement_model": "in_harness",
            }
            refusal_event["destination_classification"] = "refused-non-public"
            refusal_event["third_party_forwarding"] = {
                "provider": "jina-reader", "forwarded": False,
                "reason": "invalid-destination",
            }
            tool_events.record(refusal_event)
            return f"[SYSTEM PROTECTION — {exc}]"

    prepared_mcp = None
    prepared_mcp_client = None
    if is_mcp:
        try:
            resolved_mcp = tool_events.mcp_policy(tool_name, parameters)
            parameters = dict(resolved_mcp["parameters"])
            if tool_name in BOUND_BROWSER_TOOLS or tool_name == "mcp_github_create_repository" or (
                tool_name == "mcp_github_fork_repository"
                and not parameters.get("organization")
            ):
                prepared_mcp_client = _mcp_client
                if prepared_mcp_client is None:
                    raise ValueError("MCP client is unavailable")
                prepared_mcp = prepared_mcp_client.prepare_mcp_tool(
                    tool_name, parameters,
                )
        except Exception as exc:
            tool_events.record({
                "event": "gate", "action": tool_name, "category": "execute",
                **tool_events.FAIL_CLOSED,
                "gate": {"decision": "blocked", "why": str(exc)},
                "exit": {"ok": False, "reason": "invalid MCP authority scope"},
                "enforcement_model": "in_harness",
            })
            return f"[SYSTEM PROTECTION — {exc}]"

    file_pre_state = None
    if tool_name in {"file_read", "file_write", "file_edit"}:
        try:
            file_pre_state = _prepare_file_call(tool_name, parameters)
        except (OSError, ValueError) as exc:
            tool_events.record({
                "event": "gate", "action": tool_name,
                "category": entry.get("category", "execute"),
                "mutability": entry.get("mutability", "irreversible"),
                "sensitivity": entry.get("sensitivity", "private"),
                "egress": entry.get("egress", "none"),
                "gate": {"decision": "blocked", "why": str(exc)},
                "exit": {"ok": False, "reason": "invalid file target"},
                "enforcement_model": "in_harness",
            })
            return f"[Path validation failed: {exc}]"
    elif tool_name == "credential_store":
        try:
            _prepare_credential_call(parameters)
        except ValueError as exc:
            tool_events.record({
                "event": "gate", "action": tool_name,
                "category": "write", "mutability": "irreversible",
                "sensitivity": "secret", "egress": "none",
                "gate": {"decision": "blocked", "why": str(exc)},
                "exit": {"ok": False, "reason": "invalid credential request"},
                "enforcement_model": "in_harness",
            })
            return f"[SYSTEM PROTECTION — {exc}]"

    # Consecutive call check (includes MCP tools now)
    warning = _check_consecutive(tool_name)
    if warning and _current_consecutive_count() >= 8:
        duration = int((time.time() - start) * 1000)
        _log_dispatch(tool_name, parameters, None, "blocked-consecutive",
                      warning, duration)
        return warning

    axes, classification, shell_profile = _resolve_call_axes(
        tool_name, entry, parameters, prepared_command)
    if tool_name == "file_edit" or (
        tool_name == "file_write"
        and file_pre_state is not None
        and file_pre_state.get("kind") != "absent"
    ):
        axes["mutability"] = "irreversible"

    gate_parameters = dict(parameters)
    if prepared_command is not None:
        gate_parameters["_prepared_command"] = prepared_command.binding()
    protection_parameters = dict(gate_parameters)
    if prepared_mcp is not None:
        # Keep the raw gate identity stable so a replacement child invalidates
        # the existing approval as stale, including after an ABA restoration.
        protection_parameters["_mcp_child_launch"] = prepared_mcp.launch_id
        if prepared_mcp.browser_binding is not None:
            protection_parameters["_mcp_browser_target"] = prepared_mcp.browser_binding

    # G1.22A: classification at the same pre-effect boundary as the existing
    # execution gate.  The generic capability axes cannot express absolute
    # whole-system prohibitions or distinguish a reviewed non-channel external
    # write from an ordinary reversible local write.
    protection_policy = system_protection.classify_tool_call(
        tool_name, parameters, axes, shell_profile=shell_profile,
        prepared_command=prepared_command,
    )
    if protection_policy.outcome == "deny":
        duration = int((time.time() - start) * 1000)
        tool_events.record({
            "event": "gate", "action": protection_policy.action,
            "category": axes.get("category", "execute"),
            "mutability": axes.get("mutability", "irreversible"),
            "sensitivity": axes.get("sensitivity", "secret"),
            "egress": axes.get("egress", "external"),
            "gate": {"decision": "blocked", "why": protection_policy.reason},
            "exit": {"ok": False, "reason": protection_policy.policy_code},
            "duration_ms": duration, "enforcement_model": "in_harness",
        })
        return f"[SYSTEM PROTECTION — {protection_policy.reason}]"
    if protection_policy.outcome == "review":
        # Reuse the one-shot Paused approval path.  Escalating the resolved
        # axes here makes auto-approve mechanically unable to carry the call.
        axes["mutability"] = "irreversible"
        axes["protection_policy"] = protection_policy.policy_code

    protection_pre_state = []
    protection_approval_binding = None
    if protection_policy.outcome == "review":
        try:
            for selector in protection_policy.selectors:
                protection_pre_state.append(
                    system_protection.capture_selector_identity(selector)
                )
            review_request, review_digest = (
                system_protection.prepare_protection_request(
                    protection_policy,
                    params_digest=system_protection.params_digest(protection_parameters),
                    pre_state=protection_pre_state,
                    surface="tool_dispatcher",
                    command_binding=(
                        prepared_command.binding()
                        if prepared_command is not None else None
                    ),
                )
            )
            protection_approval_binding = {
                "request_digest": review_digest,
                "selectors": review_request["selectors"],
            }
        except system_protection.SystemProtectionError as exc:
            return f"[SYSTEM PROTECTION — {exc}]"

    # BLOCKED bash patterns short-circuit exactly as before.
    if classification and classification["level"] == "blocked":
        duration = int((time.time() - start) * 1000)
        _log_dispatch(tool_name, parameters, classification, "blocked",
                      classification["reason"], duration)
        tool_events.record({
            "event": "shell", "action": "bash:blocked",
            "category": "execute", "mutability": axes["mutability"],
            "sensitivity": axes["sensitivity"], "egress": axes["egress"],
            "args_redacted": {"command": parameters.get("command", "")[:200]},
            "gate": {"decision": "blocked", "why": classification["reason"]},
            "exit": {"ok": False, "reason": "blocked pattern"},
            "duration_ms": duration, "enforcement_model": "in_harness",
        })
        return f"[BLOCKED] {classification['reason']}"

    # The sanctioned secret channel: credential_store retrieves for a
    # service with a standing allow pass with existence-only logging (the
    # event keeps sensitivity=secret, which redacts to existence-only).
    # Everything else with secret sensitivity hits the gate below.
    queue_extra = None
    gate_axes = dict(axes)
    if tool_name == "credential_store":
        service = parameters.get("service", "")
        scope = f"credential_store:{service}"
        queue_extra = {"standing_scope": scope}
        if service and tool_events.has_standing_allow(scope):
            gate_axes["sensitivity"] = "private"  # standing allow → pass gate

    # A live human prompt is the gate's approval channel when one exists
    # (terminal approve-each / browser callback). Under auto-approve there
    # is no human present, so blocked actions queue instead.
    interactive = None
    if _permission_mode != "auto-approve":
        def interactive(action, params, gate_classification):
            if permission_callback:
                return permission_callback(action, params, gate_classification)
            print(f"\n🔐 GATE — approval required: {action}")
            print(f"   Reason: {gate_classification.get('reason', '')}")
            print(f"   Parameters: {json.dumps(params, default=str)[:300]}")
            resp = input("   Approve this action once? (y/n): ").strip().lower()
            return resp in ("y", "yes")

    description = (prepared_command.audit_command if prepared_command else None) or \
        parameters.get("command") or \
        parameters.get("path", parameters.get("file_path")) or \
        parameters.get("url") or parameters.get("query") or \
        parameters.get("service", "")
    # Recheck before the generic gate can consume a one-shot approval.  The
    # executor repeats this immediately before spawn on the SAME object.
    if prepared_command is not None:
        try:
            revalidate_prepared_command(prepared_command)
        except CommandPreparationError as exc:
            return f"[SYSTEM PROTECTION — {exc}]"
    if file_pre_state is not None:
        current_file_state = system_protection.capture_selector_identity(
            file_pre_state["selector"],
        )
        if current_file_state != file_pre_state:
            return "[SYSTEM PROTECTION — file target changed after validation]"
    if prepared_mcp is not None:
        try:
            prepared_mcp_client.revalidate_prepared_call(prepared_mcp)
        except Exception as exc:
            return f"[SYSTEM PROTECTION — {exc}]"

    decision = tool_events.gate(
        tool_name, gate_axes, params=gate_parameters,
        description=str(description or "")[:200],
        model_facing=True, interactive_approver=interactive,
        queue_extra=queue_extra,
        approval_binding=protection_approval_binding,
    )
    if not decision.allowed:
        duration = int((time.time() - start) * 1000)
        _log_dispatch(tool_name, parameters, classification,
                      f"gate-{decision.decision}", decision.why, duration)
        return decision.message or f"[GATED — {decision.why}]"

    protection_execution = None
    if protection_policy.outcome == "review":
        if not decision.approval_id:
            return "[SYSTEM PROTECTION — protected action lacks consumed approval identity]"
        try:
            protection_execution = system_protection.begin_execution(
                protection_policy,
                approval_id=decision.approval_id,
                approval_action=tool_name,
                approval_args_hash=tool_events.normalize_args_hash(
                    tool_name, gate_parameters,
                ),
                params_digest=system_protection.params_digest(protection_parameters),
                pre_state=protection_pre_state,
                surface="tool_dispatcher",
                command_binding=(
                    prepared_command.binding()
                    if prepared_command is not None else None
                ),
            )
        except system_protection.SystemProtectionError as exc:
            duration = int((time.time() - start) * 1000)
            tool_events.record({
                "event": "gate", "action": protection_policy.action,
                "category": axes.get("category", "execute"),
                "mutability": axes.get("mutability", "irreversible"),
                "sensitivity": axes.get("sensitivity", "private"),
                "egress": axes.get("egress", "none"),
                "gate": {"decision": "blocked", "why": str(exc)},
                "exit": {"ok": False, "reason": "protection audit unavailable"},
                "duration_ms": duration, "enforcement_model": "in_harness",
            })
            return f"[SYSTEM PROTECTION — {exc}]"

    # Permission gate (existing approve tier). Skipped when the gate
    # already collected a live human approval — one prompt, not two.
    if entry and entry["permission"] == "approve" and \
            decision.decision != "approved":
        approved = request_permission(tool_name, parameters, classification,
                                      callback=permission_callback)
        if not approved:
            duration = int((time.time() - start) * 1000)
            _log_dispatch(tool_name, parameters, classification, "user-denied",
                          "Permission denied by user", duration)
            return f"[Permission denied for {tool_name}]"
        permission_status = "user-approved"
    elif decision.decision == "approved":
        permission_status = "gate-approved"
    else:
        permission_status = "auto-approved"

    # Pre-tool hooks
    pre_hook_outputs = fire_hooks(
        "pre_tool", {"tool_name": tool_name, "parameters": parameters}
    )

    # Execute
    result = None
    execution_error = False
    structured_result_valid = False
    try:
        effect_context = (
            system_protection.protected_effect(protection_execution)
            if protection_execution is not None
            else contextlib.nullcontext()
        )
        with effect_context:
            if file_pre_state is not None:
                current_file_state = system_protection.capture_selector_identity(
                    file_pre_state["selector"],
                )
                if current_file_state != file_pre_state:
                    raise system_protection.ProtectionDenied(
                        "file target changed immediately before effect"
                    )
            if is_mcp:
                if prepared_mcp is not None:
                    result = prepared_mcp_client.call_mcp_tool(
                        tool_name, parameters, prepared_call=prepared_mcp,
                    )
                elif _mcp_client and hasattr(_mcp_client, 'call_mcp_tool'):
                    result = _mcp_client.call_mcp_tool(tool_name, parameters)
                else:
                    result = f"[MCP unavailable — no client for {tool_name}]"
            elif tool_name in ("web_fetch", "web_search"):
                # Execution Review Phase 8 (§2.3): the dispatcher records these
                # itself below, so suppress the tools-module LIBRARY GUARD for
                # the duration of this SYNCHRONOUS handler call (thread-local,
                # same-thread exact — the double-record kill, judge OQ-5).
                with tool_events.suppress_library_recording():
                    result = entry["handler"](parameters)
            elif tool_name == "bash_execute":
                result = _wrap_bash_execute(parameters, prepared_command)
            else:
                result = entry["handler"](parameters)
        if isinstance(result, (dict, list)):
            result_str = json.dumps(result)
            structured_result_valid = True
        else:
            result_str = str(result)
        if tool_name == "file_write" and result_str.startswith((
            "BLOCKED:", "Write error:",
        )):
            execution_error = True
        elif tool_name == "file_edit" and isinstance(result, dict) and not bool(
            result.get("success")
        ):
            execution_error = True
        if is_mcp:
            result_str, execution_error = _normalize_mcp_result(
                result, result_str,
            )
            if execution_error:
                structured_result_valid = False
    except Exception as e:
        result_str = f"[Tool error — {tool_name}: {e}]"
        execution_error = True

    if protection_execution is not None:
        protected_ok = not execution_error and not result_str.startswith((
            "[Tool error", "[MCP error", "[MCP unavailable", "[Permission",
            "[Path validation",
        ))
        post_state = []
        try:
            for selector in protection_policy.selectors:
                post_state.append(
                    system_protection.capture_selector_identity(selector)
                )
            system_protection.complete_execution(
                protection_execution,
                ok=protected_ok,
                result=result_str,
                post_state=post_state,
            )
        except system_protection.SystemProtectionError as exc:
            # The effect may already have occurred; never report ordinary
            # success without its terminal receipt.  The write-ahead record
            # remains a restart-visible broken-infrastructure signal.
            result_str = f"[SYSTEM PROTECTION BROKEN INFRASTRUCTURE — {exc}]"
            structured_result_valid = False

    # Post-tool hooks
    hook_outputs = pre_hook_outputs + fire_hooks(
        "post_tool", {"tool_name": tool_name, "result": result_str[:500]}
    )
    model_result_str = _inject_hook_outputs(
        result if structured_result_valid else None,
        result_str,
        hook_outputs,
    )

    duration = int((time.time() - start) * 1000)
    _log_dispatch(tool_name, parameters, classification, permission_status,
                  result_str[:200], duration)

    # Machine-readable tool event (the dispatch-signal substrate).
    try:
        error = execution_error or result_str.startswith((
            "[Tool error", "[MCP error", "[MCP unavailable", "[Permission",
            "[Path validation",
        ))
        # Shell results are dicts with a returncode — string matching on
        # the serialized JSON would misreport a failed command as ok.
        if tool_name == "bash_execute" and isinstance(result, dict):
            error = error or (result.get("returncode", 0) != 0) or \
                bool(result.get("timed_out"))
        if tool_name == "web_fetch" and isinstance(result, dict):
            error = error or bool(result.get("error"))
        reads = None
        if tool_name == "file_read":
            p = parameters.get("path", "")
            reads = [{"what": p, "where": "local",
                      "content_hash": hashlib.sha256(
                          result_str.encode("utf-8", "replace")).hexdigest()[:16]}]
        elif tool_name == "web_fetch":
            # Phase 8 (OQ-6): hash the CONTENT ONLY (markdown body) — hashing
            # the serialized result dict included fetched_at, so two fetches
            # of byte-identical content hashed differently, defeating the
            # hash's one consumer (provenance content identity).
            # Phase 8 (pre-check fold): sanitize the URL — the dispatcher path
            # SUPPRESSES the library guard (the only other sanitize site), and
            # web_fetch events are public-sensitivity, so a raw signed URL
            # (sig= / X-Amz-Signature=) would ride reads[].what into the event
            # log, the public-safe candidates, and the packet.
            _wf_body = (result.get("markdown") or ""
                        ) if isinstance(result, dict) else result_str
            reads = [{"what": tool_events.sanitize_url(
                          parameters.get("url", "")),
                      "where": "network",
                      "chars": len(_wf_body),
                      "content_hash": hashlib.sha256(
                          _wf_body.encode("utf-8", "replace")).hexdigest()[:16]}]
        elif tool_name == "web_search":
            reads = [{"what": f"query:{parameters.get('query', '')}",
                      "where": "network"}]
        elif tool_name == "knowledge_search":
            reads = [{"what": f"chromadb:{parameters.get('collection', 'knowledge')}"
                              f":{parameters.get('query', '')[:80]}",
                      "where": "local"}]
        event_kind = "mcp" if is_mcp else (
            "shell" if tool_name == "bash_execute" else "tool")
        action = tool_name
        if shell_profile:
            action = f"bash:{shell_profile.get('profile', 'unknown')}"
        # Phase 8 (pre-check fold): sanitize URL-bearing args for the two web
        # tools before they enter a public-sensitivity event (mirror of the
        # reads[].what sanitization above — args_redacted was the second
        # unsanitized path for a signed URL).
        _args_view = {k: str(v)[:200] for k, v in (parameters or {}).items()}
        if tool_name == "bash_execute" and prepared_command is not None:
            _args_view["command"] = prepared_command.audit_command[:200]
            _args_view["prepared"] = {
                "argv_sha256": hashlib.sha256(
                    json.dumps(list(prepared_command.argv)).encode("utf-8")
                ).hexdigest(),
                "cwd": prepared_command.cwd,
                "env_digest": prepared_command.env_digest,
                "executable": prepared_command.executable.path,
            }
        if tool_name in ("web_fetch", "web_search"):
            _args_view = {k: (tool_events.sanitize_url(v)[:200]
                              if k in ("url", "query") else v)
                          for k, v in _args_view.items()}
        event_record = {
            "event": event_kind, "action": action,
            "category": axes.get("category", "execute"),
            "mutability": axes["mutability"],
            "sensitivity": axes["sensitivity"],
            "egress": axes["egress"],
            "mutated": (axes["mutability"] != "read") and not error,
            "reads": reads,
            "args_redacted": _args_view,
            "exit": {"ok": not error,
                     "reason": result_str[:120] if error else ""},
            "duration_ms": duration,
            "gate": {"decision": decision.decision, "why": decision.why,
                     "approval_id": decision.approval_id},
            "enforcement_model": axes.get("enforcement", "in_harness"),
        }
        if tool_name == "web_fetch" and isinstance(result, dict):
            event_record["destination_classification"] = str(
                result.get("destination_classification") or "unknown",
            )[:80]
            forwarding = result.get("third_party_forwarding")
            if isinstance(forwarding, dict):
                event_record["third_party_forwarding"] = {
                    "provider": str(forwarding.get("provider") or "")[:80],
                    "forwarded": bool(forwarding.get("forwarded")),
                    "reason": str(forwarding.get("reason") or "")[:120],
                }
        tool_events.record(event_record)
    except Exception:
        pass  # recorder is best-effort; its own failure path sets health

    # Inject consecutive call warning as prefix
    if warning and _current_consecutive_count() >= 5:
        model_result_str = f"[SYSTEM: {warning}]\n\n{model_result_str}"

    return model_result_str
