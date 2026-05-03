---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Worldview Cartography

```yaml
# 0. IDENTITY
mode_id: worldview-cartography
canonical_name: Worldview Cartography
suffix_rule: analysis
educational_name: worldview cartography (multi-paradigm comparison and synthesis)

# 1. TERRITORY AND POSITION
territory: T9-paradigm-and-assumption-examination
gradation_position:
  axis: stance
  value: comparing-and-synthesizing
  depth_axis_value: molecular
adjacent_modes_in_territory:
  - mode_id: paradigm-suspension
    relationship: stance-suspending sibling (light atomic)
  - mode_id: frame-comparison
    relationship: stance-comparing sibling (thorough atomic)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "multiple worldviews are in play and I want to map the whole landscape"
    - "the disagreement is not within a frame, it's across paradigms, and I need a cartography"
    - "I want to see where paradigms cohere, where they diverge, and where they irreducibly conflict"
    - "willing to spend the time on a full multi-paradigm synthesis"
  prompt_shape_signals:
    - "worldview cartography"
    - "multi-paradigm map"
    - "compare and integrate paradigms"
    - "cross-paradigm tensions"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants integrated cartography spanning paradigm-suspension + frame-comparison + dialectical synthesis"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "want to suspend a single dominant frame to see what it hides" → paradigm-suspension
    - "want to compare two specific frames without dialectical synthesis" → frame-comparison
    - "the question is really within a single frame, evaluating an argument" → T1 modes
when_not_to_invoke:
  - "User has time pressure" → frame-comparison or paradigm-suspension
  - "User is producing an integrated synthesis across domains rather than examining paradigms" → synthesis (T12) or dialectical-analysis (T12)

# 3. EXECUTION STRUCTURE
composition: molecular
molecular_spec:
  components:
    - mode_id: paradigm-suspension
      runs: full
    - mode_id: frame-comparison
      runs: full
    - mode_id: dialectical-analysis
      runs: full
      conditional: "always; serves as synthesis stage rather than peer component"
  synthesis_stages:
    - name: paradigm-inventory
      type: parallel-merge
      input: [paradigm-suspension, frame-comparison]
      output: "consolidated paradigm inventory: each worldview named, suspended, and comparatively positioned with its dominant claims, hidden assumptions, and characteristic blindspots"
    - name: cross-paradigm-tension-surfacing
      type: contradiction-surfacing
      input: [paradigm-inventory]
      output: "explicit cross-paradigm tensions named: where paradigms make incompatible claims, where they speak past each other, where they share unrecognized common ground"
    - name: dialectical-cartography
      type: dialectical-resolution
      input: [paradigm-inventory, cross-paradigm-tension-surfacing, dialectical-analysis]
      output: "cartography of competing worldviews: synthetic positions where dialectical resolution is possible, residual incommensurabilities where it is not, and meta-level reflection on what the cartography itself reveals about the problem space"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence paradigm characterizations

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [problem_or_debate, paradigm_inventory]
    optional: [prior_frame_analyses, paradigm_genealogies]
    notes: "Applies when user supplies named paradigms or prior frame analyses."
  accessible_mode:
    required: [problem_or_debate]
    optional: [contextual_background]
    notes: "Default. Mode elicits paradigm inventory during execution."
  detection:
    expert_signals: ["paradigms include", "frames are", "worldviews", "Kuhn", "Foucault"]
    accessible_signals: ["different worldviews", "they're talking past each other", "fundamental disagreement"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the problem or debate, and what worldviews or paradigms do you see in play?'"
    on_underspecified: "Ask the user whether they want the full Worldview Cartography molecular pass or a lighter Frame Comparison / Paradigm Suspension read."
output_contract:
  artifact_type: synthesis
  required_sections:
    - paradigm_inventory
    - per_paradigm_dominant_claims_and_blindspots
    - cross_paradigm_tensions
    - dialectical_synthesis_where_possible
    - residual_incommensurabilities
    - meta_level_reflection
    - confidence_map
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has each paradigm been suspended (its assumptions surfaced) before being compared, or has the analysis evaluated paradigms from inside one of them?"
    failure_mode_if_unmet: home-paradigm-bias
  - cq_id: CQ2
    question: "Are cross-paradigm tensions named explicitly, or has the cartography smoothed over genuine incommensurability?"
    failure_mode_if_unmet: tension-collapse
  - cq_id: CQ3
    question: "Where dialectical synthesis is offered, is it grounded in the paradigms' own terms, or is it a meta-paradigm imposed from outside?"
    failure_mode_if_unmet: meta-paradigm-imposition
  - cq_id: CQ4
    question: "Are residual incommensurabilities preserved as such, or has the synthesis prematurely resolved them into a unified picture?"
    failure_mode_if_unmet: premature-resolution

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: home-paradigm-bias
    detection_signal: "All paradigms evaluated against criteria from one of them; that paradigm's assumptions remain unsurfaced."
    correction_protocol: re-dispatch (with explicit paradigm-suspension on the home paradigm)
  - name: tension-collapse
    detection_signal: "Cross-paradigm-tensions section is short or absent; output presents paradigms as complementary."
    correction_protocol: re-dispatch
  - name: meta-paradigm-imposition
    detection_signal: "Synthetic positions use vocabulary or criteria that none of the surveyed paradigms would accept."
    correction_protocol: flag and re-dispatch
  - name: premature-resolution
    detection_signal: "Output presents a unified worldview without naming residual incommensurabilities."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - kuhn-paradigm-incommensurability
  optional:
    - foucault-discursive-formation
    - rorty-final-vocabulary
    - macintyre-traditions-of-inquiry
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Worldview Cartography is the heaviest mode in T9."
  sideways:
    target_mode_id: null
    when: "No within-T9 stance/complexity sibling beyond the depth ladder."
  downward:
    target_mode_id: frame-comparison
    when: "User has time pressure; thorough comparison without dialectical synthesis suffices."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Worldview Cartography is the degree to which the dialectical-cartography stage produces synthetic positions and identified incommensurabilities that no single paradigm-suspension or frame-comparison pass could have produced. A thin molecular pass enumerates paradigms and lists their differences; a substantive pass surfaces cross-paradigm tensions, attempts dialectical resolution where possible (in the paradigms' own terms), and explicitly names where resolution fails. Test depth by asking: does the cartography contain claims that hold *across* paradigms while remaining recognizable to each?

## BREADTH ANALYSIS GUIDANCE

Breadth in Worldview Cartography is the catalog of paradigms surveyed before the cartography narrows to its core comparison. Widen the lens to scan: dominant-tradition paradigm; minority-tradition paradigm; cross-cultural paradigm; historical-genealogy paradigm; reflexive paradigm (one that explicitly thematizes paradigm-comparison itself, e.g. Kuhnian or Foucauldian). Even when only 3–4 paradigms are dialectically engaged, breadth is documented in the inventory.

## EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation checklist. A passing Worldview Cartography output suspends each paradigm (not just the foreign ones), names cross-paradigm tensions explicitly, grounds dialectical synthesis in the paradigms' own terms rather than imposing a meta-paradigm, and preserves residual incommensurabilities as such.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates paradigm summaries. Revise to surface tensions where the draft has resolved them prematurely. Resist revising toward a clean unified worldview — Worldview Cartography honors irreducible plurality where it exists; collapsing incommensurabilities is a failure mode, not a polish. Resist revising toward home-paradigm bias when the analyst's own paradigm slips in unsuspended.

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the seven required sections. Each paradigm in the inventory carries provenance to its paradigm-suspension fragment and frame-comparison output. The dialectical-cartography section is rendered with explicit named-paradigm-A / named-paradigm-B / synthetic-position structure where synthesis is offered, and explicit named-incommensurability blocks where it is not. Confidence map is per-paradigm and per-tension.

## VERIFICATION CRITERIA

Verified means: each paradigm has been suspended (not just foreign ones); cross-paradigm tensions are named explicitly; dialectical synthesis (where offered) uses the paradigms' own terms; residual incommensurabilities are preserved; confidence map is populated. The four critical questions are addressed in the output.
