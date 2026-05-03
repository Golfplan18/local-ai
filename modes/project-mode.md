---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
meta_mode: true
---

# MODE: Project Mode

```yaml
# 0. IDENTITY
mode_id: project-mode
canonical_name: Project Mode
suffix_rule: none
educational_name: project execution mode

# 1. TERRITORY AND POSITION
territory: T21-execution-project-mode
gradation_position:
  axis: specificity
  value: project-execution
adjacent_modes_in_territory:
  - mode_id: structured-output
    relationship: specificity variant (rendering-only execution; PM thinks, SO renders)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "user names a specific output to produce"
    - "user has stated requirements, success criteria, or scope"
    - "user wants a deliverable, not exploration or analysis"
  prompt_shape_signals:
    - "build"
    - "write"
    - "create"
    - "produce"
    - "draft"
    - "design"
    - "make"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user names a deliverable or specifies an output"
    - "AGO output identifies a defined artefact as the deliverable"
  routes_away_when:
    - "no deliverable stated; framing is exploration" → passion-exploration (T20) or terrain-mapping (T14)
    - "request matches an analytical mode (DUU, RCA, SD, etc.)" → that analytical mode
    - "task is rendering existing content into a format" → structured-output (T21)
    - "requirements involve questioning a foundational assumption" → paradigm-suspension (T9) first, then Project Mode
when_not_to_invoke:
  - "Request matches a specific analytical mode — dispatch to that mode rather than treating as Project Mode"
  - "Task is rendering existing content rather than producing original work — Structured Output is correct"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: constructive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [deliverable_specification, success_criteria, scope_constraints]
    optional: [prior_session_context, established_decisions, domain_standards_to_follow]
    notes: "Applies when user supplies precise requirements with scope and acceptance criteria."
  accessible_mode:
    required: [deliverable_described]
    optional: [context, motivation, audience]
    notes: "Default. Mode infers requirements through clarification when needed."
  detection:
    expert_signals: ["acceptance criteria", "scope", "requirements", "must include", "deliverable"]
    accessible_signals: ["build me", "write me", "can you create", "I need a"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What specifically should the deliverable be — its form, its scope, what it should accomplish?'"
    on_underspecified: "Ask: 'Is this a defined deliverable I should produce (Project Mode), or are you exploring what the deliverable should be (Passion Exploration / Terrain Mapping)?'"
output_contract:
  artifact_type: other
  required_sections:
    - deliverable
    - decisions_log
    - limitations_acknowledged
  format: prose

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have all stated requirements been satisfied in the deliverable?"
    failure_mode_if_unmet: requirement-unmet
  - cq_id: CQ2
    question: "Is the deliverable scoped to what was requested, or has it expanded beyond?"
    failure_mode_if_unmet: scope-creep
  - cq_id: CQ3
    question: "Does the request actually match an analytical mode, in which case dispatch is the correct response rather than direct Project Mode execution?"
    failure_mode_if_unmet: dispatch-missed
  - cq_id: CQ4
    question: "Have substantive decisions been logged with reasoning, and have ≥ 1 limitation or risk been acknowledged?"
    failure_mode_if_unmet: decision-and-limitation-omission
  - cq_id: CQ5
    question: "If a constraint looks like an unstated assumption limiting the solution space, has the lightweight paradigm check been applied?"
    failure_mode_if_unmet: assumption-lock

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: dispatch-missed
    detection_signal: "Project Mode is executing what should have been dispatched to a specific analytical mode."
    correction_protocol: re-dispatch (re-classify to the matching analytical mode)
  - name: scope-creep
    detection_signal: "Deliverable expands beyond user's stated requirements without explicit acknowledgement."
    correction_protocol: flag (trim to exactly what was requested; propose additional scope as separate suggestions)
  - name: gold-plating
    detection_signal: "Over-engineering beyond what the request needs."
    correction_protocol: flag (match quality to request)
  - name: assumption-lock
    detection_signal: "A constraint is accepted as fixed when it is actually an unstated assumption limiting the solution space."
    correction_protocol: flag (apply lightweight paradigm check)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - debono-ago (aims, goals, objectives)
    - debono-fip (first important priorities)
    - domain-specific frameworks per deliverable type
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Project Mode is its own depth target for execution; deeper means dispatch to an analytical mode for analysis input."
  sideways:
    target_mode_id: structured-output
    when: "Task is rendering existing content rather than producing original work."
  downward:
    target_mode_id: null
    when: "Project Mode is T21's heavier execution sibling; lighter would be Structured Output."
```

## DEPTH ANALYSIS GUIDANCE

Project Mode is execution-oriented; depth here means the rigor of requirement satisfaction and the substance of the decisions log. Going deeper means tracing each requirement to a specific element of the deliverable, recording each decision with its reasoning, and naming limitations and risks rather than glossing them. A thin pass produces the artefact and stops; a substantive pass cross-checks the artefact against requirements, surfaces decisions that were not in the requirements but had to be made, and names what the deliverable does not address. Test depth by asking: could the user audit the deliverable against the requirements line by line and find each requirement satisfied?

When Project Mode dispatches to an analytical mode (the typical case for analytically-shaped requests), the analytical mode's depth guidance governs — Project Mode's role becomes orchestration rather than direct execution.

## BREADTH ANALYSIS GUIDANCE

Breadth in Project Mode is the survey of alternative approaches considered before committing to the deliverable's form. Widen the lens to consider: alternative formats, alternative scopes, alternative tools, alternative interpretations of the request. Breadth markers: at least one alternative was considered before commitment; the lightweight paradigm check has been applied to constraints that look like unstated assumptions; adjacent opportunities (scope additions the user might want) are surfaced as suggestions, not silently included.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ5. The named failure modes are the evaluation checklist. The dispatch check fires first — if the request matches an analytical mode, that is the correct response rather than Project Mode execution. If Project Mode is terminal (pure document production), evaluate by: (a) requirement satisfaction; (b) scope discipline; (c) decisions log substance; (d) limitations named; (e) lightweight paradigm check applied where constraints look unnecessary. Silent scope expansion without acknowledgement is a verification failure.

## REVISION GUIDANCE

Revise to address requirements that are unaddressed (or explicitly acknowledge the gap in a Gap report). Revise to trim scope where the deliverable has expanded beyond requirements. Revise to add the decisions log substance where it is trivial. Revise to add limitations where they are missing. Resist revising toward gold-plating — match quality to request. If revision reveals the request was actually analytical, re-dispatch rather than completing in Project Mode.

## CONSOLIDATION GUIDANCE

Consolidate as the deliverable plus the three universal elements: deliverable, decisions log, limitations acknowledged. The deliverable's structure follows the user's request (a memo for a memo request, code for a code request, an outline for an outline request). The decisions log records substantive decisions with reasoning. Limitations are named with the literal prefix "Limitation N:" or "Risk N:". Format follows the deliverable type. When dispatched to an analytical mode, that mode's consolidation governs.

## VERIFICATION CRITERIA

Verified means: deliverable matches request; ≥ 1 substantive decision logged with reasoning; ≥ 1 limitation or risk acknowledged; scope discipline preserved (no silent expansion). The five critical questions are addressed. If the request actually matched an analytical mode, dispatching there is the verified-correct response — completing in Project Mode is a failure regardless of deliverable quality. The dispatch-check guard rail fires before emission: does this request match an analytical mode? If yes, dispatch.
