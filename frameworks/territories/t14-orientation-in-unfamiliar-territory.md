# Framework — Orientation in Unfamiliar Territory

*Self-contained framework for producing structured orientation in an unfamiliar domain, problem space, or codebase — the lay of the land. Compiled 2026-05-01.*

---

## Territory Header

- **Territory ID:** T14
- **Name:** Orientation in Unfamiliar Territory
- **Super-cluster:** E (Synthesis, Orientation, Structure, Generation)
- **Characterization:** Operations that take an unfamiliar domain, problem space, or codebase and produce structured orientation for the user — the lay of the land.
- **Boundary conditions:** Input is a domain or space the user is new to. Excludes deep-domain expertise application; excludes generative open exploration of an interest area (T20).
- **Primary axis:** Depth (light Quick Orientation → thorough Terrain Mapping → molecular Domain Induction).
- **Secondary axes:** None at current population.
- **Coverage status:** Strong after Wave 4.

---

## When to use this framework

Use T14 when the user is new-to-domain and wants the lay of the land — what's here, where to start, what the major sub-areas are, what pitfalls to avoid. T14 produces an analytical map of an existing domain rather than generating new content. T14 answers questions like "I'm new to this — give me the lay of the land", "where do I start?", "what are the major positions in this field?", and "induct me into this domain properly".

T14 has three modes on a clean depth ladder: Quick Orientation (~1 min, light pass), Terrain Mapping (~5 min, thorough survey), Domain Induction (~10+ min, molecular pass producing what's here + connectivity + learning sequence).

T14 does NOT do generative exploration of where an interest could go (that is T20), relationship structure mapping of a known domain (that is T11), or deep concept clarification (that is T10).

---

## Within-territory disambiguation

```
[Territory identified: orientation in unfamiliar territory]

Q1 (depth): "Want a quick lay of the land — main landmarks, common pitfalls,
             where to start — or a thorough terrain map with the major sub-areas
             and their relationships, or a full induction that walks you in
             from first principles?"
  ├─ "quick lay of the land" → quick-orientation (Tier-1)
  ├─ "thorough terrain map" → terrain-mapping (Tier-2)
  ├─ "full induction from first principles" → domain-induction molecular
                                                (Tier-3 — confirm runtime)
  └─ ambiguous → terrain-mapping (the Tier-2 default per §5.6)
```

**Default route.** `terrain-mapping` at Tier-2 when ambiguous (the central thorough mode; quick-orientation is the lighter sibling, domain-induction the heavier molecular).

**Escalation hooks.**
- After `quick-orientation` Tier-1: if the user wants to actually settle into the domain rather than just reconnoiter, hook upward to `terrain-mapping`.
- After `terrain-mapping` Tier-2: if the user wants induction into the domain's reasoning patterns rather than just its layout, hook upward to `domain-induction` molecular.
- After any T14 mode: if orientation surfaces a generative interest the user wants to explore, hook sideways to T20 (`passion-exploration`).
- After any T14 mode: if the orientation produces a relationship map as side-effect that the user wants to elaborate, hook sideways to T11 (`relationship-mapping`).

---

## Mode entries

### `quick-orientation` — Quick Orientation

**Educational name:** quick orientation in unfamiliar terrain (depth-light).

**Plain-language description.** A ~1 min light pass: one-line domain definition, three-to-five major sub-areas spread across the domain (not concentrated in one corner), the foundational distinctions that organize the domain, entry points and first concepts a newcomer should learn first, common misconceptions to avoid, and an escalation pointer to terrain-mapping if deeper orientation is needed. The mode's value is in honest tier-1 restraint — it is forewarned-is-forearmed orientation, not a substitute for deeper engagement.

**Critical questions.**
- CQ1: Has the orientation actually surveyed the major sub-areas of the domain, or focused narrowly on one corner?
- CQ2: Are the foundational distinctions named load-bearing for the domain, or decorative?
- CQ3: Has the orientation flagged the predictable wrong impressions a newcomer would form from light exposure?
- CQ4: Has depth been honestly tier-1 (light), or has analysis crept into tier-2 territory and exceeded the user's time budget?

**Per-pipeline-stage guidance.**
- **Analyst.** Survey three-to-five sub-areas spread across the domain; name load-bearing distinctions; identify common misconceptions; offer entry points; stay within tier-1 budget.
- **Evaluator.** Verify sub-areas spread (not corner-concentrated); verify distinctions load-bearing not decorative; verify misconceptions flagged; verify scope honest.
- **Reviser.** Broaden coverage where draft has stayed in one corner; drop decorative distinctions for load-bearing ones; add common misconceptions; resist depth-creep.
- **Verifier.** Confirm six required sections (domain_one_line_definition, three_to_five_major_sub_areas, foundational_distinctions, entry_points_and_first_concepts, common_misconceptions_to_avoid, escalation_pointer_to_terrain_mapping_if_deeper_orientation_needed).
- **Consolidator.** Merge as a structured synthesis with one-line characterizations per sub-area.

**Source tradition.** General orienting practice; Kuhn paradigm-structure (when domain has competing paradigms).

**Lens dependencies.**
- Required: none.
- Optional: kuhn-paradigm-structure (when domain has competing paradigms).
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `terrain-mapping` — Terrain Mapping

**Educational name:** thorough orientation in unfamiliar terrain (depth-thorough).

**Plain-language description.** A ~5 min thorough survey: focus question, known territory (settled facts), unknown or contested territory (rival schools represented when domain has them), at least three open questions tied to specific concepts, the domain's organizing structure (hierarchy / hub-and-spoke / network), at least one cross-link to an adjacent domain (Novak's marker of integrative understanding), and a boundary statement naming what is out of scope. The mode classifies each major concept by epistemic status (known / contested / open) and stays at survey level (≤30% on any single sub-area).

**Critical questions.**
- CQ1: Are concepts classified as known / contested / open, with no contested position presented as settled (or vice versa)?
- CQ2: Does the map have at least one cross-link to an adjacent domain?
- CQ3: Does the prose stay at survey level (≤30% on any single sub-area)?
- CQ4: Does the map name what is out of scope — its boundary?

**Per-pipeline-stage guidance.**
- **Analyst.** Map known/contested/open territory; name organizing structure; surface ≥1 cross-link; generate ≥3 open questions tied to specific concepts; state boundary; ≥4 concepts with hierarchy levels.
- **Evaluator.** Verify epistemic-status classification; verify cross-link present; verify survey-level discipline; verify boundary stated; verify rival schools represented when domain has them.
- **Reviser.** Pull back from drilling too deeply; add epistemic-status labels where missing; add cross-links where map is flat tree; qualify contested positions presented as settled; resist authoritative tone where domain has rival schools.
- **Verifier.** Confirm seven required sections (focus_question, known_territory, unknown_or_contested_territory, open_questions_at_least_three, domain_structure, adjacent_connections, boundary_statement); confirm concept_map envelope discipline.
- **Consolidator.** Merge as a diagram-friendly mapping; concept_map envelope with ≥4 concepts, ≥2 linking phrases, ≥3 propositions, ≥1 with `is_cross_link: true`.

**Source tradition.** Novak concept-map tradition (cross-links as integrative-understanding marker); taxonomic frameworks per the target domain.

**Lens dependencies.**
- Required: none.
- Optional: novak-concept-map-tradition, taxonomic-frameworks-for-the-target-domain.
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Atomic.

### `domain-induction` — Domain Induction

**Educational name:** domain induction (orient + terrain-map + induct what to learn) (depth-molecular).

**Plain-language description.** A ~10+ min molecular pass that integrates three components: a quick-orientation fragment (rapid lay-of-the-land — key terms, dominant figures, central debates as breadth seed), a full terrain-mapping pass (thorough structure), and a structured-induction synthesis (what's connected to what, central nodes and bridge concepts, what to learn next sequenced by dependency, learning prerequisites, confidence map). The mode produces a learning architecture — not just a map but a path through the domain ordered by genuine dependency.

**Critical questions.**
- CQ1: Has the orientation surveyed the domain broadly enough, or has it privileged the dominant subfield?
- CQ2: Does connectivity-mapping actually identify dependencies and bridges, or does it list elements without showing relations?
- CQ3: Is the what-to-learn-next sequence ordered by genuine dependency, or by analyst convenience?
- CQ4: Does the induction respect the user's stated familiarity level and goal, or default to a generic survey?

**Per-pipeline-stage guidance.**
- **Analyst.** Run quick-orientation fragment; run terrain-mapping fully; merge into orientation-and-terrain document; build connectivity-mapping (central nodes, bridge concepts); produce dependency-ordered learning sequence; populate confidence map.
- **Evaluator.** Verify orientation surveyed broadly; verify connectivity shows relations not just lists; verify learning sequence dependency-ordered; verify familiarity level respected.
- **Reviser.** Deepen synthesis where it concatenates; add bridge concepts and central nodes; re-sequence learning path where dependencies out-of-order; respect stated goal vs. generic survey.
- **Verifier.** Confirm six required sections (what_is_here, whats_connected_to_what, central_nodes_and_bridge_concepts, what_to_learn_next_sequenced, learning_dependencies_and_prerequisites, confidence_map).
- **Consolidator.** Merge as a structured synthesis with provenance to component sources (quick-orientation fragment, terrain-mapping, synthesis); each section carries source attribution.

**Source tradition.** Bloom taxonomy (cognitive-level scaffolding for learning sequence); novice-expert cognition (when familiarity level is novice).

**Lens dependencies.**
- Required: none.
- Optional: bloom-taxonomy (when learning sequence requires cognitive-level scaffolding), novice-expert-cognition (when familiarity level is novice).
- Foundational: kahneman-tversky-bias-catalog.

**Composition.** Molecular. Components: quick-orientation (fragment, light-orientation-only), terrain-mapping (full). Synthesis stages: orientation-and-terrain-merge (parallel-merge), connectivity-mapping (sequenced-build), structured-induction (dialectical-resolution).

---

## Cross-territory adjacencies

### T14 ↔ T20 (Orientation ↔ Open Exploration)

**Why adjacent.** Both engage with unfamiliar or open spaces. T14 is analytical — what's here, what's the lay of the land. T20 is generative — what could be, what opens up.

**Disambiguating question.** "Trying to orient in an unfamiliar space (what's here), or generating in an open space (what could be)?"

**Routing.** Orienting → T14. Generating → T20.

**Examples.**
- "I'm new to this codebase — give me the lay of the land." → T14.
- "I'm interested in this area — help me explore where it might go." → T20.
- "What are the major positions in this field?" → T14.
- "What questions could I be asking here?" → T20 (Research Question Generation, deferred).

### T11 ↔ T14 (Relationship Mapping ↔ Orientation)

**Why adjacent.** Orientation often produces a relationship map as a side-effect. T14 is the right home when the user is new-to-domain; T11 is the right home when the user has entities and wants their relations made explicit.

**Routing.** New-to-domain → T14. Have entities + want relations → T11.

---

## Lens references (Core Structure embedded)

### Novak Concept-Map Tradition (optional for terrain-mapping)

**Core Structure.** A concept map is a structured relational artifact with three required elements:
- **Concepts** (≥4) at varying hierarchy levels.
- **Linking phrases** (≥2) labeling each connection.
- **Propositions** (≥3) — concept-link-concept triples that read as semantic claims.

A genuine concept map carries at least one **cross-link** (`is_cross_link: true`) — a connection bridging two otherwise-separate sub-trees. Cross-links are Novak's marker of integrative understanding: they indicate the mapper has seen a connection that the standard taxonomy of the domain does not assert. In Terrain Mapping, the cross-link to an adjacent domain is required as an anti-textbook-trap discipline: a flat tree without cross-links is the textbook overview, not a usable orientation map.

### Kuhn Paradigm Structure (optional for quick-orientation)

**Core Structure.** Kuhn's framework distinguishes:
- **Normal science** — puzzle-solving within an established paradigm; the paradigm is taken for granted.
- **Anomalies** — observations that resist the paradigm's puzzle-solving methods.
- **Crisis** — accumulating anomalies destabilize confidence in the paradigm.
- **Revolution** — a new paradigm arises that re-organizes the field.
- **Incommensurability** — proponents of different paradigms partly talk past each other because their vocabularies, exemplars, and standards of evidence diverge.

For quick-orientation, the Kuhn structure surfaces when a domain has competing paradigms: the orientation must distinguish settled (within-paradigm normal science) from contested (where rival paradigms divide the field) so the newcomer is not given one paradigm's view as the domain consensus.

### Bloom Taxonomy (optional for domain-induction)

**Core Structure.** Hierarchical taxonomy of cognitive levels (revised version):
- **Remember** — recall facts and basic concepts.
- **Understand** — explain ideas, summarize, classify.
- **Apply** — use information in new situations.
- **Analyze** — distinguish parts, find evidence to support generalizations.
- **Evaluate** — justify decisions, critique work.
- **Create** — produce new or original work.

For domain-induction, Bloom's hierarchy supports learning-sequence ordering: foundational concepts at the Remember and Understand levels must precede Apply / Analyze / Evaluate operations on those concepts. A learning sequence that orders by dependency can use Bloom's hierarchy to surface where prerequisite mismatches would cause learners to fail.

### Novice-Expert Cognition (optional for domain-induction)

**Core Structure.** Drawing on Chi, Glaser, and others: experts and novices differ not just in amount of knowledge but in:
- **Chunking** — experts organize knowledge into larger meaningful units (gestalt patterns), allowing them to perceive structure where novices see isolated elements.
- **Schema-driven perception** — experts apply domain schemas automatically; novices have to construct relations explicitly.
- **Forward vs. backward problem-solving** — experts work forward from problem features to solutions via schema; novices often work backward from desired solutions.
- **Self-monitoring** — experts have richer metacognition about their own reasoning.

For domain-induction, the novice-expert distinction means the learning sequence must build chunks and schemas, not just deliver facts. Dependency ordering matters because a schema that depends on an unbuilt sub-schema cannot be assembled.

---

## Open debates

T14 carries no territory-level open debates at present. Mode-level debates do not currently apply.

---

## Citations and source-tradition attributions

- Novak, J. D. & Cañas, A. J. (2008). *The Theory Underlying Concept Maps and How to Construct and Use Them*. IHMC Cmap Tools. Foundation for Terrain Mapping's concept-map output.
- Kuhn, T. S. (1962/1996). *The Structure of Scientific Revolutions* (3rd ed.). University of Chicago Press. Paradigm structure.
- Bloom, B. S. et al. (1956); Anderson & Krathwohl (2001). *A Taxonomy for Learning, Teaching, and Assessing*. Longman. Bloom revised.
- Chi, M. T. H., Feltovich, P. J., & Glaser, R. (1981). "Categorization and Representation of Physics Problems by Experts and Novices." *Cognitive Science*. Foundational novice-expert work.
- Ericsson, K. A. (Ed.) (2018). *The Cambridge Handbook of Expertise and Expert Performance* (2nd ed.). Cambridge University Press. Standard expertise reference.
- Kahneman, D. & Tversky, A. (Various). Heuristics-and-biases catalog (foundational substrate).

*End of Framework — Orientation in Unfamiliar Territory.*
