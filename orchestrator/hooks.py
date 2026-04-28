"""Lifecycle hooks — fire external scripts at defined orchestrator events."""

from __future__ import annotations

import json
import os
import subprocess

WORKSPACE = os.path.expanduser("~/ora/")
HOOKS_DIR = os.path.join(WORKSPACE, "config/hooks/")

_hooks: list[dict] = []


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

        # Check tool_filter
        tool_filter = hook.get("tool_filter")
        if tool_filter and context.get("tool_name") != tool_filter:
            continue

        command = hook.get("command", "")
        timeout = hook.get("timeout", 10)
        inject = hook.get("inject_output", False)

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=WORKSPACE,
            )
            if inject and result.stdout.strip():
                injected.append(result.stdout.strip())
        except subprocess.TimeoutExpired:
            print(f"[hooks] Hook timed out: {hook.get('_source', 'unknown')}")
        except Exception as e:
            print(f"[hooks] Hook failed: {hook.get('_source', 'unknown')}: {e}")

    return injected
