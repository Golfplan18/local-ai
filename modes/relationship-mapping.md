---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
---

# MODE: Relationship Mapping

```yaml
# 0. IDENTITY
mode_id: relationship-mapping
canonical_name: Relationship Mapping
suffix_rule: analysis
educational_name: structural relationship mapping

# 1. TERRITORY AND POSITION
territory: T11-structural-relationship-mapping
gradation_position:
  axis: specificity
  value: general
adjacent_modes_in_territory:
  - mode_id: spatial-reasoning
    relationship: specificity variant (visual-input — structural gap detection on diagrams)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "how do these connect"
    - "what affects what"
    - "draw the connections"
    - "I want to see the structure"
  prompt_shape_signals:
    - "relationship map"
    - "causal DAG"
    - "dependency graph"
    - "concept map of"
    - "what relates to what"
disambiguation_routing:
  routes_to_this_mode_when:
    - "relationships are static or acyclic; no feedback loops dominate"
    - "user wants the topology of inter-element connections"
  routes_away_when:
    - "relationships involve feedback loops, delays, or emergent behaviour" → systems-dynamics-causal (T4) or systems-dynamics-structural (T17)
    - "user submits a diagram and asks 'what's missing' from it" → spatial-reasoning (visual-input variant within T11)
    - "user wants to understand a single concept deeply rather than its connections" → deep-clarification (T10)
    - "user is orienting in unfamiliar territory and wants the lay of the land" → terrain-mapping (T14)
when_not_to_invoke:
  - "Question is about how this works (mechanism), not how the parts relate (structure)" → mechanism-understanding (T16)
  - "Question is about temporal flow or process sequence" → process-mapping (T17)
  - "Diagram is the input and gap detection is the question" → spatial-reasoning

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [entities_named, relationship_types_understood, focal_question]
    optional: [prior_relationship_graph, exposure_outcome_pair]
    notes: "Applies when user supplies entity inventory and uses relational vocabulary (causal, correlational, dependency)."
  accessible_mode:
    required: [domain_or_situation_to_be_mapped]
    optional: [some_entities_named, hint_at_what_should_relate_to_what]
    notes: "Default. Mode infers entities from the situation and surfaces typed relationships."
  detection:
    expert_signals: ["DAGitty", "causal DAG", "exposure", "outcome", "confounder", "concept map", "linking phrase", "is_cross_link"]
    accessible_signals: ["how do these connect", "what relates to what", "show me the structure", "draw the connections"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What entities or concepts do you want mapped, and what's the question the map should answer?'"
    on_underspecified: "Ask: 'Are the relationships static, or do feedback loops matter? If feedback loops, route to systems-dynamics-causal (T4) or systems-dynamics-structural (T17) per parse.'"
output_contract:
  artifact_type: mapping
  required_sections:
    - focal_question
    - entities
    - connections_with_type_and_directionality
    - organising_structure
    - key_relationships
    - boundary_statement
    - acyclicity_check
  format: diagram-friendly

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Is every connection labelled with its type (causal / correlational / dependency / influential / structural) and directionality?"
    failure_mode_if_unmet: causation-correlation-trap
  - cq_id: CQ2
    question: "Have ≥2 non-obvious connections been surfaced, with at least one cross-link in concept-map outputs?"
    failure_mode_if_unmet: kitchen-sink-or-flat-tree
  - cq_id: CQ3
    question: "Is the output structured as a relational map, not flattened into a linear narrative?"
    failure_mode_if_unmet: linear-reduction
  - cq_id: CQ4
    question: "Is the output genuinely acyclic — no feedback loops smuggled into a DAG?"
    failure_mode_if_unmet: silent-cycle

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: linear-reduction
    detection_signal: "Output reads as a sequential narrative rather than a structured map."
    correction_protocol: re-dispatch (restructure as relational map)
  - name: kitchen-sink-or-flat-tree
    detection_signal: "Map is dense without significance, OR map is a flat tree with no cross-links."
    correction_protocol: re-dispatch (trim to significant connections; add ≥1 cross-link)
  - name: causation-correlation-trap
    detection_signal: "A correlational connection is labelled causal without mechanistic evidence."
    correction_protocol: flag (default to weakest relationship type the evidence supports)
  - name: silent-cycle
    detection_signal: "DAG contains a cycle without transition to systems-dynamics-causal (T4) or systems-dynamics-structural (T17)."
    correction_protocol: re-dispatch (either remove edge with rationale or transition)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - dagitty-causal-dag-formalism (when causal framing dominates)
    - novak-concept-map-tradition (when heterogeneous relations dominate)
    - pearl-causal-graphs
  foundational:
    - structural-relationship-taxonomy

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: spatial-reasoning
    when: "User has submitted a diagrammatic visual input and wants gap detection (specificity-visual-input variant)."
  sideways:
    target_mode_id: systems-dynamics-causal
    when: "Mapping reveals feedback loops; structure is no longer acyclic."
  downward:
    target_mode_id: null
    when: "Relationship Mapping is the territory founder; no lighter mode exists in T11."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Relationship Mapping is the precision with which connection type and directionality are assigned. A thin pass names entities and draws lines; a substantive pass labels each connection (causal / correlational / dependency / influential / structural), assigns directionality where defensible, and tests every claimed causal connection for mechanism. Test depth by asking: could each labelled connection be falsified by a specific observation? Each connection in prose carries a literal type prefix.

## BREADTH ANALYSIS GUIDANCE

Breadth in Relationship Mapping is the catalog of entities and connections, including non-obvious ones. Widen the lens to identify ≥2 non-obvious connections, surface the organising structure (hub-and-spoke / chain / hierarchy / network / bipartite), and note connections to adjacent domains. Breadth markers: at least one cross-link in concept-map outputs (Novak's marker of integrative understanding); at least two non-obvious connections explicitly named; organising structure named.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Relationship Mapping output: declares the type and directionality of every connection; surfaces ≥2 non-obvious connections; structures the output as a relational map (not a linear narrative); honours acyclicity (any cycle prompts transition to systems-dynamics-causal or systems-dynamics-structural per parse). Specifically check for the causation-correlation trap (mislabelling), linear reduction (narrative collapse), kitchen sink (no significance), and silent cycle (DAG with feedback).

## REVISION GUIDANCE

Revise to add type prefixes to connections without them. Revise to surface non-obvious connections when only obvious ones appear. Revise to restructure linear narrative as relational map. Resist revising toward dense exhaustive maps when significance is the criterion. Resist revising to retain cycles in a DAG — the structural rule is acyclicity; cycles route to systems-dynamics-causal (T4) or systems-dynamics-structural (T17) per parse.

## CONSOLIDATION GUIDANCE

Consolidate as a diagram-friendly mapping with the seven required sections (focal question / entities / connections / organising structure / key relationships / boundary / acyclicity check). Format: diagram-friendly. When envelope-bearing: concept_map for heterogeneous relations (Novak tradition); causal_dag for specifically causal framings with focal exposure and outcome (DAGitty DSL). Concept maps need ≥4 concepts, ≥2 linking phrases, ≥3 propositions, and ≥1 cross-link. Causal DAGs need acyclic structure with focal_exposure and focal_outcome resolvable to declared nodes.

## VERIFICATION CRITERIA

Verified means: every connection has a stated type and directionality; ≥2 non-obvious connections surfaced; organising structure named; output structured as a relational map (not linear narrative); acyclicity honoured (any cycle handled via transition to systems-dynamics-causal or systems-dynamics-structural per parse); boundary statement names what the map omits. The four critical questions are addressed in the output.
