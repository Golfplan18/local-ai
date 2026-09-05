"""Cross-project oversight — parent-child PED relationships.

Implements the deferred handoff item: when PE-Spawn creates a sub-project, the
parent's oversight should observe child milestone completions, blocks, and
redefinition evidence. Without this, the parent's PED stays unaware of
spawned-project progress unless the user manually annotates it.

Convention for parent linkage in a child PED's frontmatter:

    parent_nexus: <parent-project-nexus>           # required — single string
    spawned_from_milestone: <milestone-id-or-text>  # optional — context

The convention is single-parent for the first cut. A child PED with no
``parent_nexus`` field is treated as a top-level project and produces no
fan-out.

Fan-out semantics (router-side):

  1. The router processes the child's event normally (loads child PED,
     invokes Process Coherence against the child).
  2. After the primary processing, the router calls ``notify_parent`` with
     the original event and the parent's nexus.
  3. ``notify_parent`` appends a Decision Log entry to the parent PED
     describing the child event, and emits a synthesized ``Child<EventType>``
     audit record for the events log.
  4. Synthesized child-events carry ``_oversight_meta: "fan_out"`` so the
     router recognizes them as already-handled audit records and does NOT
     re-fan, re-invoke PC, or recurse into a parent's parent.

Fan-out is asymmetric: children inform parents; parents do not inform
children. There is no implicit re-routing or chained PC invocation in the
first cut — the parent's oversight observes via the Decision Log entry.

Fan-out is filtered to events that are meaningful at the parent level. See
``FAN_OUT_EVENT_TYPES`` for the set.

Per Reference — Meta-Layer Architecture; the deferred cross-project
oversight item from the 2026-05-04 implementation handoff.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ped_parser import parse_ped_file
from ped_watcher import load_ped_path
from oversight_actions import (
    append_managed_decision_log_entry,
    file_lock,
)

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp

# Roots flow from runtime_paths so fan-out writes land in the SAME
# events.jsonl / actions.jsonl the oversight_events / oversight_actions
# writers use under ORA_HOME relocation (a split here would hide fan-out
# events from every new-root reader).
WORKSPACE = _rp.WORKSPACE
OVERSIGHT_DATA_DIR = os.path.join(_rp.DATA_DIR_STR, "oversight")
EVENTS_LOG_PATH = os.path.join(OVERSIGHT_DATA_DIR, "events.jsonl")
ACTIONS_LOG_PATH = os.path.join(OVERSIGHT_DATA_DIR, "actions.jsonl")
_EVENTS_LOG_DEFAULT = EVENTS_LOG_PATH   # import-time values; patch anchors
_ACTIONS_LOG_DEFAULT = ACTIONS_LOG_PATH


def _events_log_path() -> str:
    """Explicit monkeypatch wins; otherwise the ORA_OVERSIGHT_SANDBOX
    quarantine (test runs) applies; otherwise the live log."""
    if EVENTS_LOG_PATH != _EVENTS_LOG_DEFAULT:
        return EVENTS_LOG_PATH
    return _rp.sandboxed_file(EVENTS_LOG_PATH)


def _actions_log_path() -> str:
    if ACTIONS_LOG_PATH != _ACTIONS_LOG_DEFAULT:
        return ACTIONS_LOG_PATH
    return _rp.sandboxed_file(ACTIONS_LOG_PATH)

# Events that are meaningful when echoed to a parent project.
FAN_OUT_EVENT_TYPES = {
    "MilestoneClaimed",
    "MilestoneBlocked",
    "MilestoneComplete",       # only when DRIFT_DETECTED — handled by caller
    "FrameworkComplete",       # success or failure both informative
    "RedefinitionEvidence",
}

# Sentinel that marks a synthesized child event so the router does not
# re-process it through PC or fan it out further.
FAN_OUT_META_KEY = "_oversight_meta"
FAN_OUT_META_VALUE = "fan_out"


def get_parent_nexus(child_nexus: str) -> Optional[str]:
    """Return the parent_nexus declared in the child's PED frontmatter.

    Returns None when:
      - The child has no registered PED
      - The PED file is missing or unparseable
      - The frontmatter has no ``parent_nexus`` field
    """
    if not child_nexus:
        return None
    ped_path = load_ped_path(child_nexus)
    if not ped_path or not os.path.isfile(ped_path):
        return None
    try:
        ped = parse_ped_file(ped_path)
    except Exception:
        return None
    parent = ped.frontmatter.get("parent_nexus") if ped.frontmatter else None
    if not parent:
        return None
    if isinstance(parent, list):
        parent = parent[0] if parent else None
    return str(parent).strip() or None


def get_spawned_from_milestone(child_nexus: str) -> Optional[str]:
    """Return the spawned_from_milestone declared in the child's frontmatter, if any."""
    if not child_nexus:
        return None
    ped_path = load_ped_path(child_nexus)
    if not ped_path or not os.path.isfile(ped_path):
        return None
    try:
        ped = parse_ped_file(ped_path)
    except Exception:
        return None
    val = ped.frontmatter.get("spawned_from_milestone") if ped.frontmatter else None
    return str(val).strip() if val else None


def is_fan_out_event(event: dict) -> bool:
    """True if event is a synthesized fan-out audit record (don't re-process)."""
    return event.get(FAN_OUT_META_KEY) == FAN_OUT_META_VALUE


def should_fan_out(event: dict) -> bool:
    """Return True iff the event is eligible for fan-out to a parent project.

    Excludes synthesized fan-out records (no recursion), workflow-level events
    (parent observes its child's project-level progress, not corpus details),
    and events outside the fan-out type set.
    """
    if is_fan_out_event(event):
        return False
    et = event.get("event_type", "")
    if et not in FAN_OUT_EVENT_TYPES:
        return False
    if et == "MilestoneComplete" and event.get("drift_status") != "DRIFT_DETECTED":
        # Only drift-detected MilestoneComplete is worth surfacing
        return False
    return True


def prepare_parent_notification(child_event: dict) -> Optional[dict]:
    """Freeze one watcher's complete parent fan-out plan without writing it.

    The returned plain dictionary is suitable for the existing EventLedger
    claim.  It binds the first resolved parent, canonical PED destination,
    rendered Decision Log content, and both downstream audit payloads so a
    retry never re-reads changed child or parent routing metadata.
    """
    try:
        from oversight_events import resolve_lifecycle_context
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_events import resolve_lifecycle_context
    stealth, conversation_id = resolve_lifecycle_context(child_event)
    if stealth:
        return None
    child_event = dict(child_event)
    if conversation_id and not child_event.get("conversation_id"):
        child_event["conversation_id"] = conversation_id
    if not should_fan_out(child_event):
        return None

    child_nexus = str(child_event.get("project_nexus") or "")
    if not child_nexus:
        return None
    parent_nexus = get_parent_nexus(child_nexus)
    if not parent_nexus:
        return None
    parent_ped_path = load_ped_path(parent_nexus)
    if not parent_ped_path:
        return None

    destination = _canonical_ped_destination(parent_ped_path)
    synthesized = _synthesize_parent_event(child_event, parent_nexus)
    return {
        "parent_nexus": parent_nexus,
        "parent_ped_path": destination,
        "decision_log_entry": _render_parent_decision_log_entry(synthesized),
        "synthesized_event": synthesized,
        "actions_log_entry": _parent_actions_log_entry(synthesized),
    }


def deliver_parent_notification(plan: dict) -> Optional[dict]:
    """Deliver one previously claimed parent fan-out plan exactly as stored."""
    if not isinstance(plan, dict):
        raise ValueError("watcher parent fan-out plan is invalid")
    parent_nexus = str(plan.get("parent_nexus") or "")
    parent_ped_path = str(plan.get("parent_ped_path") or "")
    decision_log_entry = plan.get("decision_log_entry")
    synthesized = plan.get("synthesized_event")
    actions_log_entry = plan.get("actions_log_entry")
    if (
        not parent_nexus
        or not parent_ped_path
        or not isinstance(decision_log_entry, str)
        or not isinstance(synthesized, dict)
        or not isinstance(actions_log_entry, dict)
        or synthesized.get("project_nexus") != parent_nexus
        or actions_log_entry.get("project_nexus") != parent_nexus
    ):
        raise ValueError("watcher parent fan-out plan is incomplete")

    destination = _reauthenticate_ped_destination(parent_ped_path)
    event_record = dict(synthesized)
    _append_parent_decision_log(
        destination,
        event_record,
        entry_text=decision_log_entry,
    )
    _append_events_log(dict(synthesized))
    _append_actions_log(dict(actions_log_entry))
    return dict(synthesized)


def notify_parent(child_event: dict, parent_nexus: str) -> Optional[dict]:
    """Notify the parent project of a child event.

    Side effects:
      - Appends a Decision Log entry to the parent PED describing the event.
      - Emits a synthesized ``Child<EventType>`` audit record into the
        events log (events.jsonl) and a corresponding actions-log entry.
      - The synthesized event carries ``_oversight_meta: fan_out`` so it is
        not re-processed by the router.

    Returns the synthesized event dict on success or when no fan-out applies.
    A stable watcher publication propagates a failed durable parent-PED write
    so its upstream delivery cannot be acknowledged prematurely.
    """
    try:
        from oversight_events import resolve_lifecycle_context
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_events import resolve_lifecycle_context
    stealth, conversation_id = resolve_lifecycle_context(child_event)
    if stealth:
        return None
    if conversation_id and not child_event.get("conversation_id"):
        child_event = {**child_event, "conversation_id": conversation_id}

    if not should_fan_out(child_event):
        return None
    if not parent_nexus:
        return None

    parent_ped_path = load_ped_path(parent_nexus)
    if not parent_ped_path or not os.path.isfile(parent_ped_path):
        return None

    synthesized = _synthesize_parent_event(child_event, parent_nexus)

    _append_parent_decision_log(parent_ped_path, synthesized)
    _append_events_log(synthesized)
    _append_actions_log(_parent_actions_log_entry(synthesized))

    return synthesized


# ---------- Helpers ----------

def _canonical_ped_destination(ped_path: str) -> str:
    """Return the absolute resolved destination named by a parent pointer."""
    candidate = Path(os.path.abspath(os.path.expanduser(str(ped_path))))
    if candidate.is_symlink():
        raise OSError(f"parent PED destination is a symlink: {candidate}")
    return str(candidate.resolve(strict=False))


def _reauthenticate_ped_destination(bound_path: str) -> str:
    """Require the claimed canonical PED destination to remain available."""
    destination = Path(bound_path)
    if not destination.is_absolute():
        raise OSError(f"bound parent PED destination is not absolute: {destination}")
    if destination.is_symlink() or not destination.is_file():
        raise OSError(f"bound parent PED destination is unavailable: {destination}")
    try:
        current = destination.resolve(strict=True)
    except OSError as exc:
        raise OSError(
            f"bound parent PED destination is unavailable: {destination}",
        ) from exc
    if current != destination:
        raise OSError(
            f"bound parent PED destination is no longer canonical: {destination}",
        )
    return str(destination)


def _synthesize_parent_event(child_event: dict, parent_nexus: str) -> dict:
    child_nexus = child_event.get("project_nexus", "")
    spawned_from = get_spawned_from_milestone(child_nexus)
    synthesized = {
        "event_type": f"Child{child_event.get('event_type', 'Event')}",
        "project_nexus": parent_nexus,
        "child_nexus": child_nexus,
        "child_event_type": child_event.get("event_type", ""),
        "child_milestone_text": child_event.get("milestone_text", ""),
        "child_milestone_id": child_event.get("milestone_id", ""),
        "child_drift_status": child_event.get("drift_status", ""),
        "child_block_reason": child_event.get("block_reason", ""),
        "spawned_from_milestone": spawned_from or "",
        "timestamp": _now_iso(),
        "conversation_id": child_event.get("conversation_id", ""),
        "conversation_tag": (
            child_event.get("conversation_tag")
            or child_event.get("tag")
            or ""
        ),
        FAN_OUT_META_KEY: FAN_OUT_META_VALUE,
    }
    publication_id = str(child_event.get("publication_id") or "")
    if publication_id:
        synthesized["source_publication_id"] = publication_id
    return synthesized


def _parent_actions_log_entry(synthesized: dict) -> dict:
    return {
        "event_type": synthesized["event_type"],
        "action": "fan_out_to_parent",
        "project_nexus": synthesized.get("project_nexus", ""),
        "child_nexus": synthesized.get("child_nexus", ""),
        "timestamp": synthesized["timestamp"],
        "conversation_id": synthesized.get("conversation_id", ""),
        "source_publication_id": str(
            synthesized.get("source_publication_id") or ""
        ),
    }


def _render_parent_decision_log_entry(synthesized: dict) -> str:
    """Append a Decision Log entry to the parent PED summarizing the child event."""
    child_event_type = synthesized.get("child_event_type", "")
    child_nexus = synthesized.get("child_nexus", "")
    spawned_from = synthesized.get("spawned_from_milestone", "")

    lines = [
        f"### {_today_iso()} — Child Project Update: {child_nexus} ({child_event_type})",
    ]
    if spawned_from:
        lines.append(f"- Spawned from parent milestone: {spawned_from}")
    if synthesized.get("child_milestone_text"):
        lines.append(f"- Child milestone: {synthesized['child_milestone_text']}")
    if synthesized.get("child_milestone_id"):
        lines.append(f"- Milestone id: {synthesized['child_milestone_id']}")
    if synthesized.get("child_drift_status"):
        lines.append(f"- Drift status: {synthesized['child_drift_status']}")
    if synthesized.get("child_block_reason"):
        lines.append(f"- Block reason: {synthesized['child_block_reason']}")
    lines.append(
        f"- Source: cross-project oversight fan-out (no parent PC invocation in v1; "
        f"observe and decide manually whether parent milestones should advance)."
    )
    return "\n".join(lines) + "\n\n"


def _append_parent_decision_log(
    parent_ped_path: str,
    synthesized: dict,
    *,
    entry_text: str | None = None,
):
    """Append a Decision Log entry to the parent PED summarizing the child event."""
    if entry_text is None:
        entry_text = _render_parent_decision_log_entry(synthesized)

    action_record: dict = {}
    append_managed_decision_log_entry(
        parent_ped_path,
        entry_text,
        synthesized,
        kind="parent_project_fanout",
        action_record=action_record,
        idempotency_key=(
            str(synthesized.get("source_publication_id") or "") or None
        ),
    )
    if action_record.get("decision_log_write_failed"):
        synthesized.setdefault("write_errors", []).append(
            action_record["decision_log_write_failed"],
        )
        if synthesized.get("source_publication_id"):
            raise OSError(action_record["decision_log_write_failed"])


def _append_jsonl_record(log_path: str, record: dict) -> None:
    """Append one fan-out record once for a stable watcher publication."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    encoded = (json.dumps(record, default=str) + "\n").encode("utf-8")
    publication_id = str(record.get("source_publication_id") or "")
    with file_lock(log_path):
        flags = os.O_APPEND | os.O_CREAT
        flags |= os.O_RDWR if publication_id else os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(log_path, flags, 0o600)
        try:
            if publication_id:
                os.lseek(fd, 0, os.SEEK_SET)
                existing = b""
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    existing += chunk
                complete_end = existing.rfind(b"\n") + 1
                if complete_end != len(existing):
                    os.ftruncate(fd, complete_end)
                    os.fsync(fd)
                    existing = existing[:complete_end]
                for raw in existing.splitlines():
                    try:
                        prior = json.loads(raw.decode("utf-8"))
                    except (UnicodeError, json.JSONDecodeError):
                        continue
                    if prior.get("source_publication_id") == publication_id:
                        os.fsync(fd)
                        return
                written = 0
                while written < len(encoded):
                    count = os.write(fd, encoded[written:])
                    if count <= 0:
                        raise OSError("fan-out audit write made no progress")
                    written += count
                os.fsync(fd)
            else:
                os.write(fd, encoded)
        finally:
            os.close(fd)


def _append_events_log(record: dict):
    try:
        from oversight_events import resolve_lifecycle_context
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_events import resolve_lifecycle_context
    stealth, conversation_id = resolve_lifecycle_context(record)
    if stealth:
        return
    record = dict(record)
    if conversation_id and not record.get("conversation_id"):
        record["conversation_id"] = conversation_id
    _append_jsonl_record(_events_log_path(), record)


def _append_actions_log(record: dict):
    try:
        from oversight_events import resolve_lifecycle_context
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_events import resolve_lifecycle_context
    stealth, conversation_id = resolve_lifecycle_context(record)
    if stealth:
        return
    record = dict(record)
    if conversation_id and not record.get("conversation_id"):
        record["conversation_id"] = conversation_id
    _append_jsonl_record(_actions_log_path(), record)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------- CLI ----------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python oversight_relationships.py parent <child_nexus>")
        print("       python oversight_relationships.py spawned_from <child_nexus>")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "parent":
        if len(sys.argv) < 3:
            print("Usage: python oversight_relationships.py parent <child_nexus>")
            sys.exit(1)
        result = get_parent_nexus(sys.argv[2])
        print(result or "(no parent declared)")
    elif cmd == "spawned_from":
        if len(sys.argv) < 3:
            print("Usage: python oversight_relationships.py spawned_from <child_nexus>")
            sys.exit(1)
        result = get_spawned_from_milestone(sys.argv[2])
        print(result or "(no spawned_from_milestone declared)")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
