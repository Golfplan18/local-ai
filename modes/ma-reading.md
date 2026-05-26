---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

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

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Ma Reading is a contemplative-descriptive-deep articulation of how operative voids and intervals do load-bearing work in a composition, applied in the Japanese-aesthetic vocabulary of Ma (void/interval-as-primary-content), Yūgen (suggestion / depth-direction), Wabi-sabi (impermanence / asymmetry / shadow-as-material), and Mu (emptiness as generative reservoir). The reading participates in articulating the experience rather than analysing it from outside — but remains defeasible: every claim carries at least one counter-reading or specifies the conditions under which it would be falsified. The mode is distinct from compositional-dynamics (universal-perceptual gestalt / Arnheim-forces reading), place-reading-genius-loci (affordance and inhabited-place), and information-density (Tufte / Bertin data-encoding analysis).

**Procedure.**

1. Scan the composition for voids/intervals; identify only those whose absence does work (apply the load-bearing test, not all empty space).
2. Survey which of the four Japanese-aesthetic operations are active in the composition (Ma / Yūgen / Wabi-sabi / Mu) — often one primary, one or two subsidiary; rarely all four.
3. Name what each operative void does in tradition-specific vocabulary (rhythm, breath, suggestion, ma-ai, kami-space, narrative caesura, perceptual rest, gravel-as-ma, intermediate-space, transcendental-style duration, shadow-as-material).
4. Perform the removal-test per operative void — what would collapse if the void were replaced by content of equal weight or its proportions altered? Active voids survive the test; passive / residual ones do not.
5. Trace suggestion-resonances — what the void invites the viewer/listener to complete (yūgen depth-direction, wabi-sabi temporal-weathering, mu generative-reservoir).
6. Distinguish productive incompleteness from under-specification — confirm the suggestion is enabled by the work, not projected by the reader onto under-developed material.
7. Ground tradition-vocabulary engagement — note where Ma / Yūgen / Wabi-sabi / Mu vocabulary is invoked via lineage, training, explicit reference, or clear convergent operation, vs. where its use would be appropriation.
8. Offer at least one counter-reading per major claim and specify the falsifiability condition — contemplative-stance with structural defeasibility, not devotional assertion.
9. Hold the contemplative posture throughout — articulate the experience, do not slide into clinical analytical-distance.

**Goal.** Produce a contemplative-descriptive-deep reading that identifies operative voids, names what each does in tradition-specific vocabulary, performs the removal-test, traces suggestion-resonances, and preserves defeasibility through counter-readings and falsifiability conditions.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — load-bearing vs incidental.** Is the interval load-bearing for meaning, or is it incidental negative space the analysis is mistaking for ma? Failure mode if unmet: `incidental-void-mistaken-for-ma`.
- **CQ2 — active vs passive void.** Is the void held open as content (generative — rhythm / breath / suggestion / kami-space / ma-ai) or passive / residual? Failure mode if unmet: `passive-void-asserted-as-active`.
- **CQ3 — removal test performed.** Would removing or altering the void substantively change the work — and has the analysis performed that test? Failure mode if unmet: `removal-test-failure`.
- **CQ4 — productive incompleteness vs under-specification.** Is the suggestion productive incompleteness (viewer invited to complete) or under-specification (failure of execution; the suggestion projected by the reader)? Failure mode if unmet: `under-specification-mistaken-for-yūgen`.
- **CQ5 — defeasibility.** Is the reading falsifiable by a counter-example in the same tradition, or asserted as inviolable? Failure mode if unmet: `inviolable-reading`.

A passing output identifies operative voids (not all empty space), names what each does in tradition-specific vocabulary, performs the removal-test per void, traces suggestion-resonances, and offers at least one counter-reading or specifies the conditions under which the reading would be falsified.

**Named failure modes.**

- *incidental-void-mistaken-for-ma* — reading treats negative space as load-bearing without applying the removal-test or showing what each void is doing.
- *passive-void-asserted-as-active* — reading describes the void's effect without showing it is held open as content (generative) rather than residual.
- *removal-test-failure* — reading does not perform the removal/alteration test.
- *under-specification-mistaken-for-yūgen* — reading attributes yūgen-like withholding to a work that is simply under-developed; the suggestion-resonances are projected by the reader.
- *inviolable-reading* — reading is asserted as inviolable; contemplative stance has slid into devotional assertion.
- *tradition-misappropriation* — reading invokes Ma/Yūgen/Wabi-sabi/Mu vocabulary on a composition that bears no engagement with those traditions, asserting an aesthetic genealogy that is not present.

## REVISION GUIDANCE

Revise to perform the removal test where the draft asserts a void's load-bearing status without showing what would collapse without it. Revise to distinguish active (held-open) from passive (residual) voids where the draft conflates them. Revise to substitute under-specification readings where the draft attributes yūgen to a work that is merely under-developed. Revise to add counter-readings where the analysis asserts inviolability. Revise to specify the tradition's role explicitly where the analysis invokes Ma/Yūgen/Wabi-sabi/Mu vocabulary on works without engagement with those traditions. Resist revising toward analytical-distancing — the mode is contemplative-descriptive-deep by design (T19 reanalysis M1); the analysis participates in articulating the experience while remaining defeasible. The contemplative stance is structural to the mode and is what distinguishes it from compositional-dynamics.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a contemplative-descriptive-deep reading: operative-void atoms (load-bearing only), what-each-does atoms in tradition-specific vocabulary, removal-test atoms, suggestion-resonance atoms, and counter-reading atoms preserving defeasibility**. The atoms are:

1. **Operative-void atoms.** Each atom names one void or interval that is *load-bearing* for meaning — not all empty space, only the empty space whose absence does work. Incidental-void-mistaken-for-ma is the named failure mode the consolidator watches for; atoms that treat residual negative space as ma without applying the removal test get reshaped or sideways-routed to compositional-dynamics.

2. **What-each-does atoms.** Each operative-void atom carries a what-it-does atom in tradition-specific vocabulary: `rhythm`, `breath`, `suggestion`, `ma-ai`, `kami-space`, `narrative caesura`, `perceptual rest`, `gravel-as-ma`, `intermediate-space`, `transcendental-style duration`, `shadow-as-material`. The vocabulary is operative, not decorative — each term carries its tradition-specific meaning. Passive-void-asserted-as-active is the named failure mode; atoms describing a void's effect without showing it is *held open as content* (generative) rather than residual get reshaped.

3. **Removal-test atoms.** Each operative-void atom carries an explicit removal-test atom: what would collapse if the void were replaced by content of equal compositional weight, or if its proportions were altered? Removal-test-failure is the named failure mode; atoms claiming load-bearing status without performing the test get reshaped.

4. **Suggestion-resonance atoms.** Each atom traces what a void invites the viewer/listener to complete: `yūgen depth-direction` (productive incompleteness, the dragon-veins of unpainted space), `wabi-sabi temporal-weathering` (impermanence reading), `mu generative-reservoir` (emptiness as all-potent because all-containing). Under-specification-mistaken-for-yūgen is the named failure mode; atoms that project suggestion-resonance onto under-developed work (where the projection comes from the reader rather than the work) get reshaped.

5. **Counter-reading atoms.** Each major claim carries at least one counter-reading or the conditions under which the reading would be falsified. Inviolable-reading is the named failure mode; contemplative-stance sliding into devotional assertion gets reshaped. Defeasibility is structural to the mode (CQ5).

6. **Tradition-engagement atoms.** Where Ma / Yūgen / Wabi-sabi / Mu vocabulary is invoked, each atom carries a brief grounding: how the work engages the tradition (lineage / training / explicit reference / clear convergent operation). Tradition-misappropriation is the named failure mode; invoking the vocabulary on work that bears no engagement with the traditions gets reshaped to flag the misappropriation or reshaped toward compositional-dynamics vocabulary.

7. **Active-operation count.** Where streams identified which of the four Japanese-aesthetic operations are active (Ma / Yūgen / Wabi-sabi / Mu), the count is preserved. Often one is primary, one or two subsidiary; rarely all four. Asserting all four where the work supports only one is bloat.

8. **Confidence and falsifiability per finding.** Each major claim carries confidence and the falsifiability condition (what would invalidate this reading? what counter-reading does the same evidence support?). Confidence is contemplative-defeasible, not absolute.

**Mode-specific bloat patterns to cut:**

- **Incidental void treated as ma** — negative space asserted as load-bearing without the removal test.
- **Passive void treated as active** — the void's effect described without showing it is held open as content rather than residual.
- **Removal-test skipped** — load-bearing claims without showing what would collapse.
- **Under-specification read as yūgen** — suggestion projected by the reader onto work that is merely under-developed.
- **Inviolable assertion** — contemplative-stance sliding into devotional reading; no counter-readings, no falsifiability conditions.
- **Tradition vocabulary on traditionless work** — invoking Ma/Yūgen/Wabi-sabi/Mu on work that bears no engagement with those traditions.
- **Analytical-distancing drift** — the contemplative posture eroded into clinical analysis. The contemplative stance is structural (T19 M1) and distinguishes the mode from compositional-dynamics; eroding it is reshaped at this layer.
- **All-four-operations claim** — asserting Ma + Yūgen + Wabi-sabi + Mu are all active when the work supports only one or two; the four operations are distinct and not interchangeable.

**What NOT to collapse:**

- **Counter-readings** — defeasibility is the mode's structural commitment; counter-readings ride alongside primary readings, never smoothed away.
- **Stream disagreement about which void is operative** — when streams identified different load-bearing voids in the same composition, both readings survive with their respective removal-test outcomes.
- **Stream disagreement about which Japanese-aesthetic operation is active** — when one stream read the work as primarily Ma and another as primarily Yūgen, both readings survive; the operations are distinct and the disagreement is a finding about the work.
- **Western-analytical vs. Eastern-experiential framings** — when one stream produced a contemplative-articulative reading and another a more analytical-predictive reading, both survive with their respective epistemic-warrant differences acknowledged.

## VERIFICATION CRITERIA

Verified means: operative voids are identified (not all empty space); what each void does is named in tradition-specific vocabulary; the removal/alteration test is performed per void; suggestion-resonances are traced; at least one counter-reading is offered per major claim; the analysis has not slid into inviolable assertion. The five critical questions are addressable from the output. Confidence per finding accompanies each major claim. Cross-reference to T19 territory-level open debates (especially Debate 4 on Western-analytical vs. Eastern-experiential epistemic warrants and Debate 5 on AI implementability of perceptual operations) is noted where the reading depends on the contemplative-stance commitment.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **ma reading-with-vocabulary** — a contemplative-descriptive-deep articulation of how operative voids/intervals do load-bearing work in the composition, in tradition-specific vocabulary, with the removal test performed and counter-readings preserved. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Operative voids.** Bulleted list. Each: `**[Void / interval]** — location in composition: [...]. Why load-bearing: [brief contemplative reading].` Only voids that survived the load-bearing test appear here; residual negative space is excluded.

2. **What each does.** Per operative void, one labelled sub-block: `**[Void]:** [what it does in tradition-specific vocabulary — rhythm / breath / suggestion / ma-ai / kami-space / narrative caesura / perceptual rest / gravel-as-ma / intermediate-space / transcendental-style duration / shadow-as-material]. [One paragraph contemplative articulation].` The vocabulary appears verbatim with operative meaning preserved.

3. **What would collapse without it.** Per operative void, one labelled sub-block: `**[Void]:** removal/alteration test — if [the void were replaced with content of equal weight, OR its proportions altered], what would change: [...]. What this confirms about the void's load-bearing status: [...].`

4. **Suggestion resonances.** Per operative void where applicable, one labelled sub-block tracing what the void invites the viewer/listener to complete: `**[Void] — yūgen depth-direction / wabi-sabi temporal-weathering / mu generative-reservoir:** [one paragraph tracing the resonance]. Distinction from under-specification: [why this is productive incompleteness rather than failure of execution].`

5. **Confidence and counter-readings.** Bulleted list. Per major claim: `**Reading:** [the primary reading]. Confidence: [contemplative-defeasible — basis]. Counter-reading: [the alternative the same evidence supports]. Falsifiability condition: [what would invalidate the primary reading].`

6. **Annotated visual overlay (when image attached).** When the user attached a photograph or raster image, optionally emit one `annotated_image` envelope to overlay annotations on the user's uploaded image at normalized image-relative coordinates. `canvas_action: annotate`; one envelope per response. Each annotation entry carries `kind` (callout / box / arrow / highlight / text), normalized `x: 0–1`, `y: 0–1` (top-left origin), and optional `width: 0–1`, `height: 0–1`, `to_x: 0–1`, `to_y: 0–1`. Use this overlay to mark held-open void regions doing operative compositional work, ma boundaries and threshold transitions, and yūgen / wabi-sabi / mu loci where the tradition vocabulary lands on specific image regions. Schema and full envelope skeleton in `modes/spatial-reasoning.md §7 Path B`.

**Per-section conventions:**

- Use H2 headings for sections 1 through 5.
- Tradition-specific vocabulary (Ma, Yūgen, Wabi-sabi, Mu, ma-ai, kami-space, transcendental-style) appears verbatim with operative meaning preserved; paraphrasing into generic aesthetic-vocabulary is reshaped at this layer.
- The contemplative stance is structural — the deliverable articulates the experience rather than explaining it from outside. Analytical-distancing drift is reshaped here.
- The removal-test (section 3) is performed for *every* operative void; absent removal-tests get reshaped before deliverable emission.
- Counter-readings (section 5) are first-class, not afterthoughts. Defeasibility is the mode's structural commitment and what distinguishes contemplative-deep stance from devotional reading.
- When a tradition-misappropriation flag survived consolidation (vocabulary invoked on work without lineage/training/reference engagement), the deliverable opens with: `**Note: this composition engages the [tradition] vocabulary via [convergent operation / explicit reference / training-lineage], but does not sit inside the [tradition] as a primary lineage; the reading honours what the work does without asserting an aesthetic genealogy it does not claim.**`
- When the operative work is being done by gestalt / Arnheim forces rather than held-open void (sideways-route signal to compositional-dynamics survived in the corpus), the deliverable opens with: `**Note: on reflection the compositional work here may be done by figure-ground / perceptual grouping / visual-weight forces rather than by held-open void; compositional-dynamics is the appropriate alternative reading.**`
- Confidence (section 5) is contemplative-defeasible per finding; collapsing to a single absolute confidence is reshaped at this layer.

## CAVEATS AND OPEN DEBATES

This mode does not carry mode-specific debates. Five territory-level debates (per Decision G) are documented in `Reference — Analytical Territories.md` T19 entry and bear on Ma Reading specifically:

1. **Spatial vs. compositional framing.** "Spatial Composition" preserves the spatial focus while allowing the underlying operation (interval-as-primary-content) to generalize to time-based compositions (Cage, Ozu, Tarkovsky). Ma Reading invokes both spatial (gardens, rooms, paintings) and temporal (pillow shots, long takes, silences) instances of the operation; the territory-level debate decides whether to keep the "spatial" name or generalize to "compositional dynamics."
2. **Aesthetic-only or also abstract spatial inputs?** Ma Reading sits firmly on the aesthetic-experiential side; the question is whether the territory unifies aesthetic and applied operations.
3. **Western-analytical and Eastern-aesthetic: same operation or convergent traditions?** The strong reading holds that gestalt's figure-ground inversion *is* what ma-reading does with different vocabulary; the weaker reading holds that the epistemic warrants differ (Western tradition is empirically falsifiable; Eastern tradition is constitutively experiential). This bears directly on Ma Reading's stance: analytical-predictive (treat ma-claims as predictions about viewer experience that could be tested) vs. contemplative-articulative (treat ma-claims as articulations of an experience the analysis participates in). The mode adopts contemplative-descriptive-deep posture (per T19 M1 spec) while retaining defeasibility (CQ5).
4. **Verbal accessibility for AI implementation.** Optimistic view: the AI's job is to predict consequences of structure, not have the experience. Pessimistic view: perceptual grouping (and arguably the experience of held-open void) is not propositional. Middle view: implementable for direct image input or high-fidelity verbal description; degrades for rough sketch.
5. **Mode granularity: general vs. tradition-specific.** Whether yūgen, wabi-sabi, and mu should be promoted to first-class modes or remain stance-flags / vocabulary inside Ma Reading. Currently the latter: Ma Reading is the home for the four-operation cluster; revisit if outputs collapse.

These five debates are *not* re-documented here. They are referenced because they bear on Ma Reading's stance, lens dependencies, and implementability. See the T19 entry in `Reference — Analytical Territories.md` for the full debate text and citations.


---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `parent`, `child`, `analogous-to`, `qualifies`, `extends`
**Deprioritize:** `precedes`, `contradicts`

*Family: spatial-composition. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
