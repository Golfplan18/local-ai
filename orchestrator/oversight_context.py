"""Oversight context loader — assembles inputs for Process Coherence.

Given an event, loads the appropriate locked definitions, output contract,
deliverable, claim, decision log, and PEF toolkit reference, returning a
ContextBundle that Process Coherence consumes per Reference — Meta-Layer
Architecture §8.

The loader handles both project-level events (E1–E6: locks come from the
matrix file — type-aware lock loading per Process Coherence v3.0) and
workflow-level events (E7–E12: locks come from corpus template + workflow
spec).

Matrix-type-aware lock loading (Process Coherence v3.0, 2026-05-08):
For matrix-level events, the lock set is dispatched on the matrix
frontmatter's ``project_type`` field. Four classifications are supported:
project / operation / passion / incubator. Each loads a different field
set; see ``_load_project_locks``, ``_load_operation_locks``,
``_load_passion_locks``, ``_load_incubator_locks``.

Author: meta-layer implementation per Reference — Meta-Layer Architecture §8.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from ped_parser import parse_ped_file, ParsedPED
    from corpus_parser import parse_corpus_file, ParsedCorpus
    from workflow_spec_parser import parse_workflow_spec_file, ParsedWorkflowSpec
    from ped_watcher import load_ped_path
    from corpus_watcher import load_workflow_pointer
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator.ped_parser import parse_ped_file, ParsedPED
    from orchestrator.corpus_parser import parse_corpus_file, ParsedCorpus
    from orchestrator.workflow_spec_parser import (
        parse_workflow_spec_file, ParsedWorkflowSpec,
    )
    from orchestrator.ped_watcher import load_ped_path
    from orchestrator.corpus_watcher import load_workflow_pointer

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp


WORKSPACE = _rp.WORKSPACE
VAULT = _rp.VAULT_STR
PEF_PATH = str(_rp.VAULT / "Framework — Problem Evolution.md")


def pef_path() -> str:
    """Current PEF path, honoring canonical and legacy vault overrides."""
    return str(_rp.vault_dir() / "Framework — Problem Evolution.md")

logger = logging.getLogger(__name__)


# Matrix-type-aware lock loading constants.
VALID_CLASSIFICATIONS = {"project", "operation", "passion", "incubator"}

# The four cycle-shape near-miss patterns from Framework — Operations Manifest.
# An Operation matrix's Excluded Outcomes should include operation-specific
# instantiations of these. Process Coherence Layer 2 checks the cycle deliverable
# against each pattern as part of cycle-close verification.
CYCLE_SHAPE_NEAR_MISS_PATTERNS = [
    "Cadence met but quality degraded",
    "Coordinated corpora consumed but unchanged",
    "Rendered output produced but not consumed",
    "Maturity gate gamed not earned",
]


class InvalidProjectTypeError(ValueError):
    """Raised when project_type frontmatter contains values that cannot be
    resolved to one of the four valid classifications.

    Per the Phase 1 implementation directive: don't fall back silently when
    the matrix declares an unrecognized classification. Surface the matrix
    path and the offending value so the user can correct the matrix.
    """
    def __init__(self, matrix_path: str, offending_value, message: str = ""):
        self.matrix_path = matrix_path
        self.offending_value = offending_value
        if not message:
            message = (
                f"project_type {offending_value!r} in matrix {matrix_path!r} "
                f"cannot be resolved to one of the four valid classifications "
                f"{sorted(VALID_CLASSIFICATIONS)}. "
                f"Update the matrix's frontmatter or extend VALID_CLASSIFICATIONS."
            )
        super().__init__(message)


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
    pef_toolkit_reference: str = field(default_factory=pef_path)
    load_errors: list = field(default_factory=list)
    matrix_classification: str = ""  # "project" / "operation" / "passion" / "incubator"
    classification_warnings: list = field(default_factory=list)

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


# ---------- Matrix classification ----------

def classify_matrix(ped: ParsedPED) -> tuple[str, list[str]]:
    """Resolve the matrix's classification from its frontmatter.

    Returns ``(classification, warnings)``. ``classification`` is one of
    {"project", "operation", "passion", "incubator"}. ``warnings`` is a
    list of human-readable notes about how the classification was reached
    (empty when the matrix declares exactly one valid classification).

    Process Coherence v3.0 Layer 1 step 2 mandates this dispatch:
      - project / incubator → endpoint-bearing locks (Resolution Statement
        or Critical Unknown, Excluded Outcomes, Constraints).
      - operation → cycle-shape locks (Service Statement, Excluded Outcomes
        with cycle-shape near-miss patterns, Cadence rule, Constraints).
      - passion → orientation-only locks (Mission Core Essence and
        Emotional Drivers, Constraints).

    The matrix's ``project_type`` field can be a string (single value),
    a list (the Project Type Registry's multi-valued convention), or
    absent. Resolution rules:

      - Absent → default to "project" (with warning).
      - Single classification token → use it.
      - Multiple classification tokens → raise ``InvalidProjectTypeError``
        (the four classifications are mutually exclusive).
      - Content-only tokens (e.g. ``[book, knowledge]`` per the Project
        Type Registry, with no classification token) → default to
        "project" (with warning).
      - Any other type (not str/list/None) → raise
        ``InvalidProjectTypeError``.

    Spec ambiguity flagged for user resolution: the strict reading of the
    Phase 1 directive ("raise an explicit error" on any value not in the
    four-classification set) conflicts with the Project Type Registry
    convention that ``project_type`` is multi-valued and may contain only
    content tokens. The implementation here treats content-only as a
    default-with-warning rather than an error to preserve compatibility
    with existing matrices; the strict-error path is reserved for
    structurally-invalid frontmatter (multiple classifications, or a
    non-str/list value).
    """
    warnings: list[str] = []
    raw = ped.frontmatter.get("project_type") if ped.frontmatter else None

    if raw is None:
        warnings.append(
            "project_type absent from matrix frontmatter; defaulting to "
            "'project' classification (current behavior, made explicit)."
        )
        return ("project", warnings)

    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = [str(v) for v in raw]
    else:
        raise InvalidProjectTypeError(
            ped.file_path,
            raw,
            f"project_type {raw!r} in matrix {ped.file_path!r} has unsupported "
            f"type {type(raw).__name__}; must be a string or a list of strings.",
        )

    classifications = [v for v in values if v in VALID_CLASSIFICATIONS]

    if len(classifications) == 1:
        return (classifications[0], warnings)

    if len(classifications) > 1:
        raise InvalidProjectTypeError(
            ped.file_path,
            classifications,
            f"project_type in matrix {ped.file_path!r} declares multiple "
            f"classifications {classifications}; the four classifications "
            f"(project / operation / passion / incubator) are mutually exclusive. "
            f"Pick one and move the others to a different field.",
        )

    # No classification tokens, only content tokens (or empty list).
    warnings.append(
        f"project_type {values!r} in matrix {ped.file_path!r} contains no "
        f"classification token from {sorted(VALID_CLASSIFICATIONS)}; "
        f"defaulting to 'project' classification. If this matrix is an "
        f"Operation, Passion, or Incubator, add the classification token "
        f"explicitly to project_type."
    )
    return ("project", warnings)


# ---------- Type-specific lock loaders ----------

def _serialize_constraints(ped: ParsedPED, classifications: tuple[str, ...]) -> list[dict]:
    """Return constraints whose classification is in the requested set."""
    return [
        {
            "classification": c.classification,
            "statement": c.statement,
            "rationale": c.rationale,
            "revisit_trigger": c.revisit_trigger,
        }
        for c in ped.constraints
        if c.classification in classifications
    ]


def _load_project_locks(ped: ParsedPED) -> dict:
    """Locks for project / incubator-style projects (endpoint-bearing).

    Note: incubators technically use Critical Unknown for the endpoint,
    but per MOM the Incubator's Resolution Statement is "The Critical
    Unknown — [Q] — has been answered in the form of [observable form
    of the answer]." So Resolution Statement is still the canonical
    endpoint field. _load_incubator_locks adds Critical Unknown
    explicitly alongside.
    """
    return {
        "matrix_classification": "project",
        "mission_resolution_statement": ped.mission_resolution_statement,
        "excluded_outcomes": list(ped.excluded_outcomes),
        "constraints": _serialize_constraints(
            ped, ("Hard", "Soft", "Working Assumption"),
        ),
    }


def _load_operation_locks(ped: ParsedPED) -> dict:
    """Locks for operation matrices (cycle-shape).

    Service Statement + Excluded Outcomes (with the cycle-shape near-miss
    pattern set surfaced as a separate field for Process Coherence Layer 2's
    cycle-close verification) + Cadence rule + Constraints.
    """
    return {
        "matrix_classification": "operation",
        "mission_service_statement": ped.mission_service_statement,
        "mission_core_essence": ped.mission_core_essence,
        "mission_emotional_drivers": list(ped.mission_emotional_drivers),
        "excluded_outcomes": list(ped.excluded_outcomes),
        "cycle_shape_near_miss_patterns": list(CYCLE_SHAPE_NEAR_MISS_PATTERNS),
        "cadence_rule": ped.cadence_rule,
        "constraints": _serialize_constraints(
            ped, ("Hard", "Soft", "Working Assumption"),
        ),
    }


def _load_passion_locks(ped: ParsedPED) -> dict:
    """Locks for passion matrices (orientation-only).

    Mission Core Essence + Emotional Drivers (Lock-protected per the
    Universal Problem-Definition Lock as extended by MOM v3.0 for Passions).
    Soft Constraints + Working Assumptions only — Passions don't typically
    have Hard endpoint constraints because they don't have an endpoint.

    Per Process Coherence v3.0 Layer 2: "Passions don't typically generate
    completion claims; matrix-level events for Passions are usually iterate-
    related (drift signals on practices, directions of travel) rather than
    terminal. If a terminal claim does fire on a Passion, it indicates
    classification drift — flag and recommend reclassification."

    The classification-drift detection happens in Process Coherence Layer 2
    (the model evaluating the bundle), not here at lock-load time. Lock load
    surfaces the orientation-only fields; the framework's downstream logic
    decides what a terminal claim against these locks means.
    """
    return {
        "matrix_classification": "passion",
        "mission_core_essence": ped.mission_core_essence,
        "mission_emotional_drivers": list(ped.mission_emotional_drivers),
        "constraints": _serialize_constraints(
            ped, ("Soft", "Working Assumption"),
        ),
        "passion_terminal_claim_warning": (
            "Passions have no terminal endpoint. A terminal claim on a "
            "Passion matrix indicates classification drift per Process "
            "Coherence v3.0 Layer 2 — recommend reclassification rather "
            "than evaluating against a phantom endpoint."
        ),
    }


def _load_incubator_locks(ped: ParsedPED) -> dict:
    """Locks for incubator matrices.

    Critical Unknown is the central locked field; Resolution Statement
    (when populated) carries the same Lock protection as a Project's
    Resolution Statement and is phrased "The Critical Unknown has been
    answered in the form of [observable form of the answer]" per MOM.
    """
    return {
        "matrix_classification": "incubator",
        "mission_critical_unknown": ped.mission_critical_unknown,
        "mission_resolution_statement": ped.mission_resolution_statement,
        "excluded_outcomes": list(ped.excluded_outcomes),
        "constraints": _serialize_constraints(
            ped, ("Hard", "Soft", "Working Assumption"),
        ),
    }


CLASSIFICATION_DISPATCH = {
    "project": _load_project_locks,
    "operation": _load_operation_locks,
    "passion": _load_passion_locks,
    "incubator": _load_incubator_locks,
}


def load_locks_for_matrix(ped: ParsedPED) -> tuple[dict, str, list[str]]:
    """Top-level dispatch — returns (locks_dict, classification, warnings).

    Pure function over a parsed matrix; no file I/O. Tests can call this
    directly with ``parse_ped_text``-built fixtures.
    """
    classification, warnings = classify_matrix(ped)
    loader = CLASSIFICATION_DISPATCH[classification]
    return (loader(ped), classification, warnings)


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
        bundle.load_errors.append(f"Matrix file not found at {ped_path!r}")
        return

    try:
        ped = parse_ped_file(ped_path)
    except Exception as e:
        bundle.load_errors.append(f"Failed to parse matrix at {ped_path!r}: {e}")
        return

    try:
        locks, classification, warnings = load_locks_for_matrix(ped)
    except InvalidProjectTypeError as e:
        bundle.load_errors.append(str(e))
        return

    bundle.project_level_locks = locks
    bundle.matrix_classification = classification
    bundle.classification_warnings = warnings
    for w in warnings:
        logger.warning("oversight_context: %s", w)

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
    """Derive the output contract — the 'done' specification — for a project-level event.

    The fallback (when no specific milestone matches) returns the matrix's
    type-appropriate endpoint statement. For projects, that's the Resolution
    Statement; for operations, the Service Statement; for incubators, the
    Critical Unknown; for passions, the Core Essence (passions have no
    endpoint, so this is best-effort orientation rather than a verifiable
    target — Process Coherence Layer 2 will surface classification drift if
    a terminal claim fires here).
    """
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
    # Type-appropriate fallback.
    if ped.mission_service_statement:
        return ped.mission_service_statement
    if ped.mission_critical_unknown and not ped.mission_resolution_statement:
        return ped.mission_critical_unknown
    if ped.mission_resolution_statement:
        return ped.mission_resolution_statement
    return ped.mission_core_essence


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
