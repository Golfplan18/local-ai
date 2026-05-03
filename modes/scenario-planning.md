---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
---

# MODE: Scenario Planning

```yaml
# 0. IDENTITY
mode_id: scenario-planning
canonical_name: Scenario Planning
suffix_rule: analysis
educational_name: alternative-future scenario planning (Wack/Schwartz lineage)

# 1. TERRITORY AND POSITION
territory: T6-future-exploration
gradation_position:
  axis: depth
  value: thorough
  secondary_axis: stance
  secondary_value: narrative-output
adjacent_modes_in_territory:
  - mode_id: consequences-and-sequel
    relationship: depth-lighter sibling (light forward projection)
  - mode_id: probabilistic-forecasting
    relationship: depth-thorough sibling (probability-output instead of narrative-output)
  - mode_id: pre-mortem-action
    relationship: stance-counterpart (adversarial-future-on-plan; shares klein-pre-mortem lens with T7's pre-mortem-fragility)
  - mode_id: wicked-future
    relationship: depth-molecular sibling (integrates multiple T6 modes)
  - mode_id: backcasting
    relationship: stance-counterpart (constructive-future — gap-deferred)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "a decision depends on future conditions that are genuinely uncertain"
    - "I'm doing strategic planning over a horizon longer than a year"
    - "everyone is assuming one default future and I want to challenge that"
    - "what if the environment changes"
    - "how should we prepare for different futures"
  prompt_shape_signals:
    - "scenarios"
    - "2x2 scenario matrix"
    - "scenario planning"
    - "possible futures"
    - "what-if matrix"
    - "alternative futures"
disambiguation_routing:
  routes_to_this_mode_when:
    - "multiple plausible futures to prepare for, narrative form"
    - "2x2 matrix with axes from critical uncertainties"
    - "5–20 year strategic horizon under genuine uncertainty"
  routes_away_when:
    - "one decision under uncertainty now (probability + payoff)" → decision-under-uncertainty (T3)
    - "want probability distributions instead of narrative scenarios" → probabilistic-forecasting
    - "questioning the foundational frame" → paradigm-suspension (T9)
    - "trace a failure backward" → root-cause-analysis (T4)
    - "stress-test a specific plan adversarially" → pre-mortem-action
    - "want lighter forward consequence cascade" → consequences-and-sequel
when_not_to_invoke:
  - "Horizon is short (under one year) and uncertainty is bounded" → consequences-and-sequel or constraint-mapping
  - "User wants to choose among present-state options, not prepare for futures" → T3
  - "Forces in play are feedback-structured and require systems-dynamics treatment" → systems-dynamics-causal (T4)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: generative

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [focal_question, planning_horizon, driving_force_inventory]
    optional: [predetermined_vs_uncertain_classification, prior_scenario_sets, STEEP_categorization]
    notes: "Applies when user supplies driving forces classified or partially classified, or names the Shell/Schwartz method explicitly."
  accessible_mode:
    required: [focal_question_or_strategic_concern]
    optional: [planning_horizon, contextual_background]
    notes: "Default. Mode infers driving forces, classifies them, selects axes, and constructs scenarios."
  detection:
    expert_signals: ["driving forces", "predetermined elements", "critical uncertainties", "STEEP", "Shell scenarios", "wild card"]
    accessible_signals: ["scenarios", "possible futures", "what could happen", "how should we prepare"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the strategic decision or focal question, and roughly what time horizon are you planning over?'"
    on_underspecified: "Ask: 'What's the focal question for these scenarios, and over what horizon?'"
output_contract:
  artifact_type: scenarios
  required_sections:
    - focal_question
    - driving_forces_classified
    - critical_uncertainties_as_axes
    - scenario_matrix_2x2
    - leading_indicators_per_scenario
    - strategic_implications
    - wild_card
  format: matrix

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the four scenarios structurally distinct (different causal logic), or merely magnitude variants (good/bad/medium)?"
    failure_mode_if_unmet: good-bad-medium-trap
  - cq_id: CQ2
    question: "Are the two axes genuinely independent, or do they correlate so the scenarios cluster on a diagonal?"
    failure_mode_if_unmet: correlated-axes-trap
  - cq_id: CQ3
    question: "Has any scenario been designated 'most likely' or 'official', undermining the mode's anti-prediction stance?"
    failure_mode_if_unmet: official-future-trap
  - cq_id: CQ4
    question: "Have driving forces been honestly classified as predetermined vs critical uncertainty, or has a genuine uncertainty been treated as predetermined?"
    failure_mode_if_unmet: certainty-masquerade-trap
  - cq_id: CQ5
    question: "Does each scenario translate into actionable strategic guidance (leading indicators, robust vs scenario-dependent strategies, contingent actions), or does it remain a story without strategy?"
    failure_mode_if_unmet: story-without-strategy-trap

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: good-bad-medium-trap
    detection_signal: "Scenarios labelled by magnitude (optimistic/pessimistic/baseline) rather than distinct causal logic."
    correction_protocol: re-dispatch
  - name: official-future-trap
    detection_signal: "One scenario labelled 'most likely' or designated as the planning baseline."
    correction_protocol: re-dispatch
  - name: story-without-strategy-trap
    detection_signal: "Scenario narratives lack leading indicators or actionable strategy translations."
    correction_protocol: flag
  - name: certainty-masquerade-trap
    detection_signal: "Driving force classified as predetermined that could plausibly go either way; classification not defended."
    correction_protocol: flag
  - name: correlated-axes-trap
    detection_signal: "Items cluster on a diagonal (axes covary); axes-independence rationale missing or trivial (< 40 chars)."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - shell-scenario-method
  optional:
    - tetlock-superforecasting
    - schwartz-art-of-the-long-view
    - STEEP-framework
    - klein-pre-mortem
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: wicked-future
    when: "Scenarios reveal multiple stakeholder values irreducibly conflict; futures need integrated analysis."
  sideways:
    target_mode_id: probabilistic-forecasting
    when: "User wants probability distributions over outcomes rather than narrative futures."
  downward:
    target_mode_id: consequences-and-sequel
    when: "Horizon is short or uncertainty is mild; light forward projection suffices."
```

## DEPTH ANALYSIS GUIDANCE

Going deeper in Scenario Planning means tracing each scenario's causal logic — what specific sequence of events makes this future coherent, which driving forces dominate, which actors respond how. A thin pass names scenarios; a substantive pass identifies the predetermined elements (forces that will happen regardless of axis position) separately from the critical uncertainties (forces that could go either way), constructs each quadrant from genuine independent uncertainty, and articulates leading indicators that would let an observer recognize early which scenario is materializing. Test depth by asking: could a strategist build contingent plans from each scenario's leading indicators alone?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning STEEP driving forces (Social, Technological, Economic, Environmental, Political) before narrowing to the two axes. Generate at least one wild-card scenario outside the 2×2 — a low-probability/high-impact future that would invalidate the matrix. Identify robust strategies (work across scenarios) vs scenario-dependent strategies (require correctly identifying which scenario is unfolding) vs contingent actions (tied to specific leading indicators). Breadth markers: every quadrant carries leading indicators; strategies are tagged robust or scenario-dependent; the wild card sits in prose, not in the matrix; the two axes' independence is argued non-trivially.

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) structural distinctiveness; (CQ2) axes independence; (CQ3) no most-likely designation; (CQ4) honest predetermined vs uncertain classification; (CQ5) strategic actionability. The named failure modes (good-bad-medium-trap, official-future-trap, story-without-strategy-trap, certainty-masquerade-trap, correlated-axes-trap) are the evaluation checklist. A passing Scenario Planning output has four scenarios with distinct causal logic, axes whose independence is argued in ≥40 chars of rationale, leading indicators per quadrant, robust vs scenario-dependent strategies distinguished, a wild card in prose, and no scenario marked "most likely."

## REVISION GUIDANCE

Revise to rewrite scenario names that use magnitude labels (optimistic/pessimistic/baseline) into names that capture distinct causal logic (Constrained boom, Wild west, Soft landing, Stall). Revise to remove any "most likely" designation — SP does not predict; each scenario receives equal standing. Revise to add leading indicators where quadrants lack them. Revise to expand the axes-independence rationale where it is asserted rather than argued (must reference distinct drivers, historical decorrelation, or orthogonal dependencies). Resist revising scenarios toward what the user "expects" — the mode's purpose is to challenge the official future, including the user's. Resist collapsing the wild card back into the matrix; the wild card is structurally outside the 2×2.

## CONSOLIDATION GUIDANCE

Consolidate as a matrix-format scenarios artifact with the seven required sections in order. The 2×2 is the load-bearing visual: x-axis and y-axis each have label, low-label, high-label; quadrants TL/TR/BL/BR each have name (causal logic, not magnitude), narrative (coherent causal sequence), action (strategic translation), and indicators (≥1 per quadrant). The axes-independence rationale accompanies the axes definition. Wild card sits in prose, not in the envelope. Strategic implications distinguish robust strategies, scenario-dependent strategies, and contingent actions tied to specific leading indicators.

## VERIFICATION CRITERIA

Verified means: all four quadrants populated with name and non-empty narrative; each quadrant has at least one leading indicator; axes-independence rationale present and non-trivial (≥40 chars); driving forces classified predetermined vs critical-uncertainty in prose; scenarios are structurally distinct (not magnitude variants); no scenario labelled "most likely"; at least one wild card present in prose; at least one robust strategy distinguished from at least one scenario-dependent strategy. The five critical questions are addressable from the output.
