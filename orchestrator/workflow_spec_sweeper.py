"""Workflow spec consistency sweeper — periodic check that workflow specs match
the bespoke frameworks they reference.

Runs on a schedule. For each registered workflow, validates referenced files
exist, section names align between the corpus template and the workflow spec,
and chain relationships resolve. Differences produce a workflow-spec-drift
report; severe drift produces an event for Layer B oversight.

Per Reference — Meta-Layer Architecture §6 W5; addresses the Workflow Spec
Drift Trap from the PFF-CFF-OFF Integration Architecture.

Author: meta-layer implementation per Reference — Meta-Layer Architecture §6 W5.
"""
from __future__ import annotations

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
from corpus_watcher import (
    load_workflow_pointer,
    list_known_workflows,
    workflow_pointer_path,
)


WORKSPACE = os.path.expanduser("~/ora/")
OVERSIGHT_DATA_DIR = os.path.join(WORKSPACE, "data/oversight/")
HEARTBEAT_FILE = os.path.join(OVERSIGHT_DATA_DIR, "workflow-spec-sweeper-heartbeat.json")

# How many consecutive sweeps a workflow's spec file may be missing before the
# watcher deregisters itself. Provisional value — 3 sweeps at the default
# 5-minute interval gives a ~15-minute grace window so a vault mid-sync rewrite
# doesn't drop a live registration, while a genuinely deleted spec (e.g. a
# smoke test's temp directory) stops emitting within the same quarter hour.
DEFAULT_MISSING_SPEC_DEREGISTER_SWEEPS = 3


@dataclass
class WorkflowDriftReport:
    workflow_id: str
    workflow_spec_path: str
    issues: list = field(default_factory=list)  # list[ReferenceIntegrityIssue]
    timestamp: str = ""
    # True when the spec file itself is gone from disk (as opposed to existing
    # but failing to parse, or referencing missing frameworks). This is the
    # stale-registration signature that triggers log-once-then-deregister.
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

    if not workflow_spec_path or not os.path.isfile(workflow_spec_path):
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
    """Run a full sweep. Emits WorkflowSpecDriftEvents for severe drift.

    A workflow whose spec file has vanished from disk is handled as a
    stale-registration candidate rather than a perpetual drift emitter:
    the drift event is emitted on the first missing sweep only, and after
    the miss limit (default 3 consecutive sweeps) the watcher deregisters
    itself — the pointer file is archived in place and a log-only
    WorkflowWatcherDeregistered event records the drop. If the spec file
    reappears (vault sync, restored file) the miss counter resets; the
    daemon's vault auto-scan re-registers any deregistered workflow whose
    spec comes back, so a false-positive drop self-heals.
    """
    _write_heartbeat()
    reports: list[WorkflowDriftReport] = []
    for workflow_id in list_known_workflows():
        pointer = load_workflow_pointer(workflow_id)
        if pointer is None:
            continue
        report = sweep_workflow(workflow_id, pointer)
        reports.append(report)

        if report.spec_file_missing:
            _handle_missing_spec(workflow_id, pointer, report, emit_event)
            continue
        _clear_missing_spec_state(workflow_id)

        # Emit an event when issues exist (severity flag set on event)
        if report.issues and emit_event:
            _emit_drift_event(workflow_id, pointer, report, emit_event)
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


# ---------- stale-registration handling ----------

def _missing_spec_limit() -> int:
    raw = os.environ.get("ORA_WORKFLOW_SWEEPER_MISSING_SPEC_SWEEPS", "")
    try:
        limit = int(raw)
        if limit > 0:
            return limit
    except ValueError:
        pass
    return DEFAULT_MISSING_SPEC_DEREGISTER_SWEEPS


def _missing_spec_state_path(workflow_id: str) -> str:
    return os.path.join(
        os.path.dirname(workflow_pointer_path(workflow_id)),
        "missing-spec-state.json",
    )


def _load_missing_spec_state(workflow_id: str) -> Optional[dict]:
    path = _missing_spec_state_path(workflow_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _clear_missing_spec_state(workflow_id: str):
    path = _missing_spec_state_path(workflow_id)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _handle_missing_spec(workflow_id: str, pointer: dict, report: WorkflowDriftReport, emit_event):
    """Track consecutive missing-spec sweeps; emit once, then deregister at limit."""
    state = _load_missing_spec_state(workflow_id) or {
        "consecutive_misses": 0,
        "first_missed_at": _now_iso(),
    }
    state["consecutive_misses"] = int(state.get("consecutive_misses", 0)) + 1
    state["last_missed_at"] = _now_iso()
    state["workflow_spec_path"] = pointer.get("workflow_spec_path", "")

    if state["consecutive_misses"] >= _missing_spec_limit():
        _deregister_workflow(workflow_id, pointer, state, emit_event)
        return

    try:
        with open(_missing_spec_state_path(workflow_id), "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        print(f"[workflow_spec_sweeper] failed to write missing-spec state for {workflow_id}: {e}")

    # Emit the drift event on first detection only; repeats add no information.
    if state["consecutive_misses"] == 1 and report.issues and emit_event:
        _emit_drift_event(workflow_id, pointer, report, emit_event)


def _deregister_workflow(workflow_id: str, pointer: dict, state: dict, emit_event):
    """Archive the pointer file so list_known_workflows() stops returning this
    workflow. The tombstone keeps the registration inspectable; the daemon's
    vault auto-scan writes a fresh pointer if the spec ever reappears."""
    pointer_path = workflow_pointer_path(workflow_id)
    tombstone = pointer_path + ".deregistered"
    try:
        os.replace(pointer_path, tombstone)
    except OSError as e:
        print(f"[workflow_spec_sweeper] failed to deregister {workflow_id}: {e}")
        return
    _clear_missing_spec_state(workflow_id)

    print(
        f"[workflow_spec_sweeper] deregistered watcher for '{workflow_id}': "
        f"spec missing for {state['consecutive_misses']} consecutive sweeps "
        f"(pointer archived at {tombstone})"
    )
    if emit_event:
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


def _write_heartbeat():
    os.makedirs(OVERSIGHT_DATA_DIR, exist_ok=True)
    with open(HEARTBEAT_FILE, "w") as f:
        json.dump({"watcher": "workflow_spec_sweeper", "beat_at": _now_iso()}, f)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    reports = sweep()
    print(f"Workflow spec sweep complete. {len(reports)} workflow(s) checked.")
    for r in reports:
        if r.issues:
            print(f"  - {r.workflow_id}: {len(r.issues)} issue(s){' [SEVERE]' if r.is_severe() else ''}")
            for i in r.issues:
                print(f"    * {i.issue_type} [{i.artifact}]: {i.identifier} — {i.detail}")
        else:
            print(f"  - {r.workflow_id}: clean")
