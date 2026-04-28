---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 3
---

# MODE: Relationship Mapping

## TRIGGER CONDITIONS

Positive:
1. "How do these connect"; systems analysis without temporal dynamics.
2. Causal modelling where acyclicity is the structural expectation (not feedback).
3. Dependency graphs; "what affects what".
4. Mapping the structure of a situation rather than analysing behaviour.
5. Request language: "relationship map", "causal DAG", "dependency graph", "draw the connections".

Negative:
- IF the relationships involve feedback loops, delays, or emergent behaviour → **Systems Dynamics** (the DAG becomes a CLD when cycles are present).
- IF the user wants to understand a single concept deeply rather than its connections → **Deep Clarification**.
- IF the user is orienting in unfamiliar territory → **Terrain Mapping**.

Tiebreaker:
- RM vs SD: **static/DAG structure** → RM; **feedback/temporal** → SD.

## EPISTEMOLOGICAL POSTURE

Structure is the primary analytical object. The relationships between entities are as important as the entities themselves. The output is a relational map — entities, connections, directionality, and types of relationship — not a linear narrative. Correlation is distinguished from causation. Dependency is distinguished from influence. Association is distinguished from mechanism.

## DEFAULT GEAR

Gear 3. Sequential adversarial review is sufficient.

## RAG PROFILE

**Retrieve (prioritise):** structural analyses, systems descriptions, dependency documentation, relational frameworks.

**Deprioritise:** descriptive sources about individual entities without structural claims.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `supports`, `contradicts`, `enables`, `requires`, `produces`, `extends`
**Deprioritise:** none — all types relevant.
**Rationale:** Relationship mapping uses the full taxonomy.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The entities or domain to be mapped |
| `conversation_rag` | Prior turns' entity lists and relationship claims |
| `concept_rag` | Mental models supplying structural primitives |
| `relationship_rag` | Domain objects already linked by typed relations |
| `spatial_representation` | Optional — user's own draft map |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. For each proposed connection, assess the type: causal (A causes B), correlational, dependency (A requires B), influential, or structural. **Causal connections become `->` edges in the DAGitty DSL; correlational ones are flagged in prose only.**
2. For causal connections, assess directionality.
3. Identify missing connections the map should contain.

Black Hat:
1. Challenge at minimum two connections. Is each genuine or assumed?
2. Identify where the map presents correlation as causation.
3. Assess completeness.

### Cascade — what to leave for the evaluator

- Label every connection in prose with a literal type prefix: `Causal:`, `Correlational:`, `Dependency:`, `Influential:`, `Structural:`. Supports M1 and the Causation-Correlation guard.
- Use the literal phrase "Acyclicity check:" at the start of the acyclicity paragraph. Supports M4.
- For `causal_dag` envelopes, state `focal_exposure` and `focal_outcome` in prose verbatim before emitting.
- When a cycle is detected, emit no envelope and write the literal phrase "Proposing transition to Systems Dynamics" in prose. Supports Transition-on-loop guard.
- **short_alt discipline — IMPORTANT (Phase 5 iteration).** Emit `spec.semantic_description.short_alt` in Cesal form: for `concept_map` — `"Concept map of <relationship domain ≤ 60 chars>."`; for `causal_dag` — `"Causal DAG of <exposure> on <outcome>."`. TARGET ≤ 100 chars. HARD MAX 150 chars — exceeding rejects the envelope with `E_SCHEMA_INVALID`. Do NOT list every node, edge, or connection type inside short_alt. Good: `"Causal DAG of exercise on sleep quality."` (40 chars). Bad: `"Concept map of the relationships between exercise, sleep, stress, caffeine, age, and other confounders with typed edges for causal, correlational, and dependency connections..."` (180+ chars — rejected).
- **Envelope-as-final-block + shape verification (Phase 5 iter-2).** The fenced `ora-visual` block MUST be the FINAL block of your response. Do not emit prose after it; do not omit it even under token pressure — if you hit budget, truncate prose rather than drop the envelope. Before emitting, verify shape: `concept_map` needs `concepts ≥ 4`, `linking_phrases ≥ 2`, `propositions ≥ 3` with all ids resolving, AND at least one proposition with `is_cross_link: true`; `causal_dag` needs `dsl` parseable as DAGitty, `focal_exposure` and `focal_outcome` both node ids in the DSL, no cycles. S1 + S2 + S7 are the dominant failures at this mode — S1 means the fence was missing; S2 + S7 mean the shape was wrong. Both are catchable with a pre-emission checklist.

### Consolidator guidance

Not applicable at this mode's default gear (Gear 3). If promoted to Gear 4, use Depth stream's acyclicity verdict as authoritative (structure over narrative wins); merge Breadth stream's non-obvious connections into the envelope only if they pass Depth's causation-correlation audit.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Identify all entities relevant to the user's question.
2. For each connection, state the type and directionality.
3. Identify at minimum two non-obvious connections.

Yellow Hat:
1. Identify which relationships are most important (disrupting which would change the most).
2. Surface the organising structure (hub-and-spoke, chain, hierarchy).
3. Note connections to adjacent domains.

### Cascade — what to leave for the evaluator

- Identify at least two non-obvious connections with the literal phrase "non-obvious connection" in prose. Supports M2.
- Name the organising structure with the literal phrase "Organising structure:" followed by one of `hub-and-spoke` / `chain` / `hierarchy` / `network` / `bipartite`. Supports M3.
- Name any connection to an adjacent domain with `Adjacent:` prefix.

## EVALUATION CRITERIA

5. **Relational Precision.** 5=every connection has stated type and directionality. 3=one connection miscategorised. 1=no type/directionality.
6. **Structural Completeness.** 5=all significant entities + at minimum two non-obvious connections. 3=non-obvious connections missing. 1=significant entities omitted.
7. **Map vs Narrative.** 5=structured as a relational map, not a linear narrative. 3=structure embedded in narrative. 1=purely linear.
8. **Acyclicity Integrity.** 5=the emitted DAG is genuinely acyclic; any cycles prompt a transition to Systems Dynamics. 3=one subtle cycle overlooked. 1=cycles present without transition proposal.

### Focus for this mode

A strong RM evaluator prioritises:

1. **Acyclicity (S8, M4).** A DAG with a cycle is structurally invalid; mandate transition to SD or envelope revision.
2. **Type-match (S3).** `concept_map` for heterogeneous relations; `causal_dag` for causal framings with focal exposure/outcome.
3. **Causation-correlation distinction (M1).** Every connection has a type prefix in prose; mislabelling correlation as causation is mandatory fix.
4. **Cross-link / non-obvious connection (M2, S7).** ≥ 2 non-obvious connections marked.
5. **Short_alt (S10).** Name the relationship being mapped, not every node.

### Suggestion templates per criterion

- **S10 (short_alt):** `suggested_change`: "Rewrite short_alt as: 'Causal DAG of <exposure> on <outcome>' OR 'Concept map of <domain> with typed relationships' — the shorter of the two. Target ≤ 100 chars."
- **S7 (concept_map shape):** apply concept-map floor template from Terrain Mapping's guidance.
- **S8 (causal_dag has cycle):** `suggested_change`: "Cycle detected between nodes <A, B, C>. Either (a) remove one edge to break the cycle and document why the removed edge is less defensible, or (b) suppress the envelope and propose transition to Systems Dynamics."
- **M1 (connection types not declared):** `suggested_change`: "Prefix each connection in prose with `Causal:`, `Correlational:`, `Dependency:`, `Influential:`, or `Structural:`. Default to the weakest relationship type the evidence supports."
- **M2 (non-obvious connections):** `suggested_change`: "Surface at least two non-obvious connections with the literal phrase 'non-obvious connection' in prose."

### Known failure modes to call out

- **Silent-Cycle Trap** → open: "DAG contains a cycle but prose does not transition to Systems Dynamics. Mandate either edge removal with rationale or transition."
- **Causation-Correlation Trap** → open: "Connection X labelled causal but prose presents only correlation evidence. Mandate relabel or add causal evidence."
- **Linear Reduction Trap** → open: "Output structured as a linear narrative rather than a relational map. Restructure."
- **Kitchen Sink Trap** → surface as SUGGESTED: "Map includes connections not central to the focal question; trim to significant relationships."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-RM-1 — Acyclicity preservation.** Revised envelope is acyclic (validator confirms via `E_GRAPH_CYCLE` absent). Silent cycle introduction is a FAIL.
- **V-RM-2 — Focal-pair preservation.** For `causal_dag`, revised `focal_exposure` and `focal_outcome` both appear as node ids in revised `spec.dsl`.
- **V-RM-3 — Connection-type preservation.** Every prose connection has a type prefix; revision must not strip these.

## CONTENT CONTRACT

In order:

1. **Focal question** — the mapping question. Becomes the connection of exposure to outcome in a DAG (or the `focus_question` in a concept map).
2. **Entities** — all relevant entities named. Become `concepts` (concept_map) or nodes in `dsl` (causal_dag).
3. **Connections** — relationships with type and directionality for each.
4. **Organising structure** — the overall pattern.
5. **Key relationships** — which connections are most significant.
6. **Boundary statement** — what the map does not include.
7. **Acyclicity check** — confirmation that no feedback loops were found (or, if found, a transition proposal to Systems Dynamics).

After your analysis, emit exactly one fenced `ora-visual` block per the EMISSION CONTRACT.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S2:** `E_GRAPH_CYCLE` → apply S8 cycle template. `E_UNRESOLVED_REF` → proposition or DSL reference is unresolved; fix.
- **S7 (concept_map):** apply concept-map floor template.
- **S8 (causal_dag):** verify DAGitty DSL parses; ensure `focal_exposure` and `focal_outcome` are node ids in the DSL; remove cycles.
- **S10:** apply short_alt template.
- **M1-M5:** apply the per-criterion templates above.
- **C1-C3:** sync prose entities / key relationships / acyclicity claim with envelope reality.

## EMISSION CONTRACT

### Envelope type selection

- **`concept_map`** — when the relationships are heterogeneous (causal + correlational + structural + dependency all mixed) and typed linking phrases carry the information.
- **`causal_dag`** — when the relationships are specifically causal and the user needs exposure/outcome framing (DAGitty DSL, with focal_exposure and focal_outcome).

Default: `concept_map`. Use `causal_dag` when the prose's focal question is phrased as "does X cause Y" or "what confounds X → Y".

### Canonical envelope (causal_dag)

```ora-visual
{
  "schema_version": "0.2",
  "id": "rm-fig-1",
  "type": "causal_dag",
  "mode_context": "relationship-mapping",
  "relation_to_prose": "integrated",
  "title": "Causal structure — exercise effect on sleep quality",
  "canvas_action": "replace",
  "spec": {
    "dsl": "dag { exercise [exposure]; sleep [outcome]; stress [latent]; age; caffeine; exercise -> sleep; stress -> exercise; stress -> sleep; age -> sleep; caffeine -> sleep }",
    "focal_exposure": "exercise",
    "focal_outcome": "sleep"
  },
  "semantic_description": {
    "level_1_elemental": "Causal DAG with 5 nodes (exercise, sleep, stress, age, caffeine) and 5 directed edges.",
    "level_2_statistical": "Stress is a latent confounder of both exposure and outcome; age and caffeine are exogenous covariates.",
    "level_3_perceptual": "The causal path exercise → sleep is shadowed by a stress backdoor; conditioning on stress is required for an unbiased estimate.",
    "short_alt": "Causal DAG of exercise on sleep with stress as a latent confounder."
  }
}
```

### Emission rules

1. **`mode_context = "relationship-mapping"`. `canvas_action = "replace"`. `relation_to_prose = "integrated"`.**
2. **`type ∈ {"concept_map", "causal_dag"}`.**
3. **Causal DAG specifics:** `spec.dsl` is a DAGitty string; `focal_exposure` and `focal_outcome` are node ids present in the DSL. The DAG must be acyclic — the validator rejects cycles with `E_GRAPH_CYCLE`.
4. **Concept map specifics:** `spec.concepts` ≥ 4, `spec.linking_phrases` ≥ 2, `spec.propositions` ≥ 3, at least one `is_cross_link`.
5. **No cycles.** If a cycle appears in the analysis, stop emission and propose a transition to Systems Dynamics.
6. **`semantic_description` required fields; `short_alt ≤ 150`.**
7. **One envelope.**

### What NOT to emit

- A DAG with a cycle — that's a CLD and belongs in Systems Dynamics.
- A concept map where every link has the same linking phrase (no relational precision).
- `canvas_action: "annotate"`.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN recommending an action based on the map, pause — Relationship Mapping produces structural understanding.

**Structure-over-narrative guard rail.** IF the output reads as a linear narrative, restructure.

**Acyclicity guard rail.** Before emitting a `causal_dag`, verify no cycles.

**Humility guard rail.** State what the map omits.

**Transition-on-loop guard rail.** IF a cycle is detected, emit no envelope and propose Systems Dynamics.

## SUCCESS CRITERIA

Structural:
- S1: one `ora-visual` fence, parseable JSON.
- S2: schema valid.
- S3: `type ∈ {"concept_map", "causal_dag"}`.
- S4: `mode_context == "relationship-mapping"`.
- S5: `canvas_action == "replace"`.
- S6: `relation_to_prose == "integrated"`.
- S7: if concept_map: `concepts ≥ 4`, `linking_phrases ≥ 2`, `propositions ≥ 3`, at least one `is_cross_link`.
- S8: if causal_dag: `dsl` parses, `focal_exposure` and `focal_outcome` resolve to declared nodes, graph is acyclic.
- S9: (reserved for future)
- S10: `semantic_description` complete, `short_alt ≤ 150`.

Semantic:
- M1: every connection type (causal / correlational / dependency / etc) declared in prose.
- M2: at least two non-obvious connections surfaced.
- M3: organising structure named in prose.
- M4: cycles either absent or handled via transition to SD.
- M5: boundary statement declares what is out of scope.

Composite:
- C1: every entity named in prose exists as a node/concept in the envelope.
- C2: prose "key relationships" correspond to high-degree nodes or focal edges in the envelope.
- C3: acyclicity claim in prose matches envelope reality.

```yaml
success_criteria:
  mode: relationship-mapping
  version: 1
  structural:
    - { id: S1,  check: envelope_present }
    - { id: S2,  check: envelope_schema_valid }
    - { id: S3,  check: type_in_allowlist, allowlist: [concept_map, causal_dag] }
    - { id: S4,  check: mode_context_equals, value: relationship-mapping }
    - { id: S5,  check: canvas_action_equals, value: replace }
    - { id: S6,  check: relation_to_prose_equals, value: integrated }
    - { id: S7,  check: concept_map_shape, applies_to: concept_map }
    - { id: S8,  check: causal_dag_shape, applies_to: causal_dag }
    - { id: S10, check: semantic_description_complete }
  semantic:
    - { id: M1, check: connection_types_declared }
    - { id: M2, check: two_nonobvious_connections }
    - { id: M3, check: organising_structure_named }
    - { id: M4, check: cycles_absent_or_transitioned }
    - { id: M5, check: boundary_stated }
  composite:
    - { id: C1, check: entity_prose_envelope_match }
    - { id: C2, check: key_relationships_match_envelope }
    - { id: C3, check: acyclicity_claim_matches_envelope }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The Linear Reduction Trap.** Flattening a network into a sequential narrative. Correction: Present as structure.

**The Kitchen Sink Trap.** Dense map conveying no structure. Correction: Map only what's significant.

**The Causation-Correlation Trap (inverse of M1).** Labelling correlation as causation without mechanism. Correction: default to the weakest relationship type the evidence supports.

**The Silent-Cycle Trap (inverse of M4, S8).** Emitting a DAG with a cycle. Correction: cycles route to Systems Dynamics; either restructure or transition.

## TOOLS

Tier 1: CAF, RAD, OPV, C&S.
Tier 2: Module 3 — Structural Analysis.

## TRANSITION SIGNALS

- IF the map reveals feedback loops → propose **Systems Dynamics**.
- IF the relational structure reveals institutional interests → propose **Cui Bono**.
- IF the user wants to understand one specific relationship deeply → propose **Deep Clarification**.
- IF the user begins defining a deliverable → propose **Project Mode**.
- IF the mapped relationships span multiple domains → propose **Synthesis**.
