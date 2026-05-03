---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Place Reading and Genius Loci

```yaml
# 0. IDENTITY
mode_id: place-reading-genius-loci
canonical_name: Place Reading and Genius Loci
suffix_rule: analysis
educational_name: place-reading and genius loci analysis (Alexander, Norberg-Schulz, Lynch, Bachelard)

# 1. TERRITORY AND POSITION
territory: T19-spatial-composition
gradation_position:
  axis: specificity
  value: descriptive-evaluative
  stance_axis_value: descriptive-evaluative-deep
  depth_axis_value: deep
adjacent_modes_in_territory:
  - mode_id: ma-reading
    relationship: stance-counterpart (contemplative-descriptive-deep, aesthetic-experiential, Japanese aesthetics; built Wave 2)
  - mode_id: compositional-dynamics
    relationship: depth-lighter sibling (universal-perceptual descriptive medium-depth; gestalt + Arnheim + Itten + Albers; built Wave 2)
  - mode_id: information-density
    relationship: specificity-counterpart (applied-evaluative-medium-depth; Tufte + Bertin + Cleveland-McGill + Bringhurst; Wave 3)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "want a reading of this place / room / building / urban scene that includes how it will be inhabited"
    - "want to know what this space invites and refuses"
    - "want a prospect-refuge / pattern-language / Lynchian legibility analysis"
    - "want to understand the genius loci / character of place"
    - "want a topoanalysis of this intimate space (Bachelard)"
    - "want to predict whether this space will be restorative or depleting"
    - "designing or evaluating an inhabited space and need affordance predictions"
  prompt_shape_signals:
    - "place reading"
    - "genius loci"
    - "spirit of place"
    - "prospect refuge"
    - "pattern language"
    - "Christopher Alexander"
    - "Norberg-Schulz"
    - "Kevin Lynch"
    - "image of the city"
    - "paths edges districts nodes landmarks"
    - "Bachelard"
    - "poetics of space"
    - "Appleton"
    - "Kaplan attention restoration"
    - "biophilic design"
    - "what does this space afford"
    - "how will people use this space"
disambiguation_routing:
  routes_to_this_mode_when:
    - "input is an inhabited or inhabitable space (room, building, garden, urban scene, landscape, depicted interior)"
    - "user wants prediction of inhabitation, dwelling-modes, or experiential consequence — not just visual reading"
    - "user wants the affordance / genius-loci tradition (Alexander / Norberg-Schulz / Lynch / Bachelard / Appleton / Kaplan) applied"
    - "user is evaluating or designing a space and needs defeasible affordance predictions"
  routes_away_when:
    - "user wants the void / interval / silence read as primary content (Japanese aesthetics)" → ma-reading
    - "user wants the universal compositional-forces / gestalt reading without affordance prediction" → compositional-dynamics
    - "user wants information-graphic / data-encoding analysis" → information-density
    - "user wants relation-extraction from a diagram" → relationship-mapping or spatial-reasoning (T11)
    - "user wants causal investigation of why this space is performing badly (root-cause framing)" → root-cause-analysis (T4)
    - "user wants process-of-inhabitation-over-time modeling" → process-mapping (T17)
    - "user wants open-ended generative exploration" → passion-exploration (T20)
when_not_to_invoke:
  - "Input is not an inhabited or inhabitable space (a chart, an abstract painting, raw data)" → other T19 modes or other territory
  - "User wants causal or process analysis of behavior in the space rather than affordance reading of the space itself" → T4 or T17
  - "User wants pure aesthetic reading without affordance / inhabitation prediction" → ma-reading (if void-focused) or compositional-dynamics

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [spatial_composition_or_place, intended_use_or_inhabitation_context, scale_room_building_urban]
    optional: [tradition_lineage_relevant, prior_readings, inhabitant_population_known, lighting_or_temporal_conditions, cultural_or_regional_context, design_brief_if_applicable]
    notes: "Applies when user supplies a place plus intended use / inhabitation context, and identifies scale (room / building / urban / landscape) and ideally the relevant tradition (pattern-language, prospect-refuge, ART, genius loci, topoanalysis)."
  accessible_mode:
    required: [spatial_composition_or_place]
    optional: [what_the_space_is_for, who_will_use_it, what_user_wants_to_know]
    notes: "Default. Mode infers intended use, scale, and inhabitant population from the description or image."
  detection:
    expert_signals: ["pattern language", "prospect refuge", "genius loci", "Norberg-Schulz", "Lynch elements", "Alexander patterns", "Bachelard", "Appleton", "ART", "biophilic"]
    accessible_signals: ["how will people use this", "is this room inviting", "does this space work", "what's the feel of this place"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe or share the space (image / description / floor plan / urban scene), say roughly what it's for, and tell me at what scale (room / building / garden / neighborhood)?'"
    on_underspecified: "Ask: 'What do you want to know — whether the space will support a particular activity, who will be drawn to which spots, whether it will feel restorative or depleting, what character of place it has?'"
output_contract:
  artifact_type: reading-with-affordance-predictions
  required_sections:
    - place_summary_and_scale
    - prospect_refuge_hazard_balance
    - active_pattern_language_patterns
    - lynchian_legibility_assessment
    - restorative_properties_assessment
    - genius_loci_character_of_place
    - bachelardian_topoanalysis_notes
    - predicted_inhabitation_and_dwelling_modes
    - design_affordance_recommendations
    - confidence_and_counter_readings
  format: reading-with-vocabulary

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the proposed affordances grounded in features of the space (concrete spatial properties: dimensions, sightlines, light, materials, thresholds, edges, scale), or are they projected by the analyst's own preferences without spatial warrant?"
    failure_mode_if_unmet: analyst-projection
  - cq_id: CQ2
    question: "Does the reading survive an inhabitant of different stature, ability, or culture from the analyst's default — i.e., would a child / elder / wheelchair user / visitor from a different cultural tradition encounter the same affordances, or are some affordances visible only from one vantage?"
    failure_mode_if_unmet: default-inhabitant-bias
  - cq_id: CQ3
    question: "Is the prospect-refuge analysis evidentially supported by spatial features (sightlines, refuge positions, hazard mitigation), or asserted as a label without spatial warrant? (Cf. the qualitative-evidence critique of prospect-refuge architectural applications.)"
    failure_mode_if_unmet: prospect-refuge-as-label
  - cq_id: CQ4
    question: "Does the reading produce predictions of observable behavior (lingering, avoidance, restoration, conversation-clustering, path-choice), or only sentiment statements that cannot be tested against use?"
    failure_mode_if_unmet: sentiment-only-reading
  - cq_id: CQ5
    question: "Has the genius loci / character-of-place reading been treated as a gestalt (a qualitative-total-phenomenon per Norberg-Schulz) rather than as an aggregate of features, or is the analysis pretending wholeness it has not actually achieved?"
    failure_mode_if_unmet: aggregate-as-gestalt
  - cq_id: CQ6
    question: "Has the reading acknowledged the limits — situations where affordance prediction depends on cultural/historical context the analysis does not have, where contested-place readings exist, or where the space's affordances conflict with its intended use — rather than asserting a unified reading the place does not support?"
    failure_mode_if_unmet: unified-reading-overreach

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: analyst-projection
    detection_signal: "Affordances asserted without grounding in concrete spatial features (dimensions, sightlines, light, materials, thresholds, scale); analyst preferences appear as place properties."
    correction_protocol: re-dispatch
  - name: default-inhabitant-bias
    detection_signal: "Reading assumes a default inhabitant (typically able-bodied, adult, of the analyst's culture); does not test whether affordances change for other stature / ability / cultural vantage."
    correction_protocol: re-dispatch
  - name: prospect-refuge-as-label
    detection_signal: "Prospect-refuge labels applied without spatial warrant (specific sightlines for prospect, specific refuge positions, specific hazard mitigation); the framework is invoked rather than applied."
    correction_protocol: re-dispatch
  - name: sentiment-only-reading
    detection_signal: "Reading produces sentiment statements (this space feels welcoming / oppressive / serene) without predictions of observable behavior that could be tested."
    correction_protocol: re-dispatch
  - name: aggregate-as-gestalt
    detection_signal: "Genius loci section lists features rather than articulating the qualitative-total character; or asserts character without showing how the features compose into it."
    correction_protocol: flag
  - name: unified-reading-overreach
    detection_signal: "Reading asserts a unified character / set of affordances the place does not support; conflicting affordances, contested readings, and cultural-context limits not acknowledged."
    correction_protocol: flag
  - name: pattern-misapplication
    detection_signal: "Pattern-language patterns invoked without showing the (context, problem, solution) triple matches the space; pattern names used as decoration rather than as analytical tools."
    correction_protocol: re-dispatch
  - name: lynchian-element-confusion
    detection_signal: "Lynch's five elements (paths, edges, districts, nodes, landmarks) misapplied — e.g., treating any boundary as an edge, any center as a node — rather than identifying the cognitive-mapping role the element plays for an actual user."
    correction_protocol: re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - alexander-pattern-language
    - norberg-schulz-genius-loci
    - lynch-image-of-the-city
    - bachelard-topoanalysis
    - appleton-prospect-refuge
    - kaplan-attention-restoration
  optional:
    - kellert-biophilic-design (when sustained-occupancy biophilic patterns are central)
    - alexander-nature-of-order (when wholeness / structure-preserving-transformations matter)
    - tuan-space-and-place (when the reading touches phenomenology of place-making)
    - relph-place-and-placelessness (when authentic-place vs. placeless-place distinction is in play)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5-8min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Place Reading is the deepest descriptive-evaluative spatial mode in T19; further depth comes from iterating with new inhabitant-vantage or temporal-condition information."
  sideways:
    target_mode_id: ma-reading
    when: "On reflection the operative work is being done by held-open void / interval / silence rather than by affordance / inhabitation; switch to contemplative-descriptive-deep stance."
  downward:
    target_mode_id: compositional-dynamics
    when: "User wants only the universal compositional-forces / gestalt reading without affordance prediction or inhabitation prediction."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Place Reading is the rigor with which six analytical operations are integrated rather than aggregated: (1) **prospect-refuge-hazard balance** (Appleton) — specific sightlines that constitute prospect, specific positions that constitute refuge, specific hazards mitigated or unmitigated; (2) **active pattern-language patterns** (Alexander) — which of the 253 patterns (or which from related catalogs: light-on-two-sides, sitting-circle, intimacy-gradient, alcoves, window-place, etc.) are present, absent, or violated, with the (context, problem, solution) triple checked per pattern; (3) **Lynchian legibility** (Lynch) — the five elements (paths, edges, districts, nodes, landmarks) identified by their cognitive-mapping role for an actual user, and the legibility of the place as a whole assessed; (4) **restorative properties** (Kaplan & Kaplan ART) — being-away, extent, compatibility, soft fascination assessed; biophilic patterns where applicable; (5) **genius loci** (Norberg-Schulz) — the qualitative-total character of place articulated as gestalt, not as feature aggregate; orientation and identification examined; dwelling modes named; (6) **Bachelardian topoanalysis** (Bachelard) — where applicable, the intimate spaces (corner, miniature, intimate immensity, drawer-as-threshold, nest, shell) and their psychological condensations. A thin pass invokes labels; a substantive pass shows the spatial features that warrant each label and predicts observable behavior. Test depth by asking: could a designer use this reading to know which one or two changes would most alter the place's affordances?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning across the six tradition-clusters before narrowing (prospect-refuge / pattern-language / Lynchian / restorative / genius loci / Bachelardian); considering the place at multiple scales (room, building, urban, landscape — affordances at one scale may conflict with affordances at another); considering temporal variation (lighting, seasons, time-of-day, social occupancy patterns); considering inhabitant variation (different stature, ability, age, culture, expertise, expectation); and considering the place's history (designed-for vs. inherited-and-adapted; contested-place readings where multiple communities claim or contest the place). Breadth markers: at least three of the six tradition-clusters are addressed substantively; the place is considered at least at its primary scale and one adjacent scale; at least one inhabitant-variation test is run (would this affordance change for a child / elder / wheelchair user / cultural visitor?).

## EVALUATION CRITERIA

Evaluate against the six critical questions: (CQ1) affordances grounded in spatial features not analyst projection; (CQ2) reading survives different inhabitant vantage; (CQ3) prospect-refuge supported by spatial warrant not asserted as label; (CQ4) reading produces testable behavioral predictions not sentiment-only; (CQ5) genius loci treated as gestalt not aggregate; (CQ6) limits acknowledged. The named failure modes are the evaluation checklist. A passing Place Reading output addresses the six tradition-clusters substantively, grounds affordances in concrete spatial features, predicts observable behavior, articulates genius loci as character-of-place gestalt where warranted, names design affordance recommendations keyed to specific spatial features, and offers counter-readings where the place admits multiple legitimate readings.

## REVISION GUIDANCE

Revise to ground asserted affordances in concrete spatial features where the draft projected analyst preferences. Revise to test inhabitant-vantage variation where the draft assumed a default inhabitant. Revise to apply prospect-refuge with spatial warrant where the draft used the labels decoratively. Revise to make behavioral predictions testable where the draft offered sentiment only. Revise to articulate genius loci as gestalt where the draft listed features. Revise to apply pattern-language patterns by checking the (context, problem, solution) triple where the draft used pattern names as decoration. Revise to identify Lynch elements by cognitive-mapping role where the draft used the labels mechanically. Resist revising toward sentiment / aesthetic-only / wholeness-claim — the mode's character is *descriptive-evaluative-deep* with predictive output; the reading is defeasible and produces testable claims about inhabitation. Resist revising toward unified-reading where the place legitimately admits conflicting affordances or contested readings — the conflict is part of the place, not a defect of the analysis.

## CONSOLIDATION GUIDANCE

Consolidate as a reading-with-vocabulary artifact with the ten required sections. Place summary and scale appear first (the analytical object is bounded). Prospect-refuge-hazard balance is grounded in specific spatial features (sightlines, refuge positions, hazard mitigation). Active pattern-language patterns are listed with the (context, problem, solution) triple checked per pattern. Lynchian legibility assessment names the five-element identifications and the place's legibility as a whole. Restorative properties assessment uses ART vocabulary (being-away, extent, compatibility, soft fascination) plus biophilic patterns where applicable. Genius loci character-of-place articulates the qualitative-total gestalt with orientation and identification. Bachelardian topoanalysis notes are present where the place includes intimate-space features (corner, miniature, intimate immensity); absent or marked as not-applicable where the place's scale or character does not invite topoanalysis. Predicted inhabitation and dwelling-modes are testable behavioral claims (where people will linger, where they will pass through, where conversations will cluster, what activities the space supports or refuses, restorative vs. depleting effect). Design affordance recommendations are specific and keyed to spatial features. Confidence and counter-readings closes the artifact: confidence per major claim; at least one counter-reading where the place admits multiple legitimate readings; explicit acknowledgment where cultural-context or temporal-condition limits constrain the reading.

## VERIFICATION CRITERIA

Verified means: place named and scale identified; prospect-refuge-hazard balance grounded in specific spatial features; active pattern-language patterns listed with (context, problem, solution) triple checked; Lynchian legibility assessment present; restorative properties assessment present (ART + biophilic where applicable); genius loci character-of-place articulated as gestalt where warranted (or marked as not-yet-coherent if the place lacks unified character); Bachelardian topoanalysis notes present where applicable (or marked not-applicable); predicted inhabitation and dwelling-modes are testable behavioral claims (not sentiment); at least three design affordance recommendations keyed to specific spatial features; at least one counter-reading or limit-acknowledgment present; the six critical questions are addressable from the output. Confidence per major finding accompanies each claim. Cross-reference to T19 territory-level open debates is noted where the reading depends on contested framing decisions (especially Debate 5 on AI implementability of perceptual operations for direct-image vs. verbal-description input).

## CAVEATS AND OPEN DEBATES

This mode does not carry mode-specific debates. Five territory-level debates (per Decision G) are documented in `Reference — Analytical Territories.md` T19 entry and bear on Place Reading specifically:

1. **Spatial vs. compositional framing.** Place Reading sits in spatial-composition territory (rooms, buildings, urban scenes); the temporal generalization (Cage / Ozu / Tarkovsky) is less directly relevant here than for ma-reading, but inhabitation has temporal dimensions (occupancy patterns, seasonal variation, lighting changes) that the reading must accommodate.
2. **Aesthetic-only or also abstract spatial inputs?** Place Reading sits on the *applied-and-experiential* side: the traditions (Alexander, Lynch, Appleton, Kaplan) operate on functional inhabited spaces, not pure aesthetic objects. The territory's coherence rests on the operation (read spatial structure as primary content with experiential / functional consequence) being shared with aesthetic-experiential modes (ma-reading) and applied modes (information-density).
3. **Western-analytical and Eastern-aesthetic: same operation or convergent traditions?** Place Reading is firmly Western-analytical (architecture / environmental psychology / cognitive mapping); the Eastern-aesthetic question bears on this mode's relationship to ma-reading more than on its internal stance.
4. **Verbal accessibility for AI implementation.** Place Reading is implementable for direct image input or high-fidelity verbal-spatial description (sightlines, dimensions, materials, thresholds); it degrades for rough sketch where critical features (refuge positions, hazard mitigation, light quality, scale) cannot be inferred. The pessimistic view — that perceptual grouping is not propositional — bears less on Place Reading than on Compositional Dynamics, because Place Reading's predictions are about behavior and use rather than perceptual phenomenology, but verbal accessibility remains a real constraint.
5. **Mode granularity: general vs. tradition-specific.** Whether Bachelardian topoanalysis (intimate immensity, corner, miniature) and biophilic design (Kellert et al.) should be promoted to first-class modes or remain stance-flags / vocabulary inside Place Reading. Currently the latter; Bachelard rides as a vocabulary cluster within Place Reading; Kellert biophilic patterns ride in the restorative-properties section. Revisit if outputs collapse or if biophilic-design workload becomes substantial.

These five debates are *not* re-documented here. They are referenced because they bear on Place Reading's stance, lens dependencies, and implementability. See the T19 entry in `Reference — Analytical Territories.md` for the full debate text and citations.
