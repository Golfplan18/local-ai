"""PED watcher — detects checkbox state changes in Active Milestones across PEDs.

Polling-based sweep (not a continuous file watcher). Runs as a scheduled
task; on each invocation, walks the known projects under oversight, loads
each PED, compares the active-milestone state against the last-known state,
and emits MilestoneClaimed events for any checkbox transitions from
unchecked to checked.

Per-project state lives at ``~/ora/data/oversight/<nexus>/last-ped-state.json``.
The pointer file ``~/ora/data/oversight/<nexus>/ped-path.json`` tells us
which PED file to read for each project.

Author: meta-layer implementation per Reference — Meta-Layer Architecture §6 W2.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from ped_parser import parse_ped_file, get_active_milestone_states


WORKSPACE = os.path.expanduser("~/ora/")
OVERSIGHT_DATA_DIR = os.path.join(WORKSPACE, "data/oversight/")
HEARTBEAT_FILE = os.path.join(OVERSIGHT_DATA_DIR, "ped-watcher-heartbeat.json")

# Debounce window — see Reference — Meta-Layer Architecture §10 O6
DEBOUNCE_SECONDS = 2


@dataclass
class MilestoneClaimedEvent:
    event_type: str
    project_nexus: str
    ped_path: str
    milestone_text: str
    claimed_at: str  # ISO timestamp
    claimer: str  # "user" / "framework" / "system"
    timestamp: str


def project_pointer_path(nexus: str) -> str:
    return os.path.join(OVERSIGHT_DATA_DIR, nexus, "ped-path.json")


def project_state_path(nexus: str) -> str:
    return os.path.join(OVERSIGHT_DATA_DIR, nexus, "last-ped-state.json")


def list_known_projects() -> list[str]:
    """Return the list of project nexus IDs that have an oversight pointer."""
    if not os.path.isdir(OVERSIGHT_DATA_DIR):
        return []
    out = []
    for name in sorted(os.listdir(OVERSIGHT_DATA_DIR)):
        full = os.path.join(OVERSIGHT_DATA_DIR, name)
        if os.path.isdir(full) and os.path.isfile(os.path.join(full, "ped-path.json")):
            out.append(name)
    return out


def load_ped_path(nexus: str) -> Optional[str]:
    """Load the PED file path for a given project nexus."""
    pointer = project_pointer_path(nexus)
    if not os.path.isfile(pointer):
        return None
    try:
        with open(pointer) as f:
            data = json.load(f)
        return data.get("ped_path")
    except (json.JSONDecodeError, OSError):
        return None


def write_ped_pointer(nexus: str, ped_path: str):
    """Write the per-project pointer file."""
    nexus_dir = os.path.join(OVERSIGHT_DATA_DIR, nexus)
    os.makedirs(nexus_dir, exist_ok=True)
    pointer = project_pointer_path(nexus)
    with open(pointer, "w") as f:
        json.dump({"ped_path": ped_path, "registered_at": _now_iso()}, f, indent=2)


def load_last_state(nexus: str) -> Optional[dict]:
    """Load the last-known PED state for a project, if any."""
    path = project_state_path(nexus)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def write_state(nexus: str, state: dict):
    """Persist the PED state snapshot."""
    nexus_dir = os.path.join(OVERSIGHT_DATA_DIR, nexus)
    os.makedirs(nexus_dir, exist_ok=True)
    path = project_state_path(nexus)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def diff_milestones(prior: dict, current: dict) -> list[tuple[str, bool, bool]]:
    """Compare prior state and current state, return list of (statement, was_complete, is_complete)
    tuples for milestones whose checkbox state changed.

    Both prior and current are dicts of {milestone_statement: is_complete (bool)}.
    """
    changes = []
    prior_map = prior.get("milestones", {}) if prior else {}
    current_map = current.get("milestones", {})
    for statement, is_complete in current_map.items():
        was_complete = prior_map.get(statement)
        if was_complete is None:
            # New milestone — only counts as a claim if it's marked complete
            if is_complete:
                changes.append((statement, False, True))
        elif was_complete != is_complete:
            changes.append((statement, was_complete, is_complete))
    return changes


def state_from_ped(ped) -> dict:
    """Build a state snapshot from a parsed PED."""
    milestones = {stmt: is_complete for stmt, is_complete in get_active_milestone_states(ped)}
    return {
        "snapshot_at": _now_iso(),
        "ped_path": ped.file_path,
        "milestones": milestones,
    }


def sweep(emit_event=None) -> list[MilestoneClaimedEvent]:
    """Run one sweep cycle. Returns list of emitted MilestoneClaimedEvents.

    If emit_event is provided, it's called with each event as it's detected.
    """
    events: list[MilestoneClaimedEvent] = []
    _write_heartbeat()

    for nexus in list_known_projects():
        ped_path = load_ped_path(nexus)
        if not ped_path or not os.path.isfile(ped_path):
            continue
        try:
            ped = parse_ped_file(ped_path)
        except Exception as exc:
            print(f"[ped_watcher] Failed to parse {ped_path}: {exc}")
            continue

        current_state = state_from_ped(ped)
        prior_state = load_last_state(nexus)

        changes = diff_milestones(prior_state or {}, current_state)
        for statement, was_complete, is_complete in changes:
            # Only emit MilestoneClaimed for transitions to complete
            if is_complete and not was_complete:
                evt = MilestoneClaimedEvent(
                    event_type="MilestoneClaimed",
                    project_nexus=nexus,
                    ped_path=ped_path,
                    milestone_text=statement,
                    claimed_at=_now_iso(),
                    claimer="user",  # default; framework hooks set this differently
                    timestamp=_now_iso(),
                )
                events.append(evt)
                if emit_event is not None:
                    try:
                        emit_event(evt)
                    except Exception as e:
                        print(f"[ped_watcher] emit_event raised: {e}")

        # Always write the new state (even if no changes — keeps snapshot timestamp fresh)
        write_state(nexus, current_state)

    return events


def _write_heartbeat():
    os.makedirs(OVERSIGHT_DATA_DIR, exist_ok=True)
    with open(HEARTBEAT_FILE, "w") as f:
        json.dump({"watcher": "ped_watcher", "beat_at": _now_iso()}, f)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    """Run one sweep and print the events detected."""
    events = sweep()
    print(f"PED watcher sweep complete. Detected {len(events)} milestone claim(s).")
    for evt in events:
        print(f"  - {evt.project_nexus}: {evt.milestone_text}")
