
# Domain Induction Analysis Framework

*A Framework for Producing a Domain Induction Document with Three Integrated Parts: (a) What Is Here in the Domain; (b) What's Connected to What; (c) What to Learn Next, Sequenced by Genuine Dependency.*

*Version 1.0*

*Bridge Strip: `[DIA — Domain Induction]`*

---

## Architectural Note

This framework supports the `domain-induction` mode, the depth-molecular operation in T14 (orientation in unfamiliar territory). The mode file at `Modes/domain-induction.md` carries the locked spec — molecular_spec.components, critical_questions, output_contract.required_sections — sufficient for the orchestrator to dispatch the two component operations (`quick-orientation` as fragment, `terrain-mapping` as full) and the three synthesis stages (orientation-and-terrain-merge, connectivity-mapping, structured-induction). This framework adds the procedural detail the spec does not carry: the elicitation prompts the orchestrator uses, the intermediate output formats, the per-stage quality gates, and the worked example showing the framework operating end-to-end.

The framework sits in T14's depth ladder above `quick-orientation` (T14-light, atomic, ~1 min lay-of-the-land) and `terrain-mapping` (T14-thorough, atomic, ~5 min concept map). It composes those siblings into a structured induction with explicit connectivity (central nodes, bridge concepts, dependencies) and a dependency-ordered learning sequence. The territory framework is implicit in `Modes/quick-orientation.md` and `Modes/terrain-mapping.md` — DIA is the heaviest analytical mode in T14.

---

## How to Use This File

This framework runs when the user is stepping into a new domain and wants more than orientation — they want a structured induction with a learning plan. DIA's value is in the synthesis stages: connectivity mapping (what's connected to what, central nodes, bridge concepts) and dependency-ordered learning sequence (what to learn next, in what order, with rationale per item).

DIA differs from quick-orientation (~1 min lay-of-the-land, no learning plan) and from terrain-mapping (~5 min thorough survey, no learning sequence). Use DIA when the user is committed to inducting into the domain, has time for the full molecular pass, and wants a learning plan tailored to their stated familiarity level and induction goal (research-level vs. working-knowledge vs. general-orientation).

Three invocation paths supported:

**User invocation:** the user invokes `domain-induction` directly with a domain name. The framework opens with brief progressive questioning to elicit prior familiarity level and induction goal.

**Pipeline-dispatched:** the four-stage pre-routing pipeline classifies the user's prompt as T14, depth-molecular, and dispatches DIA.

**Handoff from another mode:** terrain-mapping has surfaced that the user wants the learning sequence beyond the survey-level map. The handoff package includes the terrain map; DIA inherits it and runs the connectivity-mapping and structured-induction stages forward.

## INPUT CONTRACT

DIA requires:

- **Domain name** — the field, area, or topic being inducted into ("category theory," "cellular agriculture," "post-Keynesian macroeconomics," "Tibetan Buddhism's Madhyamaka tradition"). Elicit if missing: *"What's the domain you want to induct into?"*

DIA optionally accepts:

- **Prior familiarity level** — novice / some prior exposure / working knowledge in adjacent domain. If not provided, elicit: *"What's your prior familiarity — completely new, some general knowledge, or working knowledge in an adjacent domain?"*
- **Induction goal** — research-level (preparing to do original work in the domain) / working-knowledge (preparing to use the domain's tools or contribute as collaborator) / general-orientation (preparing to read about the domain with comprehension). Elicit if missing: *"Are you aiming for research-level depth, working-knowledge competence, or general orientation?"* Goal disconnection is a failure mode (CQ4: goal-disconnection).
- **Time budget for learning** — informs sequencing horizon.
- **Prior resources consulted** — books, papers, courses already encountered.
- **Why interested** — informs sub-area emphasis.

## STAGE PROTOCOL

### Stage 1 — Quick Orientation (runs: fragment, light-orientation-only)

**Purpose:** Produce the rapid lay-of-the-land as breadth seed: key terms, dominant figures, central debates. This is a fragment run — produce ONLY the lay-of-the-land, not the full quick-orientation output (which would include foundational distinctions, entry points, common misconceptions). The fragment serves as breadth seed for terrain-mapping in Stage 2.

**Elicitation prompt (orchestrator → model):**
> "You are running the `quick-orientation` mode in fragment mode (light-orientation-only) as Stage 1 of a Domain Induction pass. Domain: [domain]. Produce ONLY the rapid lay-of-the-land: domain one-line definition, three-to-five major sub-areas spread across the domain (not corner-concentrated), key terms a newcomer will encounter. Do NOT produce the full quick-orientation output (foundational distinctions, entry points, misconceptions — those are Stage 2's terrain-mapping work). The fragment is a breadth seed."

**Intermediate output format:**

```yaml
stage_1_output:
  domain_definition: "<one line>"
  major_sub_areas:
    - sub_area: "<name>"
      one_line_characterization: "<>"
  key_terms_a_newcomer_encounters: "<list — 8-15 terms>"
  dominant_figures: "<list — 3-7 names with one-line role>"
  central_debates: "<list — 2-4 active debates>"
  breadth_check:
    sub_areas_spread_across_domain: true | false
    minority_traditions_surfaced: true | false
```

**Quality gates:**
- Sub-areas spread across the domain (CQ1 of quick-orientation: corner-bias).
- Minority traditions surfaced if the domain has them.
- Output stays within fragment scope (no foundational distinctions, no entry points, no misconceptions — those are Stage 2 work).

**Hand-off to Stage 2:** the lay-of-the-land becomes orientation seed for terrain-mapping.

---

### Stage 2 — Terrain Mapping (runs: full)

**Purpose:** Produce the thorough concept map of the domain — focus question, known territory (with concepts classified as known / contested / open), domain structure (hierarchy / hub-and-spoke / network), at least one cross-link to an adjacent domain, at least three open questions tied to specific concepts, boundary statement (what's out of scope).

**Elicitation prompt (orchestrator → model):**
> "You are running the `terrain-mapping` mode (full) as Stage 2 of a Domain Induction pass. Domain: [domain]. Lay-of-the-land from Stage 1: [fragment]. Produce the full terrain-mapping output: focus question, known territory (≥4 concepts each classified known / contested / open), unknown or contested territory (rival schools represented if domain has them), open questions (≥3 tied to specific concepts), domain structure (organizing framework: hierarchy / hub-and-spoke / network), adjacent connections (≥1 cross-link to an adjacent domain), boundary statement. Stay at survey level (≤30% on any single sub-area). Concepts classified as known/contested/open with literal labels. Rival schools represented; the standard view does not silently elide dissenters."

**Intermediate output format:**

```yaml
stage_2_output:
  focus_question: "<>"
  known_territory:
    - concept_id: C1
      name: "<concept>"
      epistemic_status: known | contested | open
      epistemic_note: "<one-line — for contested: 'standard view holds X; dissenters argue Y'>"
      sub_area: "<from Stage 1>"
  open_questions:
    - question_id: Q1
      question: "<open question>"
      tied_to_concept: C_n
  domain_structure:
    organizing_framework: hierarchy | hub-and-spoke | network | layered
    structural_description: "<one paragraph>"
  adjacent_connections:
    - cross_link_id: X1
      from_concept: C_n
      to_adjacent_domain: "<adjacent domain>"
      relationship: "<one-line>"
  boundary_statement: "<one paragraph — what's out of scope>"
```

**Quality gates:**
- ≥4 concepts mapped (CQ1 of terrain-mapping: low-concept-count threshold).
- Each concept classified known/contested/open (CQ1: false-consensus avoidance).
- ≥1 cross-link to adjacent domain (CQ2: no-cross-link-trap).
- ≥3 open questions tied to specific concepts.
- Survey-level discipline (≤30% on any single sub-area — CQ3: premature-depth).
- Boundary statement present (CQ4: missing-boundary).
- Rival schools represented when domain has them.

**Hand-off to Synthesis Stage 1:** the orientation-and-terrain-merge stage receives Stage 1's lay-of-the-land and Stage 2's full terrain map.

---

### Synthesis Stage 1 — Orientation-and-Terrain Merge

**Type:** parallel-merge

**Inputs:** Stage 1 (quick-orientation fragment), Stage 2 (terrain-mapping)

**Synthesis prompt (orchestrator → model):**
> "Merge the rapid lay-of-the-land with the thorough terrain map. The merge produces the unified 'what is here' description: every sub-area from Stage 1 has been expanded into terrain-mapping detail in Stage 2; concepts carry epistemic-status labels; rival schools are represented. The output is the structured 'what is here' that the connectivity-mapping stage will operate on. Resist concatenation — produce one integrated description in which the lay-of-the-land's breadth seed has been substantively populated by the terrain map, with no residual gaps where Stage 1 surfaced a sub-area Stage 2 did not develop."

**Output format:**

```yaml
orientation_and_terrain_merge:
  what_is_here:
    - sub_area: "<from Stage 1>"
      sub_area_one_line: "<from Stage 1>"
      developed_concepts:
        - concept_id: C_n
          name: "<from Stage 2>"
          epistemic_status: known | contested | open
          one_line_characterization: "<>"
      open_questions_in_this_sub_area: "<from Stage 2>"
  cross_sub_area_concepts: "<concepts that span sub-areas>"
  domain_structure_summary: "<from Stage 2>"
  adjacent_domains: "<from Stage 2>"
  rival_schools: "<list — distinct traditions within the domain>"
  coverage_check: 
    every_stage_1_sub_area_developed: true | false
    gaps_named: "<if false, what wasn't developed>"
```

**Quality gates:**
- Every Stage 1 sub-area developed in Stage 2 (no concatenation gaps).
- Rival schools enumerated.
- Domain structure named (organizing framework).

---

### Synthesis Stage 2 — Connectivity Mapping

**Type:** sequenced-build

**Inputs:** Synthesis Stage 1 (orientation-and-terrain merge)

**Synthesis prompt (orchestrator → model):**
> "Map what's connected to what. From the orientation-and-terrain merge, identify (a) central nodes — concepts that other concepts depend on (removing them would unravel multiple downstream concepts); (b) bridge concepts — concepts that link sub-areas to each other; (c) prerequisite chains — concept A must be understood before concept B because B's definition or operation presupposes A. The output is a relational map showing dependencies, not just elements. Relation-omission is a failure mode (CQ2 of domain-induction): a list of elements without dependency arrows fails this stage. Conjectural connections (where dependency is plausible but not established) are tagged as conjectural-mapping rather than presented as established (per partial_composition_handling)."

**Output format:**

```yaml
connectivity_mapping:
  central_nodes:
    - concept_id: C_n
      name: "<>"
      downstream_dependencies: "<list of concepts that depend on this>"
      removal_consequence: "<what unravels if this concept is missed>"
  bridge_concepts:
    - concept_id: C_n
      name: "<>"
      sub_areas_connected: "<list>"
      bridging_role: "<one-line>"
  prerequisite_chains:
    - chain_id: PC1
      sequence: [C_a, C_b, C_c]
      reasoning: "<why C_b presupposes C_a; why C_c presupposes C_b>"
  conjectural_mappings: "<connections plausible but not established — flagged>"
```

**Quality gates:**
- Connectivity shown as relations, not just listed elements (CQ2: relation-omission).
- Central nodes identified.
- Bridge concepts identified.
- Prerequisite chains traced.

---

### Synthesis Stage 3 — Structured Induction

**Type:** dialectical-resolution

**Inputs:** Synthesis Stage 1 (orientation-and-terrain merge), Synthesis Stage 2 (connectivity mapping)

**Synthesis prompt (orchestrator → model):**
> "Produce the Domain Induction Document. Three integrated parts: (a) what is here — from Synthesis Stage 1's merge; (b) what's connected to what — from Synthesis Stage 2's connectivity mapping; (c) what to learn next, sequenced by genuine dependency (not by analyst convenience or alphabetical order — arbitrary-sequencing is a failure mode, CQ3). The learning sequence respects the user's stated familiarity level and induction goal (CQ4: goal-disconnection). For each item in the sequence, name the specific resource (paper, book, course, lecture series, hands-on experience) AND the rationale for placing it at this position in the sequence. Sequencing rationale references the prerequisite chains from Synthesis Stage 2. Where multiple learning paths are valid (the user could induct via theory-first or practice-first), name the alternatives explicitly with the reasoning for each. The induction goal shapes depth: research-level may require primary literature and contested-position study; working-knowledge may require canonical textbooks plus working examples; general-orientation may require accessible secondary literature."

**Output format:** see OUTPUT CONTRACT below.

**Quality gates:**
- Learning sequence is dependency-ordered (CQ3: arbitrary-sequencing is a failure mode).
- User's familiarity level and induction goal are reflected (CQ4: goal-disconnection).
- Each item names a specific resource with rationale.
- Learning dependencies and prerequisites are explicit.
- Confidence map per finding.

---

## OUTPUT CONTRACT — Final Artifact Template

```markdown
[DIA — Domain Induction]

# Domain Induction for <domain name>

## Executive Summary
- **Domain:** <one-sentence definition>
- **Induction goal:** <research-level / working-knowledge / general-orientation>
- **Prior familiarity assumed:** <novice / some exposure / adjacent-domain knowledge>
- **Total domain coverage estimate:** <N concepts mapped, M sub-areas>
- **Recommended learning sequence:** <count> items, <estimated duration>

## 1. What Is Here
[The structured "what is here" from Synthesis Stage 1's orientation-and-terrain merge:]

### Sub-area 1: <Name>
[Sub-area one-line characterization]
- **Concept C1: <Name>** — epistemic status (known / contested / open)
  - <one-line characterization>
  - For contested: standard view vs. dissenters
- **Concept C2:** ...

### Sub-area 2: <Name>
[Same structure...]

### Cross-Sub-Area Concepts
[Concepts that span sub-areas:]
- <concept + one-line — sub-areas spanned>

### Adjacent Domains
- <adjacent domain> — relationship: <one-line>

### Rival Schools / Traditions in This Domain
- **<School A>** — distinguishing commitments: <list>
- **<School B>** — distinguishing commitments: <list>

## 2. What's Connected to What

### 2a. Central Nodes
[Concepts that other concepts depend on:]
- **Central Node C_n: <Name>**
  - Downstream dependencies: <list of concepts requiring this>
  - If a learner skips this: <what unravels>

### 2b. Bridge Concepts
[Concepts that link sub-areas:]
- **Bridge Concept C_n: <Name>**
  - Sub-areas connected: <list>
  - Bridging role: <one-line>

### 2c. Prerequisite Chains
[Sequences where understanding C_b requires understanding C_a:]
- **Chain PC1:** C_a → C_b → C_c
  - Reasoning: <why each link is genuine prerequisite, not arbitrary order>

## 3. What to Learn Next (Sequenced by Dependency)

[For the user's stated familiarity level and induction goal:]

### 3a. Foundation (must come first)
- **Item 1: <specific resource — book / paper / course / lecture series / hands-on experience>**
  - Why first: <prerequisite reasoning>
  - Estimated effort: <hours / weeks>
  - What you'll be able to do after: <one-line>
- **Item 2: <specific resource>**
  - ...

### 3b. Building (after foundation)
- **Item 3: <specific resource>**
  - Why at this position: <prerequisite chain from Synthesis 2>
  - ...

### 3c. Specialization (deeper into chosen sub-area)
- **Item N: <specific resource>**
  - ...

### Alternative Learning Paths
[Where multiple valid sequences exist:]
- **Theory-first path:** <sequence variant>
- **Practice-first path:** <sequence variant>
- **Reasoning for each:** <when each path is preferable>

## 4. Learning Dependencies and Prerequisites
[Cross-reference: which items in the sequence depend on which:]
| Item | Depends On | Reason |
|------|------------|--------|
| Item 4 | Items 1, 2 | <reason> |
| Item 7 | Items 3, 5 | <reason> |
| ... | ... | ... |

## 5. Confidence Map
| Finding | Confidence | Reason |
|---------|------------|--------|
| Sub-area completeness | high / medium / low | <coverage assessment> |
| Central node identification | ... | <how well-established the dependency claim> |
| Recommended Item 5 placement | ... | <whether prerequisite chain is established or conjectural> |
| Suitability for stated goal | ... | <how well sequence matches research-level vs. working-knowledge demands> |
```

## WORKED EXAMPLE WALKTHROUGH

**Opening prompt (user):** *"I want to induct into category theory at working-knowledge level — I'm a software engineer with strong undergraduate math (analysis, linear algebra, basic abstract algebra) but no prior category theory exposure. I want to read the modern functional-programming literature with comprehension and use categorical patterns in code. Six months, ~5 hours/week budget."*

**Stage 1 output (quick-orientation fragment):**
- Domain definition: "Category theory studies mathematical structures and their relationships at a level of abstraction that unifies algebra, topology, logic, and computer science."
- Major sub-areas: (1) basic categorical structures (categories, functors, natural transformations); (2) limits and colimits; (3) adjunctions; (4) monoidal categories and enrichment; (5) applied category theory (Bayesian networks, databases, programming languages).
- Key terms: object, morphism, functor, natural transformation, limit, colimit, adjunction, monad, comonad, Yoneda lemma, presheaf, Kan extension.
- Dominant figures: Mac Lane (foundational), Eilenberg (co-founder), Lawvere (functorial semantics, topos theory), Awodey (modern textbook), Bartosz Milewski (programmer-facing).
- Central debates: foundationalism (set theory vs. category theory as foundations); applied vs. pure; how much category theory is "actually useful" for working programmers.

**Stage 2 output (terrain-mapping, full):**
- Focus question: "What is the structure of category theory and where does the user enter it?"
- Known territory:
  - Concept C1: Category (object + morphisms + composition + identity) — known.
  - Concept C2: Functor (structure-preserving map between categories) — known.
  - Concept C3: Natural transformation (morphism between functors) — known.
  - Concept C4: Limit (universal cone over a diagram) — known.
  - Concept C5: Adjunction (pair of functors with universal property) — known.
  - Concept C6: Monad (endofunctor with unit and multiplication) — known.
  - Concept C7: Yoneda lemma (every category embeds in its presheaf category) — known.
  - Concept C8: Topos (category-theoretic generalization of set theory) — known.
  - Concept C9: ∞-category (homotopy-coherent generalization) — contested in pedagogy (when to introduce; how much foundational rigor needed).
  - Concept C10: Operad / multicategory — open as research-frontier for applied work.
- Open questions: (Q1) What is the right foundation for category theory itself (sets vs. type theory vs. ETCS)? (Q2) Where does the boundary between useful applied category theory and decorative formalism lie? (Q3) How does ∞-category theory change pedagogical sequencing for newcomers?
- Domain structure: layered — basic structures (C1-C3) → universal constructions (C4-C5) → derived structures (C6-C7) → foundational (C8) → frontier (C9-C10).
- Adjacent connections: cross-link to type theory (Curry-Howard-Lambek correspondence); cross-link to algebraic topology (categories arose there); cross-link to functional programming (monads in Haskell).
- Boundary: not covering homotopy type theory in depth; not covering applied category theory's full domain (databases, Bayesian networks, etc.) beyond pointers.

**Synthesis Stage 1 (orientation-and-terrain merge):**
- All 5 sub-areas from Stage 1 developed with concepts from Stage 2.
- Cross-sub-area concept: monads (appears in basic structures C6 AND in applied programming).
- Rival schools: pure category theorists (Mac Lane lineage, foundational-set-theoretic) vs. applied/programming category theorists (Lawvere lineage, structural; Bartosz Milewski's pedagogy).
- Domain structure: layered (basic → universal → derived → foundational → frontier).

**Synthesis Stage 2 (connectivity mapping):**
- Central nodes: C1 (category) — every other concept depends on it. C2 (functor) — limits, adjunctions, monads all defined via functors. C5 (adjunction) — connects to monads, Galois connections, free-forgetful structure throughout.
- Bridge concepts: C6 (monad) bridges pure category theory and functional programming; C2 (functor) bridges category theory and algebraic topology.
- Prerequisite chains:
  - PC1: C1 (category) → C2 (functor) → C3 (natural transformation) → C4 (limit) → C5 (adjunction) → C6 (monad).
  - PC2: C1 → C2 → C7 (Yoneda) — Yoneda requires functor and category fluency.
  - PC3: C5 (adjunction) → C8 (topos) — topos theory requires adjunction fluency.
  - PC4: For programming application: C1 → C2 → C6 → applied monad use in Haskell or similar.

**Synthesis Stage 3 (structured induction document):**

[Final artifact follows OUTPUT CONTRACT template.]

For working-knowledge level with software engineering background:

Foundation (months 1-2):
- Item 1: Bartosz Milewski, *Category Theory for Programmers* (book, 350 pages, ~30 hours). Why first: programmer-facing entry point with software engineering examples; covers C1-C3 thoroughly with code analogies. After: comfortable with category, functor, natural transformation in programmer vocabulary.
- Item 2: Awodey, *Category Theory*, chapters 1-3 (textbook, ~25 hours). Why second: provides rigorous mathematical foundation for the same concepts; the parallel treatment (Milewski's intuition + Awodey's rigor) is high-leverage for working-knowledge level.

Building (months 3-4):
- Item 3: Awodey chapters 4-6 (limits, colimits, adjunctions — ~20 hours). Why now: requires C2-C3 fluency from items 1-2; introduces C4-C5 (universal constructions and adjunctions).
- Item 4: Milewski follow-up chapters on monads (~10 hours). Why now: PC4 (C1 → C2 → C6) is now traversable; monad understanding via adjunction (Item 3) makes the formalism click rather than feel arbitrary.

Specialization (months 5-6, working-knowledge in functional programming):
- Item 5: Riehl, *Category Theory in Context*, selected chapters on Yoneda lemma and Kan extensions (~20 hours). Why now: PC2 chain complete; Yoneda becomes the central theoretical insight that ties everything together.
- Item 6: Hands-on project applying categorical patterns in chosen functional language (Haskell, Scala with cats, OCaml — ~30 hours). Why now: working-knowledge means demonstrated fluency in a working context, not just textbook completion.

Alternative paths:
- **Theory-first variant:** start with Awodey, defer Milewski to later — works for users with stronger pure-math background.
- **Practice-first variant:** start with monads in Haskell, derive theory backward — works for users with strong programming background and weaker tolerance for abstract math first.

Confidence: high for sequence ordering (well-established prerequisite chains in the literature); medium for time estimates (varies by individual); high for resource selection at working-knowledge level (Milewski + Awodey is canonical for this user profile).

## CAVEATS AND OPEN DEBATES

**Composition limit — goal disconnection.** The most common failure is producing a generic survey when the user has stated a specific induction goal. Research-level vs. working-knowledge vs. general-orientation produce materially different sequences and resource selections (CQ4: goal-disconnection). The framework requires the goal to shape Stage 3's structured induction, not merely be acknowledged.

**Connectivity is conjectural sometimes.** Where dependency claims are well-established in the literature, present them as established. Where dependencies are plausible but not pedagogically validated (e.g., a new applied direction where prerequisite chains haven't been worked out by educators), flag as conjectural-mapping rather than presenting as established (per partial_composition_handling). Honest "this sequence is my best inference, not a validated path" is preferable to false confidence.

**Resource selection bias.** The framework's resource recommendations reflect the analyst's exposure to the domain's literature. For domains where the analyst has limited corpus exposure, the resources may underweight minority traditions or recent developments. Confidence-per-recommendation should reflect this honestly.

**When to escalate sideways:** if during execution the user actually wants generative exploration of an open space rather than navigable orientation, route to `passion-exploration` (T20). DIA assumes the domain has structure to be inducted into; passion-exploration handles open generative work.

## QUALITY GATES (overall)

- Quick-orientation fragment ran (lay-of-the-land breadth seed).
- Terrain-mapping full ran (concept map with epistemic-status labels, cross-links, open questions, boundary).
- Connectivity-mapping shows relations (central nodes, bridge concepts, prerequisite chains) — not just listed elements.
- Learning sequence is dependency-ordered.
- User's familiarity level and induction goal are reflected.
- Each learning-sequence item names specific resource AND rationale.
- Confidence map populated per finding.
- The four critical questions of `domain-induction` (dominant-subfield-bias, relation-omission, arbitrary-sequencing, goal-disconnection) are addressed.

## RELATED MODES AND CROSS-REFERENCES

- **Paired mode file:** `Modes/domain-induction.md`
- **Component mode files:**
  - `Modes/quick-orientation.md` (Stage 1, fragment)
  - `Modes/terrain-mapping.md` (Stage 2, full)
- **Sibling Wave 4 modes:** `Modes/decision-architecture.md` (T3), `Modes/argument-audit.md` (T1) — share the depth-molecular composition pattern.
- **Adjacent territory:** T20 (passion-exploration) for generative exploration when domain doesn't have inductable structure; T11 (relationship-mapping) when relational structure rather than orientation is the goal.
- **Lens dependencies:** bloom-taxonomy (optional, when learning sequence requires cognitive-level scaffolding), novice-expert-cognition (optional, when familiarity level is novice), novak-concept-map-tradition (via terrain-mapping), kahneman-tversky-bias-catalog (foundational).

*End of Domain Induction Analysis Framework.*
