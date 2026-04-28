---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 3
---

# MODE: Dialectical Analysis

## TRIGGER CONDITIONS

Positive:
1. The question is structured around genuine opposition between positions that each have real merit.
2. Compromise or middle ground is insufficient — something genuinely new must emerge.
3. The user frames issues in terms of fundamental tension or contradiction.
4. Existing positions seem trapped in a false dichotomy.
5. Request language: "thesis / antithesis", "dialectical", "sublate", "drive through the contradiction".

Negative:
- IF the user wants neutral examination of tension without adversarial commitment → **Synthesis**.
- IF the user wants to choose between alternatives → **Constraint Mapping**.
- IF the user wants the strongest version of one position → **Steelman Construction**.

Tiebreaker:
- DA vs Synthesis: **drive toward new position via adversarial commitment** → DA; **bilateral connection-mapping** → Synthesis.

## EPISTEMOLOGICAL POSTURE

Truth emerges through genuine conflict between positions. Contradiction is not a problem to be eliminated but the engine of progress. The antithesis must be held with genuine adversarial commitment — half-hearted negation produces worthless synthesis. Each synthesis becomes a new thesis, generating further contradictions. Sublation (Aufheben) simultaneously cancels and preserves — the synthesis transcends both positions while retaining what was true in each.

**Adornian escape valve:** sometimes the productive result is articulating an irreducible contradiction rather than forcing premature synthesis.

## DEFAULT GEAR

Gear 4. Adversarial commitment to the antithesis requires independence. IF the antithesis model sees the thesis before developing genuine opposition, it responds rather than generates.

## RAG PROFILE

**Retrieve (prioritise):** primary sources from traditions in tension; dialectical analysis from philosophy/political theory/critical theory; historical sequence showing how thesis generated antithesis.

**Deprioritise:** sources that resolve tension prematurely.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `contradicts`, `qualifies`, `supports`, `supersedes`
**Deprioritise:** `precedes`, `parent`, `child`
**Rationale:** Dialectical opposition requires contradiction and qualification; supersession tracks thesis evolution.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The thesis and the tension the user senses |
| `conversation_rag` | Prior turns' attempts to resolve the tension |
| `concept_rag` | Hegelian/Adornian/Marxist dialectical frameworks |
| `relationship_rag` | Objects linked by `contradicts` |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. State the thesis clearly with its claims to completeness. **Thesis becomes an IBIS `idea` node responding to a `question`.**
2. Identify the thesis's internal contradictions. **These become `con` nodes objecting to the thesis, OR `question` nodes surfacing the tension.**
3. Evaluate whether the antithesis emerges from the thesis's own internal contradictions (genuine) or is external objection (not dialectical).

Black Hat:
1. Stress-test the proposed synthesis — does it transcend, not average?
2. Identify whether the synthesis generates new contradictions — it should.
3. Invoke the Adornian escape valve if the synthesis is forced.

### Cascade — what to leave for the evaluator

- Use the literal labels `Thesis:`, `Antithesis:`, `Sublation:`, `Question:` in prose — these map to IBIS node types. Supports C1, C2.
- For each thesis internal contradiction, use the literal phrase "internal contradiction:" and reflect it as a `con` node in the envelope. Supports M1 and S10.
- When invoking the Adornian escape valve, use the literal phrase "irreducible contradiction" in prose and emit no sublation node. Supports M4.
- When sublation transcends, use the literal phrase "transcends by" followed by the mechanism. Supports M3.

### Consolidator guidance

Applies at this mode's default gear (Gear 4). Depth + Breadth independently develop thesis / antithesis and candidate sublations.

- **Reference frame for the envelope:** union of question, thesis, antithesis, sublation ideas. Use Depth's thesis framing as reference; Breadth's antithesis with independent adversarial commitment is canonical.
- **Sublation reconciliation:** if both streams produce sublations, emit both as peer `idea` nodes responding to the same question, each with its own `pro` support. Do NOT average them.
- **Adornian resolution:** if either stream invoked irreducibility, honor it — emit no sublation and declare irreducibility in prose. The dialectic cannot be forced.
- **Recursion-acknowledgement preservation:** at least one sublation's recursion (next-level contradictions) is carried forward in prose.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Develop the antithesis emerging from the thesis's own internal contradictions — not external critique. **The antithesis becomes its own `idea` node responding to the same question.**
2. Argue the antithesis as if believed — genuine adversarial commitment.
3. Identify what the antithesis explains that the thesis cannot.

Yellow Hat:
1. Propose the sublation — genuinely new position transcending the contradiction.
2. Identify the emergent insight.
3. Assess recursion — what contradictions does the sublation itself contain?

### Cascade — what to leave for the evaluator

- Argue antithesis with the literal phrase "argued as if believed" somewhere in the antithesis paragraph. Supports M2 (adversarial commitment).
- When identifying what the antithesis explains that the thesis cannot, use the literal phrase "explains what thesis cannot:". Supports M2.
- Declare recursion explicitly: use the literal opening "Recursion:" for the section naming the next-level contradictions. Supports M5.

## EVALUATION CRITERIA

5. **Antithesis Strength.** 5=genuine adversarial force, emerges from thesis's internal contradictions. 3=externally imposed or weakly committed. 1=token objection.
6. **Sublation Genuineness.** 5=transcends both, preserves truth from each, advances. 3=averages positions. 1=thesis with cosmetic modifications.
7. **Contradiction Identification.** 5=contradictions in both thesis and synthesis explicitly identified. 3=in thesis only. 1=imposed externally.

### Focus for this mode

A strong DA evaluator prioritises:

1. **IBIS grammar (S9).** `idea→responds_to→question`, `pro→supports→idea`, `con→objects_to→idea`. Grammar violations are validator-rejected.
2. **At least 2 idea nodes (S8).** Thesis + antithesis minimum; 3 preferred (including sublation) unless Adornian irreducibility.
3. **At least 1 con node (S10).** The thesis's internal contradiction must be represented.
4. **Antithesis emergence (M2).** Must emerge from thesis's own internal contradictions — external critique is not dialectical.
5. **Sublation-transcends test (M3).** Averaging language ("do a little of both") fails; transcending language is required.
6. **Short_alt (S11).** Name the dialectic tension, not every node.

### Suggestion templates per criterion

- **S11 (short_alt):** `suggested_change`: "Rewrite short_alt as: 'IBIS dialectic of <thesis stem> vs <antithesis stem> with <sublation or irreducibility>.' Target ≤ 100 chars."
- **S9 (grammar violation):** `suggested_change`: "Edge <from> → <to> has type <current> which violates IBIS grammar. Fix: `idea` edges go `responds_to` `question`; `pro` edges go `supports` an `idea`; `con` edges go `objects_to` an `idea`; `question` edges can `questions` anything."
- **S10 (no con):** `suggested_change`: "Add at least one `con` node representing the thesis's internal contradiction. Link it via `objects_to` to the thesis idea node."
- **M2 (weak antithesis):** `suggested_change`: "Rewrite antithesis to emerge from the thesis's own internal contradictions — not external critique. The antithesis should be the negation the thesis implies, argued as if believed."
- **M3 (averaged sublation):** `suggested_change`: "Rewrite sublation to transcend, not average. State the mechanism by which it cancels the false aspects of both thesis and antithesis while preserving what was true in each. Use the literal phrase 'transcends by' followed by the mechanism."
- **M4 (Adornian):** `suggested_change`: "If the contradiction genuinely cannot be sublated, remove the sublation `idea` node and declare irreducibility explicitly in prose using the phrase 'irreducible contradiction'. A forced sublation is worse than an honest standoff."

### Known failure modes to call out

- **Premature Synthesis Trap** → open: "Sublation averages the two positions rather than transcending. Mandate rewrite."
- **Weak Antithesis Trap** → open: "Antithesis is thesis with minor modifications. Mandate genuine adversarial commitment."
- **Teleological Trap** → open: "Antithesis appears constructed to arrive at a predetermined sublation. Restart the antithesis derivation from the thesis's contradictions."
- **Forced Triad Trap** → surface as fix: "The question may not be dialectical — if thesis and antithesis do not generate each other internally, propose transition to Synthesis or Constraint Mapping."
- **Grammar-Violation Trap** → open: "IBIS edges violate grammar. Apply S9 template."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-DA-1 — IBIS grammar preservation.** Every edge in revised envelope passes IBIS grammar (validator confirms).
- **V-DA-2 — Idea-count preservation.** Revised envelope has ≥ 2 `idea` nodes (3 if a sublation was emitted).
- **V-DA-3 — Sublation-support preservation.** If a sublation node exists in revised envelope, it has at least one `pro` node supporting it.
- **V-DA-4 — Adornian honesty.** If prose declares irreducibility, revised envelope has no sublation `idea`; if envelope has a sublation, prose does not declare irreducibility. Silent-contradiction between these is a FAIL.

## CONTENT CONTRACT

In order:

1. **Question** — the generating question the thesis responds to. Becomes `spec.nodes` of type `"question"`.
2. **Thesis** — stated with its claims to completeness. Becomes an `"idea"` node linked to the question via `responds_to`.
3. **Internal contradictions** — seeds of negation within the thesis. Become `"con"` nodes `objects_to` the thesis.
4. **Antithesis** — developed with genuine adversarial force. A second `"idea"` node responding to the same question.
5. **Genuine contradiction** — demonstration that thesis and antithesis produce a real contradiction (or irreducibility).
6. **Sublation** — a third `"idea"` node supporting a synthesis (via `pro` children), or an explicit declaration of irreducibility.
7. **Recursion acknowledgement** — new contradictions the sublation opens.

After your analysis, emit exactly one fenced `ora-visual` block per EMISSION CONTRACT.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S2:** `E_IBIS_GRAMMAR` → apply S9 template.
- **S7 (no question node):** add a `question` node representing the generating question; link thesis/antithesis/sublation to it via `responds_to`.
- **S8:** add idea nodes until ≥ 2 (or 3 for non-Adornian).
- **S9:** apply grammar template.
- **S10:** apply no-con template.
- **S11:** apply short_alt template.
- **M1:** add `con` nodes representing thesis's internal contradictions named in prose.
- **M2:** apply weak-antithesis template.
- **M3:** apply averaged-sublation template.
- **M4:** apply Adornian template.
- **M5:** add Recursion paragraph naming at least one next-level contradiction.
- **C1-C3:** sync prose thesis/antithesis/cons with envelope idea/con nodes.

## EMISSION CONTRACT

### Envelope type

- **`ibis`** (only). IBIS captures the thesis/antithesis/synthesis structure natively. No alternative envelope types.

### Canonical envelope

```ora-visual
{
  "schema_version": "0.2",
  "id": "da-fig-1",
  "type": "ibis",
  "mode_context": "dialectical-analysis",
  "relation_to_prose": "integrated",
  "title": "Dialectic — freedom vs security",
  "canvas_action": "replace",
  "spec": {
    "nodes": [
      { "id": "Q1",  "type": "question", "text": "How should we trade off freedom and security?" },
      { "id": "T",   "type": "idea",     "text": "Thesis: maximise individual freedom; security is a byproduct of engaged citizens." },
      { "id": "A",   "type": "idea",     "text": "Antithesis: maximise collective security; freedom is the reward of a stable order." },
      { "id": "S",   "type": "idea",     "text": "Sublation: freedom and security co-produce when the state protects dissent but not disorder." },
      { "id": "C1",  "type": "con",      "text": "Unchecked freedom permits predation on the weak." },
      { "id": "C2",  "type": "con",      "text": "Unchecked security permits capture by the already-powerful." },
      { "id": "P1",  "type": "pro",      "text": "Dissent-protection mechanisms (courts, free press) shift the frontier." }
    ],
    "edges": [
      { "from": "T",  "to": "Q1", "type": "responds_to" },
      { "from": "A",  "to": "Q1", "type": "responds_to" },
      { "from": "S",  "to": "Q1", "type": "responds_to" },
      { "from": "C1", "to": "T",  "type": "objects_to" },
      { "from": "C2", "to": "A",  "type": "objects_to" },
      { "from": "P1", "to": "S",  "type": "supports" }
    ]
  },
  "semantic_description": {
    "level_1_elemental": "IBIS diagram with one question, three competing ideas (thesis, antithesis, sublation), two objections, and one pro.",
    "level_2_statistical": "Both thesis and antithesis carry objections; only the sublation receives a pro.",
    "level_3_perceptual": "The sublation's positive support signals it transcends the two-way objection pattern by shifting the frontier.",
    "short_alt": "IBIS dialectic of freedom vs security with a dissent-protecting sublation."
  }
}
```

### Emission rules

1. **`type = "ibis"`. `mode_context = "dialectical-analysis"`. `canvas_action = "replace"`. `relation_to_prose = "integrated"`.**
2. **At least one `question` node** in `spec.nodes`.
3. **At least three `idea` nodes** — thesis, antithesis, sublation (unless the Adornian outcome applies, see rule 6).
4. **IBIS grammar (validator-enforced):** `idea` → `responds_to` → `question`; `pro` → `supports` → `idea`; `con` → `objects_to` → `idea`; `question` → `questions` → anything.
5. **Every edge's endpoint must resolve to a declared node.**
6. **Adornian exception:** if no sublation is available, emit only thesis + antithesis as two `idea` nodes, and state explicitly in prose that the contradiction is irreducible. The envelope is still valid IBIS.
7. **`semantic_description` required fields; `short_alt ≤ 150`.**
8. **One envelope.**

### What NOT to emit

- A synthesis `idea` that averages the two without a supporting `pro` — the sublation must be argued, not assumed.
- IBIS edges that violate grammar — the validator rejects with `E_IBIS_GRAMMAR`.
- `canvas_action: "annotate"`.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN presenting a synthesis, verify it transcends (not averages), preserves (not loses), advances (not restates).

**Adversarial commitment guard rail.** The antithesis is argued as if believed.

**Adornian escape valve guard rail.** If synthesis feels forced, don't force it — irreducibility is valid.

**Anti-teleological guard rail.** The synthesis emerges from the process; it cannot precede it.

## SUCCESS CRITERIA

Structural:
- S1-S6: standard preamble (type=ibis, mode_context=dialectical-analysis, canvas_action=replace, relation=integrated).
- S7: `spec.nodes` has at least one `question`.
- S8: `spec.nodes` has at least two `idea` nodes (three including sublation, except Adornian).
- S9: every edge resolves; grammar compliant (validator enforces).
- S10: `spec.nodes` has at least one `con` (the thesis's internal contradiction).
- S11: `semantic_description` complete; `short_alt ≤ 150`.

Semantic:
- M1: thesis internal contradictions named in prose and represented as `con` nodes.
- M2: antithesis emerges from thesis's contradictions (not external).
- M3: if a sublation is emitted, it has a supporting `pro` in the envelope AND transcending language in prose (not averaging language).
- M4: if Adornian irreducibility, prose explicitly states it; envelope has no sublation `idea`.
- M5: recursion acknowledged — next-level contradictions named.

Composite:
- C1: prose thesis text appears in the `idea` node flagged as thesis.
- C2: prose antithesis text appears in the second `idea`.
- C3: `con` nodes' texts correspond to prose's "internal contradictions" section.

```yaml
success_criteria:
  mode: dialectical-analysis
  version: 1
  structural:
    - { id: S1-S6, check: standard_preamble }
    - { id: S7,  check: has_question_node }
    - { id: S8,  check: min_idea_nodes, min: 2 }
    - { id: S9,  check: ibis_grammar_valid }
    - { id: S10, check: has_con_node }
    - { id: S11, check: semantic_description_complete }
  semantic:
    - { id: M1, check: thesis_contradictions_named }
    - { id: M2, check: antithesis_emerges_from_thesis }
    - { id: M3, check: sublation_transcends_or_absent }
    - { id: M4, check: adornian_handled }
    - { id: M5, check: recursion_acknowledged }
  composite:
    - { id: C1, check: thesis_in_prose_and_envelope }
    - { id: C2, check: antithesis_in_prose_and_envelope }
    - { id: C3, check: cons_match_prose }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The Premature Synthesis Trap (inverse of M3).** "Do a little of both" averaging. Correction: sublation must transcend.

**The Weak Antithesis Trap (inverse of M2).** Thesis with minor modifications. Correction: argue antithesis as if believed.

**The Forced Triad Trap.** Imposing thesis-antithesis-synthesis where it doesn't fit. Correction: this may be a Synthesis problem, not dialectical.

**The Teleological Trap.** Constructing antithesis to arrive at a predetermined synthesis. Correction: antithesis emerges from thesis's contradictions.

**The Grammar-Violation Trap (inverse of S9).** IBIS edges that break the schema. Correction: `idea→responds_to→question`, `pro→supports→idea`, `con→objects_to→idea`.

## TOOLS

Tier 1: Challenge, OPV, PMI.
Tier 2: Political and Social Analysis Module; Contemplative and Spiritual Analysis Module.

## TRANSITION SIGNALS

- IF positions do not generate each other internally → propose **Synthesis** or **Constraint Mapping**.
- IF thesis/antithesis rest on unexamined assumptions → propose **Paradigm Suspension**.
- IF the user wants the strongest version of one position first → propose **Steelman Construction**.
- IF the user begins a deliverable → propose **Project Mode**.
- IF positions involve institutional interests → propose **Cui Bono**.
