"""Revisit-trigger sweeper — periodic check for conditions that should fire PE-Iterate.

Walks each registered project, evaluates Working Assumption revisit triggers,
time-based reviews, and accumulated drift thresholds. Fires PE-Iterate-needed
events when any trigger is satisfied.

Per Reference — Meta-Layer Architecture §6 W3.

Author: meta-layer implementation per Reference — Meta-Layer Architecture §6 W3.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ped_parser import parse_ped_file, ParsedPED
from ped_watcher import load_ped_path, list_known_projects


WORKSPACE = os.path.expanduser("~/ora/")
OVERSIGHT_DATA_DIR = os.path.join(WORKSPACE, "data/oversight/")
HEARTBEAT_FILE = os.path.join(OVERSIGHT_DATA_DIR, "revisit-sweeper-heartbeat.json")


@dataclass
class RevisitTriggerEvent:
    event_type: str
    project_nexus: str
    triggers_fired: list = field(default_factory=list)
    timestamp: str = ""


def evaluate_working_assumption_triggers(ped: ParsedPED) -> list[str]:
    """For each Working Assumption with a revisit trigger, check whether the
    trigger condition appears to be met.

    The MVP implementation does NOT evaluate arbitrary conditions — those
    require domain-specific data sources. Instead, it surfaces all triggers
    so the user can review them periodically. Future work: machine-evaluable
    conditions per the Oversight Specification format.
    """
    fired: list[str] = []
    for c in ped.constraints:
        if c.classification == "Working Assumption" and c.revisit_trigger:
            # MVP: list every working assumption's revisit trigger as a candidate
            # for review. Real evaluation requires data sources outside the PED.
            fired.append(f"Working Assumption: {c.statement} | Revisit when: {c.revisit_trigger}")
    return fired


def evaluate_age_based_review(ped: ParsedPED, max_age_days: int = 30) -> Optional[str]:
    """If the latest iteration entry is older than max_age_days, suggest review."""
    if not ped.iteration_history:
        return None
    # Latest iteration = highest iteration number
    latest = max(ped.iteration_history, key=lambda x: x.get("iteration", 0))
    raw = latest.get("raw_text", "")
    # Look for a date pattern in the iteration block
    import re
    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", raw)
    if not date_match:
        return None
    try:
        last_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    age_days = (datetime.now(timezone.utc) - last_date).days
    if age_days >= max_age_days:
        return f"Last iteration was {age_days} days ago (latest iteration #{latest.get('iteration')})"
    return None


def sweep_project(nexus: str, ped_path: str) -> Optional[RevisitTriggerEvent]:
    """Sweep one project. Returns an event if any trigger fires."""
    try:
        ped = parse_ped_file(ped_path)
    except Exception as e:
        print(f"[revisit_sweeper] Failed to parse {ped_path}: {e}")
        return None

    fired_triggers: list[str] = []
    fired_triggers.extend(evaluate_working_assumption_triggers(ped))
    age_review = evaluate_age_based_review(ped)
    if age_review:
        fired_triggers.append(age_review)

    if not fired_triggers:
        return None

    return RevisitTriggerEvent(
        event_type="PEFIterateNeeded",
        project_nexus=nexus,
        triggers_fired=fired_triggers,
        timestamp=_now_iso(),
    )


def sweep(emit_event=None) -> list[RevisitTriggerEvent]:
    """Run a full sweep across all known projects."""
    _write_heartbeat()
    events: list[RevisitTriggerEvent] = []
    for nexus in list_known_projects():
        ped_path = load_ped_path(nexus)
        if not ped_path or not os.path.isfile(ped_path):
            continue
        evt = sweep_project(nexus, ped_path)
        if evt:
            events.append(evt)
            if emit_event:
                try:
                    emit_event(evt)
                except Exception as e:
                    print(f"[revisit_sweeper] emit_event raised: {e}")
    return events


def _write_heartbeat():
    os.makedirs(OVERSIGHT_DATA_DIR, exist_ok=True)
    with open(HEARTBEAT_FILE, "w") as f:
        json.dump({"watcher": "revisit_sweeper", "beat_at": _now_iso()}, f)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    events = sweep()
    print(f"Revisit sweep complete. Detected {len(events)} project(s) with active triggers.")
    for evt in events:
        print(f"  - {evt.project_nexus}: {len(evt.triggers_fired)} trigger(s)")
        for t in evt.triggers_fired:
            print(f"    * {t}")
