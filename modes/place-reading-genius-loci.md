---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

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

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Place Reading is the descriptive-evaluative-deep reading of an inhabited or inhabitable space, integrating six tradition-clusters (prospect-refuge per Appleton; pattern-language per Alexander; Lynchian legibility; ART/biophilic per Kaplan & Kellert; genius loci per Norberg-Schulz; Bachelardian topoanalysis) to produce defeasible affordance predictions — testable claims about how the space will be inhabited, what activities it supports or refuses, who will linger where, whether it will be restorative or depleting. It is distinct from ma-reading (contemplative-descriptive-deep aesthetic-experiential reading of held-open void), compositional-dynamics (universal-perceptual gestalt reading without affordance prediction), and information-density (Tufte / Bertin data-encoding analysis). The mode is descriptive of place character but evaluative in producing predictions and design recommendations — it lives between aesthetic reading and root-cause investigation, with stance defeasible throughout.

**Procedure.**

1. Name the place and lock its scale (room / building / garden / neighbourhood / landscape) plus intended inhabitation context and any temporal or cultural conditions that shape the reading.
2. Map prospect-refuge-hazard balance — specific sightline geometry (prospect), specific enclosure positions (refuge), specific hazards mitigated or unmitigated; warrant each with concrete spatial features, not labels.
3. Survey active pattern-language patterns — light-on-two-sides, sitting-circle, intimacy-gradient, alcoves, window-place, etc. — checking the (context, problem, solution) triple per pattern; flag presence, absence, or violation.
4. Assess Lynchian legibility — identify paths, edges, districts, nodes, landmarks by the cognitive-mapping role they play for an actual user (not mechanical pattern-match); render an overall legibility verdict.
5. Apply ART vocabulary — being-away, extent, compatibility, soft fascination — plus biophilic-pattern presence where applicable, grounded in concrete features.
6. Articulate genius loci as gestalt (Norberg-Schulz qualitative-total character) with orientation and identification assessed; or mark explicitly as `not-yet-coherent` if the place lacks unified character.
7. Where applicable, render Bachelardian topoanalysis of intimate-space features (corner, miniature, intimate immensity, nest, shell); mark `not-applicable` where scale or character doesn't invite it.
8. Produce testable behavioral predictions — where people will linger / pass through / cluster, what activities are supported, restorative-vs-depleting effect, with the observable signal that would confirm or refute each prediction.
9. Run the inhabitant-variation test — would affordances change for a child / elder / wheelchair user / cultural visitor / inhabitant of different stature, ability, or expertise from the analyst's default?
10. Generate design affordance recommendations keyed to specific spatial features, with tradeoffs.
11. Preserve counter-readings where the place legitimately admits multiple readings (contested-place, conflicting affordances across scales, multiple cultural vantages); name falsifiability conditions per major claim.

**Goal.** Produce a place reading-with-affordance-predictions that walks the six tradition-clusters on a named place, grounds every claim in concrete spatial features, predicts testable inhabitation behaviours, articulates genius loci as gestalt where warranted, and surfaces counter-readings and inhabitant-vantage variation where the place admits them.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — affordance grounding.** Are the proposed affordances grounded in concrete spatial features (dimensions, sightlines, light, materials, thresholds, edges, scale), or projected by the analyst's preferences without spatial warrant? Failure mode if unmet: `analyst-projection`.
- **CQ2 — inhabitant-vantage robustness.** Does the reading survive an inhabitant of different stature, ability, age, or cultural vantage from the analyst's default? Failure mode if unmet: `default-inhabitant-bias`.
- **CQ3 — prospect-refuge warrant.** Is the prospect-refuge analysis evidentially supported by spatial features (specific sightlines, refuge positions, hazard mitigation), or asserted as a label? Failure mode if unmet: `prospect-refuge-as-label`.
- **CQ4 — testable predictions.** Does the reading produce predictions of observable behavior (lingering, avoidance, restoration, conversation-clustering, path-choice), or only sentiment statements that cannot be tested against use? Failure mode if unmet: `sentiment-only-reading`.
- **CQ5 — gestalt vs aggregate.** Has the genius loci / character-of-place reading been treated as a gestalt (qualitative-total phenomenon per Norberg-Schulz) rather than as an aggregate of features? Failure mode if unmet: `aggregate-as-gestalt`.
- **CQ6 — limits acknowledged.** Has the reading acknowledged the limits — contested-place readings, conflicting affordances at different scales, cultural-context dependence — rather than asserting a unified reading the place does not support? Failure mode if unmet: `unified-reading-overreach`.

A passing output addresses the six tradition-clusters substantively (not as a checkbox), grounds every affordance in concrete spatial features, predicts observable behavior with the test signal named, articulates genius loci as gestalt where warranted (or marks `not-yet-coherent`), produces at least three design affordance recommendations keyed to specific features, surfaces at least one counter-reading or limit-acknowledgment, and runs at least one inhabitant-vantage variation test.

**Named failure modes.**

- *analyst-projection* — affordances asserted without grounding in concrete spatial features; analyst preferences appear as place properties.
- *default-inhabitant-bias* — reading assumes a default inhabitant (typically able-bodied, adult, of the analyst's culture); does not test whether affordances change for other stature / ability / cultural vantage.
- *prospect-refuge-as-label* — prospect-refuge labels applied without specific sightlines, refuge positions, hazard mitigation; the framework is invoked rather than applied.
- *sentiment-only-reading* — sentiment statements (this space feels welcoming / oppressive / serene) without predictions of observable behavior that could be tested.
- *aggregate-as-gestalt* — genius loci section lists features rather than articulating the qualitative-total character; or asserts character without showing how features compose into it.
- *unified-reading-overreach* — reading asserts a unified character / set of affordances the place does not support; conflicting affordances, contested readings, cultural-context limits not acknowledged.
- *pattern-misapplication* — pattern-language patterns invoked without showing the (context, problem, solution) triple matches the space; pattern names used as decoration.
- *lynchian-element-confusion* — Lynch's five elements misapplied (any boundary treated as edge, any centre as node) without identifying the cognitive-mapping role the element plays for an actual user.

## REVISION GUIDANCE

Revise to ground asserted affordances in concrete spatial features where the draft projected analyst preferences. Revise to test inhabitant-vantage variation where the draft assumed a default inhabitant. Revise to apply prospect-refuge with spatial warrant where the draft used the labels decoratively. Revise to make behavioral predictions testable where the draft offered sentiment only. Revise to articulate genius loci as gestalt where the draft listed features. Revise to apply pattern-language patterns by checking the (context, problem, solution) triple where the draft used pattern names as decoration. Revise to identify Lynch elements by cognitive-mapping role where the draft used the labels mechanically. Resist revising toward sentiment / aesthetic-only / wholeness-claim — the mode's character is *descriptive-evaluative-deep* with predictive output; the reading is defeasible and produces testable claims about inhabitation. Resist revising toward unified-reading where the place legitimately admits conflicting affordances or contested readings — the conflict is part of the place, not a defect of the analysis.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a descriptive-evaluative-deep place reading: place-and-scale lock, prospect-refuge-hazard atoms grounded in specific spatial features, pattern-language atoms with (context, problem, solution) triple checked per pattern, Lynchian five-element atoms identified by cognitive-mapping role, ART/biophilic atoms, genius-loci gestalt atom, Bachelardian topoanalysis atoms where applicable, predicted-inhabitation atoms as testable behavioral claims, design-affordance recommendations keyed to specific features, and counter-readings preserved**. The atoms are:

1. **Place-and-scale lock atom.** The place being read plus its scale (room / building / garden / neighbourhood / landscape). The reading holds the lock; subsequent atoms reference it.

2. **Prospect-refuge-hazard atoms.** Each atom names: a specific prospect (sightline geometry), a specific refuge (enclosure position), and the hazards mitigated or unmitigated. Prospect-refuge-as-label is the named failure mode the consolidator watches for; Appleton-vocabulary atoms invoked without spatial warrant get reshaped to feature-grounded atoms.

3. **Pattern-language atoms.** Each atom names one Alexander pattern (light-on-two-sides, sitting-circle, intimacy-gradient, alcoves, window-place, etc.) — present, absent, or violated — with the (`context`, `problem`, `solution`) triple checked. Pattern-misapplication is the named failure mode; pattern names used as decoration without the triple-check get reshaped.

4. **Lynchian-element atoms.** Each atom identifies one of Lynch's five elements (`paths`, `edges`, `districts`, `nodes`, `landmarks`) by the cognitive-mapping role it plays for an actual user — not by mechanical pattern-matching. The place's overall legibility is assessed as a separate atom. Lynchian-element-confusion is the named failure mode.

5. **Restorative-properties atoms.** Each atom carries an ART assessment (`being-away`, `extent`, `compatibility`, `soft fascination`) plus biophilic-pattern presence where applicable, grounded in concrete spatial features.

6. **Genius-loci atom.** A single qualitative-total-character articulation per Norberg-Schulz — the gestalt of place, with orientation (the user's spatial position-taking) and identification (the user's belonging) assessed. Aggregate-as-gestalt is the named failure mode; a feature-list that does not articulate the qualitative whole gets reshaped, or marked `not-yet-coherent — place lacks unified character`.

7. **Bachelardian-topoanalysis atoms — when applicable.** Where the place includes intimate-space features (corner, miniature, intimate immensity, drawer-as-threshold, nest, shell), each carries a brief topoanalytic note. Where scale or character does not invite topoanalysis, this is marked `not-applicable`.

8. **Predicted-inhabitation atoms.** Each atom is a *testable behavioral claim*: where people will linger, where they will pass through, where conversations will cluster, what activities the space supports or refuses, restorative or depleting effect. Sentiment-only-reading is the named failure mode; statements like "this space feels welcoming" without behavioral predictions get reshaped.

9. **Design-affordance recommendation atoms.** Each atom names: a specific change keyed to a specific spatial feature, the affordance that change would unlock or close, and the tradeoffs.

10. **Inhabitant-variation atoms.** Each atom tests an affordance against an inhabitant of different stature, ability, age, or cultural vantage from the analyst's default. Default-inhabitant-bias is the named failure mode; readings that assume an able-bodied adult of the analyst's culture without testing get reshaped.

11. **Counter-reading atoms.** Where the place admits multiple legitimate readings (contested-place, conflicting affordances at different scales, multiple cultural vantages), counter-readings ride alongside the primary reading. Unified-reading-overreach is the named failure mode.

12. **Analyst-projection flag — when applicable.** Affordances asserted without grounding in concrete spatial features (dimensions, sightlines, light, materials, thresholds, scale) get flagged. Analyst-projection is the named failure mode.

13. **Confidence and falsifiability per finding.** Each major claim carries confidence and the conditions under which the reading would be falsified.

**Mode-specific bloat patterns to cut:**

- **Analyst projection** — affordances asserted from analyst preference without spatial-feature grounding.
- **Default-inhabitant bias** — affordances tested only against the analyst's own stature/ability/culture.
- **Prospect-refuge as label** — Appleton vocabulary invoked without specific sightlines, refuge positions, hazard mitigation.
- **Sentiment-only reading** — "welcoming / oppressive / serene" statements without testable behavioural predictions.
- **Aggregate-as-gestalt** — features listed under "genius loci" without articulating the qualitative-total character.
- **Unified-reading overreach** — assertion of a single character/affordance set when the place admits conflicting affordances or contested readings.
- **Pattern-language decoration** — Alexander pattern names invoked without checking (context, problem, solution) match.
- **Lynchian-element confusion** — any boundary treated as edge, any centre as node, without the cognitive-mapping role being assessed.
- **Tradition-cluster checkbox bloat** — addressing all six tradition-clusters at thin depth rather than addressing the operative ones substantively.

**What NOT to collapse:**

- **Counter-readings** — places admit multiple legitimate readings; the corpus preserves them rather than picking one when both have warrant.
- **Affordance conflicts across scales** — when an affordance at room-scale conflicts with one at building-scale, both readings survive with the scale-conflict named.
- **Stream disagreement about gestalt vs. aggregate** — when one stream articulated a coherent genius loci and another saw only feature-aggregate, the disagreement is a finding about whether the place has achieved unified character.
- **Cultural-context-dependent affordances** — affordances that surface for one cultural vantage and not another stay flagged with their vantage conditions.
- **Stream disagreement about pattern presence** — when one stream identified a pattern as active and another as absent or violated, both readings survive with their (context, problem, solution) reasoning.

## VERIFICATION CRITERIA

Verified means: place named and scale identified; prospect-refuge-hazard balance grounded in specific spatial features; active pattern-language patterns listed with (context, problem, solution) triple checked; Lynchian legibility assessment present; restorative properties assessment present (ART + biophilic where applicable); genius loci character-of-place articulated as gestalt where warranted (or marked as not-yet-coherent if the place lacks unified character); Bachelardian topoanalysis notes present where applicable (or marked not-applicable); predicted inhabitation and dwelling-modes are testable behavioral claims (not sentiment); at least three design affordance recommendations keyed to specific spatial features; at least one counter-reading or limit-acknowledgment present; the six critical questions are addressable from the output. Confidence per major finding accompanies each claim. Cross-reference to T19 territory-level open debates is noted where the reading depends on contested framing decisions (especially Debate 5 on AI implementability of perceptual operations for direct-image vs. verbal-description input).

## OUTPUT FORMAT GUIDANCE

The deliverable is a **place reading-with-affordance-predictions** — a descriptive-evaluative-deep articulation that walks the six tradition-clusters (prospect-refuge, pattern-language, Lynchian legibility, ART/biophilic, genius loci, Bachelardian topoanalysis) on a named place, grounds every claim in concrete spatial features, predicts testable inhabitation behaviours, and surfaces counter-readings where the place admits them. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Place summary and scale.** One paragraph naming the place, its scale, its intended or actual inhabitation context, and any temporal or cultural conditions that shape the reading.

2. **Prospect-refuge-hazard balance.** A labelled block. `**Prospect:** [sightline geometry — specific]. **Refuge:** [enclosure positions — specific]. **Hazards:** [mitigated / unmitigated — specific].` Each claim carries spatial-feature warrant.

3. **Active pattern-language patterns.** Bulleted list. Each: `**[Pattern name]** — status: [present / absent / violated]. Context match: [...]. Problem the pattern addresses here: [...]. Solution implemented or missing: [...].`

4. **Lynchian legibility assessment.** Labelled sub-blocks per element:
   - `**Paths:** [identification + cognitive-mapping role].`
   - `**Edges:** [...].`
   - `**Districts:** [...].`
   - `**Nodes:** [...].`
   - `**Landmarks:** [...].`
   
   Followed by: `**Overall legibility:** [how easy to form a mental map; what's clear, what's confused].`

5. **Restorative properties assessment.** One paragraph applying ART vocabulary: `**Being-away:** [...]. **Extent:** [...]. **Compatibility:** [...]. **Soft fascination:** [...].` Plus biophilic-pattern presence where applicable.

6. **Genius loci — character of place.** One paragraph articulating the qualitative-total character as gestalt, with orientation and identification assessed. When the place lacks unified character, this section states it explicitly: `**Genius loci status:** not-yet-coherent — the place lacks unified character because [reason].`

7. **Bachelardian topoanalysis notes.** Where applicable, bulleted list of intimate-space features and their psychological condensations. Where not applicable: `Not applicable — the place's scale and character do not invite topoanalysis.`

8. **Predicted inhabitation and dwelling modes.** Bulleted list of testable behavioral predictions. Each: `**[Predicted behavior — lingering / passing-through / conversation-clustering / activity-supported / restorative-vs-depleting]** — where in the space: [...]. What spatial features drive this prediction: [...]. How to test: [observable signal].`

9. **Design affordance recommendations.** Numbered list. Each: `[N]. **[Specific change — keyed to a specific feature]** — affordance unlocked or closed: [...]. Tradeoff: [...].`

10. **Confidence and counter-readings.** Bulleted list. Per major claim: `**Reading:** [...]. Confidence: [defeasible — basis]. Counter-reading (where place admits multiple readings): [...]. Falsifiability condition: [what would invalidate this reading].`

11. **Annotated visual overlay (when image attached).** When the user attached a photograph or raster image, optionally emit one `annotated_image` envelope to overlay annotations on the user's uploaded image at normalized image-relative coordinates. `canvas_action: annotate`; one envelope per response. Each annotation entry carries `kind` (callout / box / arrow / highlight / text), normalized `x: 0–1`, `y: 0–1` (top-left origin), and optional `width: 0–1`, `height: 0–1`, `to_x: 0–1`, `to_y: 0–1`. Use this overlay to mark prospect-refuge anchors, Lynchian landmarks / edges / nodes / districts / paths visible in the image, affordance loci (surfaced and foreclosed), and Alexander pattern instances where the pattern lands on specific image regions. Schema and full envelope skeleton in `modes/spatial-reasoning.md §7 Path B`.

**Per-section conventions:**

- Use H2 headings for sections 1 through 10.
- Vocabulary stays operative: Appleton (`prospect`, `refuge`, `hazard`); Alexander pattern names with `(context, problem, solution)`; Lynch's five elements with `cognitive-mapping role`; Kaplan ART (`being-away`, `extent`, `compatibility`, `soft fascination`); Norberg-Schulz (`orientation`, `identification`, `genius loci`); Bachelard (`intimate immensity`, `corner`, `miniature`, etc.). Vocabulary used decoratively without operative grounding is reshaped at this layer.
- Every affordance claim carries spatial-feature warrant — dimensions, sightlines, light, materials, thresholds, scale. Affordance assertions without feature grounding are reshaped to analyst-projection flags.
- Predicted behaviours (section 8) are *testable* — they name what observable signal would confirm or refute the prediction. Sentiment-only statements are reshaped here.
- When the inhabitant-variation test surfaced a vantage-dependent affordance, the deliverable carries a labelled `**Vantage-dependent affordance:** [affordance] — visible for [inhabitant vantage]; absent for [other vantage]. Implication: [...].`
- When the analysis encountered low-fidelity input (description insufficient for full spatial reading), the deliverable opens with: `**Note: input fidelity is insufficient for full spatial reading (per T19 Debate 4 on verbal-accessibility for AI implementation). Findings below are partial; specific features named are inferred rather than directly observed.**`
- When the operative compositional work is being done by held-open void rather than affordance/inhabitation, the deliverable opens with: `**Note: on reflection the operative work here may be done by held-open void rather than by affordance / inhabitation; ma-reading is the appropriate sideways-route.**`
- Confidence and counter-readings (section 10) are first-class; defeasibility is the mode's structural commitment.

## CAVEATS AND OPEN DEBATES

This mode does not carry mode-specific debates. Five territory-level debates (per Decision G) are documented in `Reference — Analytical Territories.md` T19 entry and bear on Place Reading specifically:

1. **Spatial vs. compositional framing.** Place Reading sits in spatial-composition territory (rooms, buildings, urban scenes); the temporal generalization (Cage / Ozu / Tarkovsky) is less directly relevant here than for ma-reading, but inhabitation has temporal dimensions (occupancy patterns, seasonal variation, lighting changes) that the reading must accommodate.
2. **Aesthetic-only or also abstract spatial inputs?** Place Reading sits on the *applied-and-experiential* side: the traditions (Alexander, Lynch, Appleton, Kaplan) operate on functional inhabited spaces, not pure aesthetic objects. The territory's coherence rests on the operation (read spatial structure as primary content with experiential / functional consequence) being shared with aesthetic-experiential modes (ma-reading) and applied modes (information-density).
3. **Western-analytical and Eastern-aesthetic: same operation or convergent traditions?** Place Reading is firmly Western-analytical (architecture / environmental psychology / cognitive mapping); the Eastern-aesthetic question bears on this mode's relationship to ma-reading more than on its internal stance.
4. **Verbal accessibility for AI implementation.** Place Reading is implementable for direct image input or high-fidelity verbal-spatial description (sightlines, dimensions, materials, thresholds); it degrades for rough sketch where critical features (refuge positions, hazard mitigation, light quality, scale) cannot be inferred. The pessimistic view — that perceptual grouping is not propositional — bears less on Place Reading than on Compositional Dynamics, because Place Reading's predictions are about behavior and use rather than perceptual phenomenology, but verbal accessibility remains a real constraint.
5. **Mode granularity: general vs. tradition-specific.** Whether Bachelardian topoanalysis (intimate immensity, corner, miniature) and biophilic design (Kellert et al.) should be promoted to first-class modes or remain stance-flags / vocabulary inside Place Reading. Currently the latter; Bachelard rides as a vocabulary cluster within Place Reading; Kellert biophilic patterns ride in the restorative-properties section. Revisit if outputs collapse or if biophilic-design workload becomes substantial.

These five debates are *not* re-documented here. They are referenced because they bear on Place Reading's stance, lens dependencies, and implementability. See the T19 entry in `Reference — Analytical Territories.md` for the full debate text and citations.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5-8min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `parent`, `child`, `analogous-to`, `qualifies`, `extends`
**Deprioritize:** `precedes`, `contradicts`

*Family: spatial-composition. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
