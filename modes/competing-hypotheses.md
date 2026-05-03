---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
---

# MODE: Competing Hypotheses

```yaml
# 0. IDENTITY
mode_id: competing-hypotheses
canonical_name: Competing Hypotheses
suffix_rule: analysis
educational_name: analysis of competing hypotheses (ACH, Heuer-style)

# 1. TERRITORY AND POSITION
territory: T5-hypothesis-evaluation
gradation_position:
  axis: depth
  value: thorough
adjacent_modes_in_territory:
  - mode_id: differential-diagnosis
    relationship: depth-lighter sibling
  - mode_id: bayesian-hypothesis-network
    relationship: depth-molecular sibling

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "multiple plausible explanations for the same evidence"
    - "I have a favoured theory but want it stress-tested"
    - "the evidence is ambiguous or contradictory"
    - "what is actually happening here"
    - "there might be deception or information manipulation"
  prompt_shape_signals:
    - "which explanation fits best"
    - "make me an ACH matrix"
    - "what rules out X"
    - "how would we know if we're wrong"
    - "what's the strongest evidence against each theory"
    - "competing hypotheses"
disambiguation_routing:
  routes_to_this_mode_when:
    - "two or more hypotheses on the table plus a body of evidence to weigh against them"
    - "want diagnosticity-driven adjudication, not interest analysis"
    - "the question is what is true, not what to do"
  routes_away_when:
    - "choosing between action alternatives, not explanations" → decision-under-uncertainty
    - "questioning the foundational framework rather than testing within it" → paradigm-suspension
    - "tracing institutional interests behind competing claims" → cui-bono
    - "only one plausible explanation, want to strengthen it" → steelman-construction
    - "competing hypotheses are themselves whole arguments to audit" → T1
when_not_to_invoke:
  - "User has only one explanation in play; ACH requires at least two competing hypotheses" → steelman-construction or differential-diagnosis
  - "User wants a quick-read differential without full matrix construction" → differential-diagnosis (lighter T5 sibling)
  - "Hypothesis disagreement is really inter-frame disagreement using different paradigms" → T9 paradigm modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: neutral

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [hypothesis_set, evidence_inventory]
    optional: [diagnosticity_priors, deception_context, scoring_method_preference]
    notes: "Applies when user supplies explicit hypotheses (H1, H2 …) and/or an evidence inventory with credibility/relevance ratings."
  accessible_mode:
    required: [situation_with_multiple_explanations]
    optional: [user_favoured_hypothesis, evidence_so_far]
    notes: "Default. Mode generates additional hypotheses, structures evidence, and constructs the matrix."
  detection:
    expert_signals: ["ACH matrix", "Heuer", "diagnosticity", "hypothesis H1, H2", "evidence E1"]
    accessible_signals: ["which explanation", "competing theories", "what's most likely happening", "stress-test my theory"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the situation, the explanations on the table, and the evidence you've seen so far?'"
    on_underspecified: "Ask: 'What are the competing explanations you'd like me to weigh against each other, and what evidence have you encountered?'"
output_contract:
  artifact_type: ranked_options
  required_sections:
    - hypothesis_list
    - evidence_inventory
    - consistency_matrix_reading
    - diagnosticity_assessment
    - tentative_conclusions_via_elimination
    - sensitivity_analysis
    - monitoring_priorities
  format: matrix

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has at least one hypothesis beyond the user's initial set been generated, or is the matrix limited to user-proposed explanations?"
    failure_mode_if_unmet: missing-hypothesis
  - cq_id: CQ2
    question: "Has each evidence item been assessed across all hypotheses (across-the-matrix), or only against the favoured one (down-the-matrix)?"
    failure_mode_if_unmet: confirmation-framing
  - cq_id: CQ3
    question: "Is the conclusion framed as elimination of least-consistent hypotheses, or as confirmation of the favoured one?"
    failure_mode_if_unmet: confirmation-framing
  - cq_id: CQ4
    question: "Has at least one piece of evidence been identified as high-diagnosticity, distinguishing sharply between hypotheses?"
    failure_mode_if_unmet: false-rigour
  - cq_id: CQ5
    question: "If adversarial actors are plausible, has the analysis assessed whether high-diagnosticity evidence could be manufactured?"
    failure_mode_if_unmet: deception-blindness

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: missing-hypothesis
    detection_signal: "All hypotheses are user-proposed; no analyst-generated alternative or null/'something else' hypothesis."
    correction_protocol: re-dispatch
  - name: confirmation-framing
    detection_signal: "Conclusion phrased as 'H_x is supported by E1, E3' rather than 'H_x survives because fewer items contradict it'; or evidence assessed only against the favoured hypothesis."
    correction_protocol: re-dispatch
  - name: false-rigour
    detection_signal: "Matrix format used but consistency ratings are uniform across rows or unjustified; all rows non-diagnostic."
    correction_protocol: flag
  - name: deception-blindness
    detection_signal: "Adversarial context plausible but no assessment of whether high-diagnosticity evidence could be planted or manufactured."
    correction_protocol: flag
  - name: wrong-tally
    detection_signal: "Endorsed surviving hypothesis has more inconsistent (I + II) cells than an alternative; conclusion contradicts cell count."
    correction_protocol: re-dispatch
  - name: static-snapshot
    detection_signal: "No monitoring priorities or leading indicators stated; analysis treated as final in evolving situation."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - heuer-ach-methodology
  optional:
    - bayesian-base-rate-reasoning
    - counter-deception-frameworks
    - falsifiability-popper
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: bayesian-hypothesis-network
    when: "Hypothesis dependencies form a network with non-trivial conditional structure; quasi-Bayesian tally insufficient."
  sideways:
    target_mode_id: differential-diagnosis
    when: "Time-pressed user wants light-weight ranking without full matrix construction."
  downward:
    target_mode_id: differential-diagnosis
    when: "User wants quick differential rather than thorough ACH; complexity does not warrant full matrix."
```

## DEPTH ANALYSIS GUIDANCE

Going deeper in Competing Hypotheses means working **across** the evidence-hypothesis matrix (one piece of evidence evaluated against all hypotheses) rather than **down** it (collecting evidence for a favoured hypothesis). Depth shows itself in disconfirmation rigor: the matrix is fully populated, every cell is justified, the diagnosticity of each evidence item is assessed, and the conclusion follows from elimination of least-consistent hypotheses rather than confirmation of the favoured one. A thin pass tallies confirmations; a substantive pass identifies the rows whose values vary sharply (high-diagnosticity), names what would falsify each surviving hypothesis, and conducts sensitivity analysis on the most diagnostic evidence.

## BREADTH ANALYSIS GUIDANCE

Widening the lens means generating the widest plausible hypothesis set — at minimum one beyond the user's initial proposals, including unconventional explanations and a null/"something else" hypothesis. Identify what evidence would **disconfirm** each hypothesis, since disconfirmation is more diagnostic than confirmation. Identify the missing-evidence question: what single piece of information would most change the analysis? Where adversarial actors are plausible, scan for whether high-diagnosticity evidence could be manufactured. Breadth markers: at least one hypothesis is explicitly flagged as analyst-generated, sensitivity analysis names at least one evidence item whose reversal would change the ranking, and leading indicators are identified for each surviving hypothesis.

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) hypothesis breadth beyond user-proposed; (CQ2) across-not-down matrix posture; (CQ3) elimination framing; (CQ4) at least one high-diagnosticity item; (CQ5) deception assessment when applicable. The named failure modes (missing-hypothesis, confirmation-framing, false-rigour, deception-blindness, wrong-tally, static-snapshot) are the evaluation checklist. A passing ACH output has a fully populated matrix with Heuer vocabulary (CC, C, N, I, II, NA), names the surviving hypothesis as the one with fewest I+II cells, identifies high-diagnosticity evidence explicitly, performs sensitivity analysis, and lists monitoring priorities.

## REVISION GUIDANCE

Revise to fill missing cells (use NA explicitly when evidence does not bear on a hypothesis; never leave cells absent). Revise to convert custom vocabulary ("supports", "refutes") to Heuer vocabulary. Revise to add hypotheses where the matrix is too narrow, including at least one analyst-generated alternative. Revise to convert confirmation framing ("H2 is supported by E1, E3") to elimination framing ("H2 survives because fewer items contradict it — count of I+II cells per hypothesis"). Revise to recount cell tallies if the prose conclusion contradicts the matrix arithmetic. Resist revising toward the user's favoured hypothesis if the matrix doesn't support it — the methodology's purpose is to surface when the favourite loses. Silent conclusion flips during revision are failures unless cell values were also changed with rationale.

## CONSOLIDATION GUIDANCE

Consolidate as a matrix-format ranked-options artifact with the seven required sections in order. Hypotheses carry stable IDs (H1, H2 …) prefixed in prose, matching the matrix. Evidence carries stable IDs (E1, E2 …) prefixed in prose, matching the matrix. The matrix itself is the load-bearing structure: rows are evidence items, columns are hypotheses, cells use Heuer vocabulary (CC/C/N/I/II/NA). The Tentative-conclusions section names the surviving hypothesis verbatim and presents elimination arithmetic (count of I+II per hypothesis, tie-broken by II count). Sensitivity analysis and monitoring priorities accompany every conclusion.

## VERIFICATION CRITERIA

Verified means: at least 3 hypotheses in play, including at least one analyst-generated; at least 3 evidence items with credibility/relevance ratings; every (evidence × hypothesis) cell populated with Heuer vocabulary; at least one diagnostic row (cells not all equal); the surviving hypothesis named in prose has the fewest I+II cells in the matrix (tie-broken by II); at least one high-diagnosticity item explicitly named; sensitivity analysis names at least one evidence item whose reversal would change the ranking; deception check addressed when adversarial actors are plausible; monitoring priorities listed. The five critical questions are addressable from the output.
