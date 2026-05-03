# Framework — Spatial Composition

*Self-contained framework for analyzing what the spatial composition itself does as primary content — voids, groupings, forces, affordances, information density. Compiled 2026-05-01.*

*Renamed from "Visual and Spatial Structure" per Decision G. Confirmed as a real territory by the T19 reanalysis. Existing `spatial-reasoning` mode re-homed to T11 (structural gap detection on diagrammatic input is a T11 operation on visual-medium input).*

---

## Territory Header

- **Territory ID:** T19
- **Name:** Spatial Composition
- **Super-cluster:** E (Synthesis, Orientation, Structure, Generation)
- **Characterization:** Operations that take a spatial composition (painting, garden, room, page, film frame, dashboard, urban scene, network diagram qua image) and analyze what the spatial structure itself does as primary content — voids, groupings, forces, affordances.
- **Boundary conditions:** Input is a bounded spatial composition (real or depicted). Excludes inter-element relationship extraction (T11 — that is what the diagram *says*; T19 is what the *layout* does), causal investigation (T4), and process analysis (T17). When input is a diagram, T11 and T19 may both fire on the same input answering different questions.
- **Primary axis:** Specificity (aesthetic-experiential vs. universal-perceptual vs. operational-applied).
- **Secondary axes:** Depth (surface-pattern → deep-affordance); stance (descriptive vs. critical vs. contemplative).
- **Coverage status:** Strong after Wave 3.

---

## When to use this framework

Use T19 when the input is a spatial composition and the question is what the layout/composition itself does as primary content — what the empty spaces do (Ma), how perception parses the structure (Compositional Dynamics), what affordances and inhabitation the place supports (Place Reading), how densely information is encoded without losing legibility (Information Density). T19 answers questions like "read this painting compositionally — what is the layout doing?", "what is the silence doing in this scene?", "will this room feel restorative or depleting?", "is this dashboard's visual encoding doing the right job?".

T19 does NOT do relation-extraction from a diagram qua notation (that is T11), causal investigation (T4), or process analysis (T17).

---

## Within-territory disambiguation

```
[Territory identified: spatial composition, layout-as-primary-content]

Q1 (stance + specificity): "Is this a contemplative reading of a composition
                             where what matters is what the empty spaces and the
                             still moments do (often aesthetic input — painting,
                             garden, room, page),
                             or an analytical reading of a composition where the
                             question is what the layout's structure makes possible
                             or impossible (often applied input — dashboard, urban
                             scene, information graphic),
                             or a deep place-reading where the question is what the
                             place itself is (genius loci, image of the place),
                             or specifically about how densely the composition packs
                             information without losing legibility?"
  ├─ "contemplative reading, aesthetic, what the voids and stillness do" →
        ma-reading (Wave 2, Japanese aesthetics)
  ├─ "universal compositional principles, what the layout does" →
        compositional-dynamics (Wave 2, Gestalt + Arnheim)
  ├─ "deep place-reading, what the place itself is" →
        place-reading-genius-loci (Wave 3, Alexander + Norberg-Schulz)
  ├─ "information density, how densely the composition packs information" →
        information-density (Wave 3, Tufte + Bertin)
  └─ ambiguous → compositional-dynamics (the universal-principle Tier-2 default
                  when the input doesn't signal aesthetic-vs.-applied clearly)
```

**Default route.** `compositional-dynamics` at Tier-2 when ambiguous (the universal-perceptual mode that applies across both aesthetic and applied inputs).

**Escalation hooks.**
- After `compositional-dynamics`: if the input is genuinely aesthetic and the user wants the contemplative mode that articulates what the voids and stillness do, hook sideways to `ma-reading`.
- After `ma-reading`: if the user wants an analytical/predictive complement to the contemplative reading, hook sideways to `compositional-dynamics`.
- After any of {`ma-reading`, `compositional-dynamics`}: if the question is fundamentally about *what this place is*, hook sideways to `place-reading-genius-loci`.
- After any T19 mode on a dashboard or chart: if the question is specifically chart-encoding-misfit rather than generic compositional critique, hook sideways to `information-density`.
- After any T19 mode on a network diagram: if the question is "what relations does this assert" rather than "what is the layout doing", hook sideways to T11 `spatial-reasoning` per the canonical T11↔T19 disambiguator.
- After any T19 mode: if the prompt is open-ended exploration rather than analytical reading, hook sideways to T20 (`passion-exploration`).

**Reserved-mode note.** A fifth candidate — Information-Graphic Visual-Hierarchy Analysis — is held in reserve. Promotion threshold: info-graphic critique workload exceeds ~15% of T19 invocations, *or* M2+M3 outputs on dashboards visibly fail to distinguish chart-encoding-misfit from generic compositional critique. Below threshold, route info-graphic inputs through Compositional Dynamics with Tufte/Bertin/Cleveland citations.

---

## Mode entries

### `ma-reading` — Ma Reading

**Educational name:** ma reading (Japanese aesthetics: void as content) (specificity-aesthetic-experiential, contemplative-descriptive-deep).

**Plain-language description.** Contemplative reading of the void / interval / silence in a composition. Identifies operative voids/intervals (not all empty space — only what is load-bearing); names what each void *does* in tradition-specific vocabulary (rhythm, breath, suggestion, ma-ai, kami-space, narrative caesura, perceptual rest); performs the removal/alteration test (would replacing the void with content of equal weight alter the work substantively?); traces suggestion-resonances (what the void invites the viewer/listener to complete); offers counter-readings and falsifiability conditions (defeasibility — even contemplative readings carry critical questions whose negative answers invalidate them).

**Critical questions.**
- CQ1: Is the interval load-bearing for meaning, or incidental negative space?
- CQ2: Is the void *active* (held open as content) or *passive* (residual)?
- CQ3: Would removing or altering the void substantively change the work?
- CQ4: Is the apparent suggestion productive incompleteness or under-specification (Yūgen test)?
- CQ5: Is the proposed reading falsifiable by a counter-example in the same tradition?

**Per-pipeline-stage guidance.**
- **Analyst.** Identify operative voids (load-bearing only); name what each does in tradition vocabulary; perform removal test; trace suggestion-resonances; offer counter-readings.
- **Evaluator.** Apply five critical questions; flag incidental-void-mistaken-for-ma, passive-void-asserted-as-active, removal-test-failure, under-specification-mistaken-for-yūgen, inviolable-reading, tradition-misappropriation.
- **Reviser.** Perform removal test where draft asserts load-bearing without showing what would collapse; distinguish active from passive voids; substitute under-specification reading where yūgen attributed to merely under-developed work; add counter-readings; resist analytical-distancing.
- **Verifier.** Confirm five required sections (operative_voids, what_each_does, what_would_collapse_without_it, suggestion_resonances, confidence_and_counter_readings).
- **Consolidator.** Merge as a reading-with-vocabulary artifact; tradition-specific vocabulary throughout; counter-readings closing.

**Source tradition.** Japanese aesthetics catalog (Ma + Yūgen + Wabi-sabi + Mu); Cage silence-and-framing-of-attention (musical/temporal); Bordwell poetics of cinema (film); Schrader transcendental style (slow-cinema lineage); Tanizaki *In Praise of Shadows* (shadow as material).

**Lens dependencies.**
- Required: japanese-aesthetics-catalog.
- Optional: cage-silence-and-framing-of-attention, bordwell-poetics-of-cinema, schrader-transcendental-style, tanizaki-in-praise-of-shadows.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `compositional-dynamics` — Compositional Dynamics

**Educational name:** compositional dynamics analysis (Gestalt + Arnheim + Albers) (specificity-universal-perceptual, descriptive-medium-depth).

**Plain-language description.** Universal-perceptual reading of a composition: predicts how perception parses the visual field (groupings via proximity / similarity / common fate / good continuation / closure / symmetry / parallelism / common region / connectedness; figure-ground assignment with border-ownership); identifies the structural skeleton (axes, center, frame); assigns visual weights to elements on empirical grounds (size, contrast, color, isolation, position, depth); names force vectors and tensions; classifies dynamic equilibrium (stable / unstable / directional); predicts eye-path; surfaces ambiguity-loci (figure-ground reversal candidates, contested borders).

**Critical questions.**
- CQ1: Does the proposed grouping survive a swap of grouping cues?
- CQ2: Does the figure-ground assignment reverse under attention shift, or is it locked? Where contested, are borders unambiguously owned?
- CQ3: Does displacing an element by a small amount alter the reading substantively?
- CQ4: Does the structural-skeleton assignment survive cropping?
- CQ5: Are visual-weight assignments empirically defensible, or is the analyst asserting symbolic weight masquerading as visual weight?

**Per-pipeline-stage guidance.**
- **Analyst.** Predict perceptual parse with cues responsible for each grouping; identify skeleton with cropping-robustness; assign weights on empirical grounds; name force vectors; classify dynamic equilibrium; predict eye-path; surface ambiguity-loci.
- **Evaluator.** Apply five critical questions; flag cue-fragile-grouping, contested-border-asserted-as-stable, post-hoc-force-story, imposed-skeleton, symbolic-weight-confusion, void-blindness.
- **Reviser.** Perform cue-swap, displacement, and cropping tests; substitute empirical visual-weight grounds for symbolic-meaning grounds; sideways to ma-reading where operative work is held-open void.
- **Verifier.** Confirm eight required sections (perceptual_parse_groupings_and_figure_ground, structural_skeleton_axes_and_center, visual_weight_per_element, force_vectors_and_named_tensions, dynamic_equilibrium_classification, predicted_eye_path, ambiguity_loci_and_alternative_parses, confidence_per_finding).
- **Consolidator.** Merge as a reading-with-vocabulary artifact; M2+M3 integration (Gestalt parse first, Arnheim forces layered on top).

**Source tradition.** Gestalt grouping principles (Wertheimer, Köhler, Koffka, Wagemans); Arnheim compositional forces; Itten seven contrasts (when color is central); Albers interaction of color (when color-field interactions central); Hambidge dynamic symmetry (proportional vocabulary, weak empirical warrant).

**Lens dependencies.**
- Required: gestalt-grouping-principles, arnheim-compositional-forces.
- Optional: itten-seven-contrasts, albers-interaction-of-color, hambidge-dynamic-symmetry, tufte-data-ink-bertin-visual-variables-cleveland-mcgill (when input is info-graphic), bordwell-poetics-of-cinema (when film still).
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `place-reading-genius-loci` — Place Reading and Genius Loci

**Educational name:** place-reading and genius loci analysis (Alexander, Norberg-Schulz, Lynch, Bachelard) (specificity-descriptive-evaluative-deep).

**Plain-language description.** Reading of an inhabited or inhabitable space (room, building, garden, urban scene, landscape) that integrates six analytical operations: prospect-refuge-hazard balance (Appleton); active pattern-language patterns (Alexander); Lynchian legibility (paths, edges, districts, nodes, landmarks); restorative properties (Kaplan & Kaplan ART; biophilic where applicable); genius loci character-of-place (Norberg-Schulz qualitative-total gestalt); Bachelardian topoanalysis (intimate spaces — corner, miniature, intimate immensity). Predicts inhabitation and dwelling-modes; recommends design affordances keyed to spatial features; survives inhabitant-vantage variation tests (different stature, ability, age, culture).

**Critical questions.**
- CQ1: Are proposed affordances grounded in features of the space, or projected by the analyst's preferences without spatial warrant?
- CQ2: Does the reading survive an inhabitant of different stature, ability, or culture?
- CQ3: Is the prospect-refuge analysis evidentially supported by spatial features, or asserted as a label?
- CQ4: Does the reading produce predictions of observable behavior, or only sentiment statements?
- CQ5: Has genius loci been treated as a gestalt rather than as an aggregate of features?
- CQ6: Has the reading acknowledged the limits — situations where affordance prediction depends on cultural/historical context the analysis lacks?

**Per-pipeline-stage guidance.**
- **Analyst.** Survey six tradition-clusters (prospect-refuge / pattern-language / Lynchian / restorative / genius loci / Bachelardian); ground affordances in concrete spatial features; produce testable behavioral predictions; offer counter-readings.
- **Evaluator.** Apply six critical questions; flag analyst-projection, default-inhabitant-bias, prospect-refuge-as-label, sentiment-only-reading, aggregate-as-gestalt, unified-reading-overreach, pattern-misapplication, lynchian-element-confusion.
- **Reviser.** Ground asserted affordances in spatial features; test inhabitant-vantage variation; apply prospect-refuge with spatial warrant; make behavioral predictions testable; articulate genius loci as gestalt; resist sentiment / aesthetic-only / wholeness-claim.
- **Verifier.** Confirm ten required sections (place_summary_and_scale, prospect_refuge_hazard_balance, active_pattern_language_patterns, lynchian_legibility_assessment, restorative_properties_assessment, genius_loci_character_of_place, bachelardian_topoanalysis_notes, predicted_inhabitation_and_dwelling_modes, design_affordance_recommendations, confidence_and_counter_readings).
- **Consolidator.** Merge as reading-with-vocabulary; place summary and scale first; six clusters in dedicated sections; predictions testable.

**Source tradition.** Alexander pattern language; Norberg-Schulz genius loci; Lynch image of the city; Bachelard topoanalysis; Appleton prospect-refuge; Kaplan attention restoration; Kellert biophilic design (optional); Alexander nature of order (optional); Tuan space-and-place (optional).

**Lens dependencies.**
- Required: alexander-pattern-language, norberg-schulz-genius-loci, lynch-image-of-the-city, bachelard-topoanalysis, appleton-prospect-refuge, kaplan-attention-restoration.
- Optional: kellert-biophilic-design, alexander-nature-of-order, tuan-space-and-place, relph-place-and-placelessness.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `information-density` — Information Density

**Educational name:** information density and visual hierarchy (Tufte, Bertin, Cleveland-McGill) (specificity-applied-evaluative-medium-depth).

**Plain-language description.** Critique-with-prescriptive-recommendations on an information graphic (chart, dashboard, table, infographic, map, typographic page). Audits data-ink ratio (Tufte — for each mark: data-ink, structure-ink, or chartjunk); checks visual-variable mapping for fitness (Bertin — selective / associative / ordered / quantitative); checks elementary-perceptual-task fitness (Cleveland-McGill — position-on-common-scale > nonaligned-position > length > angle > direction > area > volume > color/shading); analyzes typographic hierarchy and grid (Bringhurst, Lupton); inventories chartjunk and redundancy; produces ranked, specific prescriptive recommendations (which mark, which encoding, which removal, which hierarchy strengthening); acknowledges residual tradeoffs (brand / accessibility / data-honesty / audience-expectation).

**Critical questions.**
- CQ1: Has the elementary perceptual task been identified and encoding-fitness assessed (Cleveland-McGill)?
- CQ2: Has visual-variable mapping been checked for fitness against Bertin properties?
- CQ3: Has data-ink ratio been audited specifically (which marks carry data; which carry decoration), or asserted as a vague label?
- CQ4: Has typographic hierarchy and grid been analyzed where input includes typography?
- CQ5: Are prescriptive recommendations specific or general gestures?
- CQ6: Have residual tradeoffs and constraints been acknowledged?

**Per-pipeline-stage guidance.**
- **Analyst.** Identify elementary perceptual task; check Bertin variable-fitness per data attribute; audit data-ink mark-by-mark; analyze typographic hierarchy where applicable; produce specific recommendations ranked by impact; acknowledge constraints.
- **Evaluator.** Apply six critical questions; flag elementary-task-mismatch-undiagnosed, bertin-mapping-unchecked, data-ink-as-slogan, typography-as-not-encoding, recommendations-as-gestures, constraint-blindness, tufte-orthodoxy, aesthetic-only-critique, m5-promotion-evidence.
- **Reviser.** Identify task and check encoding-fitness where Cleveland-McGill skipped; check Bertin mapping; audit specific marks rather than assert "chartjunk"; analyze typography-as-encoding; make recommendations specific; acknowledge constraints.
- **Verifier.** Confirm nine required sections (graphic_summary_and_intended_message, data_ink_ratio_audit, visual_variable_to_data_attribute_mapping_check, elementary_perceptual_task_fitness_check, typographic_hierarchy_and_grid_analysis, chartjunk_and_redundancy_inventory, prescriptive_recommendations_ranked, residual_tradeoffs_and_constraints, confidence_per_recommendation).
- **Consolidator.** Merge as critique-with-prescriptive-recommendations; recommendations ranked by impact; each keyed to operation that diagnosed problem.

**Source tradition.** Tufte data-ink and chartjunk; Bertin visual variables; Cleveland-McGill elementary perceptual tasks; Bringhurst typographic hierarchy; Lupton thinking with type; Few information-dashboard design (optional); Munzner visualization analysis and design (optional); Wilkinson grammar of graphics (optional).

**Lens dependencies.**
- Required: tufte-data-ink-chartjunk, bertin-visual-variables, cleveland-mcgill-perceptual-tasks, bringhurst-typographic-hierarchy.
- Optional: lupton-thinking-with-type, few-information-dashboard-design, munzner-visualization-analysis-and-design, kosslyn-graph-design, wilkinson-grammar-of-graphics.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

---

## Cross-territory adjacencies

### T11 ↔ T19 (Structural Relationship ↔ Spatial Composition)

**Why adjacent.** Same input — a diagram or visual artifact — answers different questions. T11 reads the diagram as notation: what relations are asserted among elements. T19 reads the diagram as composition: what the layout itself is doing.

**Disambiguating question.** "Is the question about what relations the diagram asserts among elements, or about what the layout or composition itself is doing?"

**Routing.** Relation-extraction (the diagram-as-notation) → T11. Layout-doing (the diagram-as-composition) → T19.

**Sequential dispatch.** When both legitimately fire on the same input, T11 runs first (relation-extraction is the lighter, more determinate operation); T19 layers compositional reading on top.

### T19 ↔ T20 (Spatial Composition ↔ Open Exploration)

**Disambiguating question.** "Are you asking for analytical reading of the composition (defeasible operations), or for open-ended exploration of what it opens up?"

**Routing.** Analytical reading → T19. Open exploration → T20. Both may fire when input is aesthetic and prompt is broad.

---

## Lens references (Core Structure embedded)

### Japanese Aesthetics Catalog (required for ma-reading)

**Core Structure.** Four concepts as a stack:
- **Ma (間)** — Interval as primary content. Voids are *generators* of content; the kami needs space to enter; the listener needs silence to hear; the eye needs interval to see relation. Output: name operative voids, characterize what each does, identify what would collapse without it, offer counter-readings.
- **Yūgen (幽玄)** — Suggestion / mysterious depth. Show less to invite more. The work *withholds* — declines to make the central content fully explicit — and the withholding generates depth. Output: identify withholding structures, trace how withholding generates depth, distinguish productive incompleteness from under-specification.
- **Wabi-sabi (侘寂)** — Patina, shadow, imperfection. Read materials, surfaces, and lighting as compositional elements *with temporal depth*. Patina, weathering, asymmetry, and shadow are not defects but materials. Output: identify what the work refuses to perfect, name the specific imperfection foregrounded, account for how imperfection produces quality, read shadow as figure.
- **Mu (無)** — Emptiness as generative reservoir. Provides the metaphysical warrant for treating void as primary content (vs. residual). Output: when invoked, disclose the metaphysical commitment that warrants treating voids seriously.

The four are not interchangeable — concept-melt (blending into a generic "Japanese aesthetic") is the dominant failure mode. A typical T19 ma-reading invokes Ma as primary, Yūgen as flavor when void generates suggestion, Wabi-sabi as flavor when surfaces carry temporal weathering, Mu as disclosed metaphysical stance.

### Gestalt Grouping Principles (required for compositional-dynamics)

**Core Structure.** Wertheimer / Köhler / Koffka founding principles, with later refinements (Wagemans et al. 2012 century-of-gestalt review):
- **Proximity** — items close together are perceived as grouped.
- **Similarity** — items sharing features (color, shape, size) are perceived as grouped.
- **Common fate** — items moving together are perceived as grouped.
- **Good continuation** — items along a smooth continuous line/curve are perceived as belonging together.
- **Closure** — incomplete shapes are perceived as complete.
- **Symmetry** — symmetrical regions are perceived as figure.
- **Parallelism** — parallel elements are perceived as related.
- **Common region** — items sharing an enclosing region are perceived as grouped.
- **Connectedness** — physically connected items are perceived as one unit.
- **Figure-ground** — perception assigns one region as figure (with shape, owned border) and another as ground (formless, unowned). Border-ownership (Zhou, Friedman & von der Heydt 2000) is determined by visual cues; figure-ground can reverse under attention shift in ambiguous compositions (Rubin's vase).

Cue-swap robustness: a genuine grouping survives substitution of one cue for another (proximity replaced with similarity); cue-fragile groupings collapse under substitution.

### Arnheim Compositional Forces (required for compositional-dynamics)

**Core Structure.** Rudolf Arnheim's framework:
- **Structural skeleton** — every composition has a latent skeleton (axes, center, frame) determined by the bounding shape; elements feel "in place" or "out of place" relative to the skeleton.
- **Visual weight** — elements have weight determined by size, contrast, color, isolation, position (high vs. low), depth. Heavier elements pull the eye more strongly.
- **Force vectors** — directional pulls produced by element shapes, gazes, motion lines, and the skeleton itself. Compositions have implicit force fields.
- **Dynamic equilibrium** — a composition is in stable equilibrium when forces balance, unstable when they cumulate, directional when they point.
- **Center as load-bearing position** — the geometric center of a composition is structurally privileged; placement at center carries different meaning than placement elsewhere.

Tests for analytical work: displacement (small displacement should alter the reading if force-vectors are doing work), cropping (skeleton should survive cropping if inherent rather than imposed), empirical visual-weight (assignments must rest on size/contrast/color/isolation/position/depth, not symbolic meaning).

### Alexander Pattern Language (required for place-reading-genius-loci)

**Core Structure.** Christopher Alexander's pattern language: 253 patterns organized hierarchically (region → town → neighborhood → building → room → construction) where each pattern names a (context, problem, solution) triple. Examples:
- **Light on Two Sides of Every Room** — context: rooms in buildings; problem: rooms with light on one side feel dim and uncomfortable; solution: arrange every room to have natural light from two or more sides.
- **Sitting Circle** — context: where people gather to talk; problem: rectangular arrangements suppress conversation; solution: arrange seating in a rough circle facing inward.
- **Intimacy Gradient** — context: building entry to private spaces; problem: visitors and inhabitants need different degrees of access; solution: sequence rooms from public to intimate.
- **Alcoves** — context: large rooms; problem: large rooms are unsuitable for small intimate activities; solution: provide alcoves off the main room for two or three people.

The discipline: invoke patterns by checking the (context, problem, solution) triple matches the space; pattern-name-as-decoration without triple-check is a failure mode.

### Norberg-Schulz Genius Loci (required for place-reading-genius-loci)

**Core Structure.** Christian Norberg-Schulz's phenomenology of architecture: place is a *qualitative-total phenomenon* — a gestalt that cannot be reduced to features. Two operations:
- **Orientation** — knowing where you are in the place; depends on landmarks, paths, edges, identifiable spaces.
- **Identification** — feeling a sense of belonging or character; depends on the place's distinctive qualities.

Genius loci is the place's character — what the place itself *is*. The reading must articulate this as gestalt, not as feature-aggregate. Aggregate-as-gestalt is the failure mode: listing features without showing how they compose into the qualitative-total.

### Lynch Image of the City (required for place-reading-genius-loci)

**Core Structure.** Kevin Lynch's five elements of cognitive mapping in urban environments:
- **Paths** — channels along which observers move (streets, walkways, transit).
- **Edges** — linear elements not used as paths (walls, shorelines, boundaries).
- **Districts** — medium-to-large sections with shared character.
- **Nodes** — strategic spots, focal points (intersections, plazas, junctions).
- **Landmarks** — point references external to the observer (towers, monuments, distinctive features).

Lynchian legibility is the degree to which a place's image is "read" easily by an observer. The discipline: identify the five elements by their cognitive-mapping role for an actual user, not as labels mechanically applied to any boundary or center.

### Appleton Prospect-Refuge (required for place-reading-genius-loci)

**Core Structure.** Jay Appleton's habitat theory: human aesthetic preferences are shaped by ancestral landscape needs:
- **Prospect** — the ability to see (sightlines, vantage, openness).
- **Refuge** — the ability to hide (enclosure, concealment, shelter).
- **Hazard** — threats that must be avoided.

Spaces that balance prospect and refuge with hazard mitigated are preferred. The reading must ground prospect-refuge claims in specific spatial features (sightlines for prospect, refuge positions, hazard mitigation) — prospect-refuge-as-label is the failure mode.

### Kaplan Attention Restoration Theory (ART) (required for place-reading-genius-loci)

**Core Structure.** Rachel and Stephen Kaplan's theory: certain environments restore depleted directed-attention capacity. Four components of restorative environments:
- **Being away** — psychological distance from demands.
- **Extent** — sense of being in a whole other world (richness, coherence).
- **Compatibility** — environment supports the activities one wishes to engage in.
- **Soft fascination** — effortless attention drawn by environment's qualities (clouds, water, foliage in motion).

Combined with biophilic-design patterns (when sustained-occupancy biophilic patterns are central) — Kellert et al.

### Bachelard Topoanalysis (required for place-reading-genius-loci)

**Core Structure.** Gaston Bachelard's *Poetics of Space*: intimate spaces and their psychological condensations. Key concepts:
- **The corner** — refuge of immobility; psychological retreat.
- **The miniature** — invitation to imagination; the small as condensation of the vast.
- **Intimate immensity** — interior vastness disproportionate to physical scale.
- **The drawer, the chest, the wardrobe** — containers as thresholds; depths of memory.
- **The nest** — primal refuge; the house as nest.
- **The shell** — geometric refuge; the curve of return.

Used where the place includes intimate-space features; absent or marked not-applicable where scale or character does not invite topoanalysis.

### Tufte Data-Ink and Chartjunk (required for information-density)

**Core Structure.** Edward Tufte's principles:
- **Data-ink ratio** — proportion of a graphic's ink that depicts data, vs. ink that depicts scaffolding (axes, legends) or decoration (chartjunk). Maximize data-ink within reason.
- **Chartjunk** — non-data ink that serves no analytical purpose: grid moiré, 3D effects on 2D data, gratuitous ornamentation.
- **Small multiples** — repeated parallel structures across a series, allowing comparison.
- **Sparklines** — word-sized graphics embedded in text.

Discipline: audit specific marks (data-ink / structure-ink / chartjunk per mark), do not invoke "chartjunk" as a label without specific identification.

### Bertin Visual Variables (required for information-density)

**Core Structure.** Jacques Bertin's seven visual variables × four properties:
- **Variables** — position, size, shape, value, color (hue), orientation, texture.
- **Properties** — selective (can isolate), associative (can group), ordered (carries order), quantitative (carries proportion).

Position is all four. Value is selective + associative + ordered (not quantitative reliably). Color (hue) is selective + associative (not ordered, not quantitative). Mismatching a data attribute to a variable lacking the required property is encoding misfit (e.g., quantitative data on color hue).

### Cleveland-McGill Elementary Perceptual Tasks (required for information-density)

**Core Structure.** Ranking of perceptual tasks by accuracy of judgment:
1. Position on a common scale.
2. Position on identical, nonaligned scales.
3. Length.
4. Angle.
5. Direction.
6. Area.
7. Volume.
8. Color (hue, saturation, lightness — depends on dimension).

Charts impose a perceptual task by their encoding (pie charts ask for angle/area; horizontal bar charts ask for length). Encoding misfit is using a less-accurate task than the message demands. Discipline: identify the task the chart requires and assess fitness against the message's accuracy demands.

### Bringhurst Typographic Hierarchy (required for information-density)

**Core Structure.** Robert Bringhurst's *Elements of Typographic Style*:
- **Hierarchy** — visual ordering of importance via scale, weight, color, position.
- **Rhythm** — temporal/spatial regularity (line spacing, paragraph rhythm).
- **Measure** — line length appropriate to type size and reading speed (typically 45-75 characters).
- **Leading** — vertical space between lines (typically 120-145% of type size).
- **Grid** — invisible structural framework that aligns elements.

Typography is encoding when it carries information; discipline applies to chart labels, dashboard text, and page layout. Lupton's *Thinking with Type* serves as accessible companion treatment.

---

## Open debates carried at territory level (per Decision G)

Five debates surfaced by the T19 reanalysis are documented at the territory level rather than in mode specs:

### Debate 1 — Spatial vs. compositional framing

Is "spatial dynamics" the right name, or "compositional dynamics" (which generalizes to time-based compositions)? Holding "Spatial Composition" preserves the spatial focus while allowing the underlying operation (interval/structure-as-primary-content) to be acknowledged as transferable. Ma Reading invokes both spatial (gardens, rooms, paintings) and temporal (pillow shots, long takes, silences) instances of the operation; the territory-level debate decides whether to keep the "spatial" name or generalize.

### Debate 2 — Aesthetic-only or also abstract spatial inputs?

Some traditions (Bachelard, wabi-sabi) are aesthetic-experiential; others (Tufte, Bertin, Lynch) are applied-analytical on non-aesthetic spatial inputs. The mode population (M1–M4) cuts across both; the unified territory rests on the claim that the operation is the same across both — read spatial structure as primary content with experiential or functional consequence.

### Debate 3 — Western-analytical and Eastern-aesthetic: same operation or convergent traditions?

Strong reading: gestalt's figure-ground inversion *is* what ma-reading does, with different vocabulary. Weaker reading: epistemic warrants differ — Western tradition is empirically falsifiable, Eastern tradition is constitutively experiential. Bears on Ma Reading's stance (analytical-predictive vs. contemplative-articulative). Ma Reading currently adopts contemplative-descriptive-deep posture (per T19 M1 spec) while retaining defeasibility (CQ5).

### Debate 4 — Verbal accessibility for AI implementation

Pessimistic view: Compositional Dynamics requires actual visual processing because perceptual grouping is not propositional. Optimistic view: the AI's job is to predict consequences of structure, not have the experience. Middle view: implementable for direct image input or high-fidelity verbal description; degrades for rough sketch. Bears on which inputs the modes can serve and how confidence should be calibrated for verbal-only inputs.

### Debate 5 — Mode granularity: general vs. tradition-specific

Whether more tradition-specific modes (yūgen, wabi-sabi, cinematic-montage, Information-Graphic Visual-Hierarchy) should be promoted to first-class modes or remain stance-flags / vocabulary inside the four modes. Currently the latter; revisit if outputs collapse. The reserved-M5 (Information-Graphic Visual-Hierarchy Analysis) carries the explicit promotion threshold per T19 reanalysis: ~15% of T19 invocations or visible failure to distinguish encoding-misfit from generic compositional critique.

---

## Citations and source-tradition attributions

- Isozaki, A. (1979). *MA: Space-Time in Japan*. Cooper-Hewitt Museum. Foundation for Ma Reading.
- Nitschke, G. (1966). "MA: The Japanese Sense of Place." *Architectural Design*. Placement-vs-place distinction.
- Itō, T. & Kenmochi, T. (1978). *Ma no Nihon bunka*. Ma across architecture, music, dance, theater.
- Zeami, M. (c. 1402–1424). *Fūshikaden*. Foundational nō treatise; yūgen.
- Suzuki, D. T. (1959). *Zen and Japanese Culture*. Princeton University Press. Mu and yūgen synthetic treatment.
- Tanizaki, J. (1933). *In Praise of Shadows*. Wabi-sabi as compositional principle.
- Okakura, K. (1906). *The Book of Tea*. Mu in tea-ceremony architecture.
- Cage, J. (1952). *4'33"*. Temporal-composition realization of Ma operation.
- Wertheimer, M. (1923). *Untersuchungen zur Lehre von der Gestalt II*. Foundational gestalt principles.
- Wagemans, J. et al. (2012). "A century of Gestalt psychology in visual perception." *Psychological Bulletin*. Century review.
- Rubin, E. (1921). *Visuell wahrgenommene Figuren*. Figure-ground.
- Zhou, H., Friedman, H. S., & von der Heydt, R. (2000). "Coding of Border Ownership in Monkey Visual Cortex." *Journal of Neuroscience*.
- Arnheim, R. (1954/1974). *Art and Visual Perception*. University of California Press. Compositional forces.
- Arnheim, R. (1988). *The Power of the Center*. University of California Press. Center as load-bearing position.
- Itten, J. (1961). *The Art of Color*. Reinhold. Seven contrasts.
- Albers, J. (1963). *Interaction of Color*. Yale University Press.
- Alexander, C. et al. (1977). *A Pattern Language*. Oxford University Press. 253 patterns.
- Alexander, C. (2002–2004). *The Nature of Order*. CES (4 volumes). Wholeness and structure-preserving transformations.
- Norberg-Schulz, C. (1980). *Genius Loci: Towards a Phenomenology of Architecture*. Rizzoli.
- Lynch, K. (1960). *The Image of the City*. MIT Press. Five elements.
- Bachelard, G. (1958/1994). *The Poetics of Space*. Beacon Press.
- Appleton, J. (1975). *The Experience of Landscape*. Wiley. Prospect-refuge habitat theory.
- Kaplan, R. & Kaplan, S. (1989). *The Experience of Nature*. Cambridge University Press. Attention restoration.
- Kellert, S. R., Heerwagen, J., & Mador, M. (Eds.) (2008). *Biophilic Design*. Wiley.
- Tufte, E. R. (1983/2001). *The Visual Display of Quantitative Information* (2nd ed.). Graphics Press.
- Tufte, E. R. (1990). *Envisioning Information*. Graphics Press.
- Bertin, J. (1967/1983). *Semiology of Graphics*. Wisconsin. Visual variables.
- Cleveland, W. S. & McGill, R. (1984). "Graphical Perception: Theory, Experimentation, and Application to the Development of Graphical Methods." *JASA*.
- Bringhurst, R. (1992/2012). *The Elements of Typographic Style* (4th ed.). Hartley & Marks.
- Lupton, E. (2010). *Thinking with Type* (2nd ed.). Princeton Architectural Press.
- Few, S. (2006). *Information Dashboard Design*. O'Reilly.
- Munzner, T. (2014). *Visualization Analysis and Design*. CRC Press.
- Wilkinson, L. (2005). *The Grammar of Graphics* (2nd ed.). Springer.
- Bordwell, D. (2008). *Poetics of Cinema*. Routledge.
- Schrader, P. (1972). *Transcendental Style in Film: Ozu, Bresson, Dreyer*. University of California Press.
- Tuan, Y.-F. (1977). *Space and Place*. University of Minnesota Press.
- Relph, E. (1976). *Place and Placelessness*. Pion.
- Kahneman, D. & Tversky, A. (Various). Heuristics-and-biases catalog (foundational substrate).

*End of Framework — Spatial Composition.*
