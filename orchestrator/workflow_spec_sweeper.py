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
from corpus_watcher import load_workflow_pointer, list_known_workflows


WORKSPACE = os.path.expanduser("~/ora/")
OVERSIGHT_DATA_DIR = os.path.join(WORKSPACE, "data/oversight/")
HEARTBEAT_FILE = os.path.join(OVERSIGHT_DATA_DIR, "workflow-spec-sweeper-heartbeat.json")


@dataclass
class WorkflowDriftReport:
    workflow_id: str
    workflow_spec_path: str
    issues: list = field(default_factory=list)  # list[ReferenceIntegrityIssue]
    timestamp: str = ""

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
    """Run a full sweep. Emits WorkflowSpecDriftEvents for severe drift."""
    _write_heartbeat()
    reports: list[WorkflowDriftReport] = []
    for workflow_id in list_known_workflows():
        pointer = load_workflow_pointer(workflow_id)
        if pointer is None:
            continue
        report = sweep_workflow(workflow_id, pointer)
        reports.append(report)

        # Emit an event when issues exist (severity flag set on event)
        if report.issues and emit_event:
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
    return reports


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
