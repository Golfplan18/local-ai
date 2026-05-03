---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
---

# MODE: Dialectical Analysis

```yaml
# 0. IDENTITY
mode_id: dialectical-analysis
canonical_name: Dialectical Analysis
suffix_rule: analysis
educational_name: thesis-antithesis dialectical analysis

# 1. TERRITORY AND POSITION
territory: T12-cross-domain-and-knowledge-synthesis
gradation_position:
  axis: stance
  value: thesis-antithesis
adjacent_modes_in_territory:
  - mode_id: synthesis
    relationship: stance counterpart (neutral integrative examination, not adversarial)
  - mode_id: cross-domain-analogical
    relationship: specificity variant (cross-domain analogical, deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "two positions in genuine opposition each with real merit"
    - "compromise feels like cop-out — something genuinely new must emerge"
    - "trapped in what looks like a false dichotomy"
    - "fundamental tension or contradiction in the question itself"
  prompt_shape_signals:
    - "thesis / antithesis"
    - "dialectical"
    - "sublate"
    - "drive through the contradiction"
    - "Hegelian"
disambiguation_routing:
  routes_to_this_mode_when:
    - "drives toward a new position via adversarial commitment to both sides"
    - "willing to hold the antithesis with genuine force, not as token objection"
  routes_away_when:
    - "wants neutral examination of tension without adversarial commitment" → synthesis
    - "wants to choose between alternatives" → constraint-mapping (T3)
    - "wants the strongest version of one position" → steelman-construction (T15)
    - "wants adversarial-actor stress test on a single artifact" → red-team-assessment / red-team-advocate (T15)
when_not_to_invoke:
  - "Positions do not generate each other internally — antithesis would be external critique, not dialectical negation"
  - "User wants integrative connection-mapping rather than adversarial drive" → synthesis

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: adversarial

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [thesis_position, sensed_tension, prior_dialectical_attempts]
    optional: [historical_genealogy, citations_to_dialectical_tradition]
    notes: "Applies when user references the dialectical tradition explicitly (Hegel/Adorno/Marx) or supplies a developed thesis."
  accessible_mode:
    required: [tension_or_opposition_described]
    optional: [user_position_within_tension]
    notes: "Default. Mode infers thesis structure from the user's description of the tension."
  detection:
    expert_signals: ["thesis", "antithesis", "sublation", "Aufheben", "dialectical"]
    accessible_signals: ["seems like a contradiction", "false dichotomy", "tension I can't resolve"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the position you'd start from, and what's the opposing position you sense pulling against it?'"
    on_underspecified: "Ask: 'Is this a tension between two positions each holding real merit, or are you weighing alternatives to choose between? The first invites Dialectical Analysis; the second invites Constraint Mapping.'"
output_contract:
  artifact_type: synthesis
  required_sections:
    - generating_question
    - thesis
    - internal_contradictions
    - antithesis
    - genuine_contradiction_or_irreducibility
    - sublation_or_irreducibility_declaration
    - recursion_acknowledgement
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Does the antithesis emerge from the thesis's own internal contradictions, or is it external critique?"
    failure_mode_if_unmet: weak-antithesis
  - cq_id: CQ2
    question: "Does the sublation transcend by mechanism, or does it average the two positions?"
    failure_mode_if_unmet: premature-synthesis
  - cq_id: CQ3
    question: "If no genuine sublation is available, has the analysis honored the irreducibility (Adornian escape valve) rather than forcing one?"
    failure_mode_if_unmet: forced-triad
  - cq_id: CQ4
    question: "Have the next-level contradictions the sublation generates been named explicitly?"
    failure_mode_if_unmet: recursion-omission

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: weak-antithesis
    detection_signal: "Antithesis is thesis with minor modifications, not genuine adversarial commitment."
    correction_protocol: re-dispatch (argue antithesis as if believed, emerging from thesis's contradictions)
  - name: premature-synthesis
    detection_signal: "Sublation averages positions ('do a little of both') rather than transcending."
    correction_protocol: re-dispatch (state mechanism by which sublation cancels false aspects while preserving true ones)
  - name: forced-triad
    detection_signal: "Analysis forces a sublation when the contradiction is genuinely irreducible."
    correction_protocol: flag (invoke Adornian escape valve and declare irreducibility)
  - name: teleological-construction
    detection_signal: "Antithesis appears constructed to arrive at a predetermined sublation."
    correction_protocol: re-dispatch (restart antithesis derivation from thesis's contradictions)
  - name: recursion-omission
    detection_signal: "Sublation presented as terminal without naming next-level contradictions it generates."
    correction_protocol: flag (add recursion paragraph)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - hegelian-dialectic-aufheben
  optional:
    - adornian-negative-dialectics (when irreducibility is in play)
    - marxist-historical-materialism (when material conditions structure the tension)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Dialectical Analysis is its own depth target in T12; deeper would shift mode."
  sideways:
    target_mode_id: synthesis
    when: "Positions do not generate each other internally; integrative neutral examination is correct rather than adversarial drive."
  downward:
    target_mode_id: null
    when: "T12 has no lighter sibling currently."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Dialectical Analysis is the strength of the antithesis's adversarial commitment and the genuineness of the sublation's transcendence. A thin pass produces an antithesis as token objection and a sublation as compromise. A substantive pass holds the antithesis with the literal commitment of "argued as if believed" and produces a sublation that names the mechanism by which it cancels what was false in each position while preserving what was true. Test depth by asking: would proponents of the original thesis recognize the antithesis as a serious challenge? Does the sublation generate new contradictions (it should) and have they been named?

## BREADTH ANALYSIS GUIDANCE

Breadth in Dialectical Analysis is the catalog of candidate antitheses considered before settling on the one that emerges most directly from the thesis's internal contradictions. Generate alternatives that arise from different internal contradictions in the thesis. Widen the lens to consider whether the apparent dialectic is in fact a Synthesis problem (positions do not generate each other) or a Constraint Mapping problem (alternatives to choose among). Breadth markers: the analysis tests at least one alternative antithesis derivation before locking the canonical one.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Dialectical Analysis output (a) names the generating question; (b) states the thesis with its claims to completeness; (c) surfaces internal contradictions in the thesis; (d) develops an antithesis with adversarial commitment, emerging from those contradictions; (e) either produces a sublation with transcending mechanism OR honors irreducibility per the Adornian escape valve; (f) names recursion (next-level contradictions) when sublation is offered.

## REVISION GUIDANCE

Revise to strengthen the antithesis where it reads as token. Revise to replace averaging language with transcending language in the sublation. Resist revising toward apparent resolution when the contradiction is genuinely irreducible — a forced sublation is worse than an honest standoff. Resist revising toward thesis-favorable framing — the antithesis must be argued with genuine force. If the sublation seems forced, invoke the Adornian escape valve explicitly rather than polishing a false synthesis.

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the seven required sections (six if Adornian irreducibility is invoked — sublation section becomes irreducibility-declaration). The thesis, antithesis, and sublation (when present) appear as peer positions, not as a thesis-with-modifications progression. Internal contradictions and recursion are named explicitly. The format is structured (IBIS-friendly when the dialectical structure is rendered as question/idea/pro/con).

## VERIFICATION CRITERIA

Verified means: thesis stated with claims to completeness; ≥ 1 internal contradiction named; antithesis developed with adversarial commitment from those contradictions; sublation with transcending mechanism OR explicit irreducibility declaration; recursion named when sublation is present. The four critical questions are addressed. Silent forcing of a sublation when irreducibility was the honest finding is a verification failure.
