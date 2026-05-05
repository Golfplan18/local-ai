"""Oversight verdict-action handlers.

Implements PROCEED / REVISE / ESCALATE / ESCALATE-redefinition handlers per
Reference — Meta-Layer Architecture §9. Each verdict translates into actual
state changes: Decision Log appends, framework chain dispatch, human-queue
surfacing, dependent-corpus actions.

Includes a small file-lock primitive for PED, corpus, and workflow spec
write coordination (per §10 O4 — concurrent PED writes).

Author: meta-layer implementation per Reference — Meta-Layer Architecture §9.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from oversight_context import OversightContextBundle


WORKSPACE = os.path.expanduser("~/ora/")
OVERSIGHT_DATA_DIR = os.path.join(WORKSPACE, "data/oversight/")
HUMAN_QUEUE_PATH = os.path.join(OVERSIGHT_DATA_DIR, "human-queue.jsonl")
ACTIONS_LOG_PATH = os.path.join(OVERSIGHT_DATA_DIR, "actions.jsonl")

DEFAULT_LOCK_TIMEOUT = 30  # seconds, per §10 O4
REVISE_LIMIT = 3  # per §10 O3


# ---------- File lock primitive ----------

@contextlib.contextmanager
def file_lock(path: str, timeout: float = DEFAULT_LOCK_TIMEOUT):
    """Acquire an exclusive advisory lock on a sidecar lockfile for `path`.

    The actual file isn't locked (so the lock works for files that don't
    exist yet); a sidecar `<path>.lock` file is created and locked. On
    timeout, raises TimeoutError. Always releases on context exit.
    """
    lock_path = path + ".lock"
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    fp = open(lock_path, "w")
    deadline = time.time() + timeout
    try:
        while True:
            try:
                fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() >= deadline:
                    raise TimeoutError(f"Could not acquire lock on {lock_path} within {timeout}s")
                time.sleep(0.1)
        yield
    finally:
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        fp.close()


# ---------- Verdict tracking ----------

REVISE_COUNTERS_PATH = os.path.join(OVERSIGHT_DATA_DIR, "revise-counters.json")


def _load_revise_counters() -> dict:
    if not os.path.isfile(REVISE_COUNTERS_PATH):
        return {}
    try:
        with open(REVISE_COUNTERS_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_revise_counters(counters: dict):
    os.makedirs(os.path.dirname(REVISE_COUNTERS_PATH), exist_ok=True)
    with open(REVISE_COUNTERS_PATH, "w") as f:
        json.dump(counters, f, indent=2)


def _revise_key(event: dict) -> str:
    """Per §10 O3, count REVISE verdicts per (milestone_id, project_nexus)."""
    return f"{event.get('project_nexus', '') or event.get('workflow_id', '')}::{event.get('milestone_id') or event.get('section_id') or event.get('milestone_text', '')}"


# ---------- Main entry point ----------

def apply_verdict(
    event: dict,
    bundle: OversightContextBundle,
    mode: str,
    verdict: dict,
):
    """Apply the verdict-action for the given Process Coherence verdict."""
    verdict_label = (verdict.get("verdict") or "UNKNOWN").upper()
    action_record: dict = {
        "timestamp": _now_iso(),
        "event_type": event.get("event_type", ""),
        "project_nexus": event.get("project_nexus", ""),
        "workflow_id": event.get("workflow_id", ""),
        "mode": mode,
        "verdict": verdict_label,
        "reasoning": (verdict.get("reasoning") or "")[:500],
    }

    if verdict_label == "PROCEED":
        _apply_proceed(event, bundle, action_record)
    elif verdict_label == "REVISE":
        _apply_revise(event, bundle, verdict, action_record)
    elif verdict_label.startswith("ESCALATE"):
        _apply_escalate(event, bundle, verdict, action_record, redefinition="REDEFINITION" in verdict_label)
    else:
        action_record["action"] = "unknown_verdict"

    _append_actions_log(action_record)


# ---------- Verdict implementations ----------

def _apply_proceed(event: dict, bundle: OversightContextBundle, action_record: dict):
    """PROCEED — record Decision Log entry; dispatch downstream where appropriate."""
    _append_decision_log_entry(event, bundle, "PROCEED", action_record)

    # Reset REVISE counter for this milestone
    counters = _load_revise_counters()
    key = _revise_key(event)
    if key in counters:
        del counters[key]
        _save_revise_counters(counters)

    et = event.get("event_type", "")
    if et == "FrameworkComplete":
        # If the project's oversight spec has a framework chain, dispatch the next one
        chain = bundle.framework_chain or []
        current_idx = _find_framework_in_chain(chain, event.get("framework_id", ""))
        if current_idx is not None and current_idx + 1 < len(chain):
            next_framework = chain[current_idx + 1]
            action_record["next_framework_dispatch"] = (
                next_framework.get("id") if isinstance(next_framework, dict) else next_framework
            )

    if et == "CorpusValidated":
        # Auto-dispatch eligible OFFs
        action_record["off_dispatch_pending"] = True

    if et == "ChainPropagationRequired":
        # Dispatch the propagation action per the chain rule
        action_record["chain_propagation_dispatched"] = event.get("dependent_corpora", [])

    action_record["action"] = "proceed"


def _apply_revise(event: dict, bundle: OversightContextBundle, verdict: dict, action_record: dict):
    """REVISE — record corrective action; cap revisions at 3 per §10 O3."""
    counters = _load_revise_counters()
    key = _revise_key(event)
    counters[key] = counters.get(key, 0) + 1

    if counters[key] >= REVISE_LIMIT:
        # Force escalate after 3 revisions
        del counters[key]
        _save_revise_counters(counters)
        _apply_escalate(
            event,
            bundle,
            verdict,
            action_record,
            redefinition=False,
            forced_reason=f"REVISE limit ({REVISE_LIMIT}) reached for {key}",
        )
        return

    _save_revise_counters(counters)
    _append_decision_log_entry(event, bundle, "REVISE", action_record, extra_text=verdict.get("reasoning", ""))
    action_record["action"] = "revise"
    action_record["revise_count"] = counters[key]
    action_record["corrective_specification"] = verdict.get("reasoning", "")


def _apply_escalate(
    event: dict,
    bundle: OversightContextBundle,
    verdict: dict,
    action_record: dict,
    redefinition: bool = False,
    forced_reason: str = "",
):
    """ESCALATE — pause chain, surface to human queue."""
    _append_decision_log_entry(
        event, bundle,
        "ESCALATE (redefinition)" if redefinition else "ESCALATE",
        action_record,
        extra_text=verdict.get("reasoning", "") + (f"\n\nForced: {forced_reason}" if forced_reason else ""),
    )

    queue_entry = {
        "queued_at": _now_iso(),
        "event": event,
        "verdict": verdict,
        "redefinition": redefinition,
        "forced_reason": forced_reason,
        "context_summary": {
            "project_nexus": event.get("project_nexus", ""),
            "workflow_id": event.get("workflow_id", ""),
            "claim": bundle.claim,
            "load_errors": bundle.load_errors,
        },
    }
    # Route through oversight_queue so the entry gets a stable id and an
    # AI-generated default name (used by the V3 sidebar Paused panel).
    # Falls back to a direct write if oversight_queue is unavailable for
    # any reason — preserves the existing behavior.
    try:
        from oversight_queue import add_entry as _add_queue_entry
        _add_queue_entry(queue_entry)
    except Exception:
        _append_human_queue(queue_entry)
    action_record["action"] = "escalate" + ("_redefinition" if redefinition else "")
    action_record["queued_for_human_review"] = True


# ---------- Decision Log appending ----------

def _append_decision_log_entry(
    event: dict,
    bundle: OversightContextBundle,
    verdict_label: str,
    action_record: dict,
    extra_text: str = "",
):
    """Append a Decision Log entry to the project's PED.

    Section: ## Decision Log. Lock-protected fields (Mission, Excluded
    Outcomes, Constraints) are NOT modified — only the Decision Log section.
    Per §10 O5, lock-protected mutations are rejected at the writer level.
    """
    project_nexus = event.get("project_nexus", "")
    if not project_nexus:
        return

    from ped_watcher import load_ped_path
    ped_path = load_ped_path(project_nexus)
    if not ped_path or not os.path.isfile(ped_path):
        return

    entry_lines = [
        f"### {_today_iso()} — Process Coherence Verdict: {verdict_label}",
        f"- Event type: {event.get('event_type', '')}",
        f"- Mode: {action_record.get('mode', '')}",
    ]
    milestone_ref = (
        event.get("milestone_text")
        or event.get("milestone_id")
        or event.get("section_id")
        or ""
    )
    if milestone_ref:
        entry_lines.append(f"- Milestone/section: {milestone_ref}")
    if extra_text:
        entry_lines.append("- Reasoning:")
        for line in extra_text.split("\n"):
            entry_lines.append(f"  > {line}")
    entry_text = "\n".join(entry_lines) + "\n\n"

    try:
        with file_lock(ped_path):
            with open(ped_path, encoding="utf-8") as f:
                content = f.read()
            new_content = _insert_into_decision_log(content, entry_text)
            with open(ped_path, "w", encoding="utf-8") as f:
                f.write(new_content)
    except (TimeoutError, OSError) as e:
        action_record["decision_log_write_failed"] = str(e)


def _insert_into_decision_log(content: str, entry_text: str) -> str:
    """Insert entry into the ## Decision Log section. If the section doesn't
    exist, append it to the end of the file.
    """
    import re
    # Find the Decision Log section
    match = re.search(r"^##\s+Decision Log\s*$", content, re.MULTILINE)
    if not match:
        # Append a new section at end
        return content.rstrip() + "\n\n## Decision Log\n\n" + entry_text

    insert_pos = match.end()
    # Insert immediately after the heading line
    return (
        content[:insert_pos] + "\n\n" + entry_text + content[insert_pos:].lstrip("\n")
    )


# ---------- Human queue ----------

def _append_human_queue(entry: dict):
    os.makedirs(OVERSIGHT_DATA_DIR, exist_ok=True)
    with open(HUMAN_QUEUE_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def read_human_queue() -> list[dict]:
    """Read pending human-queue entries. Used by UI to surface escalations."""
    if not os.path.isfile(HUMAN_QUEUE_PATH):
        return []
    out = []
    try:
        with open(HUMAN_QUEUE_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


# ---------- Helpers ----------

def _find_framework_in_chain(chain: list, framework_id: str) -> Optional[int]:
    for i, f in enumerate(chain):
        if isinstance(f, dict) and f.get("id") == framework_id:
            return i
        if f == framework_id:
            return i
    return None


def _append_actions_log(record: dict):
    os.makedirs(OVERSIGHT_DATA_DIR, exist_ok=True)
    with open(ACTIONS_LOG_PATH, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
