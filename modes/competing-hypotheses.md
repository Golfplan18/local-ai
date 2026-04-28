---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 2
---

# MODE: Competing Hypotheses

## TRIGGER CONDITIONS

Positive (fire the mode):
1. Multiple explanations exist for the same evidence.
2. The analyst has a favoured hypothesis that needs stress-testing.
3. Evidence is ambiguous or contradictory and the question is "what is actually happening".
4. The situation involves potential deception or information manipulation.
5. ACH-shaped request language: "which explanation fits best", "make me an ACH matrix", "what rules out X", "how would we know if we're wrong", "what's the strongest evidence against each theory".

Negative (route elsewhere):
- IF the user wants to choose between *action* alternatives rather than between *explanations* → **Decision Under Uncertainty** (or **Constraint Mapping** if probabilities don't matter).
- IF the user wants to question the foundational framework rather than test hypotheses within it → **Paradigm Suspension**.
- IF the user wants to trace institutional interests behind competing claims → **Cui Bono**.
- IF only one plausible explanation is on the table and the question is "what evidence would strengthen it" → **Steelman Construction**.

Tiebreakers:
- CH vs DUU: **choosing explanations** → CH; **choosing actions under uncertainty** → DUU.
- CH vs Cui Bono: **evidence-driven diagnosticity** → CH; **interest-driven explanation of who benefits** → CB.

## EPISTEMOLOGICAL POSTURE

Focus on **disconfirmation** rather than confirmation. The most likely hypothesis is the one with the least evidence *against* it, not the most evidence for it. Evidence is evaluated by **diagnosticity** — how well it distinguishes between hypotheses. Evidence consistent with multiple hypotheses has low diagnosticity. Evidence that rules out specific hypotheses has high diagnosticity. The analyst works **across** the evidence-hypothesis matrix (evaluating one piece of evidence against *all* hypotheses) rather than **down** it (collecting evidence for a favoured hypothesis). This directly counters confirmation bias.

## DEFAULT GEAR

Gear 4. Independent evidence assessment is the minimum for reliable output. The methodology's purpose is avoiding confirmation bias. IF one model sees the other's hypothesis ranking before evaluating evidence, the ranking anchors and the methodology fails.

## RAG PROFILE

**Retrieve (prioritise):** primary evidence sources — observational reports, direct testimony, empirical findings, log excerpts. Sources supporting each hypothesis, including hypotheses the user disfavours. IF adversarial, retrieve intelligence-analysis methodology and counter-deception frameworks (Heuer's *Psychology of Intelligence Analysis*).

**Deprioritise:** editorial opinion, interpretive analysis, secondary commentary — these conflate evidence with argument.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `supports`, `contradicts`, `qualifies`, `analogous-to`
**Deprioritise:** `parent`, `child`, `precedes`
**Rationale:** Evidence assessment requires identifying support and contradiction patterns. Analogies across domains surface hidden assumptions.


### RAG PROFILE — INPUT SPEC (context-package fields consumed)

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The question and the user's initial hypothesis set (if any) |
| `conversation_rag` | Prior-turn hypotheses, eliminated explanations, updated credibility scores |
| `concept_rag` | Mental models — Heuer's ACH, falsifiability, base-rate reasoning |
| `relationship_rag` | Domain objects with `supports` / `contradicts` / `qualifies` that ground evidence diagnosticity |
| `prior_spatial_representation` | Any ACH matrix the user drew; preserve hypothesis ids and evidence ids |
| `spatial_representation` | User's current drawing (may encode hypothesis priority spatially) |
| `annotations` | User callouts flagging an evidence item as planted, or a hypothesis as a straw-man |


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
1. List all plausible hypotheses. Include at minimum one hypothesis the user has not proposed. **Each hypothesis becomes a `spec.hypotheses[]` entry with a unique `id` and a short `label`.**
2. List all significant evidence and arguments, regardless of which hypothesis they support. **Each evidence item becomes a `spec.evidence[]` entry with `credibility ∈ {H,M,L}` and `relevance ∈ {H,M,L}`.**
3. For each piece of evidence, assess its consistency with each hypothesis: **`CC`** (strongly consistent), **`C`** (consistent), **`N`** (neutral), **`I`** (inconsistent), **`II`** (strongly inconsistent), **`NA`** (not applicable). The envelope encodes these as a fully-populated `spec.cells[evidence_id][hypothesis_id]` map.

Black Hat directives:
1. Assess the diagnosticity of each piece of evidence. Evidence consistent with all hypotheses provides no diagnostic value — the validator emits `W_ACH_NONDIAGNOSTIC` for rows where all cells equal.
2. Identify the most diagnostic evidence — pieces that sharply distinguish between hypotheses (rows with mixed `CC`/`C` vs `I`/`II` values).
3. Challenge the Breadth model's hypothesis list. Is there a hypothesis not listed that explains the evidence? Is there a listed hypothesis that should be eliminated?
4. Conduct sensitivity analysis: what if the most diagnostic evidence is wrong, deceptive, or missing?

### Cascade — what to leave for the evaluator

Explicit structural cues the Depth analyst must leave so the evaluator can mechanically verify:

- Prefix every hypothesis with a stable id (`H1:`, `H2:` …) in the prose Hypothesis list — exact-match `spec.hypotheses[].id`. Supports C1.
- Prefix every evidence item with a stable id (`E1:`, `E2:` …) in the prose Evidence inventory — exact-match `spec.evidence[].id`. Supports C2.
- Frame the conclusion in elimination terms using the literal phrase "H<id> survives because" (not "is supported by"). Supports M2.
- For each high-diagnosticity evidence item, write the literal phrase "high diagnosticity" in the surrounding sentence. Supports M3.
- For each non-diagnostic evidence row, use the literal phrase "non-diagnostic" in the diagnosticity-assessment paragraph. Supports C4.
- State the surviving hypothesis verbatim (not paraphrased) in the Tentative conclusions paragraph; use "Surviving hypothesis: H<id>". Supports C3.
- **short_alt discipline — IMPORTANT (Phase 5 iteration).** Emit `spec.semantic_description.short_alt` in Cesal form: `"ACH matrix — <surviving hypothesis label ≤ 60 chars> survives."`. TARGET ≤ 100 chars. HARD MAX 150 chars — exceeding rejects the envelope with `E_SCHEMA_INVALID`. Do NOT enumerate every hypothesis or every evidence id inside short_alt. Good: `"ACH matrix — third-party SaaS leak survives elimination."` (56 chars). Bad: `"ACH matrix of four hypotheses (H1-H4) against five evidence items (E1-E5), with Heuer cells showing H4 survives with zero inconsistencies while H2 is eliminated..."` (180+ chars — rejected).
- **C4 non-diagnostic-declaration verification (Phase 5 iter-2).** When the "Diagnosticity assessment" paragraph declares an evidence item as non-diagnostic, the envelope's `spec.cells[<evidence_id>]` MUST have all cells carrying the SAME value across every hypothesis. Non-diagnostic literally means "no variation across hypotheses"; if the prose says `E5` is non-diagnostic but `cells.E5` has varied values, C4 fails. Pre-emission check: for each prose-declared non-diagnostic evidence id, scan the envelope row — if any two cell values differ, either rewrite the cells to all-equal (typically all `N`) or remove the non-diagnostic declaration from prose.

### Consolidator guidance

Applies at this mode's default gear (Gear 4). Depth + Breadth both produce independent matrices. Reconcile as follows:

- **Reference frame for the envelope:** the union of hypotheses (Depth's + Breadth's, de-duplicated by label) and the union of evidence items. Use Depth's cell values where both streams agree; where they disagree on a cell, prefer Depth's (it is the cross-the-matrix-across-all-hypotheses posture) and surface the disagreement in prose.
- **Hypothesis addition rule:** Breadth's additional hypotheses (those not in Depth's list) get added as new columns in the consolidated matrix with Depth's evidence rows — Depth then must estimate cells for those new columns via reasoning from the evidence. If Depth's original cells cannot be extended without new analysis, emit prose noting the gap and mark the new columns' cells as `N` (not `NA`) with a disclosure.
- **Conclusion reconciliation:** if streams endorsed different surviving hypotheses, present both in the Tentative conclusions section with cell-count arithmetic for each; the envelope's conclusion-facing metadata uses the hypothesis with the fewest `I + II` cells (tie-broken by fewer `II`s per C3).
- **Deception disagreement:** if one stream flagged deception on an evidence item and the other did not, retain the flag — err toward the deception-aware posture.

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. Generate the widest plausible set of hypotheses. Include unconventional explanations. At minimum five hypotheses for non-trivial problems; at minimum three for the envelope to be diagnostic.
2. For each hypothesis, identify what evidence would **disconfirm** it — disconfirmation is more diagnostic than confirmation.
3. Identify what evidence is missing that would be most useful — what single piece of information would most change the analysis?

Yellow Hat directives:
1. For each surviving hypothesis, identify its strongest explanatory advantage — what it explains most naturally.
2. Assess what the user gains even if no single hypothesis is confirmed — what has been ruled out, what evidence gaps have been identified.
3. Identify leading indicators — future evidence that would strengthen or weaken each surviving hypothesis.

### Cascade — what to leave for the evaluator

Explicit structural cues the Breadth analyst must leave so the evaluator can mechanically verify:

- Mark at least one hypothesis explicitly as "beyond the user's initial set" in the Hypothesis list. Supports M1.
- For each surviving hypothesis's explanatory advantage paragraph, name the evidence item(s) it explains most naturally by id (`E<n>`).
- For sensitivity analysis, name at least one evidence item whose reversal would change the ranking — use the literal phrase "would change the ranking". Supports M4.
- When adversarial actors are plausible, use the literal phrase "could be manufactured" in the Deception-check paragraph. Supports M5.

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Hypothesis Coverage.** 5=all plausible hypotheses listed including at minimum one beyond the user's initial set. 3=user-proposed hypotheses covered but no additional hypotheses generated. 1=plausible hypotheses missing.
6. **Diagnosticity Assessment.** 5=every piece of evidence assessed for diagnostic value across all hypotheses, high-diagnosticity evidence explicitly identified. 3=consistency assessment performed but diagnosticity not evaluated. 1=evidence evaluated only for favoured hypothesis.
7. **Disconfirmation Rigour.** 5=conclusions based on elimination of least consistent hypotheses, with sensitivity analysis. 3=conclusions drawn but sensitivity analysis absent. 1=conclusions based on confirmation rather than elimination.
8. **Cell Completeness.** 5=every (evidence × hypothesis) cell populated with a Heuer vocabulary value and justified in prose. 3=cells populated but 1-2 are `N` by default rather than genuinely assessed. 1=cells missing.

### Focus for this mode

A strong CH evaluator prioritises in this order:

1. **Cell-completeness first (S9).** Missing cells invalidate the matrix mechanically — mandate fix.
2. **Heuer vocabulary compliance (S10).** English labels ("supports", "refutes") must become `CC`/`C`/`N`/`I`/`II`/`NA`. Mandate.
3. **At least one diagnostic row (S12).** An all-uniform matrix is tautologically non-diagnostic; mandate.
4. **Elimination framing (M2).** Conclusion phrased as confirmation rather than elimination is CH's load-bearing epistemic failure — mandate.
5. **Conclusion-cell-tally agreement (C3).** If prose endorses H_x but H_x has more `I+II` cells than an alternative, the analyst miscounted; mandate.
6. **Short_alt discipline (S13 — note CH uses S13, not S12, because it has an extra structural criterion).** Name the surviving hypothesis, not every hypothesis.

### Suggestion templates per criterion

- **S13 (short_alt):** `suggested_change`: "Rewrite short_alt as: 'ACH matrix showing <surviving hypothesis label ≤ 80 chars> as the surviving hypothesis after elimination.' Do not enumerate every hypothesis or every evidence id inside short_alt."  `criterion_it_would_move`: `S13`.
- **S9 (cell completeness):** `suggested_change`: "For evidence <id>, fill the missing cell(s) for hypothesis <id>. Use `NA` explicitly if the evidence genuinely does not bear on the hypothesis; never leave a cell absent."  `criterion_it_would_move`: `S9`.
- **S10 (vocab compliance):** `suggested_change`: "Replace cell value '<current>' with one of `CC` / `C` / `N` / `I` / `II` / `NA`. Mapping: strong confirmation ⇒ `CC`; confirmation ⇒ `C`; neutral ⇒ `N`; contradiction ⇒ `I`; strong contradiction ⇒ `II`; not applicable ⇒ `NA`."  `criterion_it_would_move`: `S10`.
- **S12 (no diagnostic row):** `suggested_change`: "At least one evidence row must have varied cell values. Either introduce a new evidence item that distinguishes between hypotheses, or revise cell values on an existing row whose ratings were set to `N` by default rather than genuinely assessed."  `criterion_it_would_move`: `S12`.
- **M2 (confirmation framing):** `suggested_change`: "Rewrite the Tentative conclusions paragraph from 'H<id> is supported by <evidence list>' to 'H<id> survives because fewer evidence items contradict it — <count> `I` + <count> `II` cells, compared to <alt-id>'s <count> `I` + `II`.'"  `criterion_it_would_move`: `M2`.
- **C3 (conclusion-tally mismatch):** `suggested_change`: "Recount `I` + `II` cells per hypothesis column. Endorse the hypothesis with the fewest; tie-breaker is fewer `II`. If the user's favourite hypothesis does NOT win the tally, state that explicitly — this is the methodology's purpose."  `criterion_it_would_move`: `C3`.

### Known failure modes to call out

Dispatch rule:

- **Missing-Cell Trap** → open: "Matrix is missing cells at (<E>, <H>). Mandatory fix — validator rejects with `E_UNRESOLVED_REF`."
- **Custom-Vocabulary Trap** → open: "Cell values use non-Heuer strings. Mandate vocabulary replacement per S10 template."
- **Non-Diagnostic-Matrix Trap** → open: "No row has varied cell values; matrix is tautological. Mandate diagnostic evidence or cell revision."
- **Confirmation Framing Trap** → open: "Conclusion framed as confirmation rather than elimination. This is the mode's load-bearing epistemic commitment — mandate rewrite."
- **Wrong-Tally Trap** → open: "Prose endorses H<id> but its `I+II` tally (<n>) exceeds <alt-id>'s (<m>). Mandate recount and retraction OR revised cells with rationale."
- **Missing-Hypothesis Trap** → surface as SUGGESTED IMPROVEMENT: "At least one hypothesis beyond the user's initial set should be added; currently all hypotheses are user-proposed."
- **Deception-Blindness Trap** → surface as SUGGESTED when adversarial context: "Evaluate whether high-diagnosticity evidence could be manufactured."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-CH-1 — Cell completeness preservation.** Revised `spec.cells` has an entry for every (evidence_id × hypothesis_id) pair. Silent cell drop during revision is a FAIL.
- **V-CH-2 — Heuer vocab preservation.** Every cell value in revised envelope is from `{CC, C, N, I, II, NA}`.
- **V-CH-3 — Surviving-hypothesis tally consistency.** Revised prose's named surviving hypothesis has the fewest `I + II` cells across revised `spec.cells`; if tied, the fewer `II`. Silent conclusion flip during revision is a FAIL.
- **V-CH-4 — Hypothesis-evidence id stability.** Revised hypothesis ids and evidence ids match those referenced in the reviser's ADDRESSED citations. Silent id renaming mid-revision is a FAIL unless CHANGELOG declares it.

## CONTENT CONTRACT

The prose is complete when it contains, in order:

1. **Hypothesis list** — all plausible hypotheses, including at minimum one beyond the user's initial set. Each hypothesis has a short label and a one-sentence description. **These become `spec.hypotheses[]` with ids `H1`, `H2`, …**
2. **Evidence inventory** — all significant evidence and arguments, each with a short text, a credibility rating (H/M/L), and a relevance rating (H/M/L). **These become `spec.evidence[]` with ids `E1`, `E2`, …**
3. **Consistency matrix reading** — short paragraph per evidence row explaining the consistency pattern. The matrix itself lives in the envelope's `spec.cells`.
4. **Diagnosticity assessment** — which evidence actually distinguishes between hypotheses. Name at least one high-diagnosticity item and at least one low-diagnosticity (non-diagnostic) item.
5. **Tentative conclusions** — based on elimination (hypotheses with the most inconsistent evidence are discarded), not confirmation.
6. **Sensitivity analysis** — how conclusions change if critical evidence is wrong, deceptive, or missing.
7. **Monitoring priorities** — what future evidence to watch for; leading indicators for the surviving hypotheses.

After your analysis, emit exactly one fenced `ora-visual` block conforming to the EMISSION CONTRACT below as the final block of the response.

### Reviser guidance per criterion

When the evaluator's output mandates a fix:

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S2 (schema):** `E_UNRESOLVED_REF` → missing cells (apply S9 template). `E_SCHEMA_INVALID` → often short_alt length; apply S13 template.
- **S6 (relation):** set `envelope.relation_to_prose = "visually_native"`.
- **S7 (< 3 hypotheses):** add hypotheses until ≥ 3. Prefer the user's disfavoured explanations and at least one null / "something else" hypothesis.
- **S8 (< 3 evidence):** add evidence items until ≥ 3, with credibility + relevance ratings.
- **S9 (cell completeness):** apply S9 template.
- **S10 (Heuer vocab):** apply S10 template.
- **S11 (scoring method):** declare `heuer_tally` (default), `bayesian`, or `weighted`.
- **S12 (diagnostic row):** apply S12 template.
- **S13 (short_alt):** apply S13 template.
- **M1 (hypothesis breadth):** explicitly mark at least one hypothesis as "beyond the user's initial set" in the Hypothesis list prose.
- **M2 (confirmation framing):** apply M2 template.
- **M3 (diagnostic evidence):** add the literal phrase "high diagnosticity" to at least one evidence-assessment sentence.
- **M4 (sensitivity):** add a Sensitivity paragraph naming at least one evidence item whose reversal would change the ranking.
- **M5 (deception):** add a Deception-check paragraph when adversarial actors are plausible.
- **C1 / C2 (id traceability):** use `H<n>` / `E<n>` prefixes in prose matching envelope ids exactly.
- **C3 (conclusion-tally mismatch):** apply C3 template.
- **C4 (non-diagnostic declaration):** ensure non-diagnostic rows in prose have all-equal cells in envelope (typically `N`).

## EMISSION CONTRACT

Competing Hypotheses produces a response containing BOTH prose (the seven content-contract sections above) AND exactly one fenced `ora-visual` block. The prose arrives first; the envelope is the final block of the response.

### Envelope type

- **Only `ach_matrix` is allowed.** ACH is the mode's native deliverable; other envelope types are structurally incompatible with the across-the-matrix method. `relation_to_prose: "visually_native"` — the matrix IS the argument.

### Canonical envelope (ach_matrix)

```ora-visual
{
  "schema_version": "0.2",
  "id": "ch-fig-1",
  "type": "ach_matrix",
  "mode_context": "competing-hypotheses",
  "relation_to_prose": "visually_native",
  "title": "Data exfiltration — competing explanations",
  "canvas_action": "replace",
  "spec": {
    "hypotheses": [
      { "id": "H1", "label": "Accidental misconfiguration" },
      { "id": "H2", "label": "Insider exfiltration" },
      { "id": "H3", "label": "External credential compromise" },
      { "id": "H4", "label": "Third-party SaaS leak" }
    ],
    "evidence": [
      { "id": "E1", "text": "Logs show legitimate credentials used at 03:00 local",  "credibility": "H", "relevance": "H" },
      { "id": "E2", "text": "No external intrusion signature in the IDS for 30 days", "credibility": "M", "relevance": "H" },
      { "id": "E3", "text": "User in question was on approved leave",                 "credibility": "H", "relevance": "M" },
      { "id": "E4", "text": "SaaS vendor disclosed a scoped breach 10 days prior",    "credibility": "H", "relevance": "H" },
      { "id": "E5", "text": "Audit-log export succeeded under admin UI",              "credibility": "H", "relevance": "L" }
    ],
    "cells": {
      "E1": { "H1": "I",  "H2": "CC", "H3": "CC", "H4": "I"  },
      "E2": { "H1": "C",  "H2": "C",  "H3": "I",  "H4": "C"  },
      "E3": { "H1": "C",  "H2": "II", "H3": "C",  "H4": "C"  },
      "E4": { "H1": "I",  "H2": "N",  "H3": "C",  "H4": "CC" },
      "E5": { "H1": "N",  "H2": "N",  "H3": "N",  "H4": "N"  }
    },
    "scoring_method": "heuer_tally"
  },
  "semantic_description": {
    "level_1_elemental": "ACH matrix of four hypotheses (H1-H4) against five evidence items (E1-E5), with Heuer cells.",
    "level_2_statistical": "H2 has one 'II' (strongly inconsistent) from E3 (user on leave). H1 has two 'I' (E1, E4). H3 has one 'I' (E2). H4 has no 'I' or 'II'.",
    "level_3_perceptual": "H4 (third-party SaaS leak) survives with zero inconsistencies; H2 is eliminated by the alibi evidence. E5 is non-diagnostic.",
    "short_alt": "ACH matrix showing H4 (third-party leak) as the surviving hypothesis after elimination."
  }
}
```

### Emission rules (ach_matrix)

1. **`type` must be `"ach_matrix"`** — no alternative envelope types are allowed in this mode.
2. **`mode_context` must be `"competing-hypotheses"`** (hyphens).
3. **`relation_to_prose` must be `"visually_native"`.**
4. **`canvas_action` must be `"replace"`.**
5. **`spec.hypotheses` must have at least 3 entries** (schema requires 2; this mode requires 3 for minimally diagnostic analysis). Each entry has a unique `id` (recommend `H1`, `H2`, …) and a non-empty `label`.
6. **`spec.evidence` must have at least 3 entries.** Each entry has a unique `id` (recommend `E1`, `E2`, …), non-empty `text`, `credibility ∈ {"H","M","L"}`, and `relevance ∈ {"H","M","L"}`.
7. **`spec.cells` must be fully populated** — for every `evidence_id`, there must be a cell value for every `hypothesis_id`. The validator rejects missing cells with `E_UNRESOLVED_REF`.
8. **Cell values must be from the Heuer vocabulary**: `"CC"`, `"C"`, `"N"`, `"I"`, `"II"`, or `"NA"`. No other strings.
9. **`spec.scoring_method` must be declared**: `"heuer_tally"`, `"bayesian"`, or `"weighted"`.
10. **At least one row must be diagnostic** (cells NOT all equal). Rows where all cells equal fire `W_ACH_NONDIAGNOSTIC`; a matrix where *every* row is non-diagnostic is useless — include at least one genuinely diagnostic evidence item.
11. **`semantic_description` has all four required fields non-empty**, with `short_alt ≤ 150 chars`.
12. **Emit exactly one `ora-visual` block.**

### What NOT to emit

- **Do not** emit an envelope of any other type — CH is ACH-only.
- **Do not** emit an ACH matrix with fewer than 3 hypotheses.
- **Do not** leave cells unpopulated — missing cells are rejected.
- **Do not** use English consistency labels ("supports", "refutes"); only the six-value Heuer enum.
- **Do not** mark every row as `N` across the board — a non-diagnostic matrix is not an analysis.

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN the analysis endorses a single hypothesis, THEN verify the endorsement is based on elimination of alternatives, not confirmation of a favourite.

**Disconfirmation-first guard rail.** Work across the matrix (one evidence item vs all hypotheses) before working down it (one hypothesis vs all evidence). The envelope's row-major `cells` structure reflects this.

**Completeness guard rail.** Before conclusions: is there an unconsidered hypothesis? Is there uninclude evidence? Add them to the envelope before tallying.

**Heuer vocabulary guard rail.** Cell values must be from `{CC, C, N, I, II, NA}` only. Do not invent custom ratings.

**Diagnosticity guard rail.** WHEN emitting a matrix, THEN verify at least one row has varied cell values (not uniform). An all-uniform matrix is tautologically non-diagnostic.

**Cell-completeness guard rail.** WHEN `len(evidence) × len(hypotheses)` cells are expected, THEN verify every (E,H) pair is present before emitting. The validator rejects missing cells.

## SUCCESS CRITERIA

### Structural (machine-checkable)

- **S1 — Envelope presence.** Exactly one `ora-visual` fence, parseable JSON.
- **S2 — Schema validity.** Passes `validate_envelope` with zero errors.
- **S3 — Mode-correct type.** `envelope.type == "ach_matrix"`.
- **S4 — Mode context.** `envelope.mode_context == "competing-hypotheses"`.
- **S5 — Canvas action.** `envelope.canvas_action == "replace"`.
- **S6 — Relation to prose.** `envelope.relation_to_prose == "visually_native"`.
- **S7 — Hypothesis count.** `len(spec.hypotheses) ≥ 3`.
- **S8 — Evidence count.** `len(spec.evidence) ≥ 3`.
- **S9 — Cell completeness.** For every `evidence_id`, `spec.cells[evidence_id]` exists and has an entry for every `hypothesis_id`.
- **S10 — Vocabulary compliance.** Every cell value is one of `{CC, C, N, I, II, NA}`.
- **S11 — Scoring method declared.** `spec.scoring_method ∈ {heuer_tally, bayesian, weighted}`.
- **S12 — At least one diagnostic row.** There exists at least one evidence row whose cells are not all equal (i.e. not every row fires `W_ACH_NONDIAGNOSTIC`).
- **S13 — Semantic description complete.** All four required fields non-empty; `short_alt ≤ 150 chars`.

### Semantic (LLM-reviewer)

- **M1 — Hypothesis breadth.** At least one hypothesis is beyond the user's initial stated set.
- **M2 — Elimination framing.** Prose conclusion is framed as "H_x survives because fewer contradictions" — not "H_x is supported because more confirmations".
- **M3 — Diagnostic evidence called out.** At least one evidence item is explicitly named as high-diagnosticity in prose.
- **M4 — Sensitivity analysis present.** Prose names at least one piece of evidence whose reversal would change the ranking.
- **M5 — Deception check.** When adversarial actors are plausible, prose addresses whether any evidence could be manufactured.

### Composite (prose + envelope)

- **C1 — Hypothesis id traceability.** Every hypothesis named in prose has a matching `spec.hypotheses[].label` or `id`.
- **C2 — Evidence id traceability.** Every evidence item named in prose has a matching `spec.evidence[].text` or `id`.
- **C3 — Conclusion-to-cells agreement.** The surviving hypothesis named in the prose conclusion has, in the envelope, the fewest `I` + `II` cells across all hypotheses (tie-broken by fewer `II`s).
- **C4 — Non-diagnostic evidence declared.** If prose names an evidence item as non-diagnostic, its row in `spec.cells` has all cells equal.

### Machine-readable summary

```yaml
success_criteria:
  mode: competing-hypotheses
  version: 1
  structural:
    - { id: S1,  check: envelope_present }
    - { id: S2,  check: envelope_schema_valid }
    - { id: S3,  check: type_equals, value: ach_matrix }
    - { id: S4,  check: mode_context_equals, value: competing-hypotheses }
    - { id: S5,  check: canvas_action_equals, value: replace }
    - { id: S6,  check: relation_to_prose_equals, value: visually_native }
    - { id: S7,  check: min_hypotheses, min: 3 }
    - { id: S8,  check: min_evidence, min: 3 }
    - { id: S9,  check: cells_fully_populated }
    - { id: S10, check: cells_vocab_compliant, vocab: [CC, C, N, I, II, NA] }
    - { id: S11, check: scoring_method_declared, allowlist: [heuer_tally, bayesian, weighted] }
    - { id: S12, check: at_least_one_diagnostic_row }
    - { id: S13, check: semantic_description_complete }
  semantic:
    - { id: M1, check: hypothesis_breadth }
    - { id: M2, check: elimination_framing }
    - { id: M3, check: diagnostic_evidence_called_out }
    - { id: M4, check: sensitivity_analysis_present }
    - { id: M5, check: deception_check_when_applicable }
  composite:
    - { id: C1, check: hypothesis_prose_envelope_match }
    - { id: C2, check: evidence_prose_envelope_match }
    - { id: C3, check: conclusion_matches_cell_tally }
    - { id: C4, check: nondiagnostic_evidence_declaration_matches }
  acceptance:
    tier_a_threshold: 0.9
    structural_must_all_pass: true
    semantic_min_pass: 0.8
    composite_min_pass: 0.75
```

## KNOWN FAILURE MODES

**The Missing-Hypothesis Trap (inverse of M1).** The correct hypothesis is not in the list, producing a "winner" that is merely the least wrong. Correction: Always include hypotheses beyond the user's initial set. After the matrix, ask: is there an unlisted explanation consistent with the most diagnostic evidence?

**The False-Rigour Trap (inverse of M3, Diagnosticity rubric).** The matrix format creates a false sense of precision when consistency ratings are subjective. Correction: State reasoning behind each non-trivial rating; acknowledge uncertainty explicitly.

**The Static-Snapshot Trap (inverse of M4, Monitoring priorities section).** Treating the analysis as final in an evolving situation. Correction: Identify monitoring priorities and conditions for re-analysis.

**The Deception-Blindness Trap (inverse of M5).** In adversarial contexts, evidence may be planted. Correction: IF adversarial actors are involved, evaluate whether each high-diagnosticity item could be manufactured.

**The Confirmation Framing Trap (inverse of M2).** Writing "H2 is supported by E1 and E3" instead of "H2 survives because fewer evidence items contradict it". Correction: Frame in elimination terms.

**The Non-Diagnostic-Matrix Trap (inverse of S12).** Every row's cells are identical (all `C` across hypotheses, or all `N`). Correction: Either add diagnostic evidence or revise cell values; a non-diagnostic matrix is not an ACH analysis.

**The Missing-Cell Trap (inverse of S9).** Cells for some (E, H) pairs are omitted because "not applicable" but no `NA` placeholder was written. Correction: Fill every cell; use `NA` explicitly when the evidence does not apply to the hypothesis.

**The Custom-Vocabulary Trap (inverse of S10).** Using cell values like "supports", "refutes", or "strong yes" instead of the Heuer enum. Correction: `{CC, C, N, I, II, NA}` only.

**The Wrong-Tally Trap (inverse of C3).** Prose conclusion endorses H_x, but H_x has MORE inconsistent cells than an alternative. Correction: Recount `I` + `II` cells per hypothesis before writing the conclusion; endorse the hypothesis with the FEWEST.

## TOOLS

Tier 1: CAF (identify all evidence and arguments), FIP (prioritise diagnostic evidence), OPV (if hypotheses involve actors, map perspectives), Challenge (test whether each hypothesis explains or merely accommodates the evidence).

Tier 2: Load based on domain signals. Political and Social Analysis Module for institutional analysis.

## TRANSITION SIGNALS

- IF hypotheses involve institutional interests → propose **Cui Bono**.
- IF a hypothesis rests on unexamined paradigmatic assumptions → propose **Paradigm Suspension**.
- IF the user needs to decide actions given surviving hypotheses → propose **Decision Under Uncertainty** or **Constraint Mapping**.
- IF the user begins defining a deliverable → propose **Project Mode**.
- IF hypotheses involve complex causal chains → propose **Root Cause Analysis**.
