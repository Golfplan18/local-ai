---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Domain Induction

```yaml
# 0. IDENTITY
mode_id: domain-induction
canonical_name: Domain Induction
suffix_rule: analysis
educational_name: domain induction (orient + terrain-map + induct what to learn)

# 1. TERRITORY AND POSITION
territory: T14-orientation-in-unfamiliar-territory
gradation_position:
  axis: depth
  value: molecular
adjacent_modes_in_territory:
  - mode_id: quick-orientation
    relationship: depth-light sibling
  - mode_id: terrain-mapping
    relationship: depth-thorough sibling

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I'm stepping into a new domain and I want a structured induction, not just a quick orientation"
    - "I need to know what's here, what's connected to what, and what to learn next, in that order"
    - "willing to spend the time to be inducted properly"
    - "I want a map plus a learning plan, not just a map"
  prompt_shape_signals:
    - "domain induction"
    - "induct me into"
    - "structured onboarding to a domain"
    - "what to learn next in this field"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants integrated induction spanning quick orientation + terrain map + structured learning sequence"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "want fast lay-of-the-land in a few minutes" → quick-orientation
    - "want thorough terrain mapping without learning sequence" → terrain-mapping
    - "the question is really generative exploration of an open space" → passion-exploration (T20)
when_not_to_invoke:
  - "User has time pressure" → quick-orientation
  - "User already has terrain-map and only needs the learning sequence" → run terrain-mapping output forward into a focused induction synthesis stage rather than full molecular pass

# 3. EXECUTION STRUCTURE
composition: molecular
molecular_spec:
  components:
    - mode_id: quick-orientation
      runs: fragment
      fragment_spec: "light-orientation-only — produce the rapid lay-of-the-land (key terms, dominant figures, central debates) as breadth seed; do not produce full quick-orientation output"
    - mode_id: terrain-mapping
      runs: full
  synthesis_stages:
    - name: orientation-and-terrain-merge
      type: parallel-merge
      input: [quick-orientation-fragment, terrain-mapping]
      output: "merged orientation: rapid lay-of-the-land integrated with thorough terrain map; what is here is named and structured"
    - name: connectivity-mapping
      type: sequenced-build
      input: [orientation-and-terrain-merge]
      output: "what's-connected-to-what: relations among elements (concepts, figures, debates, methods); identification of central nodes and bridge concepts"
    - name: structured-induction
      type: dialectical-resolution
      input: [orientation-and-terrain-merge, connectivity-mapping]
      output: "domain induction document with three integrated parts: (a) what is here; (b) what's connected to what; (c) what to learn next, sequenced by dependency"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; if connectivity cannot be inferred with confidence, document as conjectural-mapping rather than presenting as established

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [domain_name, prior_familiarity_level, induction_goal]
    optional: [time_budget_for_learning, prior_resources_consulted]
    notes: "Applies when user supplies prior familiarity level or induction goal."
  accessible_mode:
    required: [domain_name]
    optional: [why_interested, contextual_background]
    notes: "Default. Mode elicits prior familiarity and induction goal during execution."
  detection:
    expert_signals: ["prior familiarity", "induction goal", "structured onboarding"]
    accessible_signals: ["new to", "want to learn about", "just getting started in"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the domain you want to induct into, and what's your goal — research-level, working-knowledge, or general-orientation?'"
    on_underspecified: "Ask the user whether they want the full Domain Induction molecular pass or a lighter Quick Orientation / Terrain Mapping read."
output_contract:
  artifact_type: synthesis
  required_sections:
    - what_is_here
    - whats_connected_to_what
    - central_nodes_and_bridge_concepts
    - what_to_learn_next_sequenced
    - learning_dependencies_and_prerequisites
    - confidence_map
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the orientation surveyed the domain broadly enough, or has it privileged the dominant subfield?"
    failure_mode_if_unmet: dominant-subfield-bias
  - cq_id: CQ2
    question: "Does the connectivity-mapping actually identify dependencies and bridges, or does it list elements without showing relations?"
    failure_mode_if_unmet: relation-omission
  - cq_id: CQ3
    question: "Is the what-to-learn-next sequence ordered by genuine dependency, or by analyst convenience?"
    failure_mode_if_unmet: arbitrary-sequencing
  - cq_id: CQ4
    question: "Does the induction respect the user's stated familiarity level and goal, or does it default to a generic survey?"
    failure_mode_if_unmet: goal-disconnection

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: dominant-subfield-bias
    detection_signal: "What-is-here section over-represents one subfield; minority traditions or competing schools are absent."
    correction_protocol: re-dispatch (with explicit breadth prompt)
  - name: relation-omission
    detection_signal: "What's-connected-to-what is a list of elements without arrows, dependencies, or bridge concepts."
    correction_protocol: re-dispatch
  - name: arbitrary-sequencing
    detection_signal: "Learning sequence reads as alphabetical or import order rather than dependency-ordered."
    correction_protocol: re-dispatch
  - name: goal-disconnection
    detection_signal: "Induction is generic; ignores the stated familiarity level or induction goal."
    correction_protocol: flag and re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - bloom-taxonomy (when learning sequence requires cognitive-level scaffolding)
    - novice-expert-cognition (when familiarity level is novice)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Domain Induction is the heaviest mode in T14."
  sideways:
    target_mode_id: null
    when: "No within-T14 stance/complexity sibling beyond depth ladder."
  downward:
    target_mode_id: terrain-mapping
    when: "User has time pressure or scope is narrower than initially estimated."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Domain Induction is the degree to which the connectivity-mapping and structured-induction stages produce a learning architecture that no single quick-orientation or terrain-mapping pass could have produced. A thin molecular pass concatenates orientation, terrain, and learning list; a substantive pass identifies central nodes (concepts that other concepts depend on), bridge concepts (linking subfields), and dependency-ordered sequence. Test depth by asking: would the learning sequence change if a single central-node concept were removed?

## BREADTH ANALYSIS GUIDANCE

Breadth in Domain Induction is the catalog of subfields and traditions surveyed in the orientation and terrain-mapping stages. Widen the lens to scan: dominant subfield; minority traditions; cross-disciplinary inflows; methodological alternatives; historical figures vs. contemporary figures. Even when the learning sequence narrows to a focused path, breadth is documented in the what-is-here section so the user can see what's being deferred and what's being prioritized.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Domain Induction output surveys broadly before sequencing, identifies relations and dependencies (not just elements), orders the learning sequence by genuine dependency, and respects the user's stated familiarity level and induction goal.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to add bridge concepts and central nodes where the draft lists elements without showing relations. Revise to re-sequence the learning path where dependencies are out-of-order. Resist revising toward a generic survey when the stated goal is more focused (research-level vs. working-knowledge vs. general-orientation).

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the six required sections. The what-to-learn-next-sequenced section is mandatory and concrete (specific resources, papers, books, or experiences with rationale per item). Each section carries provenance to its component sources (quick-orientation fragment for rapid lay-of-the-land; terrain-mapping for thorough structure; synthesis for connectivity and sequencing). Confidence map is per-finding.

## VERIFICATION CRITERIA

Verified means: orientation surveyed broadly; terrain-mapping ran fully; connectivity-mapping shows relations not just elements; learning sequence is dependency-ordered; user's familiarity level and induction goal are reflected; confidence map is populated. The four critical questions are addressed in the output.
