---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Wicked Future

```yaml
# 0. IDENTITY
mode_id: wicked-future
canonical_name: Wicked Future
suffix_rule: analysis
educational_name: wicked future analysis (scenario + pre-mortem + probabilistic forecast composition)

# 1. TERRITORY AND POSITION
territory: T6-future-exploration
gradation_position:
  axis: depth
  value: molecular
adjacent_modes_in_territory:
  - mode_id: consequences-and-sequel
    relationship: depth-light sibling (forward projection)
  - mode_id: probabilistic-forecasting
    relationship: depth-thorough sibling (probability-output)
  - mode_id: scenario-planning
    relationship: depth-thorough sibling (narrative-output)
  - mode_id: pre-mortem-action
    relationship: stance-adversarial-future sibling

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "the future here is genuinely tangled and I want scenarios + probabilities + failure pathways together"
    - "I need narrative scenarios, calibrated probabilities, and stress tests, not one or the other"
    - "willing to spend the time on a full forward-looking molecular pass"
    - "the question is forward-looking and the standard tools each give partial answers"
  prompt_shape_signals:
    - "wicked future"
    - "long-horizon scenarios with probabilities"
    - "scenarios plus pre-mortem"
    - "what could the future look like and what could go wrong"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants integrated forward analysis with scenarios + probabilities + adversarial-future stress test"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "want quick forward projection from current state" → consequences-and-sequel
    - "want calibrated probability output without narrative" → probabilistic-forecasting
    - "want narrative scenarios without probability formalism or pre-mortem" → scenario-planning
    - "want pre-mortem on a specific plan, not exploration of the future broadly" → pre-mortem-action
when_not_to_invoke:
  - "User has time pressure" → scenario-planning or probabilistic-forecasting
  - "Question is really about a current decision rather than the future broadly" → decision-architecture or decision-under-uncertainty

# 3. EXECUTION STRUCTURE
composition: molecular
# NOTE: Backcasting (constructive-future stance) is deferred per CR-6.
# This mode composes around its absence by anchoring scenario-planning
# (neutral-future), probabilistic-forecasting (probability-output), and
# pre-mortem-action (adversarial-future). The constructive-future stance
# is gap-flagged in partial_composition_handling rather than substituted.
molecular_spec:
  components:
    - mode_id: scenario-planning
      runs: full
    - mode_id: pre-mortem-action
      runs: full
    - mode_id: probabilistic-forecasting
      runs: full
  synthesis_stages:
    - name: scenario-probability-overlay
      type: parallel-merge
      input: [scenario-planning, probabilistic-forecasting]
      output: "scenario set with calibrated probability bands and identified divergence points (where scenarios branch)"
    - name: failure-pathway-stress-test
      type: contradiction-surfacing
      input: [scenario-probability-overlay, pre-mortem-action]
      output: "scenarios stress-tested against pre-mortem failure pathways; identification of which scenarios contain pre-mortem-flagged failure modes"
    - name: integrated-future-architecture
      type: dialectical-resolution
      input: [scenario-probability-overlay, failure-pathway-stress-test]
      output: "integrated forward analysis: probability-weighted scenarios with named failure pathways, divergence-points-to-monitor, and explicit gap-flag for missing constructive-future (Backcasting deferred)"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence forecasting findings
    deferred_components:
      - mode_id: backcasting
        status: deferred (gap-deferred per CR-6)
        compensating_treatment: "Constructive-future stance is not substituted. Output explicitly gap-flags the absence of backward-from-desired-future analysis in the integrated-future-architecture stage. Consumers requiring constructive-future framing should compose Wicked Future with downstream goal-articulation work."

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [forward_question, time_horizon, key_uncertainties]
    optional: [prior_scenarios, prior_forecasts, intervention_candidates]
    notes: "Applies when user supplies key uncertainties or prior scenarios."
  accessible_mode:
    required: [forward_question]
    optional: [contextual_background, time_horizon]
    notes: "Default. Mode elicits time horizon, key uncertainties, and intervention candidates during execution."
  detection:
    expert_signals: ["scenarios", "probability bands", "key uncertainties", "time horizon"]
    accessible_signals: ["what could the future look like", "what could go wrong", "long-horizon"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the forward-looking question, and over what time horizon?'"
    on_underspecified: "Ask the user whether they want the full Wicked Future molecular pass or a lighter scenario-planning / probabilistic-forecasting read."
output_contract:
  artifact_type: synthesis
  required_sections:
    - forward_question_and_horizon
    - scenario_set_with_probability_bands
    - divergence_points
    - failure_pathway_stress_test_findings
    - integrated_forward_architecture
    - constructive_future_gap_flag
    - residual_uncertainties
    - confidence_map
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have the scenarios been constructed broadly enough, or has the analysis privileged extrapolation of the dominant trend?"
    failure_mode_if_unmet: trend-extrapolation-bias
  - cq_id: CQ2
    question: "Do the probability bands integrate with the scenario narratives, or do they sit in a separate silo from the scenario divergence points?"
    failure_mode_if_unmet: silo-aggregation
  - cq_id: CQ3
    question: "Has pre-mortem-action stress-tested the scenarios for failure pathways, or has the synthesis presented scenarios without naming failure modes?"
    failure_mode_if_unmet: pre-mortem-omission
  - cq_id: CQ4
    question: "Has the absence of constructive-future analysis (Backcasting deferred) been gap-flagged, or has the output silently presented descriptive-future as if complete?"
    failure_mode_if_unmet: silent-gap

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: trend-extrapolation-bias
    detection_signal: "All scenarios are variations of the dominant trend; no orthogonal or discontinuity scenario."
    correction_protocol: re-dispatch (with explicit divergence-scenario prompt)
  - name: silo-aggregation
    detection_signal: "Synthesis stage outputs concatenate scenario, probability, and pre-mortem sections without integration."
    correction_protocol: re-dispatch
  - name: pre-mortem-omission
    detection_signal: "pre-mortem-action did not run against the leading scenario."
    correction_protocol: flag and re-dispatch
  - name: silent-gap
    detection_signal: "Output presents integrated-future-architecture without flagging Backcasting absence."
    correction_protocol: flag and add gap-flag section

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - klein-pre-mortem
  optional:
    - tetlock-superforecasting (when scenarios extend beyond ~5 years)
    - taleb-extremistan-mediocristan (when discontinuity scenarios in play)
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Wicked Future is the heaviest mode in T6."
  sideways:
    target_mode_id: pre-mortem-action
    when: "Question is really about a specific plan's failure pathways rather than open future exploration."
  downward:
    target_mode_id: scenario-planning
    when: "User has time pressure; scenario narratives without probability formalism or pre-mortem suffice."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Wicked Future is the degree to which scenario-probability-overlay and failure-pathway-stress-test stages integrate component outputs rather than concatenating them. A thin molecular pass runs scenario-planning, probabilistic-forecasting, and pre-mortem-action and stitches their outputs; a substantive pass surfaces tensions — for instance, a scenario whose probability band collides with a pre-mortem failure pathway, or a divergence point that the probability formalism cannot price. Test depth by asking: does the integrated forward architecture contain a forecast-claim that no single component could have produced?

## BREADTH ANALYSIS GUIDANCE

Breadth in Wicked Future is the catalog of scenarios considered before narrowing to a probability-weighted set. Widen the lens to scan: trend-extrapolation; orthogonal-driver scenario; discontinuity (extremistan event); reversal; backcasting-from-desired-future (flagged as gap). Even when only 3–5 scenarios are kept, breadth is documented in the scenario-set section. Note: alternative compositions considered included substituting consequences-and-sequel for probabilistic-forecasting in lighter pass; current composition selects the full probabilistic forecasting for calibrated bands.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Wicked Future output integrates components rather than concatenating, surfaces divergence points where scenarios branch, includes pre-mortem stress test against leading scenarios, and explicitly gap-flags the constructive-future absence rather than silently presenting descriptive-future as complete.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to add discontinuity scenarios where the draft over-extrapolates dominant trend. Revise to surface divergence points where scenarios are presented as parallel narratives without identifying branching mechanism. Resist revising toward over-confident probability point-estimates — Wicked Future honors uncertainty in long-horizon forecasting; bands and confidence-per-finding are appropriate.

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the eight required sections. The constructive-future-gap-flag section is mandatory and visible — not buried in a confidence map. Each section carries provenance to its component sources (scenario-planning for scenarios; probabilistic-forecasting for probability bands; pre-mortem-action for failure pathways). Confidence map is structured per-finding.

## VERIFICATION CRITERIA

Verified means: every component ran (or was flagged as proceeded-with-gap); synthesis stages integrated rather than concatenated; pre-mortem stress-test ran against leading scenarios; constructive-future gap is explicitly flagged; confidence map is populated. The four critical questions are addressed in the output.
