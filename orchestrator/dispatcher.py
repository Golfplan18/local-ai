"""Unified tool dispatcher with permission gating, path validation,
command classification, audit logging, and consecutive call limiting."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime

WORKSPACE = os.path.expanduser("~/local-ai/")
VAULT = os.path.expanduser("~/Documents/vault/")
CONVERSATIONS = os.path.expanduser("~/Documents/conversations/")
LOG_DIR = os.path.join(WORKSPACE, "logs")

# ── Tool imports ───────────────────────────────────────────────────────────
import sys
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/tools/"))

try:
    from web_search import web_search
    from file_ops import file_read, file_write, _validate_path
    from knowledge_search import knowledge_search
    from browser_open import browser_open
    from credential_store import credential_store
    from browser_evaluate import browser_evaluate
    from api_evaluate import api_evaluate
    from bash_execute import (execute_command, classify_command,
                              stop_process, cleanup_all)
    from file_edit import edit_file
    from search_files import grep_files, list_directory
    from subagent import spawn_subagent
    _TOOLS_LOADED = True
except ImportError as e:
    print(f"[dispatcher] Tool import warning: {e}")
    _TOOLS_LOADED = False

# Non-critical imports (hooks, MCP)
try:
    from hooks import fire_hooks, load_hooks as _load_hooks
    _load_hooks()
except ImportError:
    def fire_hooks(event, context=None): return []

try:
    from mcp_client import get_manager as _get_mcp_manager, shutdown as _mcp_shutdown
except ImportError:
    _get_mcp_manager = None
    _mcp_shutdown = None


# ── Tool Registry ─────────────────────────────────────────────────────────

def _wrap_web_search(params):
    return web_search(params.get("query", ""), params.get("max_results", 5))

def _wrap_file_read(params):
    return file_read(params.get("path", ""))

def _wrap_file_write(params):
    return file_write(params.get("path", ""), params.get("content", ""))

def _wrap_file_edit(params):
    return edit_file(params.get("file_path", params.get("path", "")),
                     params.get("old_string", ""),
                     params.get("new_string", ""))

def _wrap_bash_execute(params):
    return execute_command(
        params.get("command", ""),
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
    return knowledge_search(
        params.get("query", ""),
        params.get("collection", "knowledge"),
        params.get("n_results", 5),
    )

def _wrap_browser_open(params):
    return browser_open(params.get("url", ""))

def _wrap_credential_store(params):
    return credential_store(
        params.get("action", "retrieve"),
        params.get("service", ""),
        params.get("username", ""),
        params.get("value"),
    )

def _wrap_browser_evaluate(params):
    return browser_evaluate(
        params.get("service", "claude"),
        prompt=params.get("prompt", ""),
        task_summary=params.get("task_summary", ""),
        artifact=params.get("artifact", ""),
        evaluation_focus=params.get("evaluation_focus", ""),
    )

def _wrap_api_evaluate(params):
    return api_evaluate(
        task_summary=params.get("task_summary", ""),
        artifact=params.get("artifact", ""),
        evaluation_focus=params.get("evaluation_focus", ""),
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

def _wrap_schedule_task(params):
    """Create a scheduled task entry."""
    import uuid
    from datetime import datetime as _dt
    registry_path = os.path.join(WORKSPACE, "config/scheduled-tasks.json")
    try:
        with open(registry_path) as f:
            registry = json.load(f)
    except Exception:
        registry = {"tasks": [], "settings": {"max_concurrent": 3}}

    task_id = str(uuid.uuid4())[:8]
    entry = {
        "id": task_id,
        "prompt": params.get("prompt", ""),
        "interval_minutes": params.get("interval_minutes", 30),
        "model_slot": params.get("model_slot", "small"),
        "timeout_minutes": 10,
        "created_at": _dt.now().isoformat(),
        "last_run": None,
        "run_count": 0,
        "active": True,
    }
    registry["tasks"].append(entry)
    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)
    return f"Scheduled task {task_id}: '{entry['prompt'][:60]}' every {entry['interval_minutes']}m"


TOOL_REGISTRY = {
    "web_search":       {"handler": _wrap_web_search,       "permission": "auto",    "category": "read"},
    "file_read":        {"handler": _wrap_file_read,        "permission": "auto",    "category": "read"},
    "file_write":       {"handler": _wrap_file_write,       "permission": "approve", "category": "write"},
    "file_edit":        {"handler": _wrap_file_edit,        "permission": "approve", "category": "write"},
    "bash_execute":     {"handler": _wrap_bash_execute,     "permission": "approve", "category": "execute"},
    "search_files":     {"handler": _wrap_search_files,     "permission": "auto",    "category": "read"},
    "list_directory":   {"handler": _wrap_list_directory,   "permission": "auto",    "category": "read"},
    "knowledge_search": {"handler": _wrap_knowledge_search, "permission": "auto",    "category": "read"},
    "browser_open":     {"handler": _wrap_browser_open,     "permission": "approve", "category": "execute"},
    "credential_store": {"handler": _wrap_credential_store, "permission": "approve", "category": "write"},
    "browser_evaluate": {"handler": _wrap_browser_evaluate, "permission": "approve", "category": "execute"},
    "api_evaluate":     {"handler": _wrap_api_evaluate,     "permission": "approve", "category": "execute"},
    "stop_process":     {"handler": _wrap_stop_process,     "permission": "approve", "category": "execute"},
    "spawn_subagent":   {"handler": _wrap_spawn_subagent,   "permission": "approve", "category": "execute"},
    "schedule_task":    {"handler": _wrap_schedule_task,     "permission": "approve", "category": "write"},
}

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

ALLOWED_BASES = [
    os.path.realpath(WORKSPACE),
    os.path.realpath(VAULT),
    os.path.realpath(CONVERSATIONS),
]

DENY_LIST = [".ssh", ".gnupg", ".env", "id_rsa", "id_ed25519", ".netrc",
             "credentials", "secrets", "token", ".aws/credentials"]


def validate_path(file_path: str, operation: str = "read") -> tuple[bool, str]:
    """Validate a file path for safety."""
    resolved = os.path.realpath(os.path.expanduser(file_path))

    # Block path traversal attempts
    if ".." in file_path:
        return False, f"Path traversal not allowed: {file_path}"

    # Block deny-listed patterns
    path_lower = resolved.lower()
    for pattern in DENY_LIST:
        if pattern in path_lower:
            return False, f"Access denied to sensitive path: {pattern}"

    if operation == "read":
        # Reads are allowed more broadly
        return True, "allowed"

    # Writes must be within allowed bases
    for base in ALLOWED_BASES:
        if resolved.startswith(base):
            return True, "allowed"

    return False, f"Path outside allowed locations: {resolved}"


# ── Audit logging ─────────────────────────────────────────────────────────

_session_log_path = None


def _init_log():
    global _session_log_path
    if _session_log_path is None:
        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        _session_log_path = os.path.join(LOG_DIR, f"session-{ts}.log")


def _log_dispatch(tool_name: str, parameters: dict, classification: dict | None,
                  permission: str, result_summary: str, duration_ms: int):
    """Log a tool dispatch to the session log file."""
    _init_log()
    ts = datetime.now().isoformat()
    # Redact potential secrets
    safe_params = json.dumps(parameters)[:200]
    for secret_key in ("password", "key", "token", "secret", "credential"):
        if secret_key in safe_params.lower():
            safe_params = "[REDACTED]"
            break
    level = classification.get("level", "-") if classification else "-"
    line = (f"{ts} | {tool_name} | risk={level} | {permission} | "
            f"{duration_ms}ms | params={safe_params} | result={result_summary[:200]}\n")
    try:
        with open(_session_log_path, "a") as f:
            f.write(line)
    except Exception:
        pass


# ── Consecutive call limiter ──────────────────────────────────────────────

_consecutive_tool = None
_consecutive_count = 0


def _check_consecutive(tool_name: str) -> str | None:
    """Track consecutive calls. Returns a warning message or None."""
    global _consecutive_tool, _consecutive_count

    if tool_name == _consecutive_tool:
        _consecutive_count += 1
    else:
        _consecutive_tool = tool_name
        _consecutive_count = 1

    if _consecutive_count >= 8:
        return (f"Maximum consecutive calls reached for {tool_name}. "
                "Report the current state to the user and ask for guidance.")
    if _consecutive_count >= 5:
        return (f"You have called {tool_name} {_consecutive_count} times consecutively. "
                "Pause and assess: are you making progress or repeating the same approach? "
                "State your diagnosis of the problem before making another attempt.")
    return None


def reset_consecutive():
    """Reset the consecutive call counter (called when model produces non-tool response)."""
    global _consecutive_tool, _consecutive_count
    _consecutive_tool = None
    _consecutive_count = 0


# ── MCP routing ───────────────────────────────────────────────────────────

_mcp_client = None


def set_mcp_client(client):
    """Set the MCP client module for routing mcp_ prefixed tool calls."""
    global _mcp_client
    _mcp_client = client


# ── Main dispatch function ────────────────────────────────────────────────

def dispatch(tool_name: str, parameters: dict,
             permission_callback=None) -> str:
    """Dispatch a tool call through the unified permission and safety pipeline.

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
    classification = None

    # MCP routing
    if tool_name.startswith("mcp_") and _mcp_client:
        try:
            result = _mcp_client.call_mcp_tool(tool_name, parameters)
            return json.dumps(result) if isinstance(result, dict) else str(result)
        except Exception as e:
            return f"[MCP error — {tool_name}: {e}]"

    # Check registry
    entry = TOOL_REGISTRY.get(tool_name)
    if entry is None:
        return f"[Unknown tool: {tool_name}]"

    # Consecutive call check
    warning = _check_consecutive(tool_name)
    if warning and _consecutive_count >= 8:
        duration = int((time.time() - start) * 1000)
        _log_dispatch(tool_name, parameters, None, "blocked-consecutive",
                      warning, duration)
        return warning

    # Command classification for bash_execute
    if tool_name == "bash_execute":
        cmd = parameters.get("command", "")
        classification = classify_command(cmd)
        if classification["level"] == "blocked":
            duration = int((time.time() - start) * 1000)
            _log_dispatch(tool_name, parameters, classification, "blocked",
                          classification["reason"], duration)
            return f"[BLOCKED] {classification['reason']}"

    # Permission gate
    if entry["permission"] == "approve":
        approved = request_permission(tool_name, parameters, classification,
                                      callback=permission_callback)
        if not approved:
            duration = int((time.time() - start) * 1000)
            _log_dispatch(tool_name, parameters, classification, "user-denied",
                          "Permission denied by user", duration)
            return f"[Permission denied for {tool_name}]"
        permission_status = "user-approved"
    else:
        permission_status = "auto-approved"

    # Path validation for file operations
    if tool_name in ("file_write", "file_edit"):
        file_path = parameters.get("path", parameters.get("file_path", ""))
        valid, reason = validate_path(file_path, "write")
        if not valid:
            duration = int((time.time() - start) * 1000)
            _log_dispatch(tool_name, parameters, classification, "path-blocked",
                          reason, duration)
            return f"[Path validation failed: {reason}]"
    elif tool_name == "file_read":
        file_path = parameters.get("path", "")
        valid, reason = validate_path(file_path, "read")
        if not valid:
            duration = int((time.time() - start) * 1000)
            _log_dispatch(tool_name, parameters, classification, "path-blocked",
                          reason, duration)
            return f"[Path validation failed: {reason}]"

    # Pre-tool hooks
    fire_hooks("pre_tool", {"tool_name": tool_name, "parameters": parameters})

    # Execute
    try:
        result = entry["handler"](parameters)
        if isinstance(result, dict):
            result_str = json.dumps(result)
        elif isinstance(result, list):
            result_str = json.dumps(result)
        else:
            result_str = str(result)
    except Exception as e:
        result_str = f"[Tool error — {tool_name}: {e}]"

    # Post-tool hooks
    hook_outputs = fire_hooks("post_tool", {"tool_name": tool_name, "result": result_str[:500]})
    if hook_outputs:
        result_str += "\n" + "\n".join(f"[hook: {h}]" for h in hook_outputs)

    duration = int((time.time() - start) * 1000)
    _log_dispatch(tool_name, parameters, classification, permission_status,
                  result_str[:200], duration)

    # Inject consecutive call warning as prefix
    if warning and _consecutive_count >= 5:
        result_str = f"[SYSTEM: {warning}]\n\n{result_str}"

    return result_str
