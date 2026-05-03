---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Mechanism Understanding

```yaml
# 0. IDENTITY
mode_id: mechanism-understanding
canonical_name: Mechanism Understanding
suffix_rule: analysis
educational_name: mechanism understanding (how parts produce the whole's behavior)

# 1. TERRITORY AND POSITION
territory: T16-mechanism-understanding
gradation_position:
  axis: depth
  value: thorough
adjacent_modes_in_territory: []

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want to understand how this actually works under the hood"
    - "I need to know how the parts produce the behavior I'm seeing"
    - "I want a principled explanation of the mechanism, not just a description"
    - "I need to understand the gears, not just the inputs and outputs"
  prompt_shape_signals:
    - "how does this work"
    - "mechanism"
    - "under the hood"
    - "how do the parts produce"
    - "what's the principle"
    - "explain the gears"
    - "internal workings"
    - "structural explanation"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants explanation of how parts of a phenomenon produce the whole's behavior at the principle level"
    - "user wants the gears, not the timeline (process flow) or the cause (causal chain)"
    - "user wants structural explanation rather than narrative description"
  routes_away_when:
    - "user wants to know why a particular outcome occurred (backward to causes)" → T4 causal modes
    - "user wants step-by-step process flow over time" → process-mapping (T17)
    - "user wants to know who has what role and authority" → organizational-structure (gap-deferred, T17)
    - "user wants relationships between entities in a representation" → relationship-mapping (T11)
    - "user wants to evaluate the mechanism as a proposal" → T15 stance modes
when_not_to_invoke:
  - "User wants forward-looking projection rather than current-mechanism explanation" → T6 modes
  - "User wants to find the cause of a problem to fix" → T4 modes
  - "User wants to map a process step by step" → T17 process-mapping

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [phenomenon_or_system, behavior_to_be_explained, known_components]
    optional: [domain_briefing, prior_mechanism_descriptions, scale_or_level_of_analysis]
    notes: "Applies when user supplies a scoped phenomenon with named components and an explicit behavior-to-be-explained."
  accessible_mode:
    required: [phenomenon_description]
    optional: [what_user_already_understands, why_user_wants_mechanism]
    notes: "Default. Mode elicits components and behavior-to-be-explained during execution."
  detection:
    expert_signals: ["mechanism", "structural explanation", "components and interactions", "principle-level"]
    accessible_signals: ["how does this work", "explain the gears", "what makes this happen", "under the hood"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What phenomenon are you trying to understand, and what specifically about its behavior do you want explained?'"
    on_underspecified: "Ask: 'Are you asking how it works at the principle level (the mechanism), or how it works step-by-step over time (the process)?'"
output_contract:
  artifact_type: synthesis
  required_sections:
    - phenomenon_and_behavior_locked
    - level_of_analysis
    - component_inventory
    - component_function_per_component
    - interaction_pattern_among_components
    - emergence_account
    - boundary_conditions_and_limits
    - confidence_per_finding
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the level of analysis been locked (e.g., molecular, organizational, system-wide), or has the explanation jumped between levels without acknowledgment?"
    failure_mode_if_unmet: level-confusion
  - cq_id: CQ2
    question: "Have the components been inventoried with each component's function stated, rather than merely named?"
    failure_mode_if_unmet: component-inventory-without-function
  - cq_id: CQ3
    question: "Has the interaction pattern among components been described as the source of the whole's behavior, rather than treating the whole's behavior as a separate fact alongside the components?"
    failure_mode_if_unmet: emergence-elision
  - cq_id: CQ4
    question: "Are the boundary conditions of the mechanism named — under what circumstances it applies, when it breaks down, what it does not explain?"
    failure_mode_if_unmet: scope-overreach
  - cq_id: CQ5
    question: "Has the explanation been distinguished from a process map (temporal flow) and a causal chain (backward-to-causes), or have these been conflated?"
    failure_mode_if_unmet: territory-conflation

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: level-confusion
    detection_signal: "Explanation moves between molecular, organizational, and system-wide accounts without explicit acknowledgment of level shift."
    correction_protocol: re-dispatch
  - name: component-inventory-without-function
    detection_signal: "Components named but their functional role in producing the whole's behavior not stated."
    correction_protocol: re-dispatch
  - name: emergence-elision
    detection_signal: "Whole's behavior described separately from components without an explicit account of how the interaction pattern produces it."
    correction_protocol: re-dispatch
  - name: scope-overreach
    detection_signal: "Mechanism explanation extended to phenomena outside the boundary conditions; over-generalization."
    correction_protocol: flag
  - name: territory-conflation
    detection_signal: "Output blends process-flow narration (T17) or causal-chain investigation (T4) with mechanism explanation; not parsed."
    correction_protocol: re-dispatch
  - name: just-so-explanation
    detection_signal: "Explanation appears to fit the observed behavior but makes no predictions about behavior under altered conditions."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - meadows-twelve-leverage-points (when leverage-points framework illuminates which components do most of the work)
    - senge-system-archetypes (when archetype-pattern signatures help identify mechanism class)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Mechanism Understanding is the territory founder mode in T16; expansion deferred per Wave 3 plan."
  sideways:
    target_mode_id: null
    when: "T16 has no current sibling modes; cross-territory routing handled by adjacency map."
  downward:
    target_mode_id: null
    when: "Mechanism Understanding is the only mode in T16 at current population."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Mechanism Understanding is the explicitness of (a) level-of-analysis selection, (b) per-component function attribution, and (c) the account of how interaction pattern produces the whole's behavior (the emergence account). A thin pass names components and asserts the behavior; a substantive pass locks the level of analysis, inventories components with their functional role in producing the behavior, describes the interaction pattern as the source of the behavior (rather than alongside it), and names the boundary conditions under which the mechanism applies. Test depth by asking: could the explanation predict how the whole's behavior would change if a specific component were altered, removed, or replaced — and does the answer follow from the stated mechanism rather than from intuition?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for components the analyst might omit (background conditions, supporting infrastructure, regulatory or constraining elements that do not actively contribute but enable contribution), considering alternative mechanism descriptions at different levels of analysis, and surfacing where the mechanism is incomplete or where multiple mechanisms could account for the same observed behavior. Breadth markers: the analysis names at least one background-or-enabling component that easy descriptions tend to omit, and acknowledges at least one alternative-mechanism candidate the available evidence cannot rule out.

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) level lock; (CQ2) function attribution; (CQ3) emergence account; (CQ4) boundary conditions; (CQ5) territory distinction from T4 and T17. The named failure modes (level-confusion, component-inventory-without-function, emergence-elision, scope-overreach, territory-conflation, just-so-explanation) are the evaluation checklist. A passing Mechanism Understanding output locks the level of analysis, attributes function per component, accounts for emergence as interaction-pattern-producing-behavior, names boundary conditions, and stays within T16's mechanism-territory rather than drifting into T4 causation or T17 process-flow.

## REVISION GUIDANCE

Revise to lock the level of analysis where the draft drifts. Revise to add functional role per component where components are merely named. Revise to make the emergence account explicit — the interaction pattern producing the behavior — where the draft asserts the behavior and the components separately. Revise to add boundary conditions where the explanation appears unbounded. Resist revising toward narrative process-flow or causal-chain explanation — these are different territories. If the user wants temporal flow, escalate to T17 process-mapping; if they want causes of an outcome, escalate to T4 causal modes.

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the eight required sections. The level of analysis is stated as a single locked claim. Components are inventoried in a structured table with function per component. The interaction pattern appears as an explicit description of how components together produce the behavior (suitable for diagram if helpful). The emergence account distinguishes the mechanism from a list of components. Boundary conditions name what the mechanism explains and what it does not. Confidence per finding accompanies each major claim.

## VERIFICATION CRITERIA

Verified means: the level of analysis is locked; components are inventoried with functional role per component; the interaction pattern is described as the source of the whole's behavior; emergence is accounted for rather than elided; boundary conditions are named; the explanation makes at least one prediction about behavior under altered conditions. The five critical questions are addressable from the output. Confidence per finding accompanies every claim. The output is distinguishable from a T4 causal-chain analysis or a T17 process-map.
