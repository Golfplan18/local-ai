---
nexus:
  - ora
type: mode
tags:
date created: 2026-04-17
date modified: 2026-05-01
---

# MODE: Benefits Analysis

```yaml
# 0. IDENTITY
mode_id: benefits-analysis
canonical_name: Benefits Analysis
suffix_rule: analysis
educational_name: balanced benefits-and-strengths analysis (PMI — plus, minus, interesting)

# 1. TERRITORY AND POSITION
territory: T15-artifact-evaluation-by-stance
gradation_position:
  axis: stance
  value: constructive-balanced
adjacent_modes_in_territory:
  - mode_id: steelman-construction
    relationship: stance counterpart (constructive-strong, single position only)
  - mode_id: balanced-critique
    relationship: stance counterpart (neutral, no constructive lean)
  - mode_id: red-team-assessment
    relationship: stance counterpart (adversarial-actor-modeling, assessment)
  - mode_id: red-team-advocate
    relationship: stance counterpart (adversarial-actor-modeling, advocate)
  - mode_id: devils-advocate-lite
    relationship: stance counterpart (adversarial-light, deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "have a proposal and want the full picture before deciding"
    - "looking for benefits and risks of one option, not comparing alternatives"
    - "want non-obvious implications surfaced"
  prompt_shape_signals:
    - "what are the benefits and risks of"
    - "pros and cons of"
    - "PMI for"
    - "plus / minus / interesting"
    - "evaluate this proposal"
    - "what's the full picture on"
disambiguation_routing:
  routes_to_this_mode_when:
    - "one proposal, three columns (Plus / Minus / Interesting)"
    - "wants balanced evaluation without recommendation by default"
  routes_away_when:
    - "comparing multiple options" → constraint-mapping (T3)
    - "wants the strongest version of the proposal" → steelman-construction (T15)
    - "wants the adversarial actor stress test for own decision" → red-team-assessment (T15)
    - "wants adversarial argument brief for external use" → red-team-advocate (T15)
    - "wants forward causal cascades over time" → consequences-and-sequel (T6)
when_not_to_invoke:
  - "User wants to choose between alternatives — Benefits Analysis evaluates a single proposal"
  - "User wants a verdict — Benefits Analysis presents the envelope; user decides"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: constructive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [proposal_stated_precisely, stated_goal_proposal_advances, affected_party_inventory]
    optional: [implementation_history, similar_proposal_outcomes]
    notes: "Applies when user supplies precise proposal text and identifies affected parties."
  accessible_mode:
    required: [proposal_described]
    optional: [context_or_motivation]
    notes: "Default. Mode infers affected parties from the proposal description."
  detection:
    expert_signals: ["affected parties", "stakeholders include", "stated goal is"]
    accessible_signals: ["thinking about doing X", "considering this", "wondering if I should"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the specific proposal you want me to evaluate? More detail makes the analysis more useful.'"
    on_underspecified: "Ask: 'Are you weighing this single proposal, or comparing it against alternatives? Single proposal = Benefits Analysis; alternatives = Constraint Mapping.'"
output_contract:
  artifact_type: synthesis
  required_sections:
    - proposal_stated_precisely
    - plus_column
    - minus_column
    - interesting_column
    - affected_parties_map
    - evidence_quality_note
    - most_consequential_per_column
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are all three PMI columns populated, or has the analysis collapsed into Plus/Minus only?"
    failure_mode_if_unmet: two-column-trap
  - cq_id: CQ2
    question: "Are claims grounded in the user's specific case, or generic boilerplate?"
    failure_mode_if_unmet: boilerplate-trap
  - cq_id: CQ3
    question: "Has the Interesting column captured at least one second-order implication (precedent, signaling, path-dependency) — or explicitly noted that none was identified?"
    failure_mode_if_unmet: second-order-omission
  - cq_id: CQ4
    question: "Have asymmetries (Plus for one party, Minus for another) been surfaced via the affected-parties map?"
    failure_mode_if_unmet: single-perspective-trap
  - cq_id: CQ5
    question: "Has the analysis avoided unsolicited recommendation — presenting the envelope rather than rendering a verdict?"
    failure_mode_if_unmet: verdict-trap

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: two-column-trap
    detection_signal: "Plus and Minus populated; Interesting column empty without explicit 'none identified' statement."
    correction_protocol: re-dispatch (audit for second-order implications and populate or explicitly mark empty)
  - name: boilerplate-trap
    detection_signal: "Claims read as generic — could apply to any proposal of this type."
    correction_protocol: re-dispatch (rewrite each claim with specifics from user's case)
  - name: single-perspective-trap
    detection_signal: "All claims viewed from one party's perspective; affected-parties map missing or single-row."
    correction_protocol: re-dispatch (map affected parties; surface asymmetries)
  - name: verdict-trap
    detection_signal: "Output recommends adoption (or rejection) when user did not ask for a lean."
    correction_protocol: flag (remove recommendation; BA produces envelope, not verdict)
  - name: false-symmetry-trap
    detection_signal: "Equal pros and cons presented for appearance of balance, not honest distribution."
    correction_protocol: flag (report honest distribution explicitly)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - debono-pmi
  optional:
    - stakeholder-incidence-analysis
    - second-order-effects-catalog (precedent / signaling / path-dependency)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: red-team-assessment
    when: "Stress-testing under adversarial-actor framing is needed beyond balanced-constructive evaluation; assessment stance for own decision (default), or red-team-advocate when the user needs a brief for external use."
  sideways:
    target_mode_id: balanced-critique
    when: "User wants neutral evaluation with no constructive lean rather than balanced-constructive."
  downward:
    target_mode_id: null
    when: "Benefits Analysis is one of T15's lighter evaluation stances."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Benefits Analysis is the specificity and mechanism-grounding of each column item. A thin pass produces generic claims ("improved efficiency", "potential risks"); a substantive pass names mechanism per claim (the literal phrase "mechanism:" anchors each Plus). Test depth by asking: could the same Plus or Minus apply to a different proposal? If yes, the claim is generic. The Interesting column carries particular depth weight — second-order items (precedent, signaling, path-dependency) are where motivated-optimism analysis typically underperforms.

## BREADTH ANALYSIS GUIDANCE

Breadth in Benefits Analysis is the survey of affected parties before settling on the asymmetries to surface. Widen the lens to scan: parties who benefit if the proposal succeeds; parties who pay costs; parties whose interests are unaffected but whose narrative is changed; parties whose absence from the analysis itself constitutes an asymmetry. Breadth markers: the affected-parties map has at least three rows; the Interesting column captures non-obvious implications; the analysis identifies at least one item that is Plus for one party and Minus for another.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ5. The named failure modes are the evaluation checklist. A passing Benefits Analysis output (a) populates all three PMI columns or explicitly marks an empty column; (b) grounds each claim in the user's specifics; (c) names ≥ 1 second-order implication; (d) maps affected parties and surfaces ≥ 1 asymmetry; (e) does NOT recommend unless the user asked for a lean. The Verdict Trap is the load-bearing failure mode for this stance — unsolicited recommendation invalidates the mode's contribution.

## REVISION GUIDANCE

Revise to add specificity where claims are generic. Revise to populate the Interesting column where second-order items are missing. Revise to remove recommendation language where the user did not ask for a lean. Resist revising toward false symmetry — if the honest distribution is 1 Plus and 5 Minus, say so rather than padding. Resist revising toward verdict — Benefits Analysis presents the envelope; the user decides.

## CONSOLIDATION GUIDANCE

Consolidate as a structured three-column output (Plus / Minus / Interesting) with the affected-parties map, evidence-quality note, and most-consequential-per-column annotations. The proposal is stated precisely at the top. Recommendation field is empty by default; populated only if the user asked for a lean. Format is structured (matrix-friendly when columns lend themselves to tabular presentation).

## VERIFICATION CRITERIA

Verified means: proposal stated precisely; all three columns populated (or explicit "none identified" statement); each claim grounded in user's specifics; ≥ 1 second-order implication named; affected-parties map present; ≥ 1 asymmetry surfaced; no unsolicited recommendation. The five critical questions are addressed. Silent injection of a recommendation during revision is a verification failure.
