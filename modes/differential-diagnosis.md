---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Differential Diagnosis

```yaml
# 0. IDENTITY
mode_id: differential-diagnosis
canonical_name: Differential Diagnosis
suffix_rule: analysis
educational_name: light differential diagnosis (medical-tradition lighter sibling of ACH)

# 1. TERRITORY AND POSITION
territory: T5-hypothesis-evaluation
gradation_position:
  axis: depth
  value: light
adjacent_modes_in_territory:
  - mode_id: competing-hypotheses
    relationship: depth-heavier sibling (full Heuer ACH)
  - mode_id: bayesian-hypothesis-network
    relationship: depth-molecular sibling (built Wave 4)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I have a few candidate explanations and need a quick weigh-in"
    - "what are the main possibilities and which is most likely"
    - "narrow down the candidates"
    - "rule things out quickly"
    - "what else could this be"
  prompt_shape_signals:
    - "differential"
    - "differential diagnosis"
    - "candidate explanations"
    - "what are the possibilities"
    - "rule out"
    - "most likely cause"
disambiguation_routing:
  routes_to_this_mode_when:
    - "two-to-five candidate explanations; user wants light diagnosticity weighing"
    - "user has limited time and prefers a quick narrowing over a full ACH matrix"
    - "evidence-set is small enough to weigh informally"
  routes_away_when:
    - "user wants full evidence-by-hypothesis matrix with disconfirming-evidence focus" → competing-hypotheses
    - "user wants probability network with conditional dependencies" → bayesian-hypothesis-network
    - "competing explanations are really inter-frame disagreement (paradigm clash)" → frame-comparison or worldview-cartography (T9)
when_not_to_invoke:
  - "Only one hypothesis on the table — no differential to make" → use a single-hypothesis-test mode in T1 or T4
  - "Hypotheses are themselves complete arguments needing soundness audit" → T1
  - "User wants to know who benefits, not which explanation fits" → cui-bono (T2)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: neutral

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [observed_evidence, candidate_hypotheses, prior_probability_estimates]
    optional: [diagnosticity_notes, base_rate_data, cost_of_misdiagnosis]
    notes: "Applies when user supplies a structured hypothesis list and evidence inventory."
  accessible_mode:
    required: [situation_description, candidate_explanations]
    optional: [evidence_observed_so_far]
    notes: "Default. Mode elicits evidence and infers candidate hypothesis structure if not supplied."
  detection:
    expert_signals: ["candidate hypotheses", "prior probability", "diagnosticity", "base rate", "evidence inventory"]
    accessible_signals: ["differential", "what else could this be", "rule out", "most likely cause"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you tell me what you've observed and which explanations are on the table?'"
    on_underspecified: "Ask: 'What's the symptom or pattern, and what explanations have you considered so far?'"
output_contract:
  artifact_type: ranked_options
  required_sections:
    - candidate_hypotheses_listed
    - evidence_observed
    - diagnosticity_per_hypothesis
    - ranking_with_reasoning
    - one_disconfirming_test_per_top_two
    - confidence_per_ranking
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the candidate hypotheses genuinely different explanations of the evidence, or are some of them re-descriptions of the same underlying explanation?"
    failure_mode_if_unmet: hypothesis-collapse
  - cq_id: CQ2
    question: "Does the diagnosticity assessment distinguish evidence that *rules out* hypotheses from evidence that is merely *consistent with* them, given that consistent evidence is weak diagnostic?"
    failure_mode_if_unmet: confirmation-anchoring
  - cq_id: CQ3
    question: "Has the analysis identified at least one disconfirming test for each of the top two candidates, so the user can act to narrow further?"
    failure_mode_if_unmet: no-actionable-disconfirmer
  - cq_id: CQ4
    question: "Has the analysis flagged when the evidence base is too small for a confident ranking, rather than producing a ranking it cannot support?"
    failure_mode_if_unmet: false-confidence

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: hypothesis-collapse
    detection_signal: "Two or more named hypotheses make identical predictions about the evidence; the differential is artificial."
    correction_protocol: re-dispatch
  - name: confirmation-anchoring
    detection_signal: "Diagnosticity is assessed via consistency only (this evidence is consistent with H1) rather than via disconfirming power (this evidence rules out H2)."
    correction_protocol: re-dispatch
  - name: no-actionable-disconfirmer
    detection_signal: "Top-ranked hypotheses are returned without naming a test that would distinguish them."
    correction_protocol: flag
  - name: false-confidence
    detection_signal: "A ranking is produced when evidence is too sparse to support it; confidence per ranking is inflated."
    correction_protocol: flag
  - name: missing-zebra
    detection_signal: "Common-case explanations dominate; rare-but-serious explanations are not present even as low-rank candidates."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - differential-diagnosis-schema
  optional:
    - heuer-ach (when escalating to full ACH)
    - bayesian-base-rate (when prior probabilities are available)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~1min
escalation_signals:
  upward:
    target_mode_id: competing-hypotheses
    when: "Hypothesis count exceeds five, evidence inventory is large, or user wants disconfirming-evidence focus across the matrix."
  sideways:
    target_mode_id: frame-comparison
    when: "On reflection the candidates are inter-frame disagreements (paradigm clashes) rather than within-frame hypotheses; route to T9."
  downward:
    target_mode_id: null
    when: "Differential Diagnosis is the lightest mode in T5."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Differential Diagnosis is the rigor with which diagnosticity is assessed: not just "this evidence is consistent with H1" but "this evidence rules out H2 because H2 predicted X and we observed not-X." A thin pass ranks by surface plausibility; a substantive pass distinguishes consistency from diagnosticity, names which observations would rule each top hypothesis out, and surfaces the rare-but-serious "zebra" candidates that common-case explanations would otherwise eclipse. Test depth by asking: does the ranking change appropriately when one piece of evidence is hypothetically inverted?

## BREADTH ANALYSIS GUIDANCE

Widening the lens in Differential Diagnosis means deliberate inclusion of rare-but-serious candidates, candidates from adjacent domains (a symptom that looks like X in domain A might be Y in domain B), candidates that combine mechanisms (the situation may be H1 *and* H3 together rather than H1 alone), and the null hypothesis (the situation is benign and self-resolving). Even when only the top two-or-three are ranked, the breadth pass documents the candidates considered and rejected with a one-line reason for rejection.

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) hypothesis distinctness; (CQ2) consistency vs. diagnosticity; (CQ3) actionable disconfirmer for top two; (CQ4) confidence honesty when evidence is sparse. The named failure modes (hypothesis-collapse, confirmation-anchoring, no-actionable-disconfirmer, false-confidence, missing-zebra) are the evaluation checklist. A passing Differential Diagnosis output ranks distinct hypotheses by diagnosticity, offers a disconfirming test per top candidate, and either supports its confidence with evidence or flags the ranking as evidence-limited.

## REVISION GUIDANCE

Revise to merge collapsed hypotheses where two candidates make identical predictions, or to differentiate them by predicting where their predictions diverge. Revise to upgrade consistency-language to diagnosticity-language. Revise to add a disconfirming test where the top candidates are ranked without one. Resist revising toward a single-explanation summary when the evidence supports two or three competing candidates equally — the mode's value is in honest residual uncertainty, not in delivering a verdict.

## CONSOLIDATION GUIDANCE

Consolidate as a structured ranked-options artifact with the six required sections. Candidate hypotheses are listed with one-line characterizations. Evidence observed is listed and tagged with which hypotheses it bears on. Diagnosticity per hypothesis is stated as a brief diagnostic note (rules out / consistent with / discriminating between). Ranking carries reasoning. Disconfirming tests for the top two are emitted as actionable observations or experiments. Confidence per ranking is honest about evidence sparseness.

## VERIFICATION CRITERIA

Verified means: at least two candidate hypotheses are present and distinct; diagnosticity is assessed in disconfirming-power language for at least the top two; at least one disconfirming test is emitted per top candidate; confidence per ranking explicitly addresses evidence sufficiency; rare-but-serious "zebra" candidates have been considered (or their absence noted with reason); the four critical questions are addressable from the output.
