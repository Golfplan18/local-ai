---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01
---

# MODE: Compositional Dynamics

```yaml
# 0. IDENTITY
mode_id: compositional-dynamics
canonical_name: Compositional Dynamics
suffix_rule: analysis
educational_name: compositional dynamics analysis (Gestalt + Arnheim + Albers)

# 1. TERRITORY AND POSITION
territory: T19-spatial-composition
gradation_position:
  axis: specificity
  value: universal-perceptual
  stance_axis_value: descriptive
  depth_axis_value: medium
adjacent_modes_in_territory:
  - mode_id: ma-reading
    relationship: stance-counterpart (aesthetic-experiential contemplative-descriptive-deep; built Wave 2; Japanese aesthetics of void)
  - mode_id: place-reading-genius-loci
    relationship: specificity-counterpart (descriptive-evaluative-deep; affordance + inhabited-place; Wave 3)
  - mode_id: information-density
    relationship: specificity-counterpart (applied-evaluative-medium-depth; Tufte + Bertin + Cleveland-McGill; Wave 3)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "want to know how perception parses this composition"
    - "need a figure-ground / gestalt grouping read"
    - "want a visual-weight / structural-skeleton / force-pattern reading"
    - "want to know where the eye goes and why"
    - "want a universal-perceptual reading rather than a tradition-specific one"
  prompt_shape_signals:
    - "compositional dynamics"
    - "figure-ground"
    - "gestalt grouping"
    - "perceptual grouping"
    - "Arnheim"
    - "structural skeleton"
    - "visual weight"
    - "compositional forces"
    - "Itten"
    - "Albers"
    - "eye path"
    - "where the eye goes"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants the universal-perceptual reading: figure-ground, perceptual grouping, visual weight, structural skeleton, force vectors"
    - "user wants a descriptive analytical stance (predict the viewer's perceptual parse and the dynamic forces in play)"
    - "user wants Gestalt grouping principles + Arnheim compositional forces applied (with Itten color contrasts and Albers color-field interactions where applicable)"
  routes_away_when:
    - "user wants the void / interval / silence read as primary content (Japanese aesthetics)" → ma-reading
    - "user wants prospect-refuge / pattern-language / inhabited-place reading" → place-reading-genius-loci (Wave 3)
    - "user wants information-graphic / data-encoding analysis (Tufte / Bertin / Cleveland-McGill)" → information-density (Wave 3)
    - "user wants relation-extraction from a diagram (what does the diagram assert about A→B→C)" → relationship-mapping or spatial-reasoning (T11)
    - "user wants open-ended generative exploration of what the work opens up" → passion-exploration (T20)
when_not_to_invoke:
  - "Composition is non-visual or has no structural-perceptual organization (raw text, audio without spatial-imagistic component)" → other territory
  - "User wants the void as primary content (held-open emptiness)" → ma-reading
  - "User wants causal investigation or process analysis" → T4 / T17

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [spatial_composition, focal_question_or_use_case]
    optional: [grouping_cue_inventory, color_field_specifications, prior_perceptual_readings, design_intent_if_known, displacement_test_cases]
    notes: "Applies when user supplies the composition plus the focal question (e.g., 'is the figure-ground stable?', 'where do compositional forces land?', 'is the visual weight balanced?')."
  accessible_mode:
    required: [spatial_composition]
    optional: [what_user_notices, what_seems_off_or_strong]
    notes: "Default. Mode produces a perceptual parse and a force-pattern reading from the composition itself."
  detection:
    expert_signals: ["gestalt", "figure-ground", "border-ownership", "Wertheimer", "Köhler", "Koffka", "Wagemans", "Rubin", "Arnheim", "structural skeleton", "visual weight", "force vector", "Itten", "seven contrasts", "Albers", "Interaction of Color", "Hambidge", "dynamic symmetry"]
    accessible_signals: ["where the eye goes", "what jumps out", "is this balanced", "how is this composed"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe or share the composition (image / film still / page / diagram-as-image / room) you want a perceptual reading on?'"
    on_underspecified: "Ask: 'Are you noticing a specific perceptual question (figure-ground, eye-path, balance), or do you want a general perceptual-and-force reading?'"
output_contract:
  artifact_type: reading-with-vocabulary
  required_sections:
    - perceptual_parse_groupings_and_figure_ground
    - structural_skeleton_axes_and_center
    - visual_weight_per_element
    - force_vectors_and_named_tensions
    - dynamic_equilibrium_classification
    - predicted_eye_path
    - ambiguity_loci_and_alternative_parses
    - confidence_per_finding
  format: reading-with-vocabulary

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Does the proposed grouping survive a swap of grouping cues (e.g., proximity replaced with similarity)? If the grouping is brittle to cue substitution, the parse is local rather than structural."
    failure_mode_if_unmet: cue-fragile-grouping
  - cq_id: CQ2
    question: "Does the figure-ground assignment reverse under attention shift, or is it locked? Where it is contested, are the borders unambiguously owned, or contested? (Border-ownership test per Zhou, Friedman & von der Heydt.)"
    failure_mode_if_unmet: contested-border-asserted-as-stable
  - cq_id: CQ3
    question: "Does displacing an element by a small amount alter the reading substantively? (Tests whether the force-reading is doing analytical work or is post-hoc storytelling.)"
    failure_mode_if_unmet: post-hoc-force-story
  - cq_id: CQ4
    question: "Does the structural-skeleton assignment survive cropping? (Tests whether the skeleton is inherent to the composition or imposed by the analyst's frame-of-reference.)"
    failure_mode_if_unmet: imposed-skeleton
  - cq_id: CQ5
    question: "Are visual-weight assignments empirically defensible (size, contrast, color, isolation, position), or is the analyst asserting symbolic weight masquerading as visual weight?"
    failure_mode_if_unmet: symbolic-weight-confusion

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: cue-fragile-grouping
    detection_signal: "Reading proposes a grouping that depends on a single cue and would dissolve if the cue were swapped (proximity for similarity, etc.)."
    correction_protocol: re-dispatch
  - name: contested-border-asserted-as-stable
    detection_signal: "Reading asserts a stable figure-ground assignment for a composition where border-ownership is contested or the figure-ground reverses under attention shift."
    correction_protocol: re-dispatch
  - name: post-hoc-force-story
    detection_signal: "Reading describes force vectors and tensions that would survive arbitrary displacement of elements; the force-story is decorative rather than analytical."
    correction_protocol: re-dispatch
  - name: imposed-skeleton
    detection_signal: "Reading asserts a structural skeleton that does not survive cropping the composition; the skeleton is the analyst's frame, not the composition's."
    correction_protocol: re-dispatch
  - name: symbolic-weight-confusion
    detection_signal: "Reading attributes high visual weight to an element on grounds of meaning or symbol rather than empirical visual properties (size, contrast, isolation, position, color)."
    correction_protocol: re-dispatch
  - name: void-blindness
    detection_signal: "Reading produces a forces-and-grouping analysis on a composition where the operative work is being done by held-open void; ma-reading would have been the right mode."
    correction_protocol: flag (sideways escalation to ma-reading)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - gestalt-grouping-principles
    - arnheim-compositional-forces
  optional:
    - itten-seven-contrasts (when color contrast is central)
    - albers-interaction-of-color (when color-field interactions and figure-ground reversal via color are central)
    - hambidge-dynamic-symmetry (as proportional vocabulary; treat as tool, not warrant — empirical evidence weak)
    - tufte-data-ink-bertin-visual-variables-cleveland-mcgill-elementary-tasks (when input is an information graphic; cite per Wave 3 reserved-mode threshold)
    - bordwell-poetics-of-cinema (when input is a film still and mise-en-scène is in scope)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Compositional Dynamics is the medium-depth universal-perceptual mode in T19; deepening occurs by repeated readings rather than by escalation to a heavier sibling. (Place Reading and Information Density are stance/specificity counterparts, not depth-heavier siblings.)"
  sideways:
    target_mode_id: ma-reading
    when: "On reflection the operative compositional work is being done by held-open void rather than by figure-ground / grouping / force vectors; switch to the contemplative-descriptive-deep aesthetic reading."
  downward:
    target_mode_id: null
    when: "Compositional Dynamics is already the medium-depth mode; lighter perceptual surveys are not separately implemented."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Compositional Dynamics is the precision with which (1) the perceptual parse is predicted (groupings via proximity / similarity / common fate / good continuation / closure / symmetry / parallelism / common region / connectedness; figure-ground assignment with border-ownership), (2) the structural skeleton is identified (axes, center, frame), (3) visual weights are assigned to elements on empirical grounds (size, contrast, color, isolation, position, depth), (4) force vectors and named tensions are named, and (5) ambiguity-loci (where the parse is unstable; figure-ground reversal candidates) are surfaced. A thin pass produces a generic "this composition is balanced" verdict; a substantive pass predicts the viewer's perceptual parse with the cues responsible for each grouping, identifies the skeleton with cropping-robustness, assigns weights with empirical defensibility, names the dynamic equilibrium type (stable / unstable / directional), and surfaces ambiguity-loci. Test depth by asking: would small displacements of elements alter the reading substantively (i.e., is the reading doing analytical work or post-hoc storytelling)?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning across the two integrated traditions before narrowing: **Gestalt grouping and figure-ground** (Wertheimer / Köhler / Koffka founding work; Wagemans et al. 2012 century-of-gestalt review; Rubin 1921 figure-ground; border-ownership neurons per Zhou, Friedman & von der Heydt 2000) — predicts how perception parses the visual field; **Arnheim compositional forces** (*Art and Visual Perception*, *The Power of the Center*, *The Dynamics of Architectural Form*; McManus, Stöver & Kim 2011 partial empirical support for center-of-mass formalization) — predicts the force vectors, tensions, and dynamic equilibrium once the parse is established. Where applicable, scan also: **Itten** (seven color contrasts); **Albers** (color's absolute relativity, figure-ground reversal via color); **Hambidge** (proportional vocabulary, treated as tool with weak empirical warrant); **cinematic mise-en-scène** for film stills. Breadth markers: the reading has surveyed both gestalt parsing AND Arnheim forces (the M2+M3 integration) and has applied color/proportion lenses where relevant before producing findings.

## EVALUATION CRITERIA

Evaluate against the five critical questions: (CQ1) cue-swap robustness for groupings; (CQ2) border-ownership assignment for figure-ground; (CQ3) displacement-test for force vectors; (CQ4) cropping-robustness for skeleton; (CQ5) empirical defensibility of visual-weight assignments. The named failure modes (cue-fragile-grouping, contested-border-asserted-as-stable, post-hoc-force-story, imposed-skeleton, symbolic-weight-confusion, void-blindness) are the evaluation checklist. A passing Compositional Dynamics reading predicts the perceptual parse with cue-robustness, identifies the skeleton with cropping-robustness, assigns visual weights on empirical grounds, names force vectors with displacement-robustness, classifies the dynamic equilibrium, predicts an eye-path, and surfaces ambiguity-loci.

## REVISION GUIDANCE

Revise to perform the cue-swap test where the draft proposes brittle groupings. Revise to acknowledge contested borders where the draft asserts stable figure-ground. Revise to perform the displacement test where force vectors are decorative. Revise to perform the cropping test where the skeleton may be the analyst's imposition. Revise to substitute empirical visual-weight grounds where the draft attributes weight on symbolic-meaning grounds. Revise sideways to ma-reading where the operative work is being done by held-open void. Resist revising toward purely formal description without predicted consequence — the mode is descriptive of perceptual *dynamics*; a static catalogue of elements without parse-predictions and force-predictions is a thin pass, not the medium-depth reading the mode targets.

## CONSOLIDATION GUIDANCE

Consolidate as a reading-with-vocabulary artifact with the eight required sections. Perceptual parse lists groupings and figure-ground assignments with the cues responsible for each. Structural skeleton names axes, center, frame; cropping-robustness is noted. Visual weight per element is assigned on empirical grounds (size, contrast, color, isolation, position, depth). Force vectors and named tensions describe the directional pulls and stress points. Dynamic equilibrium classification states whether the composition is stable, unstable, or directional, and why. Predicted eye-path traces the likely fixation sequence. Ambiguity-loci and alternative parses surface where the reading is unstable (figure-ground reversal candidates, contested borders, weight-distribution alternatives). Confidence per finding accompanies each major claim.

## VERIFICATION CRITERIA

Verified means: groupings survive the cue-swap test (or are flagged as cue-fragile); figure-ground assignment is accompanied by border-ownership assessment; force vectors survive the displacement test; structural skeleton survives the cropping test; visual-weight assignments are on empirical grounds; ambiguity-loci are surfaced. The five critical questions are addressable from the output. Confidence per finding accompanies each major claim. Cross-reference to T19 territory-level open debates (especially Debate 3 on aesthetic-vs.-analytical scope and Debate 5 on AI implementability of perceptual operations) is noted where the reading depends on the descriptive-analytical commitment.

## CAVEATS AND OPEN DEBATES

This mode does not carry mode-specific debates. Five territory-level debates (per Decision G) are documented in `Reference — Analytical Territories.md` T19 entry and bear on Compositional Dynamics specifically:

1. **Spatial vs. compositional framing.** "Spatial Composition" preserves the spatial focus while allowing the underlying operation to generalize. Compositional Dynamics retains the spatial focus (gestalt operations are perceptually-spatial; Arnheim forces are spatial-compositional) but the territory's name carries the open question.
2. **Aesthetic-only or also abstract spatial inputs?** Compositional Dynamics sits squarely on the universal-perceptual side: the mode applies to dashboards, network diagrams (qua images), pages of typography, and ordinary visual layouts — not just to paintings. The unified territory rests on the claim that the perceptual-grouping and force operations are the same across aesthetic and applied inputs.
3. **Western-analytical and Eastern-aesthetic: same operation or convergent traditions?** Compositional Dynamics is the analytical-Western pole; ma-reading is the experiential-Eastern pole. The strong reading holds these are the same operation in different vocabularies; the weaker reading holds the epistemic warrants differ. The mode is implemented on the analytical side, with sideways-escalation to ma-reading flagged when the operative compositional work is being done by held-open void rather than by figure-ground/grouping/forces.
4. **Verbal accessibility for AI implementation.** Pessimistic view: gestalt grouping is perceptual, not propositional, and verbal descriptions cannot reproduce the phenomenology of border-ownership flips. Optimistic view: the AI's job is to predict consequences of structure, not have the experience. Middle view: implementable for direct image input or high-fidelity verbal description; degrades for rough sketch.
5. **Mode granularity: general vs. tradition-specific.** Whether information-graphic-specific operations (Tufte data-ink, Bertin visual variables, Cleveland-McGill elementary tasks) should be promoted to a dedicated Mode 5 (held in reserve per T19 territory documentation) or remain a specificity-variant inside Compositional Dynamics. Below the 15% info-graphic-invocation threshold (per Decision G), info-graphic inputs are routed through this mode with Tufte/Bertin/Cleveland citations; above the threshold, promote.

These five debates are *not* re-documented here. They are referenced because they bear on Compositional Dynamics's stance, lens dependencies, and mode-granularity boundary with the reserved Information-Graphic mode. See the T19 entry in `Reference — Analytical Territories.md` for the full debate text and citations.

**Integration note (M2 + M3 combined per locked decisions).** This mode combines M2 (Figure-Ground & Perceptual-Grouping Analysis / Gestalt-mode) and M3 (Compositional-Forces & Balance Analysis / Arnheim-mode) from the T19 reanalysis §3 mode catalog. The integration follows the locked decisions: M2 (perceptual parse) runs first conceptually, then M3 (forces among parsed elements) layers on top — the two operations are sequenced within a single mode because (a) they almost always co-occur on the same input, (b) M3 takes M2's output as input (forces operate on parsed groupings), and (c) splitting them would generate two modes whose outputs always cite each other. Itten's seven contrasts and Albers's *Interaction of Color* ride inside as optional lenses for color-driven figure-ground and force phenomena. The reserved Mode 5 (Information-Graphic Visual-Hierarchy Analysis, Tufte/Bertin/Cleveland) is held against the territory-level promotion threshold; below threshold, info-graphic inputs route through this mode.
</content>
</invoke>