"""Lifecycle hooks — fire external scripts at defined orchestrator events."""

from __future__ import annotations

import json
import os
import subprocess

WORKSPACE = os.path.expanduser("~/ora/")
HOOKS_DIR = os.path.join(WORKSPACE, "config/hooks/")

_hooks: list[dict] = []

_INJECTABLE_EVENTS = frozenset({"pre_tool", "post_tool", "pre_compact"})


def load_hooks():
    """Load all hook definitions from config/hooks/*.json."""
    global _hooks
    _hooks = []
    if not os.path.isdir(HOOKS_DIR):
        return

    for filename in sorted(os.listdir(HOOKS_DIR)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(HOOKS_DIR, filename)
        try:
            with open(path) as f:
                hook = json.load(f)
            # Validate required fields
            if "event" in hook and "command" in hook:
                if (hook.get("inject_output", False)
                        and hook["event"] not in _INJECTABLE_EVENTS):
                    print(
                        f"[hooks] Refused {filename}: inject_output has no "
                        f"receiver for event {hook['event']!r}"
                    )
                    continue
                hook["_source"] = filename
                _hooks.append(hook)
        except Exception as e:
            print(f"[hooks] Failed to load {filename}: {e}")


def fire_hooks(event: str, context: dict = None) -> list[str]:
    """Fire all hooks matching the event. Returns list of injected outputs.

    Args:
        event: One of pre_tool, post_tool, session_start, session_end, pre_compact.
        context: Optional dict with tool_name, parameters, result, etc.

    Returns:
        List of stdout strings from hooks with inject_output=True.
    """
    if not _hooks:
        load_hooks()

    injected = []
    context = context or {}

    for hook in _hooks:
        if hook.get("event") != event:
            continue

        # Recheck at the execution boundary as well as load time. This keeps
        # a stale or programmatically supplied definition from running before
        # Ora discovers that its requested output has nowhere to go.
        if (hook.get("inject_output", False)
                and event not in _INJECTABLE_EVENTS):
            print(
                f"[hooks] Refused {hook.get('_source', 'unknown')}: "
                f"inject_output has no receiver for event {event!r}"
            )
            continue

        # Check tool_filter
        tool_filter = hook.get("tool_filter")
        if tool_filter and context.get("tool_name") != tool_filter:
            continue

        command = hook.get("command", "")
        timeout = hook.get("timeout", 10)
        inject = hook.get("inject_output", False)

        import time as _time
        _t0 = _time.time()
        _ok, _reason = True, ""
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=WORKSPACE,
            )
            _ok = result.returncode == 0
            _reason = f"exit {result.returncode}" if not _ok else ""
            if inject and result.stdout.strip():
                injected.append(result.stdout.strip())
        except subprocess.TimeoutExpired:
            _ok, _reason = False, "timeout"
            print(f"[hooks] Hook timed out: {hook.get('_source', 'unknown')}")
        except Exception as e:
            _ok, _reason = False, str(e)[:120]
            print(f"[hooks] Hook failed: {hook.get('_source', 'unknown')}: {e}")

        # Execution Review Phase 1: every hook execution is recorded. Hooks
        # are user-installed configuration and run un-gated (installing the
        # hook is the authorization — and writes into config/hooks/ are a
        # protected-config path, so a model cannot install its own), but
        # they are shell=True subprocesses Ora cannot see inside, hence
        # enforcement boundary_only and honest axes (declared in the hook
        # JSON when present, unknown-but-authorized when not).
        try:
            try:
                import tool_events as _te
            except ImportError:
                from orchestrator import tool_events as _te
            declared = {k: hook[k] for k in
                        ("mutability", "sensitivity", "egress") if k in hook}
            _te.record({
                "event": "hook",
                "action": f"hook:{hook.get('_source', 'unknown')}",
                "category": "execute",
                "mutability": declared.get("mutability", "irreversible"),
                "sensitivity": declared.get("sensitivity", "private"),
                "egress": declared.get("egress", "external"),
                "mutated": _ok and declared.get("mutability", "") != "read",
                "args_redacted": {"event": event, "command": command[:200],
                                  "declared_axes": bool(declared)},
                "exit": {"ok": _ok, "reason": _reason},
                "duration_ms": int((_time.time() - _t0) * 1000),
                "gate": {"decision": "allowed",
                         "why": "user-installed hook (pre-authorized)"},
                "enforcement_model": "boundary_only",
            })
        except Exception:
            pass

    return injected
