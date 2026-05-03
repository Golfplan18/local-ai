---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01
---

# MODE: Synthesis

```yaml
# 0. IDENTITY
mode_id: synthesis
canonical_name: Synthesis
suffix_rule: analysis
educational_name: cross-domain integrative synthesis

# 1. TERRITORY AND POSITION
territory: T12-cross-domain-and-knowledge-synthesis
gradation_position:
  axis: stance
  value: integrative
adjacent_modes_in_territory:
  - mode_id: dialectical-analysis
    relationship: stance counterpart (thesis-antithesis-sublation, adversarial commitment)
  - mode_id: cross-domain-analogical
    relationship: specificity variant (cross-domain analogical, deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "two bodies of knowledge developed separately, want to examine them together"
    - "wondering how X and Y connect"
    - "looking for the structural parallel between two frameworks"
  prompt_shape_signals:
    - "synthesise"
    - "synthesize"
    - "connect these frameworks"
    - "what's the structural parallel"
    - "map the intersection"
    - "how does X relate to Y"
disambiguation_routing:
  routes_to_this_mode_when:
    - "neutral examination of connection between two developed positions"
    - "wants to identify productive tension and structural correspondence without choosing sides"
  routes_away_when:
    - "wants to drive thesis through antithesis to produce something genuinely new" → dialectical-analysis
    - "wants to choose between the positions" → constraint-mapping (T3)
    - "wants the strongest version of one position" → steelman-construction (T15)
when_not_to_invoke:
  - "User is operating within one domain — synthesis requires two-or-more bodies of knowledge"
  - "User is comparing paradigms (frame vs frame) rather than integrating knowledge bodies" → T9 frame-comparison

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: neutral

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [framework_a_named, framework_b_named, prior_user_engagement_with_each]
    optional: [explicit_connection_hypotheses, prior_synthesis_attempts]
    notes: "Applies when user names frameworks by their established titles and references prior depth in each."
  accessible_mode:
    required: [two_or_more_topic_areas_to_connect]
    optional: [intuited_overlaps, motivating_question]
    notes: "Default. Mode infers framework boundaries from the user's description."
  detection:
    expert_signals: ["framework", "lineage", "tradition", "school of thought"]
    accessible_signals: ["how does X relate to Y", "wondering about the connection between"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What are the two (or more) bodies of knowledge or frameworks you want me to synthesise?'"
    on_underspecified: "Ask: 'Which two areas should I work between, and what's the question that's drawing you to the connection?'"
output_contract:
  artifact_type: synthesis
  required_sections:
    - frameworks_identified
    - structural_parallels
    - evidence_for_genuineness
    - emergent_insight
    - productive_tensions
    - limitations
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the proposed connections structural correspondences at the mechanism level, or surface analogies?"
    failure_mode_if_unmet: false-synthesis
  - cq_id: CQ2
    question: "Do both frameworks survive the synthesis as peer roots, or has one been reduced to a special case of the other?"
    failure_mode_if_unmet: reduction-trap
  - cq_id: CQ3
    question: "Have productive tensions been named explicitly, or smoothed over to produce apparent harmony?"
    failure_mode_if_unmet: harmony-trap
  - cq_id: CQ4
    question: "Does the synthesis produce an emergent insight unavailable from either framework alone?"
    failure_mode_if_unmet: restatement-only

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: false-synthesis
    detection_signal: "Cross-link rests on shared vocabulary or evocative similarity rather than mechanism-level correspondence."
    correction_protocol: re-dispatch (apply mechanism test before declaring cross-link)
  - name: reduction-trap
    detection_signal: "One framework appears as a special case of the other rather than as a peer root."
    correction_protocol: re-dispatch (preserve both frameworks as peer roots)
  - name: harmony-trap
    detection_signal: "No productive tensions named; frameworks rendered as fully compatible."
    correction_protocol: flag (add tension paragraph and tension cross-link)
  - name: no-cross-link
    detection_signal: "Two separate trees presented with no inter-framework connection."
    correction_protocol: re-dispatch (add at least one cross-framework link)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - cross-domain-analogical-mapping (when frameworks come from distant domains)
    - structural-isomorphism-detection
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Synthesis is its own depth target in T12; deeper integration would shift mode."
  sideways:
    target_mode_id: dialectical-analysis
    when: "The synthesis reveals deep opposition requiring adversarial commitment rather than neutral integration."
  downward:
    target_mode_id: null
    when: "T12 has no lighter integrative sibling currently."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Synthesis is the degree to which proposed connections survive the structural-vs-metaphorical test. A thin pass names parallels by shared vocabulary; a substantive pass states the mechanism that makes each parallel a structural correspondence rather than a surface analogy. Test depth by asking: could the proposed connection be falsified by examining a case where one framework's mechanism operates and the other's does not? If yes, the connection is structural. If the connection only restates that "both X and Y address related themes," it is surface.

## BREADTH ANALYSIS GUIDANCE

Breadth in Synthesis is the catalog of candidate connections considered before selecting which survive the mechanism test. Generate at minimum three candidate connections, including at least one non-obvious. Widen the lens to cross-domain analogical scans and to less-obvious correspondences (units of analysis, generative mechanisms, failure modes). Breadth markers: the synthesis surveys the productive tensions as well as the convergences, and explicitly names what it leaves out.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Synthesis output (a) names both frameworks as peer roots; (b) presents at least one cross-link with mechanism-level evidence; (c) names at least one productive tension; (d) identifies an emergent insight; (e) names at least one limitation where the synthesis breaks down. Connections that fail the mechanism test are surfaced as ruled-out rather than asserted.

## REVISION GUIDANCE

Revise to add mechanism evidence where the draft asserts connection by vocabulary alone. Revise to surface tensions where the draft has smoothed them. Resist revising toward apparent harmony — productive tensions are findings, not failures. Resist revising toward endorsing one framework — Synthesis is neutral examination, not advocacy. If a cross-link cannot be defended at the mechanism level, remove it and note in prose that the connection is superficial.

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the six required sections. Both frameworks appear as peer roots; at least one cross-link bridges them with explicit mechanism evidence. Productive tensions are marked with linking phrases like "is in productive tension with." Emergent insight is named explicitly. Limitations are named explicitly. The format is structured (matrix-friendly when the parallels are tabular; prose-with-headings otherwise).

## VERIFICATION CRITERIA

Verified means: both frameworks present as peer roots; ≥ 1 cross-link with mechanism evidence; ≥ 1 productive tension named; emergent insight named; ≥ 1 limitation named. Every cross-link's connection survives the mechanism test (could be falsified by a case where one framework's mechanism operates and the other's does not). The four critical questions are addressed in the output.
