"""Observational project-event logging and parent-project fan-out.

Process Coherence is an explicitly invoked judgment framework. This module
does not invoke it, parse verdicts, or dispatch project or Programming
transitions. The event handler retains stealth suppression, a local event
audit, and asymmetric child-to-parent visibility.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp


WORKSPACE = _rp.WORKSPACE
VAULT = _rp.VAULT_STR
ROUTER_LOG_PATH = os.path.join(_rp.DATA_DIR_STR, "oversight", "router.jsonl")
_ROUTER_LOG_DEFAULT = ROUTER_LOG_PATH


def _router_log_path() -> str:
    if ROUTER_LOG_PATH != _ROUTER_LOG_DEFAULT:
        return ROUTER_LOG_PATH
    return _rp.sandboxed_file(ROUTER_LOG_PATH)


def process_event(event: dict) -> dict:
    """Log one oversight event and surface eligible child events to a parent."""
    try:
        from oversight_events import resolve_lifecycle_context
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_events import resolve_lifecycle_context

    event = dict(event)
    stealth, conversation_id = resolve_lifecycle_context(event)
    if conversation_id and not event.get("conversation_id"):
        event["conversation_id"] = conversation_id
    if stealth:
        return {
            "event_type": event.get("event_type", ""),
            "timestamp": _now_iso(),
            "project_nexus": event.get("project_nexus", ""),
            "conversation_id": event.get("conversation_id", ""),
            "action": "stealth_suppressed",
        }

    from oversight_relationships import is_fan_out_event

    fan_out_audit = is_fan_out_event(event)
    action = {
        "event_type": event.get("event_type", ""),
        "timestamp": _now_iso(),
        "project_nexus": event.get("project_nexus", ""),
        "workflow_id": event.get("workflow_id", ""),
        "section_id": event.get("section_id", ""),
        "conversation_id": event.get("conversation_id", ""),
        "action": "fan_out_audit_only" if fan_out_audit else "logged_only",
    }
    if fan_out_audit:
        action["child_nexus"] = event.get("child_nexus", "")
    _append_router_log(action)
    if not fan_out_audit:
        _maybe_fan_out_to_parent(event)
    return action


def _maybe_fan_out_to_parent(event: dict) -> None:
    """Surface eligible child-project events on the parent PED, best effort."""
    try:
        try:
            from oversight_events import resolve_lifecycle_context
        except ImportError:  # pragma: no cover
            from orchestrator.oversight_events import resolve_lifecycle_context
        stealth, conversation_id = resolve_lifecycle_context(event)
        if stealth:
            return
        if conversation_id and not event.get("conversation_id"):
            event = {**event, "conversation_id": conversation_id}
        from oversight_relationships import (
            get_parent_nexus,
            notify_parent,
            should_fan_out,
        )
        if not should_fan_out(event):
            return
        child_nexus = event.get("project_nexus", "")
        if not child_nexus:
            return
        parent_nexus = get_parent_nexus(child_nexus)
        if parent_nexus:
            notify_parent(event, parent_nexus)
    except Exception as exc:
        print(f"[oversight_router] fan-out to parent failed: {exc}")


def _append_router_log(entry: dict) -> None:
    entry = dict(entry)
    try:
        from oversight_events import resolve_lifecycle_context
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_events import resolve_lifecycle_context
    stealth, conversation_id = resolve_lifecycle_context(entry)
    if stealth:
        return
    if conversation_id and not entry.get("conversation_id"):
        entry["conversation_id"] = conversation_id
    log_path = _router_log_path()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    encoded = (json.dumps(entry, default=str) + "\n").encode("utf-8")
    with _rp.locked_file(log_path):
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(log_path, flags, 0o600)
        try:
            os.write(descriptor, encoded)
        finally:
            os.close(descriptor)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def install() -> None:
    """Register the observational handler once during daemon boot."""
    from oversight_events import register_handler

    register_handler(process_event)


if __name__ == "__main__":
    import sys

    sample = {
        "event_type": "MilestoneClaimed",
        "project_nexus": sys.argv[1] if len(sys.argv) > 1 else "test_project",
        "milestone_text": "First draft is complete",
        "claimer": "user",
    }
    print(json.dumps(process_event(sample), indent=2, default=str))
