---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
---

# MODE: Terrain Mapping

```yaml
# 0. IDENTITY
mode_id: terrain-mapping
canonical_name: Terrain Mapping
suffix_rule: analysis
educational_name: thorough orientation in unfamiliar terrain

# 1. TERRITORY AND POSITION
territory: T14-orientation-in-unfamiliar-territory
gradation_position:
  axis: depth
  value: thorough
adjacent_modes_in_territory:
  - mode_id: quick-orientation
    relationship: lighter sibling (depth-light)
  - mode_id: domain-induction
    relationship: heavier sibling (depth-molecular)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "what is X"
    - "where do I start"
    - "what do I need to know about"
    - "give me the lay of the land"
    - "I'm unfamiliar with this"
  prompt_shape_signals:
    - "walk me through"
    - "the big picture"
    - "map this domain for me"
    - "concept map of"
    - "introduce me to"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user is unfamiliar with the domain and wants thorough orientation (~5 min)"
    - "the prompt names a domain the conversation history shows the user has not engaged with"
  routes_away_when:
    - "user wants a quick orienting summary (~1 min)" → quick-orientation
    - "user wants a deep molecular induction into the domain (~10+ min)" → domain-induction
    - "user is already familiar and wants the next mechanism beneath" → deep-clarification (T10)
    - "user is exploring open-endedly with no desire for a navigable map" → passion-exploration (T20)
    - "user has multiple competing explanations for the same evidence" → competing-hypotheses (T5)
when_not_to_invoke:
  - "User has named a specific deliverable" → Project Mode
  - "User is in execution mode and wants to act, not orient" → Project Mode
  - "Domain is intimately familiar to the user" → Deep Clarification

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [domain_to_orient_in, current_user_knowledge_level, prior_orientation_attempts]
    optional: [adjacent_domains_user_already_knows, specific_sub_areas_of_interest]
    notes: "Applies when user explicitly states their starting knowledge and asks for a navigable concept map of a specified domain."
  accessible_mode:
    required: [domain_or_topic_user_is_new_to]
    optional: [hint_at_what_user_already_knows, what_user_wants_to_do_with_the_orientation]
    notes: "Default. Mode infers user's starting level from the way the question is phrased and produces a thorough survey-level map."
  detection:
    expert_signals: ["I'm familiar with X but not Y", "the canonical introduction is", "the standard taxonomy"]
    accessible_signals: ["what is X", "where do I start", "give me the lay of the land", "introduce me to"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the domain or topic you want oriented in, and roughly what do you already know about it?'"
    on_underspecified: "Ask: 'Want a quick summary (~1 min — Quick Orientation), thorough survey (~5 min — Terrain Mapping), or deep molecular induction (~10+ min — Domain Induction)?'"
output_contract:
  artifact_type: mapping
  required_sections:
    - focus_question
    - known_territory
    - unknown_or_contested_territory
    - open_questions_at_least_three
    - domain_structure
    - adjacent_connections
    - boundary_statement
  format: diagram-friendly

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are concepts classified as known / contested / open, with no contested position presented as settled (or vice versa)?"
    failure_mode_if_unmet: false-consensus
  - cq_id: CQ2
    question: "Does the map have at least one cross-link to an adjacent domain — Novak's marker of integrative understanding?"
    failure_mode_if_unmet: no-cross-link-trap
  - cq_id: CQ3
    question: "Does the prose stay at survey level rather than drilling into one sub-area (≤30% on any single sub-area)?"
    failure_mode_if_unmet: premature-depth
  - cq_id: CQ4
    question: "Does the map name what is out of scope — its boundary?"
    failure_mode_if_unmet: missing-boundary

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: premature-depth
    detection_signal: "Prose spends more than 30% on any single sub-area before the full territory is mapped."
    correction_protocol: re-dispatch (pull back to survey level)
  - name: textbook-trap
    detection_signal: "Output reproduces a standard overview without known/contested/open separation."
    correction_protocol: re-dispatch (classify each major concept by epistemic status)
  - name: false-consensus
    detection_signal: "One school of thought's view is presented as the domain consensus when rival schools exist."
    correction_protocol: re-dispatch (qualify with 'the standard view holds X; dissenters argue Y')
  - name: no-cross-link-trap
    detection_signal: "Output is a strict tree with no lateral connections."
    correction_protocol: re-dispatch (add ≥1 cross-link to an adjacent domain)
  - name: low-concept-count
    detection_signal: "Map has fewer than 4 concepts."
    correction_protocol: re-dispatch (expand to ≥4 concepts, or route to Deep Clarification if domain is too narrow)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - novak-concept-map-tradition
    - taxonomic-frameworks-for-the-target-domain
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: domain-induction
    when: "User wants molecular induction into the domain — full ~10+ min orientation with prerequisite chain and operational competence."
  sideways:
    target_mode_id: passion-exploration
    when: "Orientation opens with no terminal point and user wants generative exploration." 
  downward:
    target_mode_id: quick-orientation
    when: "User has time pressure or wants a ~1 min orienting summary rather than a ~5 min survey."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Terrain Mapping is the precision with which concepts are classified by epistemic status (known / contested / open) and tied to organising structure. A thin pass enumerates concepts; a substantive pass labels each by epistemic status, names the organising framework (hierarchy / hub-and-spoke / network / etc.), and identifies prerequisite chains. Test depth by asking: would the map predict where a newcomer would predictably form a wrong impression from survey-level sources alone? Each concept carries a literal `known` / `contested` / `open` label.

## BREADTH ANALYSIS GUIDANCE

Breadth in Terrain Mapping is the cartographic completeness — all major sub-areas, schools of thought, and adjacent domains represented. Widen the lens to map the full landscape: settled facts, contested positions (with rival schools represented), open questions, principal actors, and adjacent domains. Generate ≥3 questions the user has not asked but would need to answer to navigate effectively. Breadth markers: at least one cross-link to an adjacent domain (`is_cross_link: true`); ≥3 open questions tied to specific concepts; rival schools represented when domain has them.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Terrain Mapping output: classifies each major concept by epistemic status; produces a survey-level map (≤30% on any single sub-area); includes ≥1 cross-link to an adjacent domain; names the boundary (what is out of scope); generates ≥3 open questions tied to specific concepts. Specifically check for premature depth (drilling too soon), textbook trap (no epistemic-status classification), false consensus (rival schools elided), and no-cross-link trap (flat tree without lateral connections).

## REVISION GUIDANCE

Revise to pull back when prose has drilled too deeply into one sub-area. Revise to add epistemic-status labels when missing. Revise to add cross-links when the map is a flat tree. Revise to qualify contested positions presented as settled. Resist revising toward authoritative tone when domain has rival schools — qualify with "the standard view holds X; dissenters argue Y". Resist revising toward exhaustive enumeration when survey breadth is the criterion.

## CONSOLIDATION GUIDANCE

Consolidate as a diagram-friendly mapping with the seven required sections (focus question / known territory / unknown-or-contested / open questions / domain structure / adjacent connections / boundary statement). Format: diagram-friendly. When envelope-bearing: type is concept_map; ≥4 concepts each with hierarchy_level; ≥2 linking phrases; ≥3 propositions with all ids resolving; ≥1 proposition with `is_cross_link: true`; non-empty `focus_question` matching prose. The orchestrator's universal pipeline-stage specs extract the relevant subsection at runtime.

## VERIFICATION CRITERIA

Verified means: focus question stated and matches envelope; ≥4 concepts mapped (below 4 is Deep Clarification territory); each concept classified known/contested/open; ≥1 cross-link to an adjacent domain; ≥3 open questions tied to specific concepts; survey-level discipline maintained (≤30% on any single sub-area); boundary statement names what is out of scope; rival schools represented when domain has them. The four critical questions are addressed in the output.
