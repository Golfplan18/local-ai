"""Oversight context loader — assembles inputs for Process Coherence.

Given an event, loads the appropriate locked definitions, output contract,
deliverable, claim, decision log, and PEF toolkit reference, returning a
ContextBundle that Process Coherence consumes per Reference — Meta-Layer
Architecture §8.

The loader handles both project-level events (E1–E6: locks come from the
PED) and workflow-level events (E7–E12: locks come from corpus template +
workflow spec).

Author: meta-layer implementation per Reference — Meta-Layer Architecture §8.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from ped_parser import parse_ped_file, ParsedPED
from corpus_parser import parse_corpus_file, ParsedCorpus
from workflow_spec_parser import parse_workflow_spec_file, ParsedWorkflowSpec
from ped_watcher import load_ped_path
from corpus_watcher import load_workflow_pointer


WORKSPACE = os.path.expanduser("~/ora/")
VAULT = os.path.expanduser("~/Documents/vault/")
PEF_PATH = os.path.join(VAULT, "Framework — Problem Evolution.md")


@dataclass
class OversightContextBundle:
    event: dict
    event_class: str  # "project-level" or "workflow-level"
    project_level_locks: Optional[dict] = None
    workflow_level_locks: Optional[dict] = None
    output_contract: str = ""
    deliverable: str = ""
    claim: str = ""
    decision_log_excerpt: list = field(default_factory=list)
    framework_chain: list = field(default_factory=list)
    pef_toolkit_reference: str = PEF_PATH
    load_errors: list = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True if all required inputs are present."""
        if self.event_class == "project-level":
            return self.project_level_locks is not None and not self.load_errors
        if self.event_class == "workflow-level":
            return (
                self.project_level_locks is not None
                and self.workflow_level_locks is not None
                and not self.load_errors
            )
        return False


PROJECT_LEVEL_EVENTS = {
    "FrameworkStarted",
    "MilestoneComplete",
    "FrameworkComplete",
    "MilestoneClaimed",
    "MilestoneBlocked",
    "RedefinitionEvidence",
}

WORKFLOW_LEVEL_EVENTS = {
    "CorpusInstanceCreated",
    "CorpusSectionPopulated",
    "CorpusValidated",
    "OFFRendered",
    "ChainPropagationRequired",
    "CorpusTemplateVersionChanged",
    "WorkflowSpecDrift",
}


def classify_event(event: dict) -> str:
    """Classify an event as project-level or workflow-level."""
    et = event.get("event_type", "")
    if et in PROJECT_LEVEL_EVENTS:
        return "project-level"
    if et in WORKFLOW_LEVEL_EVENTS:
        return "workflow-level"
    return "unknown"


def load_context(event: dict) -> OversightContextBundle:
    """Build the full context bundle for an event."""
    event_class = classify_event(event)
    bundle = OversightContextBundle(event=event, event_class=event_class)

    if event_class == "project-level":
        _load_project_level_context(event, bundle)
    elif event_class == "workflow-level":
        _load_workflow_level_context(event, bundle)
    else:
        bundle.load_errors.append(f"Unknown event type: {event.get('event_type')!r}")

    return bundle


# ---------- Project-level context loading ----------

def _load_project_level_context(event: dict, bundle: OversightContextBundle):
    project_nexus = event.get("project_nexus")
    if not project_nexus:
        bundle.load_errors.append("Event has no project_nexus — cannot load project-level locks.")
        return

    ped_path = load_ped_path(project_nexus)
    if not ped_path:
        bundle.load_errors.append(
            f"No PED registered for project_nexus={project_nexus!r}. "
            f"Run Framework — Oversight Configuration OS-Setup to register."
        )
        return

    if not os.path.isfile(ped_path):
        bundle.load_errors.append(f"PED file not found at {ped_path!r}")
        return

    try:
        ped = parse_ped_file(ped_path)
    except Exception as e:
        bundle.load_errors.append(f"Failed to parse PED at {ped_path!r}: {e}")
        return

    bundle.project_level_locks = {
        "mission_resolution_statement": ped.mission_resolution_statement,
        "excluded_outcomes": ped.excluded_outcomes,
        "constraints": [
            {
                "classification": c.classification,
                "statement": c.statement,
                "rationale": c.rationale,
                "revisit_trigger": c.revisit_trigger,
            }
            for c in ped.constraints
        ],
    }

    # Output contract for this event
    bundle.output_contract = _output_contract_for_event(event, ped)

    # Deliverable: read from event payload or scratch
    bundle.deliverable = _deliverable_for_event(event)

    # Claim: explicit or inferred
    bundle.claim = _claim_for_event(event)

    # Decision log (recent entries)
    bundle.decision_log_excerpt = [
        {"date": d.date, "summary": d.summary, "raw_text": d.raw_text}
        for d in ped.decision_log[-10:]
    ]

    # Framework chain from oversight spec
    if ped.oversight_specification:
        bundle.framework_chain = list(ped.oversight_specification.framework_chain or [])


def _output_contract_for_event(event: dict, ped: ParsedPED) -> str:
    """Derive the output contract — the 'done' specification — for a project-level event."""
    et = event.get("event_type", "")
    if et == "MilestoneClaimed":
        target = event.get("milestone_text", "")
        for m in ped.active_milestones:
            if m.statement == target or m.statement.startswith(target):
                return m.fields.get("Verification Criterion", "") or m.statement
    elif et in ("MilestoneComplete", "FrameworkComplete"):
        # Framework-completion — use the last active milestone's verification criterion
        if ped.active_milestones:
            m = ped.active_milestones[-1]
            return m.fields.get("Verification Criterion", "") or m.statement
    return ped.mission_resolution_statement


def _deliverable_for_event(event: dict) -> str:
    et = event.get("event_type", "")
    path = event.get("deliverable_path") or event.get("final_output_path")
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            pass
    if path and os.path.isdir(path):
        # Scratch dir — read the last milestone deliverable file
        try:
            files = sorted(os.listdir(path))
            for fn in reversed(files):
                full = os.path.join(path, fn)
                if os.path.isfile(full) and fn.endswith(".md"):
                    with open(full, encoding="utf-8") as f:
                        return f.read()
        except OSError:
            pass
    # Fall back: synthesize from event fields
    return event.get("milestone_text", "") or event.get("write_summary", "") or ""


def _claim_for_event(event: dict) -> str:
    et = event.get("event_type", "")
    if et == "MilestoneClaimed":
        return f"User claimed milestone complete: {event.get('milestone_text', '')!r}"
    if et == "MilestoneComplete":
        return f"Framework {event.get('framework_id')!r} reports milestone complete: drift_status={event.get('drift_status')}"
    if et == "FrameworkComplete":
        return f"Framework {event.get('framework_id')!r} reports complete (success={event.get('success')})"
    if et == "MilestoneBlocked":
        return f"Framework reports cannot achieve milestone: {event.get('block_reason', '')}"
    if et == "RedefinitionEvidence":
        return f"Redefinition evidence: {event.get('evidence_summary', '')}"
    return ""


# ---------- Workflow-level context loading ----------

def _load_workflow_level_context(event: dict, bundle: OversightContextBundle):
    workflow_id = event.get("workflow_id")
    if not workflow_id:
        bundle.load_errors.append("Event has no workflow_id — cannot load workflow-level locks.")
        return

    pointer = load_workflow_pointer(workflow_id)
    if pointer is None:
        bundle.load_errors.append(
            f"No workflow registered for workflow_id={workflow_id!r}. "
            f"Run Framework — Oversight Configuration OS-Setup."
        )
        return

    # Load corpus template
    template_path = pointer.get("corpus_template_path", "")
    template: Optional[ParsedCorpus] = None
    if template_path and os.path.isfile(template_path):
        try:
            template = parse_corpus_file(template_path)
        except Exception as e:
            bundle.load_errors.append(f"Failed to parse corpus template {template_path!r}: {e}")
    else:
        bundle.load_errors.append(f"Corpus template not found at {template_path!r}")

    # Load workflow spec
    spec_path = pointer.get("workflow_spec_path", "")
    spec: Optional[ParsedWorkflowSpec] = None
    if spec_path and os.path.isfile(spec_path):
        try:
            spec = parse_workflow_spec_file(spec_path)
        except Exception as e:
            bundle.load_errors.append(f"Failed to parse workflow spec {spec_path!r}: {e}")
    else:
        bundle.load_errors.append(f"Workflow spec not found at {spec_path!r}")

    # Workflow-level locks
    workflow_locks: dict = {}
    if template:
        # For section-targeted events, narrow to the affected section
        event_section = event.get("section_id", "")
        if event_section:
            for s in template.sections:
                if s.section_id == event_section:
                    workflow_locks["section"] = {
                        "id": s.section_id,
                        "name": s.name,
                        "source_pff": s.source_pff,
                        "missing_data_behavior": s.missing_data_behavior,
                        "oversight": (
                            {
                                "schema": s.oversight.schema,
                                "cadence": s.oversight.cadence,
                                "cross_section_rules": list(s.oversight.cross_section_rules),
                                "triggers_active": list(s.oversight.triggers_active),
                            }
                            if s.oversight
                            else None
                        ),
                    }
                    break
        # Always include the full template's section ids for cross-reference
        workflow_locks["all_sections"] = [
            {"id": s.section_id, "name": s.name, "source_pff": s.source_pff}
            for s in template.sections
        ]

    if spec and spec.oversight:
        workflow_locks["topology"] = {
            "chain_propagation_rules": [
                {"source": r.source, "dependent": r.dependent, "action": r.action, "condition": r.condition}
                for r in spec.oversight.chain_propagation_rules
            ],
            "off_dependency_rules": [
                {"off_id": r.off_id, "sections_required": list(r.sections_required), "stale_threshold_days": r.stale_threshold_days}
                for r in spec.oversight.off_dependency_rules
            ],
            "cadence_coordination": [
                {"sequence": list(r.sequence), "reason": r.reason}
                for r in spec.oversight.cadence_coordination
            ],
            "escalation_overrides": dict(spec.oversight.escalation_overrides),
        }

    bundle.workflow_level_locks = workflow_locks

    # Also load project-level locks for the same project (workflow events bring both layers)
    project_nexus = pointer.get("project_nexus", "")
    if project_nexus:
        proxy_event = dict(event)
        proxy_event["project_nexus"] = project_nexus
        _load_project_level_context(proxy_event, bundle)
        # Don't propagate proxy event's load_errors as the only error — workflow context is what we needed
        # but if PED couldn't load, that's a real issue worth surfacing
        # (load_errors already accumulates — leave as-is)

    # Output contract for workflow events
    bundle.output_contract = _workflow_output_contract(event, template, spec)

    # Deliverable: corpus instance content or OFF artifact
    bundle.deliverable = _workflow_deliverable(event)

    # Claim: from event payload
    bundle.claim = _workflow_claim(event)


def _workflow_output_contract(
    event: dict,
    template: Optional[ParsedCorpus],
    spec: Optional[ParsedWorkflowSpec],
) -> str:
    et = event.get("event_type", "")
    section_id = event.get("section_id", "")
    if section_id and template:
        for s in template.sections:
            if s.section_id == section_id:
                if s.oversight:
                    return (
                        f"Section {s.section_id!r} schema: {s.oversight.schema}\n"
                        f"Cadence: {s.oversight.cadence}\n"
                        f"Cross-section rules: {', '.join(s.oversight.cross_section_rules)}"
                    )
                return f"Section {s.section_id!r}: {s.name} (source={s.source_pff})"
    if et == "OFFRendered":
        off_id = event.get("off_framework_id", "")
        if spec:
            for o in spec.offs:
                if o.name == off_id:
                    return f"OFF {o.name!r} reads sections: {o.reads_from_sections}"
    return ""


def _workflow_deliverable(event: dict) -> str:
    path = event.get("corpus_instance_path") or event.get("artifact_path")
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            pass
    return event.get("write_summary", "") or ""


def _workflow_claim(event: dict) -> str:
    et = event.get("event_type", "")
    if et == "CorpusSectionPopulated":
        return f"PFF {event.get('writer_framework_id', 'unknown')} wrote section {event.get('section_id', '')}"
    if et == "CorpusValidated":
        return f"C-Validate result: {event.get('validation_result', '')}"
    if et == "OFFRendered":
        return f"OFF rendered artifact at {event.get('artifact_path', '')}"
    if et == "ChainPropagationRequired":
        return f"Source {event.get('source_corpus_path', '')} updated; dependents: {event.get('dependent_corpora', [])}"
    if et == "CorpusTemplateVersionChanged":
        return f"Template version: {event.get('old_version', '')} → {event.get('new_version', '')}"
    if et == "WorkflowSpecDrift":
        return f"Workflow spec drift detected; severe={event.get('severe', False)}"
    return ""
