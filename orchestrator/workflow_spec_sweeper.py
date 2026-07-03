"""Workflow spec consistency sweeper — periodic check that workflow specs match
the bespoke frameworks they reference.

Runs on a schedule. For each registered workflow, validates referenced files
exist, section names align between the corpus template and the workflow spec,
and chain relationships resolve. Differences produce a workflow-spec-drift
report; severe drift produces an event for Layer B oversight.

Emission discipline (2026-07-02): drift events are deduplicated, not repeated.
A report whose issue set is identical to the last-reported one emits nothing —
persistent drift (a renamed corpus template, a missing framework file) is
reported once per distinct issue signature instead of once per sweep, which is
what turned a stale smoke-test registration into a 9,600-line event flood.

Stale registrations: a registration whose workflow spec file has vanished from
disk is handled as log-once-then-drop. The drift event fires on the first
missing sweep; after the miss limit AND a minimum elapsed wall-clock window
(both env-tunable) the watcher deregisters itself by archiving the pointer as
``workflow-pointer.json.deregistered``. Every sweep also rechecks existing
tombstones and restores the pointer when the recorded spec path exists again —
the self-heal lives here in the sweeper (not in the daemon's one-shot vault
scan), so it works mid-process and for specs outside the vault scan roots.

Per Reference — Meta-Layer Architecture §6 W5; addresses the Workflow Spec
Drift Trap from the PFF-CFF-OFF Integration Architecture.

Author: meta-layer implementation per Reference — Meta-Layer Architecture §6 W5.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from corpus_parser import parse_corpus_file
from workflow_spec_parser import (
    parse_workflow_spec_file,
    check_reference_integrity,
    ReferenceIntegrityIssue,
)
import corpus_watcher
from corpus_watcher import (
    load_workflow_pointer,
    list_known_workflows,
    workflow_pointer_path,
)


WORKSPACE = os.path.expanduser("~/ora/")
OVERSIGHT_DATA_DIR = os.path.join(WORKSPACE, "data/oversight/")
HEARTBEAT_FILE = os.path.join(OVERSIGHT_DATA_DIR, "workflow-spec-sweeper-heartbeat.json")

# Deregistration requires BOTH gates: at least this many consecutive
# missing-spec sweeps AND at least the minimum elapsed wall-clock window since
# the first miss. The count alone proved gameable — out-of-band sweeps (the
# CLI smoke test, a concurrent session's debug run) share the on-disk counter
# and could burn a count-only grace budget in seconds. Both values are
# provisional (3 sweeps / 10 minutes ≈ the default daemon cadence) and
# env-tunable until empirically calibrated.
DEFAULT_MISSING_SPEC_DEREGISTER_SWEEPS = 3
DEFAULT_MISSING_SPEC_MIN_ELAPSED_SEC = 600


@dataclass
class WorkflowDriftReport:
    workflow_id: str
    workflow_spec_path: str
    issues: list = field(default_factory=list)  # list[ReferenceIntegrityIssue]
    timestamp: str = ""
    # True when a registered (non-empty) spec path no longer exists on disk —
    # the stale-registration signature that triggers log-once-then-deregister.
    # An intentionally blank spec path (corpus-only registration) is NOT
    # deregisterable; it flows through the signature-dedup drift path instead.
    spec_file_missing: bool = False

    def is_severe(self) -> bool:
        """A report is severe if any issue is missing_file (which means routing
        will break) — milder issues like orphan_section produce warnings only.
        """
        return any(i.issue_type == "missing_file" for i in self.issues)


@dataclass
class WorkflowSpecDriftEvent:
    event_type: str
    workflow_id: str
    project_nexus: str
    issues_summary: list  # list[dict] for serialization
    severe: bool
    timestamp: str


def sweep_workflow(workflow_id: str, pointer: dict) -> WorkflowDriftReport:
    """Validate one workflow. Returns the drift report."""
    workflow_spec_path = pointer.get("workflow_spec_path", "")
    corpus_template_path = pointer.get("corpus_template_path", "")

    report = WorkflowDriftReport(
        workflow_id=workflow_id,
        workflow_spec_path=workflow_spec_path,
        timestamp=_now_iso(),
    )

    if not workflow_spec_path:
        report.issues.append(ReferenceIntegrityIssue(
            issue_type="missing_file",
            artifact="workflow_spec",
            identifier=workflow_id,
            detail="No workflow spec path registered (corpus-only registration)",
        ))
        return report

    if not os.path.isfile(workflow_spec_path):
        report.spec_file_missing = True
        report.issues.append(ReferenceIntegrityIssue(
            issue_type="missing_file",
            artifact="workflow_spec",
            identifier=workflow_id,
            detail=f"Workflow spec file not found at {workflow_spec_path}",
        ))
        return report

    try:
        spec = parse_workflow_spec_file(workflow_spec_path)
    except Exception as e:
        report.issues.append(ReferenceIntegrityIssue(
            issue_type="missing_file",
            artifact="workflow_spec",
            identifier=workflow_id,
            detail=f"Failed to parse workflow spec: {e}",
        ))
        return report

    # Check framework files exist
    framework_files_exist = {}
    for p in spec.pffs:
        if p.path:
            framework_files_exist[p.path] = os.path.isfile(p.path)
    for o in spec.offs:
        if o.path:
            framework_files_exist[o.path] = os.path.isfile(o.path)

    # Check corpus template existence + load section ids
    corpus_template_sections: Optional[list] = None
    if corpus_template_path and os.path.isfile(corpus_template_path):
        try:
            template = parse_corpus_file(corpus_template_path)
            corpus_template_sections = [s.section_id for s in template.sections]
        except Exception as e:
            report.issues.append(ReferenceIntegrityIssue(
                issue_type="missing_file",
                artifact="corpus_template",
                identifier=corpus_template_path,
                detail=f"Failed to parse corpus template: {e}",
            ))
    elif corpus_template_path:
        report.issues.append(ReferenceIntegrityIssue(
            issue_type="missing_file",
            artifact="corpus_template",
            identifier=corpus_template_path,
            detail="Corpus template file not found",
        ))

    # Run integrity check
    issues = check_reference_integrity(
        spec,
        corpus_template_sections=corpus_template_sections,
        framework_files_exist=framework_files_exist,
    )
    report.issues.extend(issues)

    return report


def sweep(emit_event=None) -> list[WorkflowDriftReport]:
    """Run a full sweep. Emits WorkflowSpecDriftEvents for drift.

    Emission is deduplicated per workflow: a report whose issue signature
    matches the last-emitted one is silent, so persistent drift is reported
    once per distinct problem, not once per sweep.

    A workflow whose (non-empty) spec path has vanished from disk is a
    stale-registration candidate: the drift event fires on the first missing
    sweep, and once the miss count AND elapsed-time gates are both met the
    watcher deregisters itself — the pointer is archived in place and a
    log-only WorkflowWatcherDeregistered event records the drop. Each sweep
    also rechecks existing tombstones and restores any whose recorded spec
    path exists again (emitting WorkflowWatcherReregistered), so a
    false-positive drop self-heals here in the sweeper without a daemon
    restart and regardless of where the spec lives.

    Observation-only mode: when ``emit_event`` is None the sweep reports but
    persists nothing — no miss counting, no signature updates, no
    deregistration, no tombstone restore. An emitter-less invocation can
    never consume the grace window or mutate live registrations.
    """
    _write_heartbeat()
    if emit_event is not None:
        _recheck_tombstones(emit_event)
    reports: list[WorkflowDriftReport] = []
    for workflow_id in list_known_workflows():
        pointer = load_workflow_pointer(workflow_id)
        if pointer is None:
            continue
        try:
            report = sweep_workflow(workflow_id, pointer)
        except Exception as e:
            print(f"[workflow_spec_sweeper] sweep_workflow failed for {workflow_id}: {e}")
            continue
        reports.append(report)

        if emit_event is None:
            continue
        # One workflow's bad on-disk state must not abort the sweep for the
        # workflows sorted after it.
        try:
            state = _load_sweeper_state(workflow_id, pointer)
            if report.spec_file_missing:
                _handle_missing_spec(workflow_id, pointer, report, state, emit_event)
            elif report.issues:
                _handle_persistent_drift(workflow_id, pointer, report, state, emit_event)
            else:
                _clear_sweeper_state(workflow_id)
        except Exception as e:
            print(f"[workflow_spec_sweeper] drift handling failed for {workflow_id}: {e}")
    return reports


def _emit_drift_event(workflow_id: str, pointer: dict, report: WorkflowDriftReport, emit_event):
    evt = WorkflowSpecDriftEvent(
        event_type="WorkflowSpecDrift",
        workflow_id=workflow_id,
        project_nexus=pointer.get("project_nexus", ""),
        issues_summary=[
            {"type": i.issue_type, "artifact": i.artifact, "id": i.identifier, "detail": i.detail}
            for i in report.issues
        ],
        severe=report.is_severe(),
        timestamp=_now_iso(),
    )
    try:
        emit_event(evt)
    except Exception as e:
        print(f"[workflow_spec_sweeper] emit_event raised: {e}")


# ---------- sweeper sidecar state ----------
#
# One JSON sidecar per workflow dir, next to the pointer:
#   consecutive_misses / first_missed_at / last_missed_at / drift_emitted
#       — missing-spec episode tracking
#   last_issue_signature / last_issue_emitted_at
#       — dedup of persistent drift on an existing spec
#   pointer_registered_at — episode binding: state recorded against an older
#       pointer registration is stale and discarded, so a re-registered
#       workflow never inherits a previous episode's counters.

def _sweeper_state_path(workflow_id: str) -> str:
    return os.path.join(
        os.path.dirname(workflow_pointer_path(workflow_id)),
        "sweeper-state.json",
    )


def _load_sweeper_state(workflow_id: str, pointer: dict) -> dict:
    """Load the sidecar; returns {} when absent, corrupt, wrong-shaped, or
    recorded against an older registration of the same workflow_id."""
    path = _sweeper_state_path(workflow_id)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path) as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(state, dict):
        return {}
    if state.get("pointer_registered_at") != pointer.get("registered_at", ""):
        return {}
    try:
        state["consecutive_misses"] = int(state.get("consecutive_misses", 0))
    except (TypeError, ValueError):
        return {}
    return state


def _save_sweeper_state(workflow_id: str, state: dict) -> bool:
    try:
        with open(_sweeper_state_path(workflow_id), "w") as f:
            json.dump(state, f, indent=2)
        return True
    except OSError as e:
        print(f"[workflow_spec_sweeper] failed to write sweeper state for {workflow_id}: {e}")
        return False


def _clear_sweeper_state(workflow_id: str):
    path = _sweeper_state_path(workflow_id)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _issues_signature(issues) -> str:
    canonical = json.dumps(
        sorted([i.issue_type, i.artifact, i.identifier, i.detail] for i in issues)
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _elapsed_seconds(since_iso: str) -> Optional[float]:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(since_iso)).total_seconds()
    except (TypeError, ValueError):
        return None


# ---------- persistent drift (spec exists, issues found) ----------

def _handle_persistent_drift(workflow_id: str, pointer: dict, report: WorkflowDriftReport, state: dict, emit_event):
    """Emit the drift event only when the issue set differs from the last one
    reported for this registration."""
    signature = _issues_signature(report.issues)
    if state.get("last_issue_signature") == signature:
        return
    new_state = {
        "pointer_registered_at": pointer.get("registered_at", ""),
        "last_issue_signature": signature,
        "last_issue_emitted_at": _now_iso(),
    }
    # Record-then-emit: if persistence fails we stay silent and retry next
    # sweep, rather than reverting to a per-sweep event flood.
    if not _save_sweeper_state(workflow_id, new_state):
        return
    _emit_drift_event(workflow_id, pointer, report, emit_event)


# ---------- stale-registration handling (spec file vanished) ----------

def _missing_spec_limit() -> int:
    raw = os.environ.get("ORA_WORKFLOW_SWEEPER_MISSING_SPEC_SWEEPS", "")
    try:
        limit = int(raw)
        if limit > 0:
            return limit
    except ValueError:
        pass
    return DEFAULT_MISSING_SPEC_DEREGISTER_SWEEPS


def _missing_spec_min_elapsed() -> float:
    raw = os.environ.get("ORA_WORKFLOW_SWEEPER_MISSING_SPEC_MIN_SEC", "")
    try:
        sec = float(raw)
        if sec >= 0:
            return sec
    except ValueError:
        pass
    return DEFAULT_MISSING_SPEC_MIN_ELAPSED_SEC


def _handle_missing_spec(workflow_id: str, pointer: dict, report: WorkflowDriftReport, state: dict, emit_event):
    """Track a missing-spec episode; emit once, deregister when both the miss
    count and the elapsed-time gates are met."""
    now = _now_iso()
    state["pointer_registered_at"] = pointer.get("registered_at", "")
    state["workflow_spec_path"] = pointer.get("workflow_spec_path", "")
    state["consecutive_misses"] = state.get("consecutive_misses", 0) + 1
    state.setdefault("first_missed_at", now)
    state["last_missed_at"] = now

    elapsed = _elapsed_seconds(state["first_missed_at"])
    if elapsed is None:
        # Unparseable timestamp (hand edit): restart the clock rather than
        # deregistering on garbage.
        state["first_missed_at"] = now
        elapsed = 0.0

    if (state["consecutive_misses"] >= _missing_spec_limit()
            and elapsed >= _missing_spec_min_elapsed()):
        _deregister_workflow(workflow_id, pointer, state, emit_event)
        return

    first_detection = not state.get("drift_emitted")
    if first_detection:
        state["drift_emitted"] = True
    # Record-then-emit, as in _handle_persistent_drift: a failed state write
    # degrades to silence (no event, no counter advance) instead of reverting
    # to the per-sweep flood this module exists to prevent.
    if not _save_sweeper_state(workflow_id, state):
        return
    if first_detection and report.issues:
        _emit_drift_event(workflow_id, pointer, report, emit_event)


def _deregister_workflow(workflow_id: str, pointer: dict, state: dict, emit_event):
    """Archive the pointer file so list_known_workflows() stops returning this
    workflow. The tombstone keeps the registration inspectable and is restored
    by _recheck_tombstones if the recorded spec path ever exists again."""
    # Clear the sidecar BEFORE archiving: a crash in between leaves the
    # pointer live with a fresh counter (the safe direction), never an
    # orphaned counter that a future registration could inherit.
    _clear_sweeper_state(workflow_id)
    pointer_path = workflow_pointer_path(workflow_id)
    tombstone = pointer_path + ".deregistered"
    try:
        os.replace(pointer_path, tombstone)
    except OSError as e:
        print(f"[workflow_spec_sweeper] failed to deregister {workflow_id}: {e}")
        return

    print(
        f"[workflow_spec_sweeper] deregistered watcher for '{workflow_id}': "
        f"spec missing for {state['consecutive_misses']} consecutive sweeps "
        f"since {state.get('first_missed_at', '?')} "
        f"(pointer archived at {tombstone})"
    )
    try:
        emit_event({
            "event_type": "WorkflowWatcherDeregistered",
            "workflow_id": workflow_id,
            "project_nexus": pointer.get("project_nexus", ""),
            "workflow_spec_path": pointer.get("workflow_spec_path", ""),
            "consecutive_misses": state["consecutive_misses"],
            "first_missed_at": state.get("first_missed_at", ""),
            "pointer_tombstone": tombstone,
            "reason": "workflow spec file missing; watcher auto-deregistered",
            "timestamp": _now_iso(),
        })
    except Exception as e:
        print(f"[workflow_spec_sweeper] emit_event raised: {e}")


def _recheck_tombstones(emit_event):
    """Restore any archived registration whose recorded spec path exists
    again. This is the self-heal for false-positive deregistrations: it runs
    on every sweep, needs no daemon restart, and works for specs outside the
    vault scan roots because it uses the path recorded in the tombstone."""
    base = corpus_watcher.OVERSIGHT_DATA_DIR
    if not os.path.isdir(base):
        return
    for name in sorted(os.listdir(base)):
        tombstone = os.path.join(base, name, "workflow-pointer.json.deregistered")
        if not os.path.isfile(tombstone):
            continue
        pointer_path = workflow_pointer_path(name)
        if os.path.isfile(pointer_path):
            # Re-registered independently; leave the tombstone as forensics.
            continue
        try:
            with open(tombstone) as f:
                pointer = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(pointer, dict):
            continue
        spec_path = pointer.get("workflow_spec_path", "")
        if not spec_path or not os.path.isfile(spec_path):
            continue
        try:
            os.replace(tombstone, pointer_path)
        except OSError as e:
            print(f"[workflow_spec_sweeper] failed to restore pointer for {name}: {e}")
            continue
        _clear_sweeper_state(name)
        print(
            f"[workflow_spec_sweeper] restored watcher for '{name}': "
            f"spec reappeared at {spec_path}"
        )
        try:
            emit_event({
                "event_type": "WorkflowWatcherReregistered",
                "workflow_id": name,
                "project_nexus": pointer.get("project_nexus", ""),
                "workflow_spec_path": spec_path,
                "reason": "workflow spec file reappeared; archived pointer restored",
                "timestamp": _now_iso(),
            })
        except Exception as e:
            print(f"[workflow_spec_sweeper] emit_event raised: {e}")


def _write_heartbeat():
    os.makedirs(OVERSIGHT_DATA_DIR, exist_ok=True)
    with open(HEARTBEAT_FILE, "w") as f:
        json.dump({"watcher": "workflow_spec_sweeper", "beat_at": _now_iso()}, f)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    # Emit durably, like the daemon does: a CLI sweep that counts a miss or
    # deregisters must leave the same events.jsonl trace as a scheduled one.
    from oversight_events import emit
    reports = sweep(emit_event=emit)
    print(f"Workflow spec sweep complete. {len(reports)} workflow(s) checked.")
    for r in reports:
        if r.issues:
            print(f"  - {r.workflow_id}: {len(r.issues)} issue(s){' [SEVERE]' if r.is_severe() else ''}")
            for i in r.issues:
                print(f"    * {i.issue_type} [{i.artifact}]: {i.identifier} — {i.detail}")
        else:
            print(f"  - {r.workflow_id}: clean")
