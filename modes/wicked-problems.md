---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Wicked Problems

```yaml
# 0. IDENTITY
mode_id: wicked-problems
canonical_name: Wicked Problems
suffix_rule: analysis
educational_name: integrated multi-perspective analysis of tangled problems (wicked problems analysis, Rittel-Webber lineage)

# 1. TERRITORY AND POSITION
territory: T2-interest-and-power
gradation_position:
  axis: complexity
  value: systemic
  depth_axis_value: molecular
adjacent_modes_in_territory:
  - mode_id: cui-bono
    relationship: complexity-lighter sibling (simple)
  - mode_id: stakeholder-mapping
    relationship: complexity-mid sibling (multi-party-descriptive — note: lives in T8)
  - mode_id: decision-clarity
    relationship: depth-molecular sibling (decision-maker-output operation; built Wave 4)
  - mode_id: boundary-critique
    relationship: stance counterpart (critical/Ulrich CSH)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "this feels tangled"
    - "every solution we try makes it worse somewhere else"
    - "the problem itself keeps shifting as we try to define it"
    - "stakeholders disagree about what the problem even is"
  prompt_shape_signals:
    - "wicked problem"
    - "everything is connected"
    - "no clean solution"
    - "tradeoffs across multiple dimensions"
disambiguation_routing:
  routes_to_this_mode_when:
    - "tangled / wicked, want full integrated analysis with stakeholder + systems + scenario + adversarial views"
    - "willing to spend 10+ minutes for the deep version"
  routes_away_when:
    - "this one situation, who benefits" → cui-bono
    - "landscape of parties, descriptive" → stakeholder-mapping
    - "produce a decision document for a decision-maker" → decision-clarity
    - "want feedback dynamics analysis specifically" → systems-dynamics-causal
when_not_to_invoke:
  - "User has time pressure (Wicked Problems is Tier-3 ~10+ min)" → cui-bono or wicked-future light variant
  - "Problem is decision-shaped (single decision-maker, defined options)" → decision-clarity or decision-architecture

# 3. EXECUTION STRUCTURE
composition: molecular
molecular_spec:
  components:
    - mode_id: competing-hypotheses
      runs: fragment
      fragment_spec: "hypothesis-list-with-diagnosticity-only (matrix output, no full ACH report)"
    - mode_id: cui-bono
      runs: full
    - mode_id: steelman-construction
      runs: fragment
      fragment_spec: "steelman of two leading framings of the problem"
    - mode_id: systems-dynamics-causal
      runs: full
    - mode_id: scenario-planning
      runs: full
    - mode_id: red-team-assessment
      runs: fragment
      fragment_spec: "adversarial-stress-test of the leading intervention candidate (assessment stance — vulnerabilities ranked by severity for the user's own intervention-design fix-prioritisation)"
  synthesis_stages:
    - name: framing-reconciliation
      type: dialectical-resolution
      input: [competing-hypotheses-fragment, steelman-construction-fragment, cui-bono]
      output: "reconciled framing with named tensions and dominant-frame note"
    - name: dynamic-projection
      type: sequenced-build
      input: [framing-reconciliation, systems-dynamics-causal, scenario-planning]
      output: "dynamic projection of the problem under multiple framings and scenarios"
    - name: intervention-stress-test
      type: contradiction-surfacing
      input: [dynamic-projection, red-team-fragment]
      output: "candidate-intervention catalog with stress-test findings"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence findings

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [problem_statement, stakeholder_inventory, prior_intervention_history]
    optional: [domain_briefing, prior_systems_analyses]
    notes: "Applies when user supplies stakeholder inventory or prior analyses."
  accessible_mode:
    required: [problem_description]
    optional: [contextual_background]
    notes: "Default. Mode elicits stakeholder inventory and prior interventions during execution."
  detection:
    expert_signals: ["stakeholder inventory", "prior interventions", "intervention history"]
    accessible_signals: ["this is wicked", "everything is connected", "solutions keep failing"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the problem and any history of attempts to address it?'"
    on_underspecified: "Ask the user whether they want to spend the time on a full Wicked Problems pass, or a lighter Cui Bono / Stakeholder Mapping read."
output_contract:
  artifact_type: synthesis
  required_sections:
    - reconciled_framing
    - dynamic_projection
    - candidate_intervention_catalog
    - stress_test_findings
    - residual_tensions
    - confidence_map
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have all major framings been steelmanned, or has the analysis privileged one frame?"
    failure_mode_if_unmet: frame-privileging
  - cq_id: CQ2
    question: "Do the systems-dynamics findings actually integrate with the cui-bono findings, or do they sit in separate silos?"
    failure_mode_if_unmet: silo-aggregation
  - cq_id: CQ3
    question: "Have candidate interventions been stress-tested against the leading adversarial scenarios, or only against neutral projections?"
    failure_mode_if_unmet: stress-test-omission
  - cq_id: CQ4
    question: "Are the residual tensions named explicitly, or has the synthesis collapsed them prematurely?"
    failure_mode_if_unmet: premature-resolution

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: frame-privileging
    detection_signal: "Steelman-construction-fragment surfaces only one framing."
    correction_protocol: re-dispatch (to second steelman pass)
  - name: silo-aggregation
    detection_signal: "Synthesis stage outputs concatenate component outputs without integration."
    correction_protocol: re-dispatch (synthesis stage with explicit integration prompt)
  - name: stress-test-omission
    detection_signal: "red-team-fragment did not run against the leading intervention."
    correction_protocol: flag and re-dispatch
  - name: premature-resolution
    detection_signal: "Output presents a single recommended intervention without residual tensions."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - rittel-webber-wicked-characteristics
    - meadows-twelve-leverage-points
    - senge-system-archetypes
  optional:
    - ulrich-csh-boundary-categories
    - tetlock-superforecasting (when scenarios extend beyond ~5 years)
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Wicked Problems is the heaviest mode in T2's complexity ladder."
  sideways:
    target_mode_id: decision-clarity
    when: "Output should be a decision-clarity document for a decision-maker rather than an integrated analysis."
  downward:
    target_mode_id: cui-bono
    when: "User has time pressure or scope is narrower than initially estimated."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Wicked Problems Analysis is the degree to which framing-reconciliation, dynamic-projection, and intervention-stress-test stages actually integrate their component outputs rather than concatenating them. A thin molecular pass runs each component and aggregates; a substantive pass surfaces the tensions between components and resolves them dialectically. Test depth by asking: does the synthesis output contain claims that no single component could have produced?

## BREADTH ANALYSIS GUIDANCE

Breadth in Wicked Problems Analysis is the catalog of framings considered before the steelman fragment narrows to two leading framings. Widen the lens to scan: dominant-paradigm framing; stakeholder-position framing; historical-genealogy framing; cross-domain analogical framing. Even when only two framings are steelmanned, breadth is documented in the framing-reconciliation stage.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Wicked Problems output integrates components rather than concatenating, surfaces residual tensions explicitly, and assigns confidence per major finding (especially in the synthesis stages, which inherit lower confidence from component aggregation).

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to surface residual tensions where the draft has resolved them. Resist revising toward clean-recommendation framing — Wicked Problems Analysis honors irresolvability; collapsing tensions is a failure mode, not a polish.

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the six required sections. Each section carries provenance to its component sources. The confidence map at the end is structured (per-finding confidence with reason).

## VERIFICATION CRITERIA

Verified means: every component ran (or was flagged as proceeded-with-gap); synthesis stages integrated rather than concatenated; residual tensions are named; confidence map is populated. The four critical questions are addressed in the output.

## CAVEATS AND OPEN DEBATES

**Debate D3 — Wicked problems: sui generis or extreme cases of complex problems?** Rittel & Webber (1973) treat wickedness as intrinsic and distinct from ordinary complexity. Later scholarship (Pesch & Vermaas 2020; some complexity-science readings) treats wicked problems as extreme cases along the complexity gradient rather than as a separate category. This mode operates without adjudicating the debate: it applies the Rittel-Webber characteristics as analytical lens (treating "wickedness" as a useful descriptor for problems exhibiting the ten characteristics) while remaining agnostic on whether wickedness is a category or a degree. Citations: Rittel & Webber 1973; Pesch & Vermaas 2020; Conklin 2006 (*Dialogue Mapping*).
