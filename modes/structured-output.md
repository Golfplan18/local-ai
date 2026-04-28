---
nexus: obsidian
type: mode
date created: 2026/03/30
date modified: 2026/04/18
rebuild_phase: 3
meta_mode: true
passthrough: true
---

# MODE: Structured Output

## TRIGGER CONDITIONS

Positive:
1. The user requests a specific document format: "write this as a report", "format as a memo", "create a comparison table", "put this in outline form", "draft a one-pager".
2. Content or analysis already exists (from prior sessions, other mode's output, or the user's own knowledge) and the task is rendering.
3. The deliverable is primarily presentational.

Negative:
- IF original analysis is needed to produce the deliverable → **Project Mode** (PM thinks; SO renders).
- IF the content does not yet exist → Front-End Process for clarification first.
- IF the user wants to explore rather than produce a formatted output → **Terrain Mapping** or **Passion Exploration**.

## EPISTEMOLOGICAL POSTURE

The content is input, not a subject for analysis. The task is faithful rendering. When the content is ambiguous or incomplete, flag gaps rather than filling them. SO does not generate content to compensate for missing input.

## DEFAULT GEAR

Gear 2. Single primary model with RAG. SO is a rendering task; adversarial review unnecessary for formatting.

IF the deliverable is high-stakes (publication, client-facing, regulatory), user can escalate to Gear 3.

## RAG PROFILE

**Retrieve (prioritise):** the source content — prior session outputs, vault notes, conversation history, referenced documents; format templates for the requested document type.

**Deprioritise:** analytical sources — the task is rendering, not research.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `parent`, `child`, `precedes`, `requires`
**Deprioritise:** `contradicts`, `supersedes`
**Rationale:** Structured output assembly uses hierarchical and sequential relationships.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The format request and the source content reference |
| `conversation_rag` | Prior turns' content to be rendered |
| `concept_rag` | Format templates |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.6
retrieval_approach: auto
```

*SO runs with a higher conversation history ceiling — the source content is usually in history.*

## DEPTH MODEL INSTRUCTIONS

Not applicable at Gear 2. IF Gear 3:

White Hat:
1. Verify all source content faithfully represented — no additions, omissions, or reframing.
2. Check structural completeness.

Black Hat:
1. Identify any point where formatting introduced a substantive claim not in the source.
2. Identify gaps where the format requires content the source does not provide. Flag; do not generate filler.

### Cascade — what to leave for the evaluator

Structured Output is a **passthrough mode**. Cascade cues focus on byte-equivalent preservation:

- For every substantive claim in the output, ensure it traces to a specific passage in the source. Use the literal phrase "source:" with a quote from the source when the claim could be contested. Supports M1.
- For every passthrough envelope, ensure `mode_context` is preserved from source — do NOT rewrite to `structured-output`. Supports S3.
- Flag every gap between source and format with the literal prefix `Gap:`. Supports M3.
- Use the literal prefix `Format note:` when declaring a structural choice (ordering, compression, section organisation).

### Consolidator guidance

Not applicable at this mode's default gear (Gear 2, single-model, passthrough). SO is inherently single-pass rendering; parallel consolidation defeats the fidelity invariant. If user forces Gear 3 for high-stakes rendering, use single-stream with adversarial review — NOT parallel streams.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Organise the source content into the requested structure. Apply format conventions.
2. Identify appropriate level of detail for the format (one-pager = compressed; full report = comprehensive).
3. IF source does not cleanly fit, propose an adaptation — do not force.

Yellow Hat:
1. Ensure strongest elements are structurally prominent.
2. Assess readability and usability.

### Cascade — what to leave for the evaluator

- When compressing, use the literal phrase "Compression note:" explaining what was dropped.
- When adapting an ill-fitting format, use the literal phrase "Adaptation:" with rationale.
- Preserve every passthrough envelope's `id` verbatim when referencing it in prose.

## EVALUATION CRITERIA

5. **Fidelity.** 5=all source content faithfully represented, no reframing. 3=substantially faithful, one claim subtly reframed. 1=altered beyond source.
6. **Format Conformance.** 5=follows requested format conventions. 3=one structural element missing. 1=format mismatch.
7. **Gap Identification.** 5=all gaps explicitly flagged. 3=major gaps flagged. 1=gaps filled silently.

### Focus for this mode

A strong SO evaluator prioritises (passthrough):

1. **Fidelity (M1).** No substantive claim in output that was not in source. This is SO's load-bearing invariant.
2. **Envelope-byte-equivalence (S2).** Passthrough envelopes identical to source; no schema drift.
3. **mode_context preservation (S3).** Never rewrite `mode_context` to `structured-output`.
4. **Gap identification (M3).** Gaps explicitly flagged, not silently filled.
5. **No recommendation added (M4).** SO renders, does not advise.
6. **Envelope count match (S1).** If source has N, output has N.

Threshold is higher here: **≥ 95%** (not 90%) because rendering should be reliable.

### Suggestion templates per criterion

- **S1/S2 (envelope regeneration):** `suggested_change`: "Envelope <id> was regenerated during rendering; restore byte-equivalent passthrough from source. SO never modifies envelope JSON during rendering."
- **S3 (mode_context rewritten):** `suggested_change`: "Passthrough envelope's `mode_context` was changed from `<original>` to `structured-output`. Restore the original — SO preserves source attribution."
- **M1 (fidelity — new claim):** `suggested_change`: "Claim '<quote>' appears in output but not in source. Remove the claim OR attribute explicitly as an SO-added inference with rationale (rare — this is a departure from passthrough)."
- **M3 (gap silently filled):** `suggested_change`: "Section <X> includes content that was not in source, implicitly filling a format gap. Move this content to the Gap report with prefix `Gap:` and leave the section structurally present but textually empty."
- **M4 (recommendation added):** `suggested_change`: "Output includes recommendation '<quote>' not in source. SO renders, does not advise. Remove the recommendation; if the source contains an implicit recommendation, surface it as a direct quote with attribution."

### Known failure modes to call out

- **Schema-Drift-on-Passthrough Trap** → open: "Passthrough envelope's JSON differs from source. Mandate byte-equivalent restoration."
- **Analyst Trap** → open: "Output has shifted from rendering to analysis. Every claim must trace to source."
- **Template Trap** → surface as SUGGESTED: "Content forced into ill-fitting structure. Adapt the format to serve the content; note the adaptation."
- **Compression Trap** → surface as SUGGESTED: "Compression lost critical qualification. Preserve nuance; flag compression explicitly."
- **Embellishment Trap** → open: "Transitional framing introduced substantive claim not in source. Transitions are structural, not analytical."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-SO-1 — Envelope byte-equivalence preservation.** Every revised passthrough envelope's JSON is byte-equivalent to source.
- **V-SO-2 — Envelope count preservation.** Revised output has same N envelopes as source.
- **V-SO-3 — mode_context preservation.** Every revised passthrough envelope's `mode_context` is the source's, not `structured-output`.
- **V-SO-4 — Fidelity preservation.** Every substantive claim in revised output traces to source. Silent addition during revision is a FAIL.

## CONTENT CONTRACT

The content contract is defined by the user's format request and the source content. Universal elements:

1. **The formatted deliverable** — the source content rendered in the requested format.
2. **Gap report** — IF the source does not fully satisfy the format's requirements, a list of what is missing.
3. **Format notes** — IF structural choices were made (ordering, compression, section organisation), a brief note on what was decided and why.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S1 (envelope count mismatch):** restore source's envelope count — if source had 2 and revised has 1, find the dropped envelope in source and re-emit.
- **S2 (byte-equivalence):** apply envelope-regeneration template.
- **S3 (mode_context):** apply mode_context template.
- **S4 (universal elements):** add deliverable / gap report / format notes sections.
- **M1 (fidelity):** apply fidelity template.
- **M2 (format conformance):** adjust structural elements to match requested format.
- **M3 (gap identification):** apply gap template.
- **M4 (recommendation added):** apply recommendation template.

## EMISSION CONTRACT

**Structured Output is a passthrough mode for visuals.** It does not generate new `ora-visual` blocks.

### Passthrough rule

1. IF the source content contains one or more `ora-visual` fenced blocks, **re-emit them verbatim** in the formatted output — byte-equivalent JSON, preserved `id`, no regeneration.
2. IF the source content contains none, emit none.
3. Do NOT generate new visuals to illustrate the formatted content. If the user explicitly asks for a new visual, that is original analysis; transition to the appropriate analytical mode.

### Emission rules

1. Passthrough only — the envelope JSON is identical to the source.
2. `mode_context` in a passthrough envelope is preserved from the source (it may say `root-cause-analysis`, `systems-dynamics`, etc). SO does not rewrite `mode_context` to `"structured-output"`.
3. Envelope order in the output matches source order.
4. Do not modify `canvas_action` on passthrough envelopes.

### What NOT to emit

- Do NOT invent visuals. If the format requires one the source doesn't provide, flag the gap.
- Do NOT rewrite `mode_context` to `"structured-output"`.
- Do NOT modify a passthrough envelope's contents (no schema drift allowed).

## GUARD RAILS

**Solution Announcement Trigger.** WHEN the output includes a recommendation / conclusion not in source, pause — SO renders, does not analyse.

**Fidelity guard rail.** Every substantive claim traces to source content.

**Gap transparency guard rail.** Do not fill gaps silently.

**Passthrough integrity guard rail.** Envelopes are re-emitted byte-equivalent; no regeneration.

## SUCCESS CRITERIA

### Structural

- S1: If source has N `ora-visual` blocks, output has N `ora-visual` blocks.
- S2: Each output envelope's JSON is byte-equivalent to its source envelope.
- S3: `mode_context` unchanged from source in passthrough envelopes.
- S4: Universal elements (deliverable + gap report + format notes) present in prose.

### Semantic

- M1: Fidelity — no substantive claim is in the output that was not in the source.
- M2: Format conformance — output follows the requested format conventions.
- M3: Gap identification — gaps between source and format flagged explicitly.
- M4: No recommendation or conclusion added that was not in source.

### Composite

- C1: Every passthrough envelope's `id` appears in prose as a reference (if the format supports cross-references).
- C2: Source's headings / sections match output's corresponding sections (at the structural level of the chosen format).

```yaml
success_criteria:
  mode: structured-output
  version: 1
  passthrough: true
  structural:
    - { id: S1, check: envelope_count_matches_source }
    - { id: S2, check: envelopes_byte_equivalent_to_source }
    - { id: S3, check: mode_context_preserved }
    - { id: S4, check: universal_elements_present }
  semantic:
    - { id: M1, check: fidelity_no_new_substantive_claims }
    - { id: M2, check: format_conformance }
    - { id: M3, check: gap_identification }
    - { id: M4, check: no_added_recommendation }
  composite:
    - { id: C1, check: envelope_ids_referenced_in_prose }
    - { id: C2, check: source_sections_mapped_to_output_sections }
  acceptance: { tier_a_threshold: 0.95,  # higher — rendering should be reliable
                structural_must_all_pass: true,
                semantic_min_pass: 0.85, composite_min_pass: 0.8 }
```

## KNOWN FAILURE MODES

**The Analyst Trap (inverse of M1).** Shifting from rendering to analysis. Correction: every claim traces to source.

**The Template Trap.** Forcing content into an ill-fitting structure. Correction: adapt the format to serve the content.

**The Compression Trap.** Losing critical nuance when compressing. Correction: preserve qualifications and caveats.

**The Embellishment Trap (inverse of M4).** Adding transitional framing that introduces substantive claims. Correction: transitions are structural, not analytical.

**The Schema-Drift-on-Passthrough Trap (inverse of S2).** Rewriting envelope JSON during rendering. Correction: byte-equivalent passthrough; no regeneration.

## TOOLS

Tier 1: AGO, FIP.
Tier 2: No default module.

## TRANSITION SIGNALS

- IF the user realises original analysis is needed → propose **Project Mode**.
- IF source content requires adversarial review before formatting → propose the appropriate analytical mode first.
- IF user wants to explore the content → propose **Passion Exploration** or **Deep Clarification**.
- IF gap report reveals source is insufficient → propose the mode to generate the missing content.
