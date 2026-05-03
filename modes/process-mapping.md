---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Process Mapping

```yaml
# 0. IDENTITY
mode_id: process-mapping
canonical_name: Process Mapping
suffix_rule: analysis
educational_name: process mapping (workflow / dependency / bottleneck identification)

# 1. TERRITORY AND POSITION
territory: T17-process-and-system-analysis
gradation_position:
  axis: specificity
  value: process-flow
  secondary_axis: complexity
  secondary_value: single-process
adjacent_modes_in_territory:
  - mode_id: systems-dynamics-structural
    relationship: complexity-counterpart (feedback structure rather than linear-process flow)
  - mode_id: organizational-structure
    relationship: specificity-counterpart (organizational rather than process-flow; gap-deferred)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I need to map out how this process actually works step by step"
    - "I want to find the bottlenecks in this workflow"
    - "I need to see the dependencies between steps"
    - "I want to document the current state before changing anything"
    - "I need to identify where things slow down or break"
  prompt_shape_signals:
    - "process map"
    - "workflow"
    - "swim lane"
    - "value stream"
    - "bottleneck"
    - "dependency"
    - "flow chart"
    - "current state"
    - "as-is process"
    - "step by step how does this work"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants step-by-step documentation of how a current process works"
    - "user wants explicit identification of bottlenecks, dependencies, and decision points"
    - "user wants current-state ('as-is') mapping rather than future-state design"
    - "process is largely linear or branching but not characterized by feedback loops"
  routes_away_when:
    - "system has feedback loops where outputs influence inputs cyclically" → systems-dynamics-structural
    - "question is why a particular outcome happened" → T4 causal modes
    - "question is how the parts produce the whole's behavior at the principle level" → mechanism-understanding (T16)
    - "question is about who has what role and authority" → organizational-structure (gap-deferred)
when_not_to_invoke:
  - "User wants to design a future state rather than document the current state" → execution-tier (T21) or future-mode (T6)
  - "User wants to evaluate the process as a proposal" → T15 stance modes
  - "User wants causal-chain analysis of an outcome" → T4 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [process_name_or_scope, process_boundaries, known_actors_or_roles]
    optional: [existing_documentation, known_pain_points, prior_process_maps]
    notes: "Applies when user supplies a scoped process with explicit start-and-end conditions and named actors."
  accessible_mode:
    required: [process_description]
    optional: [why_user_wants_map, recent_problems_with_process]
    notes: "Default. Mode elicits boundaries, actors, and pain points during execution."
  detection:
    expert_signals: ["swim lane", "value stream", "as-is process", "RACI", "process boundaries"]
    accessible_signals: ["how does this work", "step by step", "where does it slow down", "map out the workflow"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What process are you mapping, where does it start, and where does it end?'"
    on_underspecified: "Ask: 'What triggers the process to begin, and how do you know when it's complete?'"
output_contract:
  artifact_type: mapping
  required_sections:
    - process_scope_and_boundaries
    - actor_or_role_inventory
    - sequential_step_breakdown
    - decision_points_and_branches
    - dependency_map
    - bottleneck_identification
    - handoff_and_friction_points
    - confidence_per_finding
  format: diagram-friendly

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have the process boundaries been locked (clear start trigger and end condition), or is the scope ambiguous?"
    failure_mode_if_unmet: scope-creep
  - cq_id: CQ2
    question: "Has the analysis distinguished between the documented (official) process and the actual (lived) process, or has it described only one as if it were both?"
    failure_mode_if_unmet: official-vs-actual-elision
  - cq_id: CQ3
    question: "Have decision points and branching paths been identified with explicit decision criteria, or has the process been flattened into a single happy path?"
    failure_mode_if_unmet: happy-path-flattening
  - cq_id: CQ4
    question: "Have bottlenecks been identified with the constraint that creates them named, rather than just the symptom?"
    failure_mode_if_unmet: bottleneck-symptom-only
  - cq_id: CQ5
    question: "Have handoffs between actors been examined for friction and information loss, or treated as frictionless?"
    failure_mode_if_unmet: handoff-blindness

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: scope-creep
    detection_signal: "Process boundaries shifted during execution; map covers more than the locked scope."
    correction_protocol: re-dispatch
  - name: official-vs-actual-elision
    detection_signal: "Map describes the process as documented in policy without acknowledging known deviations or workarounds."
    correction_protocol: flag
  - name: happy-path-flattening
    detection_signal: "All branching paths collapsed to one main flow; exception paths absent."
    correction_protocol: re-dispatch
  - name: bottleneck-symptom-only
    detection_signal: "Bottleneck named (e.g., 'approval takes too long') without the underlying constraint identified (e.g., 'single approver, no delegation')."
    correction_protocol: flag
  - name: handoff-blindness
    detection_signal: "Handoffs between actors presented without examining where information is lost, transformed, or queued."
    correction_protocol: flag
  - name: causal-overreach
    detection_signal: "Process map presented as causal explanation of why outcomes occur; mode boundary violation into T4."
    correction_protocol: escalate

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - meadows-twelve-leverage-points (when bottleneck-as-leverage-point analysis is central)
    - senge-system-archetypes (when process exhibits archetype-pattern signatures)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: systems-dynamics-structural
    when: "Process exhibits feedback loops where outputs cyclically influence inputs; linear-flow mapping insufficient."
  sideways:
    target_mode_id: null
    when: "Sibling specificity-organizational mode (organizational-structure) gap-deferred per CR-6."
  downward:
    target_mode_id: null
    when: "Process Mapping is the lightest specificity-process-flow mode in T17 at current population."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Process Mapping is the explicitness of (a) actor-and-role attribution per step (who does what), (b) decision-point criteria (what triggers each branch), (c) dependency relationships between steps (what blocks what), and (d) bottleneck constraint-identification (not just where it slows but why it slows). A thin pass lists the steps; a substantive pass attributes each step to an actor, identifies decision-point criteria explicitly, maps step-to-step dependencies, and names the underlying constraint at each bottleneck (capacity / authority / information / sequencing). Test depth by asking: could a new actor entering the process at any step understand from the map alone what they need, who they wait for, and what unblocks them?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for exception paths and edge cases (what happens when the input is malformed, when an actor is absent, when a dependency is unavailable), surfacing the gap between documented and actual process flow, and identifying handoff friction (information loss, role-confusion, queue accumulation) at every actor boundary. Breadth markers: the map shows at least one exception path explicitly, surfaces at least one official-vs-actual deviation, and flags handoffs as friction zones rather than treating them as transparent.

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) boundary lock; (CQ2) official-vs-actual distinction; (CQ3) decision-point and branch surfacing; (CQ4) bottleneck constraint-identification; (CQ5) handoff examination. The named failure modes (scope-creep, official-vs-actual-elision, happy-path-flattening, bottleneck-symptom-only, handoff-blindness, causal-overreach) are the evaluation checklist. A passing Process Mapping output locks scope, distinguishes documented from actual flow, surfaces decision points and branches with criteria, identifies bottlenecks with underlying constraints named, and examines handoffs for friction.

## REVISION GUIDANCE

Revise to add exception paths where the draft shows only the happy path. Revise to surface official-vs-actual deviations where the draft conflates them. Revise to identify the constraint underlying each bottleneck where the draft names only the symptom. Revise to examine handoffs as friction zones where the draft treats them as transparent. Resist revising toward causal explanation of outcomes — the mode's analytical character is descriptive process documentation. If the user wants causal analysis of why the process produces particular outcomes, escalate to T4 causal modes rather than overreaching the mapping.

## CONSOLIDATION GUIDANCE

Consolidate as a diagram-friendly mapping with the eight required sections. The sequential step breakdown is suitable for swim-lane or flow-chart rendering, with actor attribution per step. Decision points are presented with explicit criteria and branch-paths. The dependency map identifies what blocks what (suitable for a directed acyclic dependency graph). Bottlenecks are named with underlying constraints in a structured table. Handoff and friction points are listed separately. Confidence per finding accompanies each major claim.

## VERIFICATION CRITERIA

Verified means: process boundaries are locked with explicit start trigger and end condition; actors are inventoried with role attribution per step; decision points are surfaced with criteria; dependencies are mapped; bottlenecks are identified with underlying constraints (not just symptoms); handoffs are examined for friction; official-vs-actual distinction is acknowledged. The five critical questions are addressable from the output. Confidence per finding accompanies every claim.
