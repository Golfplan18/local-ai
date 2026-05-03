---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
---

# MODE: Decision Under Uncertainty

```yaml
# 0. IDENTITY
mode_id: decision-under-uncertainty
canonical_name: Decision Under Uncertainty
suffix_rule: analysis
educational_name: decision analysis under uncertainty (probability and time-weighted)

# 1. TERRITORY AND POSITION
territory: T3-decision-making-under-uncertainty
gradation_position:
  axis: depth
  value: thorough
adjacent_modes_in_territory:
  - mode_id: constraint-mapping
    relationship: depth-light sibling (deterministic tradeoffs)
  - mode_id: multi-criteria-decision
    relationship: complexity sibling (multi-criteria weighting)
  - mode_id: decision-architecture
    relationship: depth-molecular sibling (full molecular orchestration)
  - mode_id: real-options-decision
    relationship: specificity counterpart (staged investment) — gap-deferred
  - mode_id: ethical-tradeoff
    relationship: stance counterpart (normative + values-laden) — gap-deferred

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "a choice must be made between alternatives with uncertain outcomes"
    - "probabilities matter but are not precisely known"
    - "the cost of being wrong is high"
    - "should we act now or wait"
    - "is it worth waiting for more information"
  prompt_shape_signals:
    - "expected value"
    - "decision tree"
    - "should we wait"
    - "value of information"
    - "downside of each option"
disambiguation_routing:
  routes_to_this_mode_when:
    - "probabilities and time-value are central to the choice"
    - "the option to defer or buy information has value worth assessing"
  routes_away_when:
    - "tradeoffs are deterministic; no probability arithmetic needed" → constraint-mapping
    - "user wants to compare multiple weighted criteria" → multi-criteria-decision
    - "decision is a molecular orchestration with stakeholders + risk + future" → decision-architecture
    - "user wants to explore multiple possible futures rather than make one decision now" → scenario-planning (T6)
    - "user wants to understand which explanation fits the evidence" → competing-hypotheses (T5)
when_not_to_invoke:
  - "User has already chosen and wants execution" → Project Mode
  - "Decision involves active negotiation between parties" → T13 negotiation
  - "Question is 'what could go wrong' along a causal cascade" → consequences-and-sequel (T6)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [decision_context, candidate_alternatives_named, probability_estimates_or_ranges, utility_units]
    optional: [base_rate_data, prior_decisions_in_similar_contexts, value_of_information_estimates]
    notes: "Applies when user explicitly carries probabilities, payoffs, and decision theory vocabulary."
  accessible_mode:
    required: [decision_or_choice_situation, sense_of_what_is_uncertain]
    optional: [hint_at_some_alternatives, time_pressure_or_deadline]
    notes: "Default. Mode elicits probabilities (or ranges or qualitative bands), surfaces defer/sequence/hedge alternatives, and supplies utility units."
  detection:
    expert_signals: ["expected value", "EV", "decision tree", "real options", "minimax regret", "value of information", "VOI", "tornado chart", "influence diagram", "Bayesian"]
    accessible_signals: ["should we wait", "is it worth the risk", "what's the downside", "what if we're wrong"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the decision you're facing, what alternatives are you weighing, and what's uncertain about each one?'"
    on_underspecified: "Ask: 'Are probabilities and time-value central (route here), or are the tradeoffs deterministic (Constraint Mapping)?'"
output_contract:
  artifact_type: recommendation
  required_sections:
    - decision_framing
    - uncertainty_identification
    - consequence_analysis
    - value_of_information_analysis
    - recommendation
    - non_quantifiable_factors
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Is each critical variable classified as risk (assignable probability), uncertainty (estimable range), or deep uncertainty (no meaningful probability)?"
    failure_mode_if_unmet: false-precision
  - cq_id: CQ2
    question: "Have defer / sequence / hedge / buy-information alternatives been considered alongside direct choices?"
    failure_mode_if_unmet: missing-defer
  - cq_id: CQ3
    question: "Have non-quantifiable factors (ethics, relationships, identity, reputation) been presented alongside the quantitative framework, not as footnotes?"
    failure_mode_if_unmet: quantification-trap
  - cq_id: CQ4
    question: "Does the recommendation name what would change it — the conditions under which it should be revisited?"
    failure_mode_if_unmet: unconditional-recommendation
  - cq_id: CQ5
    question: "Are probabilities grounded in base rates or qualitative bands, not anchored to initial guesses presented as point estimates?"
    failure_mode_if_unmet: anchoring-trap

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: false-precision
    detection_signal: "Specific point probability (e.g. '17%') assigned without base-rate grounding."
    correction_protocol: flag (replace with range or qualitative band)
  - name: analysis-paralysis
    detection_signal: "Real options framing rationalises indefinite delay; cost of delay not assessed against value of information."
    correction_protocol: re-dispatch (assess cost-of-delay vs VOI explicitly)
  - name: quantification-trap
    detection_signal: "All factors reduced to utility numbers when some (ethics, identity, morale) resist meaningful quantification."
    correction_protocol: re-dispatch (add non-quantifiable factors section)
  - name: missing-defer
    detection_signal: "Decision framed as binary (A or B) when 'wait and learn' or 'buy information' is feasible."
    correction_protocol: re-dispatch (add defer/pilot/hedge alternative)
  - name: anchoring-trap
    detection_signal: "Initial probability estimates anchor subsequent analysis regardless of evidence."
    correction_protocol: re-dispatch (generate estimates independently before comparison)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - expected-utility-theory
  optional:
    - real-options-methodology (when financial/staged-investment)
    - minimax-regret-and-robust-decision-making (under deep uncertainty)
    - tetlock-superforecasting (when probabilities can be calibrated)
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: decision-architecture
    when: "Decision requires molecular orchestration: stakeholders + risk + future + multi-criteria all interact."
  sideways:
    target_mode_id: scenario-planning
    when: "Multiple plausible futures need to be explored before a choice is made."
  downward:
    target_mode_id: constraint-mapping
    when: "Probabilities are not material; deterministic tradeoff mapping suffices."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Decision Under Uncertainty is the rigour with which uncertainty is classified, probabilities are grounded, and consequences are characterised. A thin pass attaches numbers to outcomes; a substantive pass classifies each variable (risk / uncertainty / deep uncertainty), grounds each probability in a base rate or qualitative band, traces consequences under each plausible state, and assesses the value of additional information against the cost of delay. Test depth by asking: could the recommendation predict how it would shift if a specific input changed? Each critical variable carries the literal label `risk` / `uncertainty` / `deep uncertainty`.

## BREADTH ANALYSIS GUIDANCE

Breadth in Decision Under Uncertainty is the catalog of alternatives the framing might exclude. Widen the lens to surface defer, sequence, hedge, and buy-information options alongside direct choices. Identify robust alternatives (perform acceptably across multiple states) versus optimal alternatives (best in one state). Surface non-quantifiable factors. Breadth markers: at least one defer/pilot/hedge alternative; explicit assessment of which alternatives are robust vs optimal; reversibility cost named per alternative.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ5. The named failure modes are the evaluation checklist. A passing Decision Under Uncertainty output: classifies each critical variable; surfaces defer/sequence/hedge alternatives; assesses value of information vs cost of delay; states the recommendation with conditions under which it should be revisited; presents non-quantifiable factors alongside the quantitative framework. Specifically check for false precision (point probabilities without base rates), analysis paralysis (delay rationalised indefinitely), quantification trap (ethics reduced to numbers), and missing defer (binary framing when wait-and-learn is feasible).

## REVISION GUIDANCE

Revise to convert point probabilities into ranges when no base rate grounds the precision. Revise to add defer/pilot/hedge alternatives when binary framing has masked them. Revise to add non-quantifiable factors when only utility numbers appear. Revise to add recommendation conditions ("this would change if X"). Resist revising toward over-confident point estimates — humility about probability is part of the output. Resist revising toward exhaustive enumeration when robustness analysis suffices.

## CONSOLIDATION GUIDANCE

Consolidate as a structured artifact with the six required sections (decision framing / uncertainty identification / consequence analysis / VOI analysis / recommendation / non-quantifiable factors). Format: structured. When envelope-bearing: decision_tree for sequential choices under assignable probabilities; influence_diagram when dependency structure dominates; tornado for parameter-sensitivity questions. Each chance node's children probabilities sum to 1.0. Decision-node children carry no probability. Utility units stated verbatim and aligned between prose and envelope.

## VERIFICATION CRITERIA

Verified means: each critical variable classified as risk/uncertainty/deep uncertainty with reasoning; defer/sequence/hedge alternatives considered alongside direct choices; value-of-information assessed against cost of delay; recommendation states what would change it; non-quantifiable factors present alongside quantitative framework; probabilities grounded in base rates or qualitative bands. The five critical questions are addressed in the output.
