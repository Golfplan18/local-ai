---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Ma Reading

```yaml
# 0. IDENTITY
mode_id: ma-reading
canonical_name: Ma Reading
suffix_rule: reading
educational_name: ma reading (Japanese aesthetics: void as content)

# 1. TERRITORY AND POSITION
territory: T19-spatial-composition
gradation_position:
  axis: specificity
  value: aesthetic-experiential
  stance_axis_value: contemplative-descriptive-deep
adjacent_modes_in_territory:
  - mode_id: compositional-dynamics
    relationship: stance-counterpart (universal-perceptual descriptive medium-depth; built Wave 2; covers gestalt grouping + Arnheim forces)
  - mode_id: place-reading-genius-loci
    relationship: specificity-counterpart (descriptive-evaluative-deep; affordance + inhabited-place; Wave 3)
  - mode_id: information-density
    relationship: specificity-counterpart (applied-evaluative-medium-depth; Tufte + Bertin + Cleveland-McGill; Wave 3)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "want a contemplative reading of the void / interval / silence in this composition"
    - "want to know what the empty space is doing"
    - "the apparent absence in this work seems to be load-bearing"
    - "want to surface the suggestion / withholding / depth-direction this work performs"
    - "ma in this garden / room / film frame / page / score is doing the work"
  prompt_shape_signals:
    - "ma reading"
    - "Ma"
    - "yūgen"
    - "wabi-sabi"
    - "mu"
    - "void as content"
    - "interval as content"
    - "the empty space here"
    - "Japanese aesthetic reading"
    - "what is the silence doing"
    - "Ozu pillow shot"
    - "Tarkovsky long take"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants the void / interval / silence read as primary content (not as residual negative space)"
    - "user wants contemplative-descriptive stance (the analysis participates in articulating the experience)"
    - "user wants Japanese-aesthetics vocabulary (Ma + Yūgen + Wabi-sabi + Mu) applied"
  routes_away_when:
    - "user wants the universal compositional-forces / gestalt reading (figure-ground, perceptual grouping, visual weight, Arnheim forces)" → compositional-dynamics
    - "user wants prospect-refuge / pattern-language / inhabited-place reading" → place-reading-genius-loci (Wave 3)
    - "user wants information-graphic / data-encoding analysis (Tufte / Bertin)" → information-density (Wave 3)
    - "user wants relation-extraction from a diagram (what does the diagram assert about A→B→C)" → relationship-mapping or spatial-reasoning (T11)
    - "user wants open-ended generative exploration of what the work opens up rather than analytical reading" → passion-exploration (T20)
when_not_to_invoke:
  - "Composition has no operative voids/intervals/silences (every element fills space; there is no held-open absence)" → compositional-dynamics
  - "Input is not a spatial composition (raw data, prose, instructions)" → other territory
  - "User wants causal investigation or process analysis" → T4 / T17

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: contemplative

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [spatial_composition, focal_voids_or_intervals_if_known]
    optional: [tradition_lineage_relevant, prior_readings, related_compositions, removal_or_alteration_test_cases]
    notes: "Applies when user supplies the composition plus specific voids/intervals to focus the reading on, or names the relevant tradition (Ma, Yūgen, Wabi-sabi, Mu, Ozu, Tarkovsky, Cage)."
  accessible_mode:
    required: [spatial_composition]
    optional: [what_user_notices_about_the_emptiness, why_user_wants_this_reading]
    notes: "Default. Mode identifies operative voids/intervals from the composition itself."
  detection:
    expert_signals: ["Ma", "間", "Yūgen", "Wabi-sabi", "Mu", "Isozaki", "Nitschke", "Itō", "Suzuki", "Okakura", "Tanizaki", "ma-ai", "Cage 4'33", "Ozu pillow shot", "Tarkovsky long take", "Sesshū splashed ink", "Ryōan-ji"]
    accessible_signals: ["the empty space here", "the silence", "the void in this", "what the absence is doing"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe or share the composition (image / film still / garden / room / page) you want a ma reading on, and roughly where the operative emptiness sits if you've noticed it?'"
    on_underspecified: "Ask: 'Are you noticing a specific void or interval doing work, or do you want me to surface what's load-bearing in the composition?'"
output_contract:
  artifact_type: reading
  required_sections:
    - operative_voids
    - what_each_does
    - what_would_collapse_without_it
    - suggestion_resonances
    - confidence_and_counter_readings
  format: reading-with-vocabulary

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Is the interval load-bearing for meaning, or is it incidental negative space? (If incidental, this is not a ma reading and the analysis should defer to compositional-dynamics for visual-weight balance.)"
    failure_mode_if_unmet: incidental-void-mistaken-for-ma
  - cq_id: CQ2
    question: "Is the void *active* — held open as content, generating rhythm / breath / suggestion / kami-space / ma-ai — or *passive* / residual?"
    failure_mode_if_unmet: passive-void-asserted-as-active
  - cq_id: CQ3
    question: "Would removing or altering the void substantively change the work? (If no — if a content of equal compositional weight could replace the void without loss — the mode does not apply.)"
    failure_mode_if_unmet: removal-test-failure
  - cq_id: CQ4
    question: "Is the apparent suggestion productive incompleteness (the viewer/listener invited to complete) or actually under-specification (failure of execution)? (Yūgen test.)"
    failure_mode_if_unmet: under-specification-mistaken-for-yūgen
  - cq_id: CQ5
    question: "Is the proposed reading falsifiable by a counter-example in the same tradition, or is it asserted as inviolable? (Defeasibility test — even contemplative readings carry critical questions whose negative answers invalidate them.)"
    failure_mode_if_unmet: inviolable-reading

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: incidental-void-mistaken-for-ma
    detection_signal: "Reading treats negative space as load-bearing without applying the removal-test or showing what each void is doing."
    correction_protocol: re-dispatch (or sideways to compositional-dynamics)
  - name: passive-void-asserted-as-active
    detection_signal: "Reading describes the void's effect without showing it is *held open as content* (generative) rather than residual."
    correction_protocol: re-dispatch
  - name: removal-test-failure
    detection_signal: "Reading does not perform the removal/alteration test (would replacing the void with content of equal weight alter the work substantively?)."
    correction_protocol: re-dispatch
  - name: under-specification-mistaken-for-yūgen
    detection_signal: "Reading attributes yūgen-like withholding to a work that is simply under-developed; the suggestion-resonances are projected by the reader rather than enabled by the work."
    correction_protocol: re-dispatch
  - name: inviolable-reading
    detection_signal: "Reading is asserted as inviolable (no counter-readings, no falsifiability conditions); contemplative stance has slid into devotional assertion."
    correction_protocol: re-dispatch
  - name: tradition-misappropriation
    detection_signal: "Reading invokes Ma/Yūgen/Wabi-sabi/Mu vocabulary on a composition that bears no engagement with those traditions, asserting an aesthetic genealogy that is not present."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - japanese-aesthetics-catalog
  optional:
    - cage-silence-and-framing-of-attention (when input is musical or temporal-composition)
    - bordwell-poetics-of-cinema (when input is film, especially Ozu)
    - schrader-transcendental-style (when input is slow-cinema lineage: Ozu / Bresson / Tarkovsky)
    - tanizaki-in-praise-of-shadows (when input involves shadow-as-material, lighting, or Japanese architectural interior)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Ma Reading is the deepest contemplative-descriptive mode in T19; deepening occurs by repeated readings rather than by escalation to a heavier sibling."
  sideways:
    target_mode_id: compositional-dynamics
    when: "On reflection the operative compositional work is being done by figure-ground / gestalt grouping / visual-weight forces rather than by held-open void; switch to the universal-perceptual reading."
  downward:
    target_mode_id: null
    when: "Ma Reading is the only contemplative-descriptive-deep mode in T19."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Ma Reading is the precision with which (1) operative voids/intervals are identified (not all empty space; only the empty space that is load-bearing), (2) what each void *does* is named in vocabulary the tradition supplies (rhythm, breath, suggestion, ma-ai, kami-space, narrative caesura, perceptual rest), (3) the removal/alteration test is performed (would replacing the void with content of equal weight alter the work?), and (4) suggestion-resonances are traced — what the void invites the viewer/listener to complete. A thin pass identifies emptiness and asserts ma; a substantive pass shows the void is held open as content (active), names what each void does in tradition-specific vocabulary, performs the removal test, and traces the resonances. Depth in this mode is *contemplative-deep* per T19 reanalysis M1: the analysis participates in articulating the experience, but it remains defeasible — every reading has critical questions whose negative answers invalidate it. Test depth by asking: would a practitioner of the relevant tradition (a tea master, a nō actor, a slow-cinema director) recognize the reading as articulating something present in the work?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning across the four Japanese-aesthetic operations before narrowing: **Ma** (the void/interval as primary content; placement-spacing rather than place; Isozaki / Nitschke / Itō); **Yūgen** (suggestion / withholding / depth-direction; Zeami; the dragon-veins of unpainted space; Suzuki's "cloudy impenetrability... not utter darkness"); **Wabi-sabi** (impermanence / asymmetry / shadow-as-material; Tanizaki's *In Praise of Shadows*); **Mu** (emptiness as generative reservoir; Suzuki / Okakura's "vacuum is all-potent because all-containing"). Where applicable, scan also: Cage's framing-of-attention silence; Ozu's pillow shots and intermediate spaces; Tarkovsky's sculpting in time; Sesshū's unpainted space. Breadth markers: the reading has surveyed which of the four operations are active in the composition (often one is primary, one or two are subsidiary; rarely all four) before narrowing the reading.

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) load-bearing vs. incidental; (CQ2) active vs. passive void; (CQ3) removal/alteration test performed; (CQ4) productive incompleteness vs. under-specification; (CQ5) defeasibility (counter-readings present). The named failure modes (incidental-void-mistaken-for-ma, passive-void-asserted-as-active, removal-test-failure, under-specification-mistaken-for-yūgen, inviolable-reading, tradition-misappropriation) are the evaluation checklist. A passing Ma Reading identifies operative voids, names what each does in tradition-specific vocabulary, performs the removal test per void, traces suggestion-resonances, and offers at least one counter-reading or specifies the conditions under which the reading would be falsified.

## REVISION GUIDANCE

Revise to perform the removal test where the draft asserts a void's load-bearing status without showing what would collapse without it. Revise to distinguish active (held-open) from passive (residual) voids where the draft conflates them. Revise to substitute under-specification readings where the draft attributes yūgen to a work that is merely under-developed. Revise to add counter-readings where the analysis asserts inviolability. Revise to specify the tradition's role explicitly where the analysis invokes Ma/Yūgen/Wabi-sabi/Mu vocabulary on works without engagement with those traditions. Resist revising toward analytical-distancing — the mode is contemplative-descriptive-deep by design (T19 reanalysis M1); the analysis participates in articulating the experience while remaining defeasible. The contemplative stance is structural to the mode and is what distinguishes it from compositional-dynamics.

## CONSOLIDATION GUIDANCE

Consolidate as a reading-with-vocabulary artifact with the five required sections. Operative voids are listed (not all empty space; only what is load-bearing). What each void does is named in tradition-specific vocabulary (rhythm, breath, suggestion, ma-ai, kami-space, narrative caesura, perceptual rest, gravel-as-ma, intermediate-space, transcendental-style duration, shadow-as-material). What would collapse without each void is stated explicitly (the removal/alteration test in narrative form). Suggestion-resonances per void traces what the void invites the viewer/listener to complete (yūgen depth-direction, wabi-sabi temporal-weathering, mu generative-reservoir). Confidence and counter-readings closes the artifact: at least one counter-reading per major claim, plus the conditions under which the reading would be falsified.

## VERIFICATION CRITERIA

Verified means: operative voids are identified (not all empty space); what each void does is named in tradition-specific vocabulary; the removal/alteration test is performed per void; suggestion-resonances are traced; at least one counter-reading is offered per major claim; the analysis has not slid into inviolable assertion. The five critical questions are addressable from the output. Confidence per finding accompanies each major claim. Cross-reference to T19 territory-level open debates (especially Debate 4 on Western-analytical vs. Eastern-experiential epistemic warrants and Debate 5 on AI implementability of perceptual operations) is noted where the reading depends on the contemplative-stance commitment.

## CAVEATS AND OPEN DEBATES

This mode does not carry mode-specific debates. Five territory-level debates (per Decision G) are documented in `Reference — Analytical Territories.md` T19 entry and bear on Ma Reading specifically:

1. **Spatial vs. compositional framing.** "Spatial Composition" preserves the spatial focus while allowing the underlying operation (interval-as-primary-content) to generalize to time-based compositions (Cage, Ozu, Tarkovsky). Ma Reading invokes both spatial (gardens, rooms, paintings) and temporal (pillow shots, long takes, silences) instances of the operation; the territory-level debate decides whether to keep the "spatial" name or generalize to "compositional dynamics."
2. **Aesthetic-only or also abstract spatial inputs?** Ma Reading sits firmly on the aesthetic-experiential side; the question is whether the territory unifies aesthetic and applied operations.
3. **Western-analytical and Eastern-aesthetic: same operation or convergent traditions?** The strong reading holds that gestalt's figure-ground inversion *is* what ma-reading does with different vocabulary; the weaker reading holds that the epistemic warrants differ (Western tradition is empirically falsifiable; Eastern tradition is constitutively experiential). This bears directly on Ma Reading's stance: analytical-predictive (treat ma-claims as predictions about viewer experience that could be tested) vs. contemplative-articulative (treat ma-claims as articulations of an experience the analysis participates in). The mode adopts contemplative-descriptive-deep posture (per T19 M1 spec) while retaining defeasibility (CQ5).
4. **Verbal accessibility for AI implementation.** Optimistic view: the AI's job is to predict consequences of structure, not have the experience. Pessimistic view: perceptual grouping (and arguably the experience of held-open void) is not propositional. Middle view: implementable for direct image input or high-fidelity verbal description; degrades for rough sketch.
5. **Mode granularity: general vs. tradition-specific.** Whether yūgen, wabi-sabi, and mu should be promoted to first-class modes or remain stance-flags / vocabulary inside Ma Reading. Currently the latter: Ma Reading is the home for the four-operation cluster; revisit if outputs collapse.

These five debates are *not* re-documented here. They are referenced because they bear on Ma Reading's stance, lens dependencies, and implementability. See the T19 entry in `Reference — Analytical Territories.md` for the full debate text and citations.
</content>
</invoke>