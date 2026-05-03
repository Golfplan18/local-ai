---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Probabilistic Forecasting

```yaml
# 0. IDENTITY
mode_id: probabilistic-forecasting
canonical_name: Probabilistic Forecasting
suffix_rule: analysis
educational_name: probabilistic forecasting (Tetlock superforecasting)

# 1. TERRITORY AND POSITION
territory: T6-future-exploration
gradation_position:
  axis: depth
  value: thorough
  secondary_axis: stance
  secondary_value: probability-output
adjacent_modes_in_territory:
  - mode_id: consequences-and-sequel
    relationship: depth-lighter sibling (forward causal cascade, no probability output)
  - mode_id: scenario-planning
    relationship: depth-counterpart (thorough but narrative-output rather than probability-output)
  - mode_id: pre-mortem-action
    relationship: stance-counterpart (adversarial-future on the action plan)
  - mode_id: wicked-future
    relationship: depth-molecular sibling (built Wave 4)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want a probability on this happening"
    - "what are the odds"
    - "give me a calibrated estimate"
    - "I want a forecast I could bet on"
    - "what's the base rate for something like this"
  prompt_shape_signals:
    - "probability of"
    - "what are the chances"
    - "forecast"
    - "superforecasting"
    - "Tetlock"
    - "calibrated probability"
    - "base rate for"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants a numeric probability or probability range as the primary output"
    - "user wants explicit base-rate reasoning, reference-class selection, and inside-vs-outside-view comparison"
    - "the question has a resolvable outcome (something that will be observably true or false by some date)"
  routes_away_when:
    - "user wants narrative scenarios rather than a probability number" → scenario-planning
    - "user wants light forward causal cascade with no probability commitment" → consequences-and-sequel
    - "user wants adversarial failure-mode walk on a plan" → pre-mortem-action
    - "user wants integrated multi-perspective forward analysis" → wicked-future
when_not_to_invoke:
  - "Question has no resolvable outcome (vague, contested definition of success) — clarify first via deep-clarification (T10) or escalate to scenario-planning"
  - "User is choosing among options now rather than estimating future state" → T3 modes
  - "User is examining historical causes of an outcome already observed" → T4 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [forecast_question, resolution_criteria, time_horizon]
    optional: [reference_class_candidates, prior_probability, named_hypothesis_drivers, evidence_inventory]
    notes: "Applies when user supplies a structured question with explicit resolution criteria and named drivers."
  accessible_mode:
    required: [forward_question]
    optional: [time_horizon_estimate, why_user_wants_forecast]
    notes: "Default. Mode elicits resolution criteria and time horizon during execution if missing."
  detection:
    expert_signals: ["resolution criteria are", "time horizon is", "reference class", "base rate", "prior probability"]
    accessible_signals: ["what are the odds", "probability of", "give me a forecast", "chances of"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What event are you forecasting, and by when would we know whether it happened?'"
    on_underspecified: "Ask: 'How would we know, in concrete observable terms, whether the forecast resolved yes or no?'"
output_contract:
  artifact_type: scenarios
  required_sections:
    - resolution_criteria_locked
    - reference_class_and_base_rate
    - inside_view_drivers
    - outside_view_adjustment
    - probability_estimate_with_range
    - leading_indicators_and_update_triggers
    - confidence_in_estimate
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Is the forecast question operationally resolvable, or has it been left vague enough to escape evaluation?"
    failure_mode_if_unmet: unresolvable-question
  - cq_id: CQ2
    question: "Has an explicit reference class been selected and its base rate stated, or has the analysis jumped to inside-view reasoning without an outside-view anchor?"
    failure_mode_if_unmet: base-rate-neglect
  - cq_id: CQ3
    question: "Has the analysis distinguished inside-view drivers (what's specific to this case) from outside-view adjustment (how this case compares to the reference class), and shown the math of the adjustment?"
    failure_mode_if_unmet: view-collapse
  - cq_id: CQ4
    question: "Has the probability been stated as a range (with explicit confidence interval or fermization) rather than a false-precision point estimate?"
    failure_mode_if_unmet: false-precision

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: unresolvable-question
    detection_signal: "Resolution criteria section is empty or contains hedged language ('roughly', 'meaningfully', 'in the ballpark') without operational definition."
    correction_protocol: re-dispatch
  - name: base-rate-neglect
    detection_signal: "No reference class named, or reference class named without a base-rate number."
    correction_protocol: re-dispatch
  - name: view-collapse
    detection_signal: "Inside-view drivers and outside-view base rate not separately stated; final estimate not derivable from the two views' combination."
    correction_protocol: re-dispatch
  - name: false-precision
    detection_signal: "Probability stated as a single point (e.g., '37%') without range, or with range narrower than the evidence supports."
    correction_protocol: flag
  - name: anchor-bias
    detection_signal: "Final estimate suspiciously close to the first-mentioned base rate or to a salient round number."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - tetlock-superforecasting
  optional:
    - kahneman-tversky-bias-catalog (when bias-corrections are central)
    - knightian-risk-uncertainty-ambiguity (when the question crosses risk/uncertainty boundary)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: wicked-future
    when: "Question depends on multiple interacting feedback loops or stakeholder conflicts that single-question forecasting cannot decompose."
  sideways:
    target_mode_id: scenario-planning
    when: "User wants narrative scenarios with named pathways rather than a single probability number."
  downward:
    target_mode_id: consequences-and-sequel
    when: "User wants light forward causal cascade with no probability commitment."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Probabilistic Forecasting is the explicitness of base-rate reasoning, reference-class construction, and inside-vs-outside-view adjustment. A thin pass produces a number with intuitive justification; a substantive pass selects a reference class, states its base rate with citation or reasoning, names the inside-view drivers that distinguish this case from the reference class, shows the math of the adjustment, and produces a probability range whose width reflects the analyst's actual confidence rather than a default fermization. Test depth by asking: could a reader reproduce the estimate from the artifact, including the directional and magnitude adjustments from base rate?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means surveying multiple candidate reference classes before locking one (or explicitly weighting across several), scanning for inside-view drivers in multiple categories (mechanism, motivation, capacity, environment, base-rate-defying factors), and surfacing leading indicators that would update the estimate. A breadth-passing analysis names at least two candidate reference classes and explains the choice, even if only one is used for the final estimate.

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) operational resolvability; (CQ2) explicit reference class with stated base rate; (CQ3) inside-vs-outside-view separation with shown adjustment; (CQ4) range rather than false-precision point. The named failure modes (unresolvable-question, base-rate-neglect, view-collapse, false-precision, anchor-bias) are the evaluation checklist. A passing forecast states resolution criteria operationally, names reference class and base rate, separates and combines inside/outside views, and produces a probability range with leading indicators for update.

## REVISION GUIDANCE

Revise to add explicit base-rate citation where the draft asserts "common" or "rare" without a number. Revise to widen the probability range where the draft has anchored on false precision. Revise to surface inside-view drivers individually rather than aggregating them into a vague "case-specific factors" mention. Resist revising toward narrative — the mode's analytical character is probability-output. If the user wants narrative, escalate sideways to scenario-planning rather than diluting this mode's contract.

## CONSOLIDATION GUIDANCE

Consolidate as a structured scenarios artifact with the seven required sections. Resolution criteria appear as a locked operational definition. Reference class is named with base-rate number. Inside-view drivers appear as a list with directional and magnitude estimates. Outside-view adjustment shows the math (e.g., "base rate 15%, inside-view drivers shift estimate up by ~10–20pp, final 25–35%"). Leading indicators are observable signals that would prompt revision. Confidence-in-estimate distinguishes calibration confidence (am I right about the range) from point confidence (where in the range is most likely).

## VERIFICATION CRITERIA

Verified means: resolution criteria are operational and locked; reference class is named with base-rate number; inside-view drivers and outside-view base rate are separately stated; the final probability is a range whose construction can be reproduced from the artifact; leading indicators are named with thresholds; the four critical questions are addressable from the output. Confidence-in-estimate accompanies the probability range.

## CAVEATS AND OPEN DEBATES

**Debate D8 — Tetlock's commandments as binding rules vs. heuristics held lightly.** Tetlock's *Superforecasting* (2015) closes with "ten commandments" for would-be forecasters (triage, break problems into components, balance inside and outside views, etc.). A persistent failure mode in popular Tetlock readings is treating these commandments as binding rules — applied mechanically regardless of question shape. Tetlock himself has been explicit, in interviews and follow-up writing, that the commandments are heuristics that must be held lightly: superforecasters do not follow them mechanically; they cultivate the underlying disposition (probabilistic thinking, bias awareness, willingness to update) and apply the commandments where they help. This mode operates with the heuristics-held-lightly stance: the seven required output sections encode the disposition (operational resolvability, base-rate anchoring, view-separation, range-not-point) without prescribing rote commandment-by-commandment execution. Citations: Tetlock & Gardner 2015 *Superforecasting*; Tetlock subsequent interview and methodological clarifications.
