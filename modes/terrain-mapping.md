---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 3
---

# MODE: Terrain Mapping

## TRIGGER CONDITIONS

Positive (fire the mode):
1. The user asks "what is", "how does X work", "where do I start", "what do I need to know about", or expresses unfamiliarity with a domain.
2. The prompt names a domain the conversation history shows the user has not previously engaged with.
3. The CAF scan during Phase C produces an incomplete factor list or unclear domain boundary.
4. Orientation-shaped request language: "walk me through", "give me the lay of the land", "what's the big picture", "map this domain for me", "concept map of".

Negative (route elsewhere):
- IF the user names a specific deliverable or states requirements → **Project Mode**.
- IF the user is familiar but wants deeper mechanics of a known concept → **Deep Clarification**.
- IF the user has multiple competing explanations for the same evidence → **Competing Hypotheses**.
- IF the user is exploring open-endedly with no desire for a map → **Passion Exploration**.

Tiebreakers:
- TM vs Deep Clarification: **unfamiliar territory** → TM; **familiar domain, deeper mechanism** → DC.
- TM vs Passion Exploration: **wants a navigable map** → TM; **wants to wander** → PE.

## EPISTEMOLOGICAL POSTURE

All sources are treated as orientation material, not as authoritative. Survey literature and domain overviews are treated as maps — useful for navigation, unreliable for fine-grained claims. Consensus positions are reported as "the standard view holds X" rather than asserted as fact. The goal is to reveal the shape of the territory, including where the maps disagree.

## DEFAULT GEAR

Gear 3. Terrain Mapping is an orientation task. Sequential adversarial review is sufficient — the Breadth model maps the territory, the Depth model challenges whether the map is complete and whether any region has been mischaracterised.

## RAG PROFILE

**Retrieve (prioritise):** survey literature, domain overviews, introductory sources, encyclopaedic references, taxonomic frameworks. IF the domain has known schools of thought or competing paradigms, retrieve at least one source representing each school.

**Deprioritise:** primary research, narrow technical papers, deep specialist sources — survey breadth is the goal.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `parent`, `child`, `extends`, `analogous-to`
**Deprioritise:** `contradicts`, `supersedes`
**Rationale:** Territory mapping uses hierarchical relationships to reveal domain structure and analogies to connect to known domains.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The domain the user wants oriented in |
| `conversation_rag` | What the user already knows; prior orientation attempts |
| `concept_rag` | Mental models that cross into this domain |
| `relationship_rag` | Domain objects linked by `parent`/`child`/`extends` |
| `spatial_representation` | Optional — user's own concept-map-in-progress |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

*Token measurements to be calibrated during Phase 8E testing.*

## DEPTH MODEL INSTRUCTIONS

White Hat directives:
1. Identify what is known and well-established in this domain — settled facts, accepted frameworks, standard terminology. **These populate the prose "Known territory" section and become `concepts` with `hierarchy_level` 0 or 1 in the envelope.**
2. Identify what is unknown, contested, or actively debated — open questions, rival interpretations, gaps in current understanding. **These populate "Unknown territory" and become concepts at deeper hierarchy levels.**
3. Identify what the user would need to learn next to operate competently — prerequisite knowledge, key distinctions, common misconceptions.

Black Hat directives:
1. Evaluate the Breadth model's territory map for completeness. Identify regions the map omits or underrepresents.
2. Flag any region where the map presents a contested position as settled, or a settled position as contested.
3. Identify at minimum two areas where a newcomer would predictably form a wrong impression from survey-level sources alone.

### Cascade — what to leave for the evaluator

- State the orientation question in the first paragraph with the literal opening "Focus question:" so C1 traces to `spec.focus_question`.
- Classify every major concept as `known` / `contested` / `open` using those literal labels in prose. Supports M1.
- Use the literal phrase "adjacent domain" when introducing cross-domain concepts — supports M4 and cross-link detection.
- Use the literal phrase "out of scope" in the Boundary statement paragraph. Supports M3.
- **short_alt discipline — IMPORTANT (Phase 5 iteration).** Emit `spec.semantic_description.short_alt` in Cesal form: `"Concept map of <domain name ≤ 60 chars>."`. TARGET ≤ 100 chars. HARD MAX 150 chars — exceeding rejects the envelope with `E_SCHEMA_INVALID`. Do NOT list every sub-area or cross-link inside short_alt — use `level_1_elemental` for that. Good: `"Concept map of retrieval-augmented generation."` (46 chars). Bad: `"Concept map showing the landscape of RAG, its core components, schools of thought on embeddings, hybrid search vs dense-only, and adjacent domains like knowledge graphs..."` (180+ chars — rejected).

### Consolidator guidance

Not applicable at this mode's default gear (Gear 3). If promoted to Gear 4 for deep multi-domain orientation, merge both streams' concept inventories; retain Depth's known/contested/open classifications; add Breadth's adjacent-domain cross-links as additional `is_cross_link: true` propositions.

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. Map the full landscape: major sub-areas, key concepts, foundational distinctions, principal actors or schools of thought. **Each sub-area becomes a `concept` in the envelope; distinctions between them become `linking_phrases`.**
2. Identify adjacent domains that connect to this territory — where the borders are and what lies beyond them.
3. Generate at minimum three questions the user has not asked but would need to answer to navigate this domain effectively.

Yellow Hat directives:
1. Identify what is most accessible and immediately useful — entry points, quick wins, concepts that unlock the most territory.
2. Surface frameworks, mental models, or organising structures that make the domain navigable rather than overwhelming.
3. Note where this domain connects to domains the user already knows (draw on conversation RAG for the user's existing knowledge).

### Cascade — what to leave for the evaluator

- Generate at minimum three numbered open questions (`Open question 1:` ... `Open question 3:`) tied to concept ids. Supports M2.
- Surface organising-structure name (hub-and-spoke / hierarchy / network / etc.) in the Domain structure section — supports Navigational Utility rubric.
- Assign each concept an explicit `hierarchy_level` in the envelope (the visual renderer uses this); prose need not repeat the number but must communicate the depth ordering.

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Cartographic Completeness.** 5=all major sub-areas and schools of thought represented. 3=one significant sub-area or school missing. 1=the map covers only a fragment of the territory.
6. **Known/Unknown/Open Separation.** 5=all three categories populated with no miscategorisation. 3=categories present but one item miscategorised. 1=categories blurred or missing.
7. **Navigational Utility.** 5=clear entry points, prerequisite chain, and next questions identified. 3=orientation present but next steps vague. 1=output reads as a data dump without navigational structure.

### Focus for this mode

A strong TM evaluator prioritises:

1. **Cross-link presence (S10).** `is_cross_link: true` on at least one proposition — a flat tree is not a concept map.
2. **Concept floor (S7).** ≥ 4 concepts; below that, the visual is Deep Clarification territory.
3. **Focus question (S11, C1).** Non-empty `spec.focus_question` and matches prose's focus question.
4. **Known/unknown/open separation (M1).** Prose explicitly uses the three labels.
5. **Short_alt (S12).** Name the domain, not every concept.

### Suggestion templates per criterion

- **S12:** `suggested_change`: "Rewrite short_alt as: 'Concept map of <domain name ≤ 80 chars>.' Do not enumerate all concepts. Target ≤ 100 chars."
- **S10 (no cross-link):** `suggested_change`: "Add at least one proposition with `is_cross_link: true` connecting a concept to an adjacent-domain concept. If no adjacent domain was identified, add one with hierarchy_level 1 and link it."
- **S7 (< 4 concepts):** `suggested_change`: "Add concepts until `spec.concepts` has ≥ 4. Fewer than 4 is not a landscape — below that, consider routing to Deep Clarification instead."
- **M1 (known/unknown/open not separated):** `suggested_change`: "Prefix each concept in prose with one of `known` / `contested` / `open` labels to signal its epistemic status."
- **M3 (boundary not stated):** `suggested_change`: "Add a Boundary statement paragraph using the literal phrase 'out of scope' to name what the map deliberately omits."

### Known failure modes to call out

- **No-Cross-Link Trap** → open: "Map is a flat tree — `is_cross_link: true` required on ≥1 proposition."
- **Premature Depth Trap** → open: "Prose over-invests in one sub-area; pull back to survey-level."
- **Textbook Trap** → open: "Output reproduces a standard overview without known/unknown/open separation."
- **False Consensus Trap** → open: "Contested positions presented as settled on branch X."
- **Low-Concept-Count Trap** → open: "Map has < 4 concepts; either expand or route to Deep Clarification."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-TM-1 — Cross-link preservation.** ≥ 1 `is_cross_link: true` proposition in revised envelope.
- **V-TM-2 — Focus-question match.** Revised `spec.focus_question` appears in the revised prose with stem-overlap ≥ 0.6.
- **V-TM-3 — Concept-floor preservation.** Revised `spec.concepts` has ≥ 4 entries; silent drop below floor during revision is a FAIL.

## CONTENT CONTRACT

The prose is complete when it contains, in order:

1. **Focus question** — the orientation question the user is asking, stated precisely. Becomes `spec.focus_question`.
2. **Known territory** — established concepts with their labels. Each becomes a `concept` at hierarchy_level 0.
3. **Unknown / contested territory** — debated or open concepts. Deeper hierarchy_levels in the envelope.
4. **Open questions** — at minimum three, tied to specific concepts.
5. **Domain structure** — the organising framework (hierarchy, network, hub-and-spoke, or other). Expressed in the envelope as the propositions linking concepts.
6. **Adjacent connections** — where this domain borders other domains; mark these as cross-links (`is_cross_link: true`) in the envelope.
7. **Boundary statement** — what the map does not cover and what would be needed to extend it.

After your analysis, emit exactly one fenced `ora-visual` block conforming to the EMISSION CONTRACT below as the final block of the response.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S2:** `E_UNRESOLVED_REF` → a proposition references an undeclared concept id or linking-phrase id; add the declaration or fix the id.
- **S7-S9 (shape floors):** apply the shape-floor templates above.
- **S10:** apply cross-link template.
- **S12:** apply short_alt template.
- **M2 (< 3 open questions):** add open questions until ≥ 3, each tied to a concept id.
- **M3 (boundary):** apply boundary template.
- **M4 (adjacent not identified):** mark at least one concept with `hierarchy_level: 1` and connect it via `is_cross_link: true`.
- **M5 (contested-as-settled):** edit prose to qualify the contested claim with "the standard view holds X; dissenters argue Y".
- **C1-C3:** sync prose and envelope on focus_question, concept labels, and adjacent-domain mentions respectively.

## EMISSION CONTRACT

Terrain Mapping produces a response containing prose (the seven content-contract sections) AND exactly one `ora-visual` block of type `concept_map`.

### Canonical envelope

```ora-visual
{
  "schema_version": "0.2",
  "id": "tm-fig-1",
  "type": "concept_map",
  "mode_context": "terrain-mapping",
  "relation_to_prose": "integrated",
  "title": "Landscape of X",
  "canvas_action": "replace",
  "spec": {
    "focus_question": "What is the landscape of X?",
    "concepts": [
      { "id": "C1", "label": "Root domain",         "hierarchy_level": 0 },
      { "id": "C2", "label": "Settled sub-area",    "hierarchy_level": 1 },
      { "id": "C3", "label": "Contested sub-area",  "hierarchy_level": 1 },
      { "id": "C4", "label": "Open question",       "hierarchy_level": 2 },
      { "id": "C5", "label": "Adjacent domain",     "hierarchy_level": 1 }
    ],
    "linking_phrases": [
      { "id": "L1", "text": "contains" },
      { "id": "L2", "text": "debates" },
      { "id": "L3", "text": "borders" }
    ],
    "propositions": [
      { "from_concept": "C1", "via_phrase": "L1", "to_concept": "C2" },
      { "from_concept": "C1", "via_phrase": "L1", "to_concept": "C3" },
      { "from_concept": "C3", "via_phrase": "L2", "to_concept": "C4" },
      { "from_concept": "C1", "via_phrase": "L3", "to_concept": "C5", "is_cross_link": true }
    ]
  },
  "semantic_description": {
    "level_1_elemental": "Concept map with five nodes hierarchically organised under a root domain.",
    "level_2_statistical": "Three hierarchy levels; one cross-link to an adjacent domain.",
    "level_3_perceptual": "Root branches into two sub-areas (one settled, one contested); the contested branch has an open question beneath it.",
    "short_alt": "Concept map of a domain with settled, contested, and adjacent regions."
  }
}
```

### Emission rules

1. **`type` must be `"concept_map"`.**
2. **`mode_context` must be `"terrain-mapping"`.**
3. **`relation_to_prose` must be `"integrated"`.** `canvas_action: "replace"`.
4. **`spec.focus_question` non-empty** and matches the prose's focus question.
5. **`spec.concepts` must have at least 4 entries** (fewer than 4 is not a landscape). Each has `id`, `label`, and `hierarchy_level` (≥0).
6. **`spec.linking_phrases` must have at least 2 entries** with `id` and non-empty `text`.
7. **`spec.propositions` must have at least 3 entries.** Every `from_concept`, `via_phrase`, `to_concept` resolves to a declared id.
8. **At least one proposition has `is_cross_link: true`** — cross-links are the Novak marker of integrative understanding. The validator emits `W_NO_CROSS_LINKS` otherwise.
9. **`semantic_description` required fields non-empty; `short_alt ≤ 150 chars`.**
10. **Emit exactly one `ora-visual` block.**

### What NOT to emit

- Do not emit a map with fewer than 4 concepts; that is Deep Clarification's output form, not Terrain Mapping's.
- Do not set `canvas_action: "annotate"` (that's Spatial Reasoning).
- Do not invent propositions that reference ids not in `concepts` or `linking_phrases` — the validator rejects with `E_UNRESOLVED_REF`.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN the output moves toward a specific recommendation, THEN pause — Terrain Mapping produces maps, not answers.

**Anti-depth guard rail.** IF the prose spends more than 30% on any single sub-area, pull back to survey level.

**Humility guard rail.** State explicitly what the map does not cover.

**Cross-link guard rail.** WHEN emitting, verify at least one proposition has `is_cross_link: true` — a flat tree with no cross-links is not yet a concept map.

## SUCCESS CRITERIA

### Structural (machine-checkable)

- S1: one `ora-visual` fence, parseable JSON.
- S2: schema validity (zero errors).
- S3: `envelope.type == "concept_map"`.
- S4: `envelope.mode_context == "terrain-mapping"`.
- S5: `envelope.canvas_action == "replace"`.
- S6: `envelope.relation_to_prose == "integrated"`.
- S7: `len(spec.concepts) ≥ 4` and each has `hierarchy_level`.
- S8: `len(spec.linking_phrases) ≥ 2`.
- S9: `len(spec.propositions) ≥ 3` and all ids resolve.
- S10: at least one proposition has `is_cross_link: true`.
- S11: `spec.focus_question` non-empty.
- S12: `semantic_description` complete; `short_alt ≤ 150 chars`.

### Semantic (LLM-reviewer)

- M1: known/unknown/open separation present in prose.
- M2: at least three open questions tied to specific concepts.
- M3: boundary statement names what is out of scope.
- M4: adjacent domains identified and marked via cross-links.
- M5: no contested claim is presented as settled (and vice versa).

### Composite (prose + envelope)

- C1: `spec.focus_question` appears verbatim (or stem-overlap ≥ 0.6) in prose.
- C2: every `concept.label` appears in prose (or stem-overlap).
- C3: prose's "Adjacent connections" section corresponds to concepts connected by cross-link propositions.

```yaml
success_criteria:
  mode: terrain-mapping
  version: 1
  structural:
    - { id: S1,  check: envelope_present }
    - { id: S2,  check: envelope_schema_valid }
    - { id: S3,  check: type_equals, value: concept_map }
    - { id: S4,  check: mode_context_equals, value: terrain-mapping }
    - { id: S5,  check: canvas_action_equals, value: replace }
    - { id: S6,  check: relation_to_prose_equals, value: integrated }
    - { id: S7,  check: min_concepts, min: 4 }
    - { id: S8,  check: min_linking_phrases, min: 2 }
    - { id: S9,  check: propositions_resolve_ids, min: 3 }
    - { id: S10, check: at_least_one_cross_link }
    - { id: S11, check: focus_question_nonempty }
    - { id: S12, check: semantic_description_complete }
  semantic:
    - { id: M1, check: known_unknown_open_separation }
    - { id: M2, check: three_open_questions }
    - { id: M3, check: boundary_statement_present }
    - { id: M4, check: adjacent_domains_identified }
    - { id: M5, check: contested_not_claimed_settled }
  composite:
    - { id: C1, check: focus_question_prose_envelope_match }
    - { id: C2, check: concept_labels_in_prose }
    - { id: C3, check: adjacent_connections_in_prose }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The Premature Depth Trap (inverse of anti-depth guard).** Drilling into one sub-area before the full territory is mapped. Correction: Complete the survey-level map of all sub-areas before exploring any in detail.

**The Textbook Trap (inverse of M1).** Reproducing a standard overview rather than mapping known vs unknown vs open. Correction: For every major claim, classify whether it is settled, contested, or open.

**The False Consensus Trap (inverse of M5).** Presenting one school of thought's view as the domain consensus when rival schools exist. Correction: When RAG returns sources from different schools, represent each explicitly.

**The No-Cross-Link Trap (inverse of S10).** Producing a strict tree with no lateral connections, missing the integrative structure. Correction: Add at least one `is_cross_link: true` proposition.

**The Low-Concept-Count Trap (inverse of S7).** Emitting a concept map with 2-3 concepts. Correction: Below 4 concepts, the visual is Deep Clarification's territory; expand the map or switch modes.

## TOOLS

Tier 1: CAF (primary — map all factors), Concept Fan (discover the right level of abstraction), RAD (recognise domain type, analyse components, divide if multiple territories are conflated).

Tier 2: Problem Definition Question Bank (Module 1 — Problem Scoping; Module 2 — Information Audit).

## TRANSITION SIGNALS

- IF the user begins naming specific deliverables → propose **Project Mode**.
- IF a foundational assumption surfaces → propose **Paradigm Suspension**.
- IF the exploration opens with no terminal point → propose **Passion Exploration**.
- IF multiple competing explanations for the same evidence emerge → propose **Competing Hypotheses**.
- IF the territory contains feedback loops → propose **Systems Dynamics**.
- IF the user asks about possible futures → propose **Scenario Planning**.
