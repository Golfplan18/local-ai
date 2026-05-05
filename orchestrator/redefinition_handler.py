"""Redefinition follow-through — handles approved ESCALATE (redefinition) entries.

When Process Coherence issues an ESCALATE (redefinition) verdict, the
escalation queues to the human queue. When the user approves the
redefinition, this module:

  1. Archives the current PED to a dated copy in the same directory
  2. Creates a new PED at iteration 1 with the proposed updated definition
  3. Queues a re-evaluation task for prior work against the new definition
  4. Removes the entry from the human queue

The user approves via Framework — Oversight Configuration's OS-Modify mode
or via a direct CLI / slash command. This module does the mechanical
follow-through; the decision itself stays with the user.

Per Reference — Meta-Layer Architecture §9 ESCALATE (redefinition).
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from oversight_actions import file_lock, HUMAN_QUEUE_PATH


WORKSPACE = os.path.expanduser("~/ora/")
OVERSIGHT_DATA_DIR = os.path.join(WORKSPACE, "data/oversight/")
REEVAL_QUEUE_PATH = os.path.join(OVERSIGHT_DATA_DIR, "reeval-queue.jsonl")
ARCHIVED_PEDS_LOG = os.path.join(OVERSIGHT_DATA_DIR, "archived-peds.jsonl")


@dataclass
class RedefinitionResult:
    success: bool
    archived_path: str = ""
    new_ped_path: str = ""
    reeval_task_id: str = ""
    error: str = ""


@dataclass
class QueueEntry:
    """A pending human-queue entry awaiting approval."""
    queued_at: str
    event: dict
    verdict: dict
    redefinition: bool
    forced_reason: str = ""
    context_summary: dict = field(default_factory=dict)
    queue_index: int = 0  # 0-based position in the queue file


def list_pending_redefinitions() -> list[QueueEntry]:
    """Read the human queue and return pending redefinition entries."""
    entries: list[QueueEntry] = []
    if not os.path.isfile(HUMAN_QUEUE_PATH):
        return entries
    try:
        with open(HUMAN_QUEUE_PATH) as f:
            lines = f.readlines()
    except OSError:
        return entries

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not data.get("redefinition"):
            continue
        entries.append(QueueEntry(
            queued_at=data.get("queued_at", ""),
            event=data.get("event", {}),
            verdict=data.get("verdict", {}),
            redefinition=True,
            forced_reason=data.get("forced_reason", ""),
            context_summary=data.get("context_summary", {}),
            queue_index=i,
        ))
    return entries


def list_pending_escalations(redefinition_only: bool = False) -> list[QueueEntry]:
    """Read the human queue and return all pending entries (or only redefinitions).

    Used by `/queue` slash command to show what's awaiting human review.
    """
    entries: list[QueueEntry] = []
    if not os.path.isfile(HUMAN_QUEUE_PATH):
        return entries
    try:
        with open(HUMAN_QUEUE_PATH) as f:
            lines = f.readlines()
    except OSError:
        return entries

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if redefinition_only and not data.get("redefinition"):
            continue
        entries.append(QueueEntry(
            queued_at=data.get("queued_at", ""),
            event=data.get("event", {}),
            verdict=data.get("verdict", {}),
            redefinition=bool(data.get("redefinition")),
            forced_reason=data.get("forced_reason", ""),
            context_summary=data.get("context_summary", {}),
            queue_index=i,
        ))
    return entries


def approve_redefinition(
    queue_index: int,
    proposed_definition: Optional[str] = None,
) -> RedefinitionResult:
    """Approve a pending redefinition. Performs the follow-through:

    1. Archive the current PED
    2. Create a new PED at iteration 1 with the proposed definition
       (if proposed_definition is provided; otherwise the verdict's
       redefinition payload is used)
    3. Queue a re-evaluation task for prior work
    4. Remove the entry from the human queue

    Args:
        queue_index: 0-based index of the entry in the human queue.
        proposed_definition: optional override for the new problem definition.

    Returns: RedefinitionResult.
    """
    entries = list_pending_escalations(redefinition_only=False)
    target = next((e for e in entries if e.queue_index == queue_index), None)
    if target is None:
        return RedefinitionResult(success=False, error=f"No queue entry at index {queue_index}")
    if not target.redefinition:
        return RedefinitionResult(success=False, error=f"Queue entry {queue_index} is not a redefinition")

    project_nexus = target.event.get("project_nexus", "")
    workflow_id = target.event.get("workflow_id", "")

    if not project_nexus:
        return RedefinitionResult(success=False, error="Queue entry has no project_nexus — cannot resolve PED")

    from ped_watcher import load_ped_path, write_ped_pointer
    ped_path = load_ped_path(project_nexus)
    if not ped_path or not os.path.isfile(ped_path):
        return RedefinitionResult(success=False, error=f"PED not found for project_nexus={project_nexus}")

    # Step 1: Archive the current PED
    archived_path = _archive_ped(ped_path)

    # Step 2: Create the new PED at iteration 1
    if proposed_definition is None:
        proposed_definition = _extract_proposed_definition(target)
    new_ped_path = _create_new_ped(ped_path, project_nexus, proposed_definition, archived_path)

    # Repoint the project to the new PED
    try:
        write_ped_pointer(project_nexus, new_ped_path)
    except Exception as e:
        return RedefinitionResult(
            success=False,
            archived_path=archived_path,
            new_ped_path=new_ped_path,
            error=f"Failed to update project pointer: {e}",
        )

    # Step 3: Queue a re-evaluation task
    reeval_task_id = _queue_reeval(project_nexus, archived_path, new_ped_path, target)

    # Step 4: Remove from human queue
    _remove_queue_entry(queue_index)

    # Step 5: Emit a follow-through event for audit
    try:
        from oversight_events import emit
        emit({
            "event_type": "RedefinitionApplied",
            "project_nexus": project_nexus,
            "workflow_id": workflow_id,
            "archived_ped": archived_path,
            "new_ped": new_ped_path,
            "reeval_task_id": reeval_task_id,
            "approved_at": _now_iso(),
        })
    except Exception:
        pass

    return RedefinitionResult(
        success=True,
        archived_path=archived_path,
        new_ped_path=new_ped_path,
        reeval_task_id=reeval_task_id,
    )


def deny_redefinition(queue_index: int, reason: str = "") -> RedefinitionResult:
    """Deny a pending redefinition. Removes the entry from the queue and
    logs the denial. The PED is left unchanged.
    """
    entries = list_pending_escalations(redefinition_only=False)
    target = next((e for e in entries if e.queue_index == queue_index), None)
    if target is None:
        return RedefinitionResult(success=False, error=f"No queue entry at index {queue_index}")

    _remove_queue_entry(queue_index)

    try:
        from oversight_events import emit
        emit({
            "event_type": "RedefinitionDenied",
            "project_nexus": target.event.get("project_nexus", ""),
            "workflow_id": target.event.get("workflow_id", ""),
            "denial_reason": reason,
            "denied_at": _now_iso(),
        })
    except Exception:
        pass

    return RedefinitionResult(success=True)


# ---------- Helpers ----------

def _archive_ped(ped_path: str) -> str:
    """Copy the PED to a dated archive in the same directory."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base, ext = os.path.splitext(ped_path)
    archived_path = f"{base}.archived-{today}{ext}"
    # If a same-day archive already exists, append a counter
    counter = 1
    while os.path.exists(archived_path):
        archived_path = f"{base}.archived-{today}-{counter}{ext}"
        counter += 1

    with file_lock(ped_path):
        shutil.copy2(ped_path, archived_path)

    # Log the archival
    os.makedirs(os.path.dirname(ARCHIVED_PEDS_LOG), exist_ok=True)
    with open(ARCHIVED_PEDS_LOG, "a") as f:
        f.write(json.dumps({
            "original": ped_path,
            "archived": archived_path,
            "archived_at": _now_iso(),
        }) + "\n")

    return archived_path


def _extract_proposed_definition(entry: QueueEntry) -> str:
    """Pull the proposed definition out of the verdict payload, with fallback."""
    verdict = entry.verdict or {}
    raw_output = verdict.get("raw_output") or verdict.get("reasoning") or ""
    return f"# Proposed redefinition (extracted from Process Coherence verdict)\n\n{raw_output}"


def _create_new_ped(
    old_ped_path: str,
    project_nexus: str,
    proposed_definition: str,
    archived_path: str,
) -> str:
    """Write a fresh PED at iteration 1 with the new problem definition."""
    new_ped_path = old_ped_path  # same path, replacing content (old is archived)

    new_content = _build_new_ped_body(project_nexus, proposed_definition, archived_path)

    with file_lock(old_ped_path):
        with open(new_ped_path, "w", encoding="utf-8") as f:
            f.write(new_content)

    return new_ped_path


def _build_new_ped_body(
    project_nexus: str,
    proposed_definition: str,
    archived_path: str,
) -> str:
    """Construct the body of a new iteration-1 PED post-redefinition."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archived_basename = os.path.basename(archived_path)
    return f"""---
nexus:
  - {project_nexus}
type: PED
iteration: 1
date created: {today}
date modified: {today}
prior_ped_archive: {archived_basename}
---

# Problem Evolution Document — {project_nexus}

*Iteration 1, created from approved ESCALATE (redefinition) on {today}. The prior PED has been archived to `{archived_basename}`.*

## Problem Definition

{proposed_definition}

## Mission

- **Resolution Statement:** *(To be defined as part of re-evaluation against the new definition.)*

## Excluded Outcomes

*(To be elicited via PE-Iterate as the new definition is operationalized.)*

## Constraints

*(Carry forward applicable constraints from the archived PED; review each.)*

## Objectives

*(To be set as part of re-evaluation.)*

## Active Milestones

- [ ] Re-evaluate prior work against the new problem definition
- [ ] Confirm or revise carried-forward Constraints
- [ ] Establish new Mission Resolution Statement and Excluded Outcomes

## Aspirational Milestones

*(Pending re-evaluation outcome.)*

## Decision Log

### {today} — Redefinition applied
- Prior PED archived at `{archived_basename}`
- Process Coherence ESCALATE (redefinition) verdict approved by user
- First task under the new definition: re-evaluate prior work; carry forward what still applies, discard what doesn't, identify what needs rework
- This iteration begins with locked fields intentionally minimal; PE-Iterate populates them as the new definition is operationalized

## Oversight Specification

```yaml
oversight_specification:
  triggers_active: [milestone_claimed, framework_complete, milestone_blocked, redefinition_evidence]
  framework_chain: []
  per_milestone_criteria: use_declared
  revisit_triggers: []
  escalation_contact: user
```
"""


def _queue_reeval(
    project_nexus: str,
    archived_path: str,
    new_ped_path: str,
    entry: QueueEntry,
) -> str:
    """Queue a re-evaluation task — first thing to happen under the new PED."""
    task_id = f"reeval-{project_nexus}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    task = {
        "task_id": task_id,
        "task_type": "redefinition_reevaluation",
        "project_nexus": project_nexus,
        "archived_ped": archived_path,
        "new_ped": new_ped_path,
        "originating_event": entry.event,
        "queued_at": _now_iso(),
        "instructions": (
            "Re-evaluate prior work against the new problem definition. "
            "For each Active milestone, prior framework output, and prior decision in "
            "the archived PED, classify as: (a) still applies and transfers, "
            "(b) needs adjustment for the new definition, or (c) is no longer relevant. "
            "Update the new PED's Active Milestones and Decision Log accordingly."
        ),
    }
    os.makedirs(os.path.dirname(REEVAL_QUEUE_PATH), exist_ok=True)
    with open(REEVAL_QUEUE_PATH, "a") as f:
        f.write(json.dumps(task) + "\n")
    return task_id


def _remove_queue_entry(queue_index: int):
    """Rewrite the human queue without the entry at queue_index."""
    if not os.path.isfile(HUMAN_QUEUE_PATH):
        return
    with file_lock(HUMAN_QUEUE_PATH):
        with open(HUMAN_QUEUE_PATH) as f:
            lines = f.readlines()
        kept = [line for i, line in enumerate(lines) if i != queue_index]
        with open(HUMAN_QUEUE_PATH, "w") as f:
            f.writelines(kept)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- CLI ----------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python redefinition_handler.py list")
        print("  python redefinition_handler.py approve <queue_index> [<proposed_definition>]")
        print("  python redefinition_handler.py deny <queue_index> [<reason>]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "list":
        entries = list_pending_redefinitions()
        if not entries:
            print("No pending redefinitions.")
        else:
            print(f"{len(entries)} pending redefinition(s):")
            for e in entries:
                print(f"  [{e.queue_index}] queued {e.queued_at} — project {e.event.get('project_nexus', '?')}")
                print(f"      reasoning: {(e.verdict.get('reasoning') or '')[:200]}")
    elif cmd == "approve":
        if len(sys.argv) < 3:
            print("Usage: approve <queue_index> [<proposed_definition>]")
            sys.exit(1)
        idx = int(sys.argv[2])
        prop = sys.argv[3] if len(sys.argv) >= 4 else None
        result = approve_redefinition(idx, prop)
        if result.success:
            print(f"OK: archived to {result.archived_path}")
            print(f"    new PED at {result.new_ped_path}")
            print(f"    reeval queued as {result.reeval_task_id}")
        else:
            print(f"FAIL: {result.error}")
            sys.exit(2)
    elif cmd == "deny":
        if len(sys.argv) < 3:
            print("Usage: deny <queue_index> [<reason>]")
            sys.exit(1)
        idx = int(sys.argv[2])
        reason = sys.argv[3] if len(sys.argv) >= 4 else ""
        result = deny_redefinition(idx, reason)
        if result.success:
            print("OK: denial recorded; queue entry removed.")
        else:
            print(f"FAIL: {result.error}")
            sys.exit(2)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
