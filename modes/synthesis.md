---
type: mode
date created: 2026/03/23
date modified: 2026/04/18
nexus: obsidian
rebuild_phase: 3
---

# MODE: Synthesis

## TRIGGER CONDITIONS

Positive:
1. Cross-domain connection — "how does X relate to Y".
2. Two bodies of knowledge that have been explored separately and now need to be examined together.
3. Integrative analysis — the user wants to examine productive tension between developed positions.
4. Request language: "synthesise", "connect these frameworks", "what's the structural parallel", "map the intersection".

Negative:
- IF the user wants to choose between positions → **Constraint Mapping**.
- IF the user wants to drive thesis through antithesis to produce a genuinely new position → **Dialectical Analysis**.
- IF the user wants the strongest version of one position → **Steelman Construction**.

Tiebreaker:
- Synthesis vs Dialectical: **neutral examination of connection** → Synthesis; **adversarial commitment + sublation** → DA.

## EPISTEMOLOGICAL POSTURE

Both (or all) positions are treated as developed and worth taking seriously. The task is not to choose between them but to identify structural correspondence, productive tension, and what emerges from examining them together. Neutral examination — the mode does not advocate for either position. Connections claimed must be genuine structural parallels, not surface-level analogies or metaphorical similarities.

## DEFAULT GEAR

Gear 4. Genuine synthesis requires independent analysis. IF one model sees the other's framing before developing its own, it anchors to that framing. The convergence/divergence signal between independently developed analyses is the primary quality indicator.

## RAG PROFILE

**Retrieve (prioritise):** primary sources from each framework; cross-domain and interdisciplinary literature; existing work connecting the specific frameworks.

**Deprioritise:** introductory sources — synthesis requires depth in each domain, not breadth across domains.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `extends`, `analogous-to`, `supports`, `qualifies`, `derived-from`
**Deprioritise:** `precedes`, `parent`, `child`
**Rationale:** Cross-domain synthesis follows extension, analogy, and derivation chains across frameworks.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The two (or more) frameworks the user wants synthesised |
| `conversation_rag` | Prior work on either framework |
| `concept_rag` | Mental models bridging the frameworks |
| `relationship_rag` | Objects linked by `analogous-to` across domains |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. Map each framework's core claims, structures, and mechanisms. **Each framework contributes `concepts` to the envelope at hierarchy_level 0; within-framework concepts at levels 1-2.**
2. Identify specific structural elements in each framework that may correspond to elements in the other. **These become cross-domain cross-linked propositions.**
3. Distinguish genuine structural correspondence from surface analogy.

Black Hat:
1. Stress-test every proposed connection — does it hold under examination?
2. Identify at minimum one proposed connection that is superficial. Explain why it fails.
3. Evaluate whether the synthesis reveals something genuinely new or merely restates what was already known.

### Cascade — what to leave for the evaluator

- State both framework root names in the "Frameworks identified" paragraph and emit them as two `hierarchy_level: 0` concepts. Supports S7 (two-roots shape).
- Use the literal phrase "structural correspondence" when introducing each cross-link; reserve "surface analogy" for connections being ruled out. Supports M2 (mechanism-not-metaphor).
- Use the literal phrase "emergent insight" in the Emergent insight paragraph. Supports M4.
- Use the literal phrase "productive tension" in the tension paragraph and emit a linking phrase named "is in productive tension with" for at least one cross-link. Supports M3.
- **short_alt discipline — IMPORTANT (Phase 5 iteration).** Emit `spec.semantic_description.short_alt` in Cesal form: `"Synthesis concept map linking <Framework A> and <Framework B>."`. TARGET ≤ 100 chars. HARD MAX 150 chars — exceeding rejects the envelope with `E_SCHEMA_INVALID`. Do NOT list every cross-link or concept inside short_alt — use `level_1_elemental` for enumeration. Good: `"Synthesis concept map linking ecology and organisational theory."` (62 chars). Bad: `"Synthesis concept map of ecology and organisational theory showing core mechanisms, unit of analysis, three cross-links for structural correspondence and two for productive tension..."` (180+ chars — rejected).

### Consolidator guidance

Applies at this mode's default gear (Gear 4). Depth + Breadth both produce independent syntheses — this mode's core signal. Reconcile as:

- **Reference frame for the envelope:** union of concepts from both streams; de-duplicate by label. Preserve both frameworks as `hierarchy_level: 0` peers.
- **Convergent cross-links:** when both streams identified the same structural correspondence, mark the consolidated proposition with both streams' attribution in prose and emit one `is_cross_link: true` edge.
- **Divergent cross-links:** when only one stream identified a correspondence, emit it with single-stream attribution and mark it as "tentative" in prose.
- **Superficial-analogy disputes:** if Depth ruled out a connection Breadth proposed, defer to Depth (structural test wins); surface the Breadth proposal in prose as "Breadth proposed X but the structural test fails — superficial analogy, not emitted".
- **Neither stream should be flattened into the other** — two peer `hierarchy_level: 0` roots are non-negotiable.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Look for structural isomorphisms across the frameworks.
2. Generate at minimum three candidate connections, including at least one non-obvious.
3. Explore what the synthesis reveals that neither framework reveals alone.

Yellow Hat:
1. Identify the most productive tension between the frameworks.
2. Assess practical value — new approaches, resolved puzzles, research directions.
3. Note where the synthesis is incomplete.

### Cascade — what to leave for the evaluator

- Generate at least three candidate connections in prose, flagging at least one as "non-obvious" explicitly.
- For each accepted cross-link, state the mechanism that makes it structural rather than metaphorical — one sentence minimum.
- End with a Limitations paragraph naming at least one place where the synthesis breaks down. Supports M5.

## EVALUATION CRITERIA

Extends the base rubric with:

5. **Connection Genuineness.** 5=all connections are structural parallels at the mechanism level. 3=one relies on surface analogy. 1=connections are primarily metaphorical.
6. **Emergent Insight.** 5=the synthesis produces ≥1 insight unavailable from either framework independently. 3=clarifies each framework but no genuinely new insight. 1=restates what was known.
7. **Tension Identification.** 5=productive tensions identified without premature resolution. 3=tensions noted but not explored. 1=tensions smoothed over.

### Focus for this mode

A strong Synthesis evaluator prioritises:

1. **Two roots (S7).** Both frameworks must be present as `hierarchy_level: 0` concepts. Single-root maps reduce one framework to a special case of the other — a structural failure.
2. **Cross-link presence (S10).** Without cross-links, there is no synthesis — just two disconnected trees.
3. **Mechanism-not-metaphor (M2).** Every cross-link carries prose evidence of structural correspondence.
4. **Tension honesty (M3).** Productive tensions have linking phrases like "is in tension with" — smoothed-over tensions fail the mode's core commitment.
5. **Short_alt (S12).** Name the two frameworks being synthesised.

### Suggestion templates per criterion

- **S12:** `suggested_change`: "Rewrite short_alt as: 'Synthesis concept map linking <framework A> and <framework B>.' Do not enumerate every cross-link. Target ≤ 100 chars."
- **S7 (no two roots):** `suggested_change`: "Add the missing framework as a second `hierarchy_level: 0` concept; ensure at least two concepts from each framework appear beneath their respective roots."
- **S10 (no cross-link):** `suggested_change`: "Add at least one proposition with `is_cross_link: true` connecting a concept from framework A to a concept from framework B. The cross-link's linking phrase should be 'structurally corresponds to' or 'is in productive tension with'."
- **M2 (superficial analogy):** `suggested_change`: "For cross-link <id>, either (a) add prose evidence of mechanism-level correspondence, or (b) remove the cross-link and note in prose that the connection is superficial."
- **M3 (tension smoothed):** `suggested_change`: "Add a linking phrase 'is in productive tension with' and emit at least one cross-link using it. Do not resolve the tension in prose — name it as a finding."

### Known failure modes to call out

- **No-Cross-Link Trap** → open: "Two separate trees without cross-links is not a synthesis."
- **Reduction Trap** → open: "Framework X is reduced to a special case of framework Y — both must remain peer `hierarchy_level: 0` roots."
- **False Synthesis Trap** → open: "Cross-link <id> relies on surface analogy, not structural correspondence."
- **Harmony Trap** → open: "Productive tensions have been smoothed over; add at least one 'is in tension with' cross-link."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-SYN-1 — Two-root preservation.** Revised envelope has at least two `hierarchy_level: 0` concepts with distinct framework names.
- **V-SYN-2 — Cross-link preservation.** Revised envelope has ≥ 1 `is_cross_link: true` proposition.
- **V-SYN-3 — Mechanism-evidence preservation.** Each cross-link in revised envelope has prose evidence of structural correspondence in the revised "Structural parallel(s)" section.

## CONTENT CONTRACT

In order:

1. **Frameworks identified** — the two (or more) frameworks being synthesised, each named.
2. **Structural parallel(s)** — specific correspondences with precision about what maps to what.
3. **Evidence for genuineness** — each connection passes the structural-vs-metaphorical test.
4. **Emergent insight** — what the synthesis reveals that neither framework reveals alone.
5. **Productive tensions** — where the frameworks disagree in illuminating ways.
6. **Limitations** — where the synthesis breaks down.

After your analysis, emit exactly one fenced `ora-visual` block per the EMISSION CONTRACT.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S2:** `E_UNRESOLVED_REF` → proposition references undeclared id; fix.
- **S7 (two-roots):** apply two-roots template.
- **S9 (< 4 propositions):** add connecting propositions; each framework's root should link to its within-framework concepts; add ≥ 1 cross-link.
- **S10:** apply cross-link template.
- **S12:** apply short_alt template.
- **M1 (both frameworks mapped):** both must appear in prose Frameworks-identified paragraph; add the missing one.
- **M2 (mechanism evidence):** apply superficial-analogy template.
- **M3 (productive tension):** apply tension template.
- **M4 (emergent insight):** add the Emergent insight paragraph using the literal phrase; name what the synthesis reveals that neither framework reveals alone.
- **M5 (limitation):** add the Limitations paragraph.
- **C1-C3:** sync envelope concept labels and cross-links with prose parallels.

## EMISSION CONTRACT

Synthesis produces prose + exactly one `concept_map` envelope.

### Canonical envelope

```ora-visual
{
  "schema_version": "0.2",
  "id": "syn-fig-1",
  "type": "concept_map",
  "mode_context": "synthesis",
  "relation_to_prose": "integrated",
  "title": "Synthesis of framework A and framework B",
  "canvas_action": "replace",
  "spec": {
    "focus_question": "Where do framework A and framework B structurally correspond?",
    "concepts": [
      { "id": "A",  "label": "Framework A",          "hierarchy_level": 0 },
      { "id": "B",  "label": "Framework B",          "hierarchy_level": 0 },
      { "id": "A1", "label": "A's core mechanism",   "hierarchy_level": 1 },
      { "id": "A2", "label": "A's unit of analysis", "hierarchy_level": 1 },
      { "id": "B1", "label": "B's core mechanism",   "hierarchy_level": 1 },
      { "id": "B2", "label": "B's unit of analysis", "hierarchy_level": 1 }
    ],
    "linking_phrases": [
      { "id": "L1", "text": "contains" },
      { "id": "L2", "text": "structurally corresponds to" },
      { "id": "L3", "text": "is in productive tension with" }
    ],
    "propositions": [
      { "from_concept": "A",  "via_phrase": "L1", "to_concept": "A1" },
      { "from_concept": "A",  "via_phrase": "L1", "to_concept": "A2" },
      { "from_concept": "B",  "via_phrase": "L1", "to_concept": "B1" },
      { "from_concept": "B",  "via_phrase": "L1", "to_concept": "B2" },
      { "from_concept": "A1", "via_phrase": "L2", "to_concept": "B1", "is_cross_link": true },
      { "from_concept": "A2", "via_phrase": "L3", "to_concept": "B2", "is_cross_link": true }
    ]
  },
  "semantic_description": {
    "level_1_elemental": "Concept map of two frameworks (A, B) each decomposed into a mechanism and a unit of analysis, with two cross-framework links.",
    "level_2_statistical": "Six concepts, two hierarchy levels, two cross-links — one correspondence, one tension.",
    "level_3_perceptual": "The parallel structure visually separates within-framework containment from across-framework correspondence.",
    "short_alt": "Synthesis concept map linking Framework A and Framework B by mechanism and unit."
  }
}
```

### Emission rules

1. **`type = "concept_map"`. `mode_context = "synthesis"`. `canvas_action = "replace"`. `relation_to_prose = "integrated"`.**
2. **`spec.concepts` ≥ 4**, at least two from each framework. Each framework's root concept sits at `hierarchy_level: 0`.
3. **`spec.linking_phrases` ≥ 2.**
4. **`spec.propositions` ≥ 4** with all ids resolving.
5. **At least one proposition has `is_cross_link: true`** — that is the synthesis itself. A concept map with no cross-links is not a synthesis.
6. **`semantic_description` required fields non-empty; `short_alt ≤ 150 chars`.**
7. **One envelope per turn.**

### What NOT to emit

- A concept map with concepts from only one framework (no synthesis happened).
- Cross-links between concepts that the prose flagged as surface-analogy rather than structural.
- `canvas_action: "annotate"`.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN the synthesis moves toward endorsing one framework, pause — Synthesis examines connections, not superiority.

**Structural test guard rail.** Every cross-link must survive the structural-vs-metaphorical test.

**Independence guard rail.** Neither framework should be distorted to fit the connection.

**Cross-link guard rail.** Emit at least one `is_cross_link: true`.

## SUCCESS CRITERIA

### Structural

- S1: one `ora-visual` fence, parseable JSON.
- S2: schema validity.
- S3: `type == "concept_map"`.
- S4: `mode_context == "synthesis"`.
- S5: `canvas_action == "replace"`.
- S6: `relation_to_prose == "integrated"`.
- S7: `len(concepts) ≥ 4` with at least two distinct hierarchy_level=0 roots (the frameworks).
- S8: `len(linking_phrases) ≥ 2`.
- S9: `len(propositions) ≥ 4`, all ids resolve.
- S10: at least one `is_cross_link: true`.
- S11: `focus_question` non-empty.
- S12: `semantic_description` complete, `short_alt ≤ 150`.

### Semantic

- M1: both frameworks' core claims/structures mapped in prose.
- M2: at least one cross-link has explicit prose evidence of structural correspondence (mechanism match, not wording match).
- M3: at least one productive tension identified in prose and marked via a linking phrase in the envelope.
- M4: emergent insight named in prose.
- M5: one limitation explicitly named.

### Composite

- C1: every `concept.label` appears in prose or is derivable from it.
- C2: cross-link propositions correspond to prose "Structural parallels" claims.
- C3: the framework identified as A in prose maps to the concept with higher prose-salience.

```yaml
success_criteria:
  mode: synthesis
  version: 1
  structural:
    - { id: S1,  check: envelope_present }
    - { id: S2,  check: envelope_schema_valid }
    - { id: S3,  check: type_equals, value: concept_map }
    - { id: S4,  check: mode_context_equals, value: synthesis }
    - { id: S5,  check: canvas_action_equals, value: replace }
    - { id: S6,  check: relation_to_prose_equals, value: integrated }
    - { id: S7,  check: two_root_frameworks_min_four_concepts }
    - { id: S8,  check: min_linking_phrases, min: 2 }
    - { id: S9,  check: propositions_resolve_ids, min: 4 }
    - { id: S10, check: at_least_one_cross_link }
    - { id: S11, check: focus_question_nonempty }
    - { id: S12, check: semantic_description_complete }
  semantic:
    - { id: M1, check: both_frameworks_mapped }
    - { id: M2, check: cross_link_mechanism_evidence }
    - { id: M3, check: productive_tension_present }
    - { id: M4, check: emergent_insight_named }
    - { id: M5, check: limitation_named }
  composite:
    - { id: C1, check: concept_labels_in_prose }
    - { id: C2, check: cross_links_match_prose_parallels }
    - { id: C3, check: framework_A_salience }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The False Synthesis Trap (inverse of M2).** Claiming a connection that is a surface analogy without structural correspondence. Correction: apply the mechanism test before declaring a cross-link.

**The Reduction Trap.** Reducing one framework to a special case of the other. Correction: both frameworks remain as peer roots in the envelope (two `hierarchy_level: 0` concepts).

**The Harmony Trap (inverse of M3).** Smoothing over genuine tensions. Correction: productive tensions become linking phrases like "is in tension with" and get their own cross-links.

**The No-Cross-Link Trap (inverse of S10).** Two separate trees with no connection between them is not a synthesis. Correction: add at least one cross-framework link.

## TOOLS

Tier 1: Concept Fan, Challenge, PMI, CAF.
Tier 2: Load based on domain signals from the specific frameworks.

## TRANSITION SIGNALS

- IF the synthesis reveals deep opposition requiring adversarial commitment → propose **Dialectical Analysis**.
- IF the user wants to choose between the frameworks → propose **Constraint Mapping**.
- IF a foundational assumption surfaces → propose **Paradigm Suspension**.
- IF the user begins defining a deliverable → propose **Project Mode**.
- IF the frameworks connect through feedback loops → propose **Systems Dynamics**.
