---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Decision Architecture

```yaml
# 0. IDENTITY
mode_id: decision-architecture
canonical_name: Decision Architecture
suffix_rule: analysis
educational_name: decision architecture (integrated decision analysis with stakeholders + risk + alternatives)

# 1. TERRITORY AND POSITION
territory: T3-decision-making-under-uncertainty
gradation_position:
  axis: depth
  value: molecular
adjacent_modes_in_territory:
  - mode_id: constraint-mapping
    relationship: depth-light sibling (deterministic constraint pass)
  - mode_id: decision-under-uncertainty
    relationship: depth-thorough sibling (probability-and-time-weighted)
  - mode_id: multi-criteria-decision
    relationship: complexity sibling (multi-criteria weighting)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "this is a big decision and I want the full treatment"
    - "I need to think through this with stakeholders, constraints, and what could go wrong"
    - "the decision is real and I want a structured architecture, not just a recommendation"
    - "willing to spend the time to do this properly"
  prompt_shape_signals:
    - "decision architecture"
    - "full decision analysis"
    - "should I do X or Y, taking everything into account"
    - "structured decision document"
disambiguation_routing:
  routes_to_this_mode_when:
    - "decision is high-stakes; user wants integrated architecture spanning constraints + uncertainty + stakeholders + failure modes"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "decision is constraint-bounded only (no uncertainty)" → constraint-mapping
    - "decision is probability-weighted but stakeholder-light" → decision-under-uncertainty
    - "decision is multi-criteria with clean criteria weights" → multi-criteria-decision
    - "the decision is really stakeholder-conflict at heart, not your-decision-with-inputs" → stakeholder-mapping or T8 modes
when_not_to_invoke:
  - "User has time pressure (Decision Architecture is Tier-3 ~10+ min)" → decision-under-uncertainty or constraint-mapping
  - "Decision is genuinely simple (one constraint dominates)" → constraint-mapping
  - "User is producing a decision document for a third-party decision-maker, not making a decision themselves" → decision-clarity

# 3. EXECUTION STRUCTURE
composition: molecular
molecular_spec:
  components:
    - mode_id: decision-under-uncertainty
      runs: full
    - mode_id: constraint-mapping
      runs: full
    - mode_id: stakeholder-mapping
      runs: full
    - mode_id: pre-mortem-action
      runs: full
  synthesis_stages:
    - name: decision-frame-integration
      type: parallel-merge
      input: [decision-under-uncertainty, constraint-mapping]
      output: "integrated decision frame: alternatives × probability-weighted outcomes × binding constraints"
    - name: stakeholder-impact-overlay
      type: sequenced-build
      input: [decision-frame-integration, stakeholder-mapping]
      output: "decision frame with per-alternative stakeholder-impact mapping and identified power-asymmetries"
    - name: failure-mode-stress-test
      type: contradiction-surfacing
      input: [stakeholder-impact-overlay, pre-mortem-action]
      output: "leading alternatives stress-tested against pre-mortem failure pathways; revised alternative ranking"
    - name: integrated-decision-architecture
      type: dialectical-resolution
      input: [decision-frame-integration, stakeholder-impact-overlay, failure-mode-stress-test]
      output: "single integrated decision architecture document with recommendation, residual risks, and decision-conditions-to-monitor"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence stakeholder or pre-mortem findings

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [decision_statement, alternatives, criteria, stakeholder_inventory]
    optional: [constraint_inventory, prior_decisions, risk_history]
    notes: "Applies when user supplies alternatives plus stakeholder inventory."
  accessible_mode:
    required: [decision_description]
    optional: [contextual_background, time_pressure_indicator]
    notes: "Default. Mode elicits alternatives, criteria, and stakeholder inventory during execution."
  detection:
    expert_signals: ["alternatives are A, B, C", "stakeholders include", "constraints are", "criteria"]
    accessible_signals: ["big decision", "should I do X", "thinking through this"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the decision, and what are the alternatives you're choosing among?'"
    on_underspecified: "Ask the user whether they want the full Decision Architecture pass or a lighter Decision Under Uncertainty / Constraint Mapping read."
output_contract:
  artifact_type: synthesis
  required_sections:
    - decision_frame
    - alternatives_with_probability_weighted_outcomes
    - binding_constraints
    - stakeholder_impact_per_alternative
    - failure_mode_stress_test_findings
    - recommended_alternative_with_residual_risks
    - decision_conditions_to_monitor
    - confidence_map
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have the alternatives been generated broadly enough, or is the analysis evaluating an artificially narrow option set?"
    failure_mode_if_unmet: option-set-poverty
  - cq_id: CQ2
    question: "Do the constraint findings actually bound the alternatives, or do they sit in a separate silo from the probability-weighted outcomes?"
    failure_mode_if_unmet: silo-aggregation
  - cq_id: CQ3
    question: "Are the stakeholder impacts surfaced per alternative, or aggregated into a generic stakeholder list disconnected from choice?"
    failure_mode_if_unmet: stakeholder-disconnection
  - cq_id: CQ4
    question: "Has the leading alternative been pre-mortem-stress-tested, or has the synthesis presented a recommendation without naming failure pathways?"
    failure_mode_if_unmet: pre-mortem-omission
  - cq_id: CQ5
    question: "Are the decision-conditions-to-monitor concrete enough to detect drift, or vague enough to be unfalsifiable?"
    failure_mode_if_unmet: monitoring-vagueness

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: option-set-poverty
    detection_signal: "Alternatives enumerated are fewer than three or are obvious binary; no creative or boundary alternative considered."
    correction_protocol: re-dispatch (with explicit alternative-generation prompt)
  - name: silo-aggregation
    detection_signal: "Synthesis stages concatenate constraint, decision-under-uncertainty, stakeholder, and pre-mortem outputs without integration."
    correction_protocol: re-dispatch (synthesis stage with explicit integration prompt)
  - name: stakeholder-disconnection
    detection_signal: "Stakeholder impacts are listed once for the situation generally rather than mapped per alternative."
    correction_protocol: re-dispatch
  - name: pre-mortem-omission
    detection_signal: "pre-mortem-action did not run against the leading alternative."
    correction_protocol: flag and re-dispatch
  - name: monitoring-vagueness
    detection_signal: "Decision-conditions-to-monitor are stated as 'watch how things develop' or similar without concrete signals."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - kahneman-tversky-bias-catalog (when decision is intuition-heavy)
    - knightian-risk-uncertainty-ambiguity (when uncertainty regime is ambiguous)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Decision Architecture is the heaviest mode in T3."
  sideways:
    target_mode_id: decision-clarity
    when: "Output should be a decision-clarity document for a third-party decision-maker rather than your own integrated decision."
  downward:
    target_mode_id: decision-under-uncertainty
    when: "User has time pressure or scope is narrower than initially estimated."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Decision Architecture is the degree to which the four synthesis stages actually integrate component outputs rather than concatenating them. A thin molecular pass runs decision-under-uncertainty, constraint-mapping, stakeholder-mapping, and pre-mortem-action and stitches their outputs together; a substantive pass surfaces tensions among them — for instance, a constraint that invalidates the probability-weighted leading option, or a stakeholder impact that flips the pre-mortem failure scenario. Test depth by asking: does the integrated architecture contain a recommendation that no single component could have produced?

## BREADTH ANALYSIS GUIDANCE

Breadth in Decision Architecture is the catalog of alternatives considered before the architecture narrows to a recommendation. Widen the lens to scan: status-quo alternative; obvious binary; creative third option; do-nothing; reverse-the-question; defer-and-monitor. Even when the recommendation lands on one alternative, breadth is documented in the alternatives section. Breadth also covers stakeholder enumeration: ensure the stakeholder-mapping fragment surveys absent voices, not just visible parties.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ5. The named failure modes are the evaluation checklist. A passing Decision Architecture output integrates components rather than concatenating, surfaces stakeholder impacts per alternative, names concrete failure pathways for the leading alternative, and specifies decision-conditions-to-monitor that are concrete enough to be falsifiable.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to surface tensions where the draft has resolved them prematurely (e.g., stakeholder impacts that quietly contradict the recommendation should be named, not smoothed over). Revise to add concrete monitoring conditions where the draft is vague. Resist revising toward clean-recommendation framing that omits residual risks — Decision Architecture honors residual uncertainty.

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the eight required sections. Each section carries provenance to its component sources (decision-under-uncertainty for probability-weighted outcomes; constraint-mapping for binding constraints; stakeholder-mapping for stakeholder impact; pre-mortem-action for failure pathways). The confidence map at the end is structured (per-finding confidence with reason), and decision-conditions-to-monitor are stated as observable signals.

## VERIFICATION CRITERIA

Verified means: every component ran (or was flagged as proceeded-with-gap); the four synthesis stages integrated rather than concatenated; the leading alternative carries a pre-mortem stress test; decision-conditions-to-monitor are concrete; confidence map is populated. The five critical questions are addressed in the output.
