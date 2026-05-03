---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
---

# MODE: Deep Clarification

```yaml
# 0. IDENTITY
mode_id: deep-clarification
canonical_name: Deep Clarification
suffix_rule: analysis
educational_name: deep conceptual clarification (ordinary-language tradition)

# 1. TERRITORY AND POSITION
territory: T10-conceptual-clarification
gradation_position:
  axis: depth
  value: thorough
adjacent_modes_in_territory:
  - mode_id: conceptual-engineering
    relationship: stance counterpart (ameliorative; Cappelen/Plunkett)
  - mode_id: definitional-dispute
    relationship: specificity counterpart (essentially-contested; Gallie) — gap-deferred

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "why does X work that way"
    - "explain the mechanics of"
    - "what's really going on underneath"
    - "I want depth, not orientation"
  prompt_shape_signals:
    - "deeper"
    - "mechanism"
    - "how does it actually work"
    - "explain the physics / math / internals"
disambiguation_routing:
  routes_to_this_mode_when:
    - "the domain is already familiar; user wants the next mechanism beneath the current explanation"
    - "concept is uncontested but its inner workings are sought"
  routes_away_when:
    - "user wants to engineer the concept normatively (should we redefine X)" → conceptual-engineering
    - "concept is essentially contested with rival defenders" → definitional-dispute
    - "user is unfamiliar and needs the lay of the land first" → terrain-mapping
    - "user wants to question whether the framework holding the concept is itself sound" → paradigm-suspension
when_not_to_invoke:
  - "User is exploring an unfamiliar domain — Terrain Mapping is the right depth"
  - "User has a deliverable in mind and wants execution" → Project Mode
  - "Concept is contested between rival camps; the question is which definition wins" → definitional-dispute or T1 frame audit

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [phenomenon_or_concept, user_current_level_of_understanding]
    optional: [domain_briefing, primary_sources_already_consulted]
    notes: "Applies when user explicitly states their starting depth and asks for the next level beneath."
  accessible_mode:
    required: [phenomenon_or_concept]
    optional: [hint_at_user_intuition_or_misconception]
    notes: "Default. Mode infers user's starting level from the way the question is phrased and pushes ≥2 levels beneath."
  detection:
    expert_signals: ["I already understand X at level Y", "first-principles", "primary literature", "the canonical reference is"]
    accessible_signals: ["explain it deeper", "what's underneath", "how does it really work"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the phenomenon or concept you want to understand deeper, and roughly what level of explanation do you already have?'"
    on_underspecified: "Ask: 'Are you familiar with the surface explanation already, or do you want the lay of the land first?' If the latter, route to Terrain Mapping."
output_contract:
  artifact_type: clarification
  required_sections:
    - surface_explanation
    - mechanistic_clarification_two_levels_deeper
    - epistemic_boundary
    - practical_implications
  format: prose

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Is each successive level a genuine mechanism beneath, or is it horizontal detail at the same level?"
    failure_mode_if_unmet: elaboration-trap
  - cq_id: CQ2
    question: "Has the epistemic boundary been marked — where settled knowledge ends and current-best-understanding begins?"
    failure_mode_if_unmet: false-certainty
  - cq_id: CQ3
    question: "Does the deeper understanding change what the user would do or conclude — is there a practical implication?"
    failure_mode_if_unmet: academic-drift

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: lateral-drift-trap
    detection_signal: "Successive levels move to adjacent topics rather than deeper into the same phenomenon."
    correction_protocol: re-dispatch (redirect to same-phenomenon depth)
  - name: elaboration-trap
    detection_signal: "Deeper level adds more facts at the same level of abstraction rather than revealing mechanism."
    correction_protocol: re-dispatch (depth is vertical — name the mechanism beneath)
  - name: jargon-trap
    detection_signal: "Replacing accessible explanation with terminology without naming a mechanism in plain terms."
    correction_protocol: flag
  - name: false-certainty
    detection_signal: "Mechanistic claims presented as settled when current science is indeterminate."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - engineering-and-technical-analysis-module (for technical domains)
  foundational:
    - ordinary-language-philosophy-tradition

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: conceptual-engineering
    when: "Clarification reveals the concept's current definition is normatively inadequate; user wants to ameliorate it."
  sideways:
    target_mode_id: paradigm-suspension
    when: "Clarification surfaces a load-bearing assumption the framework depends on; user wants to question the framework."
  downward:
    target_mode_id: null
    when: "Deep Clarification is the depth-thorough founder; lighter clarification routes to T14 quick-orientation."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Deep Clarification is vertical: each successive level reveals the mechanism beneath the previous one, not more detail at the same level. A thin pass restates the surface explanation in different words; a substantive pass identifies what causes the phenomenon at level N-1 and exposes the next mechanism beneath. Test depth by asking: could the deeper level predict behaviours the surface level cannot? Each level uses the literal labels "Surface:" / "Level 1 beneath:" / "Level 2 beneath:".

## BREADTH ANALYSIS GUIDANCE

Breadth in Deep Clarification is the surrounding terrain that anchors the mechanism: analogies in other domains, alternative mechanistic explanations, connections to adjacent areas of the user's knowledge, and the point at which further depth becomes academic rather than actionable. Widen the lens to identify ≥1 analogy, ≥1 alternative mechanism, and ≥1 practical implication. Breadth markers: the analysis identifies where deeper understanding changes practical implications and where it does not.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ3. The named failure modes are the evaluation checklist. A passing Deep Clarification output: states the surface explanation as baseline; pushes ≥2 levels beneath, each genuinely mechanistic; marks the epistemic boundary explicitly; names ≥1 practical implication; resists lateral drift and elaboration. Specifically check for the jargon trap (terminology substituting for mechanism) and false certainty (presenting current-best-understanding as settled).

## REVISION GUIDANCE

Revise to convert horizontal elaboration into vertical mechanism. Revise to add the epistemic boundary where missing. Revise to name the mechanism in plain terms when jargon has substituted for explanation. Resist revising toward authoritative tone when current science is indeterminate — humility about the boundary is part of the output. Resist revising toward generality when the user asked for depth — depth is the contract.

## CONSOLIDATION GUIDANCE

Consolidate as prose in the four required sections (surface / mechanistic clarification / epistemic boundary / practical implications). Format: prose first; envelope optional. Default to no diagram. The narrow exception is a flowchart envelope when the mechanism being clarified is itself procedural or spatial (a multi-step process, a pipeline, a control-flow algorithm). When in doubt, suppress the envelope. Each level uses the literal labels "Surface:" / "Level 1 beneath:" / "Level 2 beneath:" / "epistemic boundary:" / "Practical implication:".

## VERIFICATION CRITERIA

Verified means: surface explanation present (not skipped); ≥2 mechanistic levels below surface, each genuinely vertical (not horizontal detail); epistemic boundary marked; ≥1 practical implication named; no jargon-substitution-for-mechanism; if a flowchart envelope is emitted, the mechanism is genuinely procedural. The three critical questions are addressed in the output.
