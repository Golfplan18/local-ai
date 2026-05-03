---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Frame Comparison

```yaml
# 0. IDENTITY
mode_id: frame-comparison
canonical_name: Frame Comparison
suffix_rule: analysis
educational_name: frame comparison (Lakoff strict-father vs. nurturant-parent and other frames)

# 1. TERRITORY AND POSITION
territory: T9-paradigm-and-assumption-examination
gradation_position:
  axis: stance
  value: comparing
adjacent_modes_in_territory:
  - mode_id: paradigm-suspension
    relationship: stance-counterpart (suspending — single-frame surfacing without comparison)
  - mode_id: worldview-cartography
    relationship: depth-molecular sibling (built Wave 4)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "two camps are talking past each other"
    - "I want to see what each side is assuming about the same situation"
    - "the disagreement isn't about facts, it's about how we frame the issue"
    - "I want to understand both worldviews on their own terms"
  prompt_shape_signals:
    - "frame comparison"
    - "compare the framings"
    - "Lakoff"
    - "strict father vs nurturant parent"
    - "conceptual metaphor"
    - "competing frames"
    - "how each side sees this"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user has named (or implies) ≥2 frames or worldviews to compare"
    - "user wants each frame articulated on its own terms before any cross-frame evaluation"
    - "the analytical object is the frames themselves, not which frame is correct"
  routes_away_when:
    - "user wants to surface the implicit frame of a single artifact" → paradigm-suspension or T1 frame-audit
    - "user wants integrated cartography across many worldviews" → worldview-cartography
    - "user wants to evaluate which frame is more sound" → T1 modes (frame as embedded in argument)
    - "user wants synthesis across the frames" → T12 synthesis
when_not_to_invoke:
  - "Disagreement is about empirical facts within a shared frame — frames are not in dispute" → T5 hypothesis evaluation
  - "Only one frame is in play (no comparison object)" → paradigm-suspension
  - "User wants to negotiate between parties holding the frames" → T13 negotiation modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [frame_inventory, comparison_axis, situation_or_issue]
    optional: [frame_typology_reference, prior_frame_analyses, conceptual_metaphor_seeds]
    notes: "Applies when user supplies named frames (e.g., 'strict-father vs. nurturant-parent', 'systemic vs. individual', 'market vs. commons') or a frame typology to apply."
  accessible_mode:
    required: [issue_or_disagreement, two_or_more_perspectives_to_compare]
    optional: [why_user_wants_comparison, named_camps_or_voices]
    notes: "Default. Mode infers frames from descriptions of the perspectives or camps."
  detection:
    expert_signals: ["frame typology", "Lakoff", "conceptual metaphor", "strict-father", "nurturant-parent", "narrative frames"]
    accessible_signals: ["how each side sees", "compare the framings", "two camps", "talking past each other"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the issue, and what are the perspectives or camps you want to compare?'"
    on_underspecified: "Ask: 'Could you describe how each camp talks about the issue, in their own words if possible?'"
output_contract:
  artifact_type: mapping
  required_sections:
    - frames_named_and_described
    - core_metaphors_per_frame
    - moral_or_value_commitments_per_frame
    - what_each_frame_makes_visible
    - what_each_frame_obscures
    - cross_frame_translation_difficulty
    - residual_irreducibility
    - confidence_per_finding
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has each frame been articulated on its own terms (steelman-mode within the frame), or has the analyst's preferred frame received fuller articulation than the others?"
    failure_mode_if_unmet: asymmetric-articulation
  - cq_id: CQ2
    question: "Have the core conceptual metaphors of each frame been surfaced (Lakoff-style), or has the analysis stayed at the level of stated positions without descending to the metaphors that structure the positions?"
    failure_mode_if_unmet: surface-position-only
  - cq_id: CQ3
    question: "Has the analysis surfaced what each frame *obscures* as well as what it makes visible, or has it presented each frame as if the frame had no blind spots?"
    failure_mode_if_unmet: blind-spot-omission
  - cq_id: CQ4
    question: "Has irreducibility been honored — i.e., has the analysis resisted the temptation to translate one frame into the other's vocabulary, when such translation distorts?"
    failure_mode_if_unmet: false-translation

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: asymmetric-articulation
    detection_signal: "One frame's section is substantially longer, more nuanced, or more sympathetic than the others'."
    correction_protocol: re-dispatch
  - name: surface-position-only
    detection_signal: "Frames are described in terms of stated positions and policy preferences without surfacing the underlying conceptual metaphors that structure them."
    correction_protocol: re-dispatch
  - name: blind-spot-omission
    detection_signal: "What-each-frame-obscures section is empty, thin, or applied only to the analyst's non-preferred frame."
    correction_protocol: flag
  - name: false-translation
    detection_signal: "Cross-frame translation is presented as smooth when residual-irreducibility is more honest; or one frame's vocabulary is used to describe the other's commitments."
    correction_protocol: flag
  - name: typology-imposition
    detection_signal: "Lakoff's strict-father / nurturant-parent (or other named typology) is applied to a domain where it does not naturally fit, distorting the actual frames in play."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - lakoff-conceptual-metaphor
  optional:
    - lakoff-strict-father-nurturant-parent (when political-moral framings are in play)
    - schon-rein-frame-reflection (when policy frames are in play)
    - benford-snow-collective-action-frames (when movement frames are in play)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: worldview-cartography
    when: "More than three frames are in play, or frames need to be situated in a larger cartography of worldviews."
  sideways:
    target_mode_id: paradigm-suspension
    when: "On reflection only one frame is the analytical object; comparison was not the right move."
  downward:
    target_mode_id: paradigm-suspension
    when: "User wants single-frame surfacing rather than cross-frame comparison."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Frame Comparison is the descent from stated positions to the conceptual metaphors and moral commitments that structure them. A thin pass restates each side's position; a substantive pass surfaces the core metaphor each frame deploys (e.g., nation-as-family with strict father vs. nurturant parent; market-as-natural-system vs. market-as-human-construction; disease-as-invader vs. disease-as-imbalance), names the moral commitments the metaphor entails, articulates what each frame makes visible and what it obscures, and honors residual irreducibility where translation distorts. Test depth by asking: could a partisan of each frame recognize their own view in the analysis as a steelmanned articulation, not as the opposing camp's caricature?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means surveying the frame typologies that might apply (Lakoff's family-based moral frames, Schön-Rein policy frames, collective-action frames, narrative frames, frame-of-justice variants), considering whether the named frames exhaust the live alternatives or whether unnamed frames are also in play (a third or fourth perspective excluded from the comparison), and scanning for hybrid or emerging frames that don't fit either pole cleanly. Breadth markers: at least three frame-typology candidates are considered before locking the comparison axis; the possibility of frames-not-yet-named is acknowledged.

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) symmetric articulation; (CQ2) descent to conceptual metaphor; (CQ3) blind-spot surfacing; (CQ4) honored irreducibility. The named failure modes (asymmetric-articulation, surface-position-only, blind-spot-omission, false-translation, typology-imposition) are the evaluation checklist. A passing Frame Comparison output articulates each frame on its own terms with equal rigor, surfaces core metaphors, identifies blind spots per frame, and honors residual irreducibility.

## REVISION GUIDANCE

Revise to balance asymmetric articulation where one frame received fuller treatment. Revise to descend to conceptual metaphor where the draft stayed at stated positions. Revise to add blind-spot surfacing per frame where the draft presented frames as if blind-spot-free. Resist revising toward synthesis — the mode's analytical character is comparing, not integrating. If integration is wanted, escalate to T12 synthesis rather than collapsing irreducibility within this mode.

## CONSOLIDATION GUIDANCE

Consolidate as a structured mapping with the eight required sections. Each frame appears as its own column or block with parallel internal structure (description, core metaphor, moral commitments, what-it-makes-visible, what-it-obscures). Cross-frame translation difficulty is its own section that names where translation works smoothly and where it distorts. Residual irreducibility is named explicitly — the places where one frame's commitment cannot be cashed out in the other's vocabulary without loss. Confidence-per-finding accompanies each major claim.

## VERIFICATION CRITERIA

Verified means: each frame is articulated symmetrically; core conceptual metaphors per frame are surfaced; moral/value commitments per frame are named; what-each-frame-makes-visible and what-it-obscures are both populated; cross-frame translation difficulty is acknowledged; residual irreducibility is honored where present; the four critical questions are addressable from the output. Confidence per major finding accompanies each claim.
