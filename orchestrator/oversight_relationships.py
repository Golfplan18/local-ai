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
from typing import Optional

from ped_parser import parse_ped_file
from ped_watcher import load_ped_path
from oversight_actions import file_lock, _insert_into_decision_log


WORKSPACE = os.path.expanduser("~/ora/")
OVERSIGHT_DATA_DIR = os.path.join(WORKSPACE, "data/oversight/")
EVENTS_LOG_PATH = os.path.join(OVERSIGHT_DATA_DIR, "events.jsonl")
ACTIONS_LOG_PATH = os.path.join(OVERSIGHT_DATA_DIR, "actions.jsonl")

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


def notify_parent(child_event: dict, parent_nexus: str) -> Optional[dict]:
    """Notify the parent project of a child event.

    Side effects:
      - Appends a Decision Log entry to the parent PED describing the event.
      - Emits a synthesized ``Child<EventType>`` audit record into the
        events log (events.jsonl) and a corresponding actions-log entry.
      - The synthesized event carries ``_oversight_meta: fan_out`` so it is
        not re-processed by the router.

    Returns the synthesized event dict on success, None on failure.
    """
    if not should_fan_out(child_event):
        return None
    if not parent_nexus:
        return None

    parent_ped_path = load_ped_path(parent_nexus)
    if not parent_ped_path or not os.path.isfile(parent_ped_path):
        return None

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
        FAN_OUT_META_KEY: FAN_OUT_META_VALUE,
    }

    _append_parent_decision_log(parent_ped_path, synthesized)
    _append_events_log(synthesized)
    _append_actions_log({
        "event_type": synthesized["event_type"],
        "action": "fan_out_to_parent",
        "project_nexus": parent_nexus,
        "child_nexus": child_nexus,
        "timestamp": synthesized["timestamp"],
    })

    return synthesized


# ---------- Helpers ----------

def _append_parent_decision_log(parent_ped_path: str, synthesized: dict):
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
    entry_text = "\n".join(lines) + "\n\n"

    try:
        with file_lock(parent_ped_path):
            with open(parent_ped_path, encoding="utf-8") as f:
                content = f.read()
            new_content = _insert_into_decision_log(content, entry_text)
            with open(parent_ped_path, "w", encoding="utf-8") as f:
                f.write(new_content)
    except (TimeoutError, OSError):
        # Best-effort — Decision Log write failure shouldn't crash the router
        pass


def _append_events_log(record: dict):
    os.makedirs(os.path.dirname(EVENTS_LOG_PATH), exist_ok=True)
    with open(EVENTS_LOG_PATH, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _append_actions_log(record: dict):
    os.makedirs(os.path.dirname(ACTIONS_LOG_PATH), exist_ok=True)
    with open(ACTIONS_LOG_PATH, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


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
