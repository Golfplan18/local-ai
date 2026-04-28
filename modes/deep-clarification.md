---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 3
no_visual_default: true
---

# MODE: Deep Clarification

## TRIGGER CONDITIONS

Positive:
1. "Why does X work that way"; "explain the mechanics of"; "what's really going on underneath".
2. Technical depth in a known domain.
3. The user has an established position and wants to push past first-level explanation to underlying mechanics.
4. The domain is already identified — the user is not exploring, they are drilling.
5. Request language: "deeper", "mechanism", "how does it actually work", "explain the physics / math / internals".

Negative:
- IF user is unfamiliar with the domain and needs orientation → **Terrain Mapping**.
- IF user has a deliverable in mind → **Project Mode**.
- IF user wants to question foundational assumptions → **Paradigm Suspension**.

Tiebreaker:
- DC vs Terrain Mapping: **already familiar, wants depth** → DC; **unfamiliar, wants orientation** → TM.
- DC vs Paradigm Suspension: **explain within the frame** → DC; **question the frame** → PS.

## EPISTEMOLOGICAL POSTURE

The domain is accepted. The position or claim is known. The task is to push understanding deeper — from surface explanation to mechanism, from mechanism to underlying principle, from principle to foundational structure. Primary sources and technical depth are preferred over surveys.

## DEFAULT GEAR

Gear 3. Sequential review. Depth pushes toward the deepest available explanation; Breadth checks whether the clarification is genuinely deeper or merely more elaborate.

## RAG PROFILE

**Retrieve (prioritise):** primary sources, technical papers, foundational texts, mechanistic explanations, canonical reference works.

**Deprioritise:** surveys and introductions — the user already has surface-level understanding.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `supports`, `extends`, `derived-from`, `requires`
**Deprioritise:** `precedes`, `parent`, `child`
**Rationale:** Mechanistic understanding follows evidential chains.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The phenomenon to explain deeper |
| `conversation_rag` | The user's starting level of understanding |
| `concept_rag` | Mechanistic mental models |
| `relationship_rag` | Objects linked by `derived-from` / `requires` |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. Start from the user's current level and identify the next mechanism beneath it.
2. For each mechanism provided, identify the next level beneath. Push ≥ 2 levels deeper.
3. Distinguish established explanations from current-best-understanding (contested or incomplete). Mark the epistemic boundary.

Black Hat:
1. Test whether each "deeper" explanation is genuinely deeper (mechanism) or merely more detailed.
2. Identify where depth reaches the limits of current knowledge.
3. Identify ≥ 1 common misconception arising at the requested depth.

### Cascade — what to leave for the evaluator

- Label each explanatory level with `Surface:` / `Level 1 beneath:` / `Level 2 beneath:` in prose. Supports M2 depth floor.
- Use the literal phrase "mechanism:" when introducing each level's causal/structural substrate. Supports M3.
- Use the literal phrase "epistemic boundary:" when knowledge ends. Supports M4.
- Envelope is optional; if the mechanism is non-procedural (e.g. Rayleigh scattering), suppress the envelope explicitly in prose with "No visual produced — mechanism is not procedural".

### Consolidator guidance

Not applicable at this mode's default gear (Gear 3). If promoted to Gear 4 for high-stakes mechanistic clarification, use Depth's mechanistic chain as reference frame; Breadth's alternative mechanisms and cross-domain analogies are emitted as separate prose sections. Preserve the epistemic boundary at the lesser depth of the two streams.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Identify analogies or parallel mechanisms in other domains.
2. Identify ≥ 1 alternative mechanistic explanation.
3. Surface connections to other areas of the user's knowledge.

Yellow Hat:
1. Assess the point at which further depth becomes academic rather than actionable.
2. Identify the most useful depth for the user's likely purposes.
3. Note where deeper understanding changes practical implications.

### Cascade — what to leave for the evaluator

- Identify ≥ 1 analogy with the literal prefix "Analogy:".
- Identify ≥ 1 alternative mechanistic explanation with the literal prefix "Alternative mechanism:".
- Name at least one practical implication with the literal prefix "Practical implication:". Supports M5.

## EVALUATION CRITERIA

5. **Depth Genuine.** 5=≥ 2 levels below starting understanding, each genuinely mechanistic. 3=one level. 1=horizontal detail.
6. **Epistemic Boundary.** 5=settled vs best-current-understanding marked. 3=boundary unclear. 1=no distinction.

### Focus for this mode

A strong DC evaluator prioritises:

1. **Envelope-optional handling (S1).** Zero envelope is acceptable; if present, must be `flowchart` for procedural mechanisms only.
2. **Depth floor (M2).** ≥ 2 levels of mechanism below surface.
3. **Mechanistic not horizontal (M3).** Each deeper level reveals mechanism, not more surface detail.
4. **Epistemic boundary (M4).** Settled vs best-current-understanding marked.
5. **Unnecessary-envelope trap.** Flowchart for non-procedural mechanism is a mandatory fix.
6. **Short_alt (S5).** Name the mechanism, not every step.

### Suggestion templates per criterion

- **S3/S5 (flowchart short_alt):** `suggested_change`: "If flowchart envelope emitted: rewrite short_alt as 'Flowchart of <mechanism name ≤ 80 chars>.' Target ≤ 100 chars."
- **S1 (envelope emitted for non-procedural mechanism):** `suggested_change`: "Mechanism is not procedural (e.g. scattering, emergence, quantum state). Suppress the envelope; declare in prose: 'No visual produced — mechanism is not procedural.'"
- **M2 (depth floor):** `suggested_change`: "Add a second-level mechanism beneath the current first-level explanation. Ask: what underlies <current level>? State the next mechanism with the literal label 'Level 2 beneath:'."
- **M3 (horizontal detail):** `suggested_change`: "Level <N> provides more surface detail, not a deeper mechanism. Rewrite to reveal what causes the phenomenon at level <N-1>, not to enumerate sub-examples at the same level."
- **M4 (epistemic boundary):** `suggested_change`: "Add 'epistemic boundary:' paragraph distinguishing settled knowledge from current-best-understanding. Name specifically where current science is indeterminate."
- **M5 (no practical implication):** `suggested_change`: "Add 'Practical implication:' paragraph naming how the deeper understanding changes what the user would do or conclude."

### Known failure modes to call out

- **Unnecessary-Envelope Trap** → open: "Flowchart emitted for non-procedural mechanism. Suppress envelope."
- **Lateral Drift Trap** → open: "Level <N> drifts to adjacent topic rather than deeper same-phenomenon. Redirect."
- **Elaboration Trap** → open: "Level <N> adds detail at same level, not deeper mechanism. Depth is vertical."
- **Jargon Trap** → surface as SUGGESTED: "Level <N> replaces accessible explanation with terminology without naming mechanism. State the mechanism in plain terms."

### Verifier checks for this mode

Universal V1-V5 apply (V2/V3/V6 N/A for Gear 3 single-stream); then:

- **V-DC-1 — Envelope-match-mechanism preservation.** If revised envelope is present, mechanism is genuinely procedural. Silent envelope addition for non-procedural mechanisms during revision is a FAIL.
- **V-DC-2 — Depth preservation.** Revised prose retains ≥ 2 mechanistic levels below surface.
- **V-DC-3 — Epistemic-boundary preservation.** Revised prose retains the `epistemic boundary:` declaration.

## CONTENT CONTRACT

In order:

1. **Surface explanation** — the commonly understood explanation, stated concisely as baseline.
2. **Mechanistic clarification** — ≥ 2 levels of deeper explanation, each revealing mechanism.
3. **Epistemic boundary** — where knowledge ends and uncertainty begins.
4. **Practical implications** — how the deeper understanding changes what the user would do or conclude.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S1 (envelope absent but mechanism is procedural):** emit a `flowchart` envelope with Mermaid DSL.
- **S1 (envelope present but mechanism not procedural):** apply suppression template.
- **S2-S5:** ensure `type == "flowchart"`, `dialect == "flowchart"`, DSL starts with `flowchart ` or `graph `, short_alt ≤ 150.
- **M1-M5:** apply the per-criterion templates above.

## EMISSION CONTRACT

**Deep Clarification defaults to NO `ora-visual` block.** The native deliverable is prose; mechanistic depth is linguistic, not spatial.

### Narrow exception — flowchart

Emit a `flowchart` envelope ONLY when the mechanism being clarified is itself procedural or spatial (a multi-step process, a pipeline, a control-flow algorithm). In that narrow case:

- `type = "flowchart"`.
- `mode_context = "deep-clarification"`.
- `canvas_action = "replace"`.
- `relation_to_prose = "integrated"`.
- `spec.dialect = "flowchart"`; `spec.dsl` is Mermaid flowchart syntax (must start with `flowchart ` or `graph `).

**Default: suppress.** When in doubt, emit no envelope.

### Example — narrow exception

```ora-visual
{
  "schema_version": "0.2",
  "id": "dc-fig-1",
  "type": "flowchart",
  "mode_context": "deep-clarification",
  "relation_to_prose": "integrated",
  "title": "TCP retransmission timer mechanism",
  "canvas_action": "replace",
  "spec": {
    "dialect": "flowchart",
    "dsl": "flowchart TD\n  S[Send segment] --> A[Start RTO timer]\n  A --> B{ACK before RTO?}\n  B -->|yes| C[Stop timer, advance window]\n  B -->|no| D[Double RTO, retransmit]\n  D --> A"
  },
  "semantic_description": {
    "level_1_elemental": "Flowchart of TCP retransmission: send → start timer → ACK-or-timeout decision → advance or retransmit with doubled timer.",
    "level_2_statistical": "One decision node, one feedback edge (retransmit returns to start-timer).",
    "level_3_perceptual": "The feedback edge is the retransmission loop; the doubling is captured as a loop edge rather than as growth over time.",
    "short_alt": "Flowchart of TCP retransmission with exponential backoff on timeout."
  }
}
```

### What NOT to emit

- A diagram for a non-procedural mechanism (e.g. "why is the sky blue" — Rayleigh scattering is not a control-flow).
- Any other envelope type.
- `canvas_action: "annotate"`.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN clarification moves toward recommending an action, pause — DC produces understanding.

**Vertical discipline guard rail.** IF exploration drifts to adjacent topics, redirect.

**Honest limits guard rail.** When depth reaches knowledge boundary, say so.

**Suppression-by-default guard rail.** Emit no envelope unless the mechanism is explicitly procedural/spatial.

## SUCCESS CRITERIA

### Structural (prose-first; envelope optional)

- S1: zero-or-one `ora-visual` fence. Absent is the default pass.
- S2: if present, schema valid, `type == "flowchart"`, `mode_context == "deep-clarification"`.
- S3: if present, `dsl` starts with `flowchart ` or `graph `.
- S4: prose contains all four CONTENT CONTRACT sections.
- S5: if present, `semantic_description` complete and `short_alt ≤ 150`.

### Semantic (LLM-reviewer)

- M1: surface explanation stated (not skipped).
- M2: ≥ 2 mechanistic levels below surface.
- M3: each deeper level reveals mechanism (not horizontal detail).
- M4: epistemic boundary stated.
- M5: ≥ 1 practical implication.

```yaml
success_criteria:
  mode: deep-clarification
  version: 1
  envelope_optional: true
  structural:
    - { id: S1, check: zero_or_one_envelope }
    - { id: S2, check: envelope_schema_valid_if_present }
    - { id: S3, check: flowchart_mermaid_dsl_if_present }
    - { id: S4, check: four_content_sections_present }
    - { id: S5, check: semantic_description_complete_if_present }
  semantic:
    - { id: M1, check: surface_explanation_present }
    - { id: M2, check: two_levels_deeper }
    - { id: M3, check: mechanistic_not_horizontal }
    - { id: M4, check: epistemic_boundary_stated }
    - { id: M5, check: practical_implication_present }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8 }
```

## KNOWN FAILURE MODES

**The Lateral Drift Trap.** Moving to adjacent topics. Correction: each level is about the same phenomenon at deeper level.

**The Elaboration Trap (inverse of M3).** More facts at the same level. Correction: depth is vertical (mechanism beneath mechanism).

**The Jargon Trap.** Replacing accessible explanation with terminology. Correction: name a mechanism, not just a vocabulary.

**The Unnecessary-Envelope Trap.** Emitting a flowchart for a non-procedural mechanism. Correction: default to suppression.

## TOOLS

Tier 1: Challenge, CAF, Concept Fan.
Tier 2: Engineering and Technical Analysis Module for technical domains.

## TRANSITION SIGNALS

- IF clarification reveals an unexamined assumption → propose **Paradigm Suspension**.
- IF user begins asking about connections between the clarified concept and others → propose **Relationship Mapping** or **Synthesis**.
- IF user starts defining a deliverable → propose **Project Mode**.
- IF domain is unfamiliar enough to need a broader map first → propose **Terrain Mapping**.
