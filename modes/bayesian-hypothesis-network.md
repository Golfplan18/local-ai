---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Bayesian Hypothesis Network

```yaml
# 0. IDENTITY
mode_id: bayesian-hypothesis-network
canonical_name: Bayesian Hypothesis Network
suffix_rule: analysis
educational_name: Bayesian hypothesis network (probabilistic posterior over competing explanations)

# 1. TERRITORY AND POSITION
territory: T5-hypothesis-evaluation
gradation_position:
  axis: depth
  value: molecular
adjacent_modes_in_territory:
  - mode_id: differential-diagnosis
    relationship: depth-light sibling (medical-tradition triage)
  - mode_id: competing-hypotheses
    relationship: depth-thorough sibling (Heuer ACH)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want a probabilistic read on competing explanations, not just a ranked list"
    - "the hypotheses depend on each other and I need to see how priors propagate"
    - "willing to spend the time to set up priors and update with evidence properly"
    - "I want a network view, not a flat matrix"
  prompt_shape_signals:
    - "Bayesian network"
    - "posterior probability"
    - "prior and likelihood"
    - "probabilistic hypothesis"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants probability distribution over hypotheses with explicit priors and evidential updates"
    - "hypotheses are interdependent (one's truth affects another's prior)"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "want quick triage among 3-5 explanations" → differential-diagnosis
    - "want full ACH matrix without Bayesian formalism" → competing-hypotheses
    - "the disagreement is really about frame, not within-frame hypothesis weighing" → frame-comparison or worldview-cartography
when_not_to_invoke:
  - "User has no priors and no evidence-likelihood intuitions to anchor" → competing-hypotheses (qualitative ACH)
  - "Hypotheses are arguments-as-artifacts to audit" → T1 (argument-audit)

# 3. EXECUTION STRUCTURE
composition: molecular
molecular_spec:
  components:
    - mode_id: differential-diagnosis
      runs: fragment
      fragment_spec: "hypothesis-list-only — produce the candidate hypothesis set without ranking or full triage; serves as breadth seed for the Bayesian network"
    - mode_id: competing-hypotheses
      runs: full
  synthesis_stages:
    - name: prior-elicitation
      type: parallel-merge
      input: [differential-diagnosis-fragment, competing-hypotheses]
      output: "consolidated hypothesis set with elicited prior probabilities per hypothesis (and noted base-rate sources)"
    - name: bayesian-network-construction
      type: sequenced-build
      input: [prior-elicitation, competing-hypotheses]
      output: "Bayesian hypothesis network: hypotheses as nodes with priors; evidence-items as nodes with likelihoods; conditional dependencies between hypotheses named explicitly"
    - name: posterior-update
      type: dialectical-resolution
      input: [bayesian-network-construction]
      output: "posterior probability distribution over hypotheses after evidence integration; sensitivity analysis identifying which evidence items most shift the posterior"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected stage; if priors cannot be elicited with confidence, document as flat-prior assumption rather than fabricating point estimates

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [hypothesis_set, evidence_inventory, prior_estimates]
    optional: [base_rate_sources, conditional_dependency_map]
    notes: "Applies when user supplies hypotheses with prior estimates."
  accessible_mode:
    required: [phenomenon_or_question]
    optional: [evidence_observations, candidate_explanations]
    notes: "Default. Mode elicits hypotheses, evidence, and priors during execution."
  detection:
    expert_signals: ["prior probability", "likelihood", "base rate", "P(H)", "P(E|H)"]
    accessible_signals: ["competing explanations", "what's the most likely"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the phenomenon you're trying to explain, and what candidate explanations are on the table?'"
    on_underspecified: "Ask the user whether they want the full Bayesian network pass or a lighter ACH matrix (competing-hypotheses)."
output_contract:
  artifact_type: synthesis
  required_sections:
    - hypothesis_set_with_priors
    - evidence_inventory_with_likelihoods
    - conditional_dependencies
    - bayesian_network_diagram_or_table
    - posterior_distribution
    - sensitivity_analysis
    - leading_hypothesis_with_residual_uncertainty
    - confidence_map
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have priors been elicited from base rates or domain knowledge, or are they fabricated point estimates?"
    failure_mode_if_unmet: prior-fabrication
  - cq_id: CQ2
    question: "Have conditional dependencies among hypotheses been surfaced, or has the network treated all hypotheses as independent?"
    failure_mode_if_unmet: independence-assumption-collapse
  - cq_id: CQ3
    question: "Has sensitivity analysis identified which evidence items most shift the posterior, or does the output present a single posterior without robustness check?"
    failure_mode_if_unmet: sensitivity-omission
  - cq_id: CQ4
    question: "Are the hypotheses mutually exclusive and collectively exhaustive (or is non-MECE structure explicitly named)?"
    failure_mode_if_unmet: mece-violation-unnamed

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: prior-fabrication
    detection_signal: "Priors are stated as round numbers (0.5, 0.33) without base-rate or domain-knowledge anchor."
    correction_protocol: re-dispatch (with explicit base-rate-elicitation prompt) or flag and convert to flat-prior assumption
  - name: independence-assumption-collapse
    detection_signal: "Network has no conditional-dependency arcs even when hypotheses share underlying mechanism."
    correction_protocol: re-dispatch
  - name: sensitivity-omission
    detection_signal: "Posterior reported without indication of which evidence items dominate the update."
    correction_protocol: flag and re-dispatch
  - name: mece-violation-unnamed
    detection_signal: "Hypotheses overlap or do not exhaust the space, and this is not flagged in the output."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - heuer-ach-diagnosticity
  optional:
    - pearl-do-calculus (when network has causal interpretation)
    - tetlock-superforecasting (when long-horizon hypotheses)
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Bayesian Hypothesis Network is the heaviest mode in T5."
  sideways:
    target_mode_id: null
    when: "No within-T5 stance/complexity sibling beyond depth ladder."
  downward:
    target_mode_id: competing-hypotheses
    when: "User has time pressure or priors cannot be elicited; full ACH matrix substitutes."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Bayesian Hypothesis Network is the degree to which the prior-elicitation, network-construction, and posterior-update stages produce a probabilistic structure that no single component could have produced. A thin molecular pass extends ACH with point-estimate priors and reports a posterior; a substantive pass elicits priors from base rates, surfaces conditional dependencies among hypotheses, and runs sensitivity analysis identifying which evidence items dominate. Test depth by asking: would the analysis predict differently if a single key evidence item were removed?

## BREADTH ANALYSIS GUIDANCE

Breadth in Bayesian Hypothesis Network is the catalog of hypotheses considered before the network narrows. The differential-diagnosis fragment serves as breadth seed: enumerate widely (including unlikely-but-possible explanations) before pruning. Widen the lens to scan: dominant-narrative hypothesis; orthogonal hypothesis (different mechanism); null hypothesis (no underlying cause, observations are noise); cross-domain analogical hypothesis. Even when the network narrows to 3–5 hypotheses for the formalism, breadth is documented in the hypothesis-set section.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing output anchors priors in base rates or named domain knowledge, surfaces conditional dependencies (or names independence as an explicit assumption), reports a posterior with sensitivity analysis, and flags MECE violations rather than papering over them.

## REVISION GUIDANCE

Revise to anchor priors more rigorously where they appear fabricated. Revise to add conditional-dependency arcs where hypotheses share mechanism. Revise to add sensitivity analysis where the posterior is reported without robustness check. Resist revising toward false precision — when priors and likelihoods are genuinely uncertain, the output should report posterior as a distribution-with-confidence rather than a single number.

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the eight required sections. The Bayesian-network-diagram-or-table section is rendered as a structured table (hypothesis nodes, evidence nodes, conditional arcs) or, when complex, a diagram-friendly description. Provenance: hypothesis set carries differential-diagnosis fragment provenance; ACH matrix carries competing-hypotheses provenance; posterior carries Bayesian-update provenance.

## VERIFICATION CRITERIA

Verified means: every component ran (or was flagged as proceeded-with-gap); priors are anchored or flat-prior assumption is explicit; conditional dependencies are surfaced or independence is named; sensitivity analysis identifies dominant evidence; MECE structure is checked. The four critical questions are addressed in the output.
