---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Decision Clarity

```yaml
# 0. IDENTITY
mode_id: decision-clarity
canonical_name: Decision Clarity
suffix_rule: analysis
educational_name: decision clarity document (for decision-maker; cui-bono + stakeholder + scenario + red-team-assessment composition)

# 1. TERRITORY AND POSITION
territory: T2-interest-and-power
gradation_position:
  axis: depth
  value: molecular
adjacent_modes_in_territory:
  - mode_id: cui-bono
    relationship: complexity-lighter sibling (simple)
  - mode_id: boundary-critique
    relationship: stance counterpart (critical/Ulrich CSH)
  - mode_id: wicked-problems
    relationship: depth-molecular sibling (integrated multi-perspective analysis operation)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I need a decision document for a decision-maker, not an exploratory analysis"
    - "produce something the decision-maker can act on"
    - "give them clarity on who benefits, who's affected, what could happen, and what could go wrong"
    - "the deliverable is a decision-clarity document, not a wicked-problem map"
  prompt_shape_signals:
    - "decision clarity"
    - "decision document for"
    - "brief the decision-maker"
    - "executive decision brief"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user's deliverable is a decision document for a third-party decision-maker"
    - "user wants integrated cui-bono + stakeholder + scenario + adversarial-stress in a decision-shaped output"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "user is making the decision themselves with full alternatives + constraints + uncertainty" → decision-architecture
    - "user wants integrated wicked-problems analysis without decision-shape constraint" → wicked-problems
    - "want quick read on who benefits" → cui-bono
    - "want critical surfacing of marginalized voices" → boundary-critique
when_not_to_invoke:
  - "User has time pressure" → cui-bono or stakeholder-mapping
  - "There is no identified decision-maker; the deliverable is exploratory" → wicked-problems

# 3. EXECUTION STRUCTURE
composition: molecular
# NOTE: Decision H parse — Wicked Problems framework parsed into wicked-problems mode
# (integrated multi-perspective analysis) plus decision-clarity mode (decision-maker-output).
# Paired with restructured Framework — Decision Clarity Analysis.md (Phase 2).
molecular_spec:
  components:
    - mode_id: cui-bono
      runs: full
    - mode_id: stakeholder-mapping
      runs: full
    - mode_id: scenario-planning
      runs: fragment
      fragment_spec: "two-scenario-only — produce two contrasting scenarios (most-likely + most-adverse) sufficient for decision-maker context; do not produce full scenario-planning narrative set"
    - mode_id: red-team-assessment
      runs: fragment
      fragment_spec: "adversarial-stress-test of leading intervention only — adversarial-actor stress test against the leading recommended intervention candidate (assessment stance for the decision-maker's own benefit; advocate stance is not used in this composition because the synthesised document is decision-maker-facing, not external-audience-facing), not full red-team-assessment battery"
  synthesis_stages:
    - name: interest-and-stakeholder-merge
      type: parallel-merge
      input: [cui-bono, stakeholder-mapping]
      output: "merged interest-and-stakeholder picture: who benefits, who pays, who has power, who is absent, with per-stakeholder positions and concerns"
    - name: scenario-overlay
      type: sequenced-build
      input: [interest-and-stakeholder-merge, scenario-planning-fragment]
      output: "interest-and-stakeholder picture overlaid on the two scenarios: how does each scenario shift who benefits, who pays, and where power flows"
    - name: intervention-stress-test
      type: contradiction-surfacing
      input: [scenario-overlay, red-team-fragment]
      output: "leading intervention candidate stress-tested by red-team-fragment; surfaced adversarial dynamics that the cui-bono and scenario passes did not see"
    - name: decision-clarity-document
      type: dialectical-resolution
      input: [interest-and-stakeholder-merge, scenario-overlay, intervention-stress-test]
      output: "Decision Clarity Document for the decision-maker: situation framing, stakeholder map, scenario range, recommended intervention with stress-test findings, residual risks, and decision-maker-actionable recommendations"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence stakeholder or red-team findings; if scenario fragment cannot produce contrasting scenarios, document as one-scenario assumption

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [decision_maker_identity, decision_at_hand, stakeholder_inventory, intervention_candidates]
    optional: [prior_decisions, organizational_context]
    notes: "Applies when user supplies decision-maker identity plus intervention candidates."
  accessible_mode:
    required: [decision_at_hand, decision_maker_identity]
    optional: [contextual_background]
    notes: "Default. Mode elicits stakeholder inventory and intervention candidates during execution."
  detection:
    expert_signals: ["brief the", "decision-maker is", "stakeholders include", "intervention options"]
    accessible_signals: ["decision document", "give them clarity", "for the executive"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Who is the decision-maker, and what's the decision they need clarity on?'"
    on_underspecified: "Ask the user whether they want the full Decision Clarity molecular pass or a lighter Cui Bono / Stakeholder Mapping read."
output_contract:
  artifact_type: synthesis
  required_sections:
    - decision_at_hand
    - decision_maker_context
    - stakeholder_map_with_positions
    - interest_and_power_summary
    - scenario_range
    - leading_intervention_recommendation
    - stress_test_findings
    - residual_risks_and_decision_conditions
    - decision_maker_actionable_recommendations
    - confidence_map
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Does the document address the actual decision-maker's context (what they can do, what they cannot), or does it present generic analysis?"
    failure_mode_if_unmet: decision-maker-disconnection
  - cq_id: CQ2
    question: "Are stakeholder positions surfaced with concrete interests and concerns, or have they been collapsed into generic categories?"
    failure_mode_if_unmet: stakeholder-collapse
  - cq_id: CQ3
    question: "Has the leading intervention been stress-tested by the red-team fragment, or has the recommendation been presented without adversarial pressure?"
    failure_mode_if_unmet: stress-test-omission
  - cq_id: CQ4
    question: "Are the recommendations actionable by the named decision-maker, or do they exceed the decision-maker's authority or scope?"
    failure_mode_if_unmet: out-of-scope-recommendation
  - cq_id: CQ5
    question: "Are the two scenarios genuinely contrasting (most-likely + most-adverse), or are they variations of the same trajectory?"
    failure_mode_if_unmet: scenario-flattening

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: decision-maker-disconnection
    detection_signal: "Document is generic; no reference to the decision-maker's role, authority, or constraints."
    correction_protocol: re-dispatch (with explicit decision-maker-context prompt)
  - name: stakeholder-collapse
    detection_signal: "Stakeholders are listed in generic categories (e.g., 'employees', 'customers') without concrete interests or positions."
    correction_protocol: re-dispatch
  - name: stress-test-omission
    detection_signal: "red-team-fragment did not run against the leading intervention."
    correction_protocol: flag and re-dispatch
  - name: out-of-scope-recommendation
    detection_signal: "Recommendations require authority or scope the named decision-maker does not have."
    correction_protocol: flag and re-dispatch
  - name: scenario-flattening
    detection_signal: "Two scenarios differ only in degree, not in kind; both privilege the dominant trajectory."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - rumelt-strategy-kernel (when intervention is strategic)
    - ulrich-csh-boundary-categories (when boundary critique cross-cuts)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Decision Clarity is the heaviest mode in T2's depth ladder."
  sideways:
    target_mode_id: wicked-problems
    when: "Output should be integrated multi-perspective analysis rather than decision-clarity document."
  downward:
    target_mode_id: cui-bono
    when: "User has time pressure or scope is narrower than initially estimated."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Decision Clarity is the degree to which the four synthesis stages produce a decision-document that no single component could have produced. A thin molecular pass concatenates cui-bono + stakeholder + scenario + red-team outputs into a document; a substantive pass surfaces tensions — for instance, a stakeholder whose interests flip across scenarios, or a red-team adversarial dynamic that invalidates the leading intervention's interest-rationale. Test depth by asking: does the document contain decision-maker-actionable recommendations that no single component could have produced?

## BREADTH ANALYSIS GUIDANCE

Breadth in Decision Clarity is the catalog of stakeholders and intervention candidates considered before narrowing to the recommendation. Widen the lens to scan: visible stakeholders; absent stakeholders (boundary-critique territory); intervention status quo; intervention reversal; intervention defer-and-monitor. Even when the recommendation lands on one intervention, breadth is documented in the stakeholder-map-with-positions and intervention-recommendation sections. Note: alternative compositions considered included substituting full red-team for the fragment; current composition uses the fragment to keep the document decision-shaped rather than analysis-shaped.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ5. The named failure modes are the evaluation checklist. A passing Decision Clarity output addresses the named decision-maker's actual context, surfaces concrete stakeholder interests rather than generic categories, includes red-team stress-test against the leading intervention, and stays within the decision-maker's scope of authority.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to ground recommendations more concretely in the decision-maker's authority and constraints. Revise to add adversarial dynamics where the red-team fragment surfaces them. Resist revising toward exploratory framing — Decision Clarity is decision-shaped, not analysis-shaped; the document's purpose is to help the decision-maker act, not to map the territory exhaustively. (When the user wants exhaustive mapping, route to wicked-problems instead.)

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the ten required sections. The decision-maker-actionable-recommendations section is mandatory and concrete. Each section carries provenance to its component sources (cui-bono for interest pathways; stakeholder-mapping for positions; scenario-planning fragment for scenario range; red-team fragment for stress-test findings). Confidence map is per-finding. Document tone is decision-brief, not exploratory essay.

## VERIFICATION CRITERIA

Verified means: every component ran (or was flagged as proceeded-with-gap); the four synthesis stages integrated rather than concatenated; leading intervention carries red-team stress-test; recommendations are within the named decision-maker's scope; two scenarios are genuinely contrasting; confidence map is populated. The five critical questions are addressed in the output.
