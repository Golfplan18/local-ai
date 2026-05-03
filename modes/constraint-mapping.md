---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
---

# MODE: Constraint Mapping

```yaml
# 0. IDENTITY
mode_id: constraint-mapping
canonical_name: Constraint Mapping
suffix_rule: analysis
educational_name: constraint and option mapping (light decision analysis)

# 1. TERRITORY AND POSITION
territory: T3-decision-making-under-uncertainty
gradation_position:
  axis: depth
  value: light
adjacent_modes_in_territory:
  - mode_id: decision-under-uncertainty
    relationship: depth-thorough sibling (probability and time-weighted)
  - mode_id: multi-criteria-decision
    relationship: complexity sibling (multi-criteria)
  - mode_id: decision-architecture
    relationship: depth-molecular sibling
  - mode_id: real-options-decision
    relationship: specificity counterpart (staged investment) — gap-deferred
  - mode_id: ethical-tradeoff
    relationship: stance counterpart (normative + values-laden) — gap-deferred

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "multiple viable options exist"
    - "which should I choose"
    - "tradeoff analysis"
    - "compare alternatives"
  prompt_shape_signals:
    - "compare alternatives"
    - "map the tradeoffs"
    - "what are the pros and cons of each option"
disambiguation_routing:
  routes_to_this_mode_when:
    - "deterministic tradeoffs in a known environment; no probability arithmetic needed"
    - "the user wants the choice terrain mapped, not the choice made"
  routes_away_when:
    - "probabilities and time-value are central" → decision-under-uncertainty
    - "decision involves multiple weighted criteria" → multi-criteria-decision
    - "decision is a molecular orchestration with stakeholders + risk + future" → decision-architecture
    - "user wants to evaluate ONE proposal's merits and risks" → benefits-analysis (T15)
    - "user is questioning the framework within which alternatives exist" → paradigm-suspension (T9)
when_not_to_invoke:
  - "User has already chosen and wants execution" → Project Mode
  - "Decision is fundamentally about who benefits from each alternative" → Cui Bono (T2)
  - "User is searching for the right answer rather than choosing among alternatives" → other T-investigative mode

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [decision_context, candidate_alternatives_named, hard_constraints]
    optional: [soft_constraints, prior_decision_history]
    notes: "Applies when user explicitly names the alternatives and the constraint structure."
  accessible_mode:
    required: [decision_or_choice_situation]
    optional: [hint_at_some_alternatives]
    notes: "Default. Mode elicits at least 3 alternatives during execution, including any the user has not named."
  detection:
    expert_signals: ["alternatives are A, B, C", "hard constraint is", "must satisfy", "the constraints are"]
    accessible_signals: ["which should I choose", "compare these options", "what are the tradeoffs"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the choice you're facing, and what are the alternatives you're considering?'"
    on_underspecified: "Ask: 'Are probabilities and time-value central to this choice (route to Decision Under Uncertainty), or are the tradeoffs deterministic?'"
output_contract:
  artifact_type: ranked_options
  required_sections:
    - decision_context_and_constraints
    - alternatives_at_least_three
    - per_alternative_analysis_success_failure_gain_forfeit
    - cross_alternative_comparison
    - no_lose_elements
  format: matrix

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are at least three alternatives mapped, including any the user has not named?"
    failure_mode_if_unmet: false-dichotomy
  - cq_id: CQ2
    question: "Are success and failure conditions stated as testable propositions for each alternative, with identical analytical depth across alternatives?"
    failure_mode_if_unmet: advocacy-asymmetry
  - cq_id: CQ3
    question: "Have no-lose elements (actions valuable regardless of which alternative is chosen) been surfaced explicitly?"
    failure_mode_if_unmet: missed-no-lose
  - cq_id: CQ4
    question: "Does the mode map the choice terrain without making the choice for the user, unless explicitly asked?"
    failure_mode_if_unmet: choice-collapse

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: false-dichotomy
    detection_signal: "Only two alternatives mapped when ≥3 are viable, OR a binary framing masks the option space."
    correction_protocol: re-dispatch (generate ≥3 alternatives or switch to pro/con form for genuinely binary choices)
  - name: advocacy-asymmetry
    detection_signal: "One alternative receives substantially deeper analysis than others."
    correction_protocol: re-dispatch (equalise analytical depth across alternatives)
  - name: abstraction-trap
    detection_signal: "Success or failure conditions stated as vague abstractions, not testable propositions with thresholds or observables."
    correction_protocol: re-dispatch (rewrite as testable conditions)
  - name: choice-collapse
    detection_signal: "Mode delivers a single recommended alternative when the user asked for the terrain mapped."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - rumelt-strategy-kernel (when alternatives are strategic options)
    - strategic-2x2-matrix-tradition
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~1min
escalation_signals:
  upward:
    target_mode_id: decision-under-uncertainty
    when: "Probability arithmetic or time-value analysis is required for the choice."
  sideways:
    target_mode_id: multi-criteria-decision
    when: "Decision involves multiple weighted criteria across alternatives."
  downward:
    target_mode_id: null
    when: "Constraint Mapping is already the lightest depth in T3."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Constraint Mapping is the testability of success and failure conditions per alternative. A thin pass enumerates pros and cons in vague terms; a substantive pass states each success condition as a testable proposition with a threshold or observable, and traces the cost of each forfeit concretely. Test depth by asking: could each alternative's success be falsified by a specific observation? Each alternative carries the same four sub-sections (success conditions / failure conditions / uniquely gained / forfeited), with identical analytical depth.

## BREADTH ANALYSIS GUIDANCE

Breadth in Constraint Mapping is the catalog of alternatives, including any the user has not named. Widen the lens to identify ≥3 alternatives (or 2 in genuinely binary cases), generate hybrid or sequencing strategies, and surface no-lose elements (actions valuable regardless of choice). Breadth markers: alternatives include at least one the user did not initially name; at least one no-lose element is identified; hybrid or sequencing options are considered.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Constraint Mapping output: maps ≥3 alternatives (or 2 in pro/con form); states success and failure conditions as testable propositions per alternative; treats every alternative with equal analytical depth; surfaces no-lose elements explicitly; resists collapsing into a single recommendation unless asked. Specifically check for false dichotomy (only two alternatives), advocacy asymmetry (asymmetric depth), and abstraction trap (vague conditions).

## REVISION GUIDANCE

Revise to add alternatives until ≥3 (or switch to pro/con form for genuinely binary choices). Revise to equalise analytical depth across alternatives. Revise to convert vague conditions into testable propositions. Resist revising toward a final choice if the user asked for the terrain mapped — the mode's contract is mapping, not deciding. Resist revising toward consensus framing — the mode honours genuine tradeoffs.

## CONSOLIDATION GUIDANCE

Consolidate as a structured matrix with the five required sections. Format: matrix (strategic 2×2 when alternatives can be plotted on two orthogonal criteria; pro/con tree when the choice is genuinely binary). Each alternative becomes an item in the matrix or a structured pro/con block. Per-alternative analysis carries success conditions, failure conditions, uniquely gained, and forfeited — symmetric across alternatives. The cross-alternative comparison surfaces critical differentiating factors. No-lose elements appear as a separate section.

## VERIFICATION CRITERIA

Verified means: ≥3 alternatives mapped (or 2 in pro/con form for genuinely binary choices); success and failure conditions stated as testable propositions per alternative; analytical depth symmetric across alternatives; no-lose elements explicitly called out; the mode does not make the final choice unless the user explicitly asked. The four critical questions are addressed in the output.
