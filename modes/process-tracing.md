---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Process Tracing

```yaml
# 0. IDENTITY
mode_id: process-tracing
canonical_name: Process Tracing
suffix_rule: analysis
educational_name: process tracing (Bennett-Checkel hoop / smoking-gun / doubly-decisive tests)

# 1. TERRITORY AND POSITION
territory: T4-causal-investigation
gradation_position:
  axis: specificity
  value: historical-event
  secondary_axis: depth
  secondary_value: thorough
adjacent_modes_in_territory:
  - mode_id: root-cause-analysis
    relationship: complexity-lighter sibling (single cause-chain, no evidence-test framework)
  - mode_id: systems-dynamics-causal
    relationship: complexity-counterpart (feedback structure rather than historical-event)
  - mode_id: causal-dag
    relationship: specificity-counterpart (general formal causal-graph rather than historical-event-specific)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I want to know what actually caused this specific historical event"
    - "I need to test competing causal explanations of a single case"
    - "I have evidence and want to know which causal story it actually supports"
    - "I want to assess the strength of causal evidence rigorously"
  prompt_shape_signals:
    - "process tracing"
    - "Bennett Checkel"
    - "smoking gun"
    - "hoop test"
    - "doubly decisive"
    - "straw in the wind"
    - "what really happened"
    - "trace the causal chain"
    - "case study causal inference"
disambiguation_routing:
  routes_to_this_mode_when:
    - "specific historical event or single case where evidence is available"
    - "user wants to evaluate competing causal hypotheses against observable evidence"
    - "user wants explicit evidence-test framework (necessary, sufficient, both, neither)"
    - "user wants causal certainty calibrated to the diagnostic strength of available evidence"
  routes_away_when:
    - "general causal structure, not tied to a specific historical event" → causal-dag
    - "system has ongoing feedback dynamics" → systems-dynamics-causal
    - "single cause-chain with no need for evidence-test calibration" → root-cause-analysis
    - "evaluating multiple hypotheses with formal Bayesian diagnosticity matrix" → competing-hypotheses (T5)
when_not_to_invoke:
  - "User wants to map how a process currently works" → T17
  - "User wants to forecast a future event" → T6 modes
  - "Question is about an argument's soundness, not a historical cause" → T1

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [historical_event_or_case, candidate_causal_hypotheses, evidence_inventory]
    optional: [hypothesis_priors, evidence_provenance_notes, prior_process-tracing_analyses]
    notes: "Applies when user supplies a structured case, named competing hypotheses, and an explicit evidence inventory."
  accessible_mode:
    required: [event_or_case_description]
    optional: [what_user_thinks_caused_it, available_evidence_sources]
    notes: "Default. Mode elicits competing hypotheses and evidence inventory during execution."
  detection:
    expert_signals: ["process tracing", "hoop test", "smoking gun", "doubly decisive", "straw in the wind", "Bennett", "Checkel"]
    accessible_signals: ["what really caused", "trace what happened", "what evidence supports", "case causal inference"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What event or case are you trying to explain, and what are the competing causal stories you want to test?'"
    on_underspecified: "Ask: 'What evidence do you have access to (documents, testimony, records, observations) that could discriminate between the hypotheses?'"
output_contract:
  artifact_type: synthesis
  required_sections:
    - case_and_question_locked
    - competing_hypotheses_inventory
    - evidence_inventory_with_provenance
    - test_classification_per_evidence_piece
    - hypothesis_status_after_tests
    - causal_chain_reconstruction
    - residual_uncertainty
    - confidence_per_finding
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have at least two genuinely competing causal hypotheses been named, or has the analysis privileged one explanation by failing to construct alternatives?"
    failure_mode_if_unmet: hypothesis-monoculture
  - cq_id: CQ2
    question: "Has each piece of evidence been classified by test type (hoop / smoking-gun / doubly-decisive / straw-in-the-wind), with the classification justified rather than asserted?"
    failure_mode_if_unmet: test-misclassification
  - cq_id: CQ3
    question: "Has the analysis updated each hypothesis's status appropriately given the test outcomes (failed-hoop eliminates, passed-smoking-gun strongly confirms, etc.), or has it overweighted weak evidence?"
    failure_mode_if_unmet: evidence-overreach
  - cq_id: CQ4
    question: "Has the provenance and reliability of each evidence piece been assessed, or has the analysis treated all sources as equally credible?"
    failure_mode_if_unmet: source-naivety
  - cq_id: CQ5
    question: "Has the causal chain been reconstructed in temporal sequence with explicit links, or have intermediate steps been elided?"
    failure_mode_if_unmet: chain-elision

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: hypothesis-monoculture
    detection_signal: "Only one causal hypothesis tested; no genuinely competing alternative considered."
    correction_protocol: re-dispatch
  - name: test-misclassification
    detection_signal: "Evidence treated as smoking-gun (sufficient) when its absence would not eliminate the hypothesis (only hoop), or vice versa."
    correction_protocol: re-dispatch
  - name: evidence-overreach
    detection_signal: "Hypothesis declared confirmed on straw-in-the-wind evidence, or eliminated on weak negative evidence."
    correction_protocol: flag
  - name: source-naivety
    detection_signal: "All evidence pieces treated as equally credible; no provenance assessment."
    correction_protocol: flag
  - name: chain-elision
    detection_signal: "Causal chain skips intermediate steps without justification (e.g., 'X led to Z' with Y unexplained)."
    correction_protocol: re-dispatch
  - name: presentism
    detection_signal: "Hypotheses constructed from present knowledge that actors at the time could not have held; counterfactual reasoning anachronistic."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - bennett-checkel-process-tracing-tests
    - pearl-causal-graphs
  optional:
    - pearl-do-calculus (when intervention or counterfactual reasoning is central)
    - tetlock-superforecasting (when evidence is partly forward-looking and probability matters)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Process Tracing is the heaviest specificity-historical mode in T4 at thorough tier; molecular escalation deferred."
  sideways:
    target_mode_id: causal-dag
    when: "Question generalizes beyond the specific historical event into structural causal reasoning."
  downward:
    target_mode_id: root-cause-analysis
    when: "Evidence is sparse or single-cause-chain suffices without formal test framework."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Process Tracing is the explicitness of (a) competing causal hypotheses constructed before evidence is considered, (b) per-evidence-piece test classification (hoop / smoking-gun / doubly-decisive / straw-in-the-wind), and (c) update of hypothesis status given test outcomes. A thin pass narrates what happened; a substantive pass names competing hypotheses, classifies each evidence piece by what its presence-or-absence would do to each hypothesis, applies the tests, updates hypothesis status, and reconstructs the causal chain in temporal sequence with explicit links. Test depth by asking: could a reader reproduce the verdict from the artifact, including which evidence pieces did the heavy lifting and which would have changed the conclusion if absent?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for additional plausible causal hypotheses (especially ones favored by different theoretical traditions or stakeholder perspectives), surfacing evidence the analyst lacks but could obtain, and noting which evidence-piece-not-yet-found would be doubly-decisive (eliminate one hypothesis and confirm another). Breadth markers: the analysis names at least three plausible hypotheses (even if only two are seriously tested), and identifies the most diagnostic evidence-piece that does not currently exist in the inventory.

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) competing hypotheses; (CQ2) test classification; (CQ3) appropriate updating; (CQ4) provenance assessment; (CQ5) causal chain reconstruction. The named failure modes (hypothesis-monoculture, test-misclassification, evidence-overreach, source-naivety, chain-elision, presentism) are the evaluation checklist. A passing Process Tracing output names competing hypotheses, classifies each evidence piece by test type with justification, updates hypothesis status appropriately, assesses source provenance, and reconstructs the causal chain with explicit intermediate links.

## REVISION GUIDANCE

Revise to add competing hypotheses where the draft tests only one. Revise to reclassify test types where the draft asserts smoking-gun status without checking sufficiency, or hoop status without checking necessity. Revise to downgrade conclusions where evidence overreach has occurred. Revise to add provenance notes where sources were treated as equally credible. Resist revising toward narrative coherence at the expense of test discipline — the mode's analytical character is calibrated evidence-driven inference, not satisfying storytelling. If sources are weak, the conclusion must reflect that weakness rather than smoothing it over.

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the eight required sections. The competing hypotheses appear as a labeled inventory. Evidence is presented as a structured table with provenance, test classification, and per-hypothesis implication. Hypothesis status appears as a post-test verdict (eliminated / weakly supported / strongly supported / confirmed) with the test outcomes that drove the verdict. The causal chain is reconstructed in temporal sequence with explicit links. Residual uncertainty names what evidence would change the conclusion. Confidence per finding accompanies each major claim.

## VERIFICATION CRITERIA

Verified means: at least two competing hypotheses were tested; each evidence piece is classified by test type with justification; hypothesis status reflects appropriate Bayesian updating given test outcomes; source provenance is assessed; the causal chain is reconstructed in temporal sequence with explicit intermediate links; residual uncertainty names diagnostic evidence not yet available. The five critical questions are addressable from the output. Confidence per finding accompanies every causal claim.
