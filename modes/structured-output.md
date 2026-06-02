---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-30
date modified: 2026-05-24
meta_mode: true
passthrough: true

---

# MODE: Structured Output

```yaml
# 0. IDENTITY
mode_id: structured-output
canonical_name: Structured Output
suffix_rule: none
educational_name: structured output formatting

# 1. TERRITORY AND POSITION
territory: T21-execution-project-mode
gradation_position:
  axis: specificity
  value: rendering-only
adjacent_modes_in_territory:
  - mode_id: project-mode
    relationship: specificity variant (original-execution; PM thinks, SO renders)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "user has content and wants it rendered into a specific format"
    - "deliverable is presentational rather than analytical"
    - "task is faithful rendering of existing material, not original analysis"
  prompt_shape_signals:
    - "write this as a report"
    - "format as a memo"
    - "create a comparison table"
    - "put this in outline form"
    - "draft a one-pager"
    - "render this in"
disambiguation_routing:
  routes_to_this_mode_when:
    - "content already exists and the task is rendering"
    - "deliverable is primarily presentational; format is the core value-add"
  routes_away_when:
    - "original analysis is needed to produce the deliverable" → project-mode (T21)
    - "content does not yet exist" → upstream Front-End Process for clarification first
    - "user wants to explore rather than format" → passion-exploration (T20) or terrain-mapping (T14)
when_not_to_invoke:
  - "Original analysis is required — Project Mode thinks; Structured Output renders. SO does NOT generate content to compensate for missing input."
  - "User wants the content itself adversarially reviewed — that requires the source content's analytical mode, not SO"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [source_content_reference, requested_format_specification, target_audience]
    optional: [format_template, voice_or_style_constraints, prior_format_examples]
    notes: "Applies when user supplies precise source-content reference and named format template."
  accessible_mode:
    required: [source_content, format_request]
    optional: [audience_or_purpose]
    notes: "Default. Mode infers format conventions from the named document type."
  detection:
    expert_signals: ["template", "format spec", "house style", "per the standard"]
    accessible_signals: ["write this as", "format as", "put in the form of", "render this"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the source content I should render, and what format do you want it in?'"
    on_underspecified: "Ask: 'Should I render existing content into this format (Structured Output), or do you need me to also produce the analysis first (Project Mode or an analytical mode)?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Does every substantive claim in the output trace to source content, or has the rendering introduced new claims?"
    failure_mode_if_unmet: analyst-trap
  - cq_id: CQ2
    question: "Has the requested format been followed faithfully, or has format mismatch occurred?"
    failure_mode_if_unmet: format-mismatch
  - cq_id: CQ3
    question: "Have gaps between source and format been flagged explicitly, or have they been silently filled?"
    failure_mode_if_unmet: gap-silently-filled
  - cq_id: CQ4
    question: "Has the rendering avoided introducing recommendation or conclusion not in source — SO renders, does not advise?"
    failure_mode_if_unmet: embellishment
  - cq_id: CQ5
    question: "If source contains visual envelopes, are they preserved byte-equivalent in the output (no schema drift)?"
    failure_mode_if_unmet: schema-drift-on-passthrough

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: analyst-trap
    detection_signal: "Output contains substantive claims that do not trace to source content."
    correction_protocol: re-dispatch (every claim must trace to source; remove or attribute SO-added inferences explicitly)
  - name: template-trap
    detection_signal: "Source content forced into ill-fitting structure; misalignment between content and format."
    correction_protocol: flag (adapt the format to serve the content; note the adaptation)
  - name: compression-trap
    detection_signal: "Compression dropped critical qualifications or caveats."
    correction_protocol: flag (preserve nuance; declare compression explicitly)
  - name: embellishment
    detection_signal: "Transitional framing introduced substantive claim not in source."
    correction_protocol: re-dispatch (transitions are structural, not analytical)
  - name: schema-drift-on-passthrough
    detection_signal: "Visual envelope JSON differs from source after rendering."
    correction_protocol: re-dispatch (byte-equivalent passthrough; no regeneration)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - format-template-library (per document type)
    - debono-ago (when format selection requires goal clarification)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~1min
escalation_signals:
  upward:
    target_mode_id: project-mode
    when: "User realizes original analysis is needed to produce the deliverable, not just rendering."
  sideways:
    target_mode_id: null
    when: "T21 has only PM and SO; no sideways sibling within territory."
  downward:
    target_mode_id: null
    when: "Structured Output is already T21's lightest execution sibling."
```

## DEPTH ANALYSIS GUIDANCE

Structured Output is rendering-oriented; depth here means the rigor of fidelity-to-source rather than depth-of-analysis. Going deeper means tracing every substantive claim to a specific passage in the source, preserving qualifications and caveats through compression, and surfacing gaps between source and requested format rather than filling them silently. A thin pass renders the format and stops; a substantive pass cross-checks each output claim against source, declares format adaptations explicitly, and produces a Gap report when source does not fully satisfy the format. Test depth by asking: could the user audit the output line by line and trace each claim to its source passage?

The depth ceiling for SO is set by the source — SO does not deepen content beyond what source supports. Adversarial review at Gear 3 is appropriate for high-stakes rendering (publication, client-facing, regulatory) but consolidator merging is NOT applied (passthrough fidelity defeats parallel consolidation).

## BREADTH ANALYSIS GUIDANCE

Breadth in Structured Output is the survey of format options considered before settling on the rendering approach. Widen the lens to: alternative organizations (chronological vs thematic vs priority-ordered); alternative compression levels (one-pager vs full report); alternative section conventions per requested format. Breadth markers: when source does not cleanly fit the requested format, alternative formats are surfaced as adaptations rather than the rendering being forced. Compression notes name what was dropped; format adaptations name what was changed and why.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Structured Output is a passthrough/meta rendering mode — it formats existing content into a requested format (memo / report / one-pager / outline / comparison-table / etc.) without performing original analysis. It is `meta_mode: true` and `passthrough: true` by spec; consolidator merging is not applied (passthrough fidelity defeats parallel consolidation). The mode is distinct from project-mode (T21 sibling that thinks while SO renders) and from any analytical mode (SO renders, does not advise). The fidelity threshold is higher than analytical modes (≥95%): rendering should be reliable.

**Procedure.**

0. Source-presence gate (precedes all rendering). First check whether ANY renderable source content exists (prompt, conversation context, or knowledge package). If NO source content exists at all, do NOT emit a skeleton or gap report — emit only the elicitation question (`What's the source content I should render, and what format do you want it in?`) and stop. The gap-report / format-notes scaffolding below applies only to PARTIAL gaps, where some source exists but does not fully satisfy the requested format.

1. Lock the source content — name what is being rendered. SO does not extend beyond what source supports.
2. Identify the requested format and its conventions (memo / report / one-pager / outline / comparison-table / etc.).
3. Render source into the format faithfully — structure follows the requested format type, not a generic analytical-mode shape.
4. Trace each substantive claim in the output to a specific passage in source — line-by-line auditability. The narrow exception is structural transitions ("First…", "In summary…"), which are renderer-added but carry no substantive content.
5. Pass through visual envelopes byte-equivalent — no regeneration, no editing, no schema drift; `mode_context` preserved from source (NOT rewritten to `structured-output`); envelope count matches source.
6. Surface gaps explicitly where source did not fully satisfy the requested format — name what's missing and what the user could supply. Do not silently fill format-required content.
7. Declare compression where source was condensed for the format — name what was dropped, so loss of qualifications and caveats is auditable.
8. Adapt format and declare the adaptation where source genuinely doesn't fit the requested format cleanly — never force source into an ill-fitting structure silently.
9. Refuse to add recommendation or conclusion not in source — transitional framing stays structural, not analytical ("This demonstrates…", "The implication is…" are reshaped out).

**Goal.** Produce the user-requested formatted deliverable plus two universal accompanying elements — gap report and format notes — where every substantive claim traces to source, visual envelopes pass through byte-equivalent, and any gaps or adaptations are explicit rather than silently filled.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — claim-to-source trace (load-bearing).** Does every substantive claim in the output trace to source content, or has the rendering introduced new claims? Failure mode if unmet: `analyst-trap`.
- **CQ2 — format conventions followed.** Has the requested format been followed faithfully, or has format mismatch occurred? Failure mode if unmet: `format-mismatch`.
- **CQ3 — gaps surfaced, not silently filled.** Have gaps between source and format been flagged explicitly, or have they been silently filled? Failure mode if unmet: `gap-silently-filled`.
- **CQ4 — no recommendation added.** Has the rendering avoided introducing recommendation or conclusion not in source? Failure mode if unmet: `embellishment`.
- **CQ5 — envelope byte-equivalence (load-bearing).** If source contains visual envelopes, are they preserved byte-equivalent in the output (no schema drift, `mode_context` preserved, envelope count matches)? Failure mode if unmet: `schema-drift-on-passthrough`.

A passing output renders source into the requested format with every substantive claim traceable to source, surfaces gaps explicitly with what the user could supply, declares compression and format adaptations where applicable, passes visual envelopes through byte-equivalent with `mode_context` preserved, and emits no recommendation or conclusion that was not in source.

**Named failure modes.**

- *analyst-trap* — output contains substantive claims that do not trace to source content.
- *template-trap* — source content forced into ill-fitting structure; misalignment between content and format.
- *compression-trap* — compression dropped critical qualifications or caveats without explicit declaration.
- *embellishment* — transitional framing introduced substantive claim not in source.
- *schema-drift-on-passthrough* — visual envelope JSON differs from source after rendering; or `mode_context` rewritten to `structured-output`.

## REVISION GUIDANCE

Revise to remove substantive claims that do not trace to source. Revise to flag gaps that were silently filled. Revise to restore visual envelope byte-equivalence where regeneration occurred. Revise to preserve `mode_context` on passthrough envelopes (do NOT rewrite to `structured-output`). Resist revising toward analytical contribution — SO renders, does not advise. If the source is genuinely insufficient for the format, expand the Gap report rather than padding the output.

## CONSOLIDATION GUIDANCE

**Note: pipeline architecture applies imperfectly to T21 rendering modes — SO is `passthrough: true` by spec.** Structured Output renders existing content rather than generating original analysis; consolidator merging is *not* applied (passthrough fidelity defeats parallel consolidation). Where the corpus-shape applies (when the rendering itself was reviewed across passes), organize as **a rendering atom set: source-content lock, requested-format specification, claim-trace atoms (every output claim traced to source), gap-report atoms, format-note atoms, and envelope-byte-equivalence check**. The atoms are:

1. **Source-content lock atom.** The source material being rendered, named explicitly. Subsequent atoms reference this lock; the rendering does not extend beyond what source supports.

2. **Requested-format specification atom.** The format the user wants (memo / report / one-pager / outline / comparison table / etc.) with its conventions noted. Format-mismatch is the named failure mode the consolidator watches for; renderings that violate the requested format's conventions get reshaped.

3. **Claim-trace atoms.** Each substantive claim in the output traces to a specific passage in source. Analyst-trap is the named failure mode; claims that do not trace get reshaped out of the deliverable or labelled as SO-added inferences with explicit attribution.

4. **Gap-report atoms.** Each atom names: a place where source did not fully satisfy the requested format's requirements, what's missing, and what the user could supply to close the gap. Gap-silently-filled is the named failure mode; silently filling format-required content the source did not provide gets reshaped to explicit gap reporting.

5. **Format-note atoms.** Each atom records: a structural choice the renderer made (ordering, compression, section organisation, format adaptation). Compression-trap is the named failure mode; compression that dropped critical qualifications or caveats gets reshaped to preserve nuance with explicit compression declaration.

6. **Visual-envelope passthrough atoms — when source contains envelopes.** Each atom records: the source envelope, byte-equivalence check (output envelope = source envelope, byte-for-byte), `mode_context` preservation (source's mode_context kept, NOT rewritten to `structured-output`). Schema-drift-on-passthrough is the named failure mode; envelope JSON that differs from source after rendering gets reshaped to passthrough fidelity.

7. **No-recommendation discipline atom.** A standing atom: SO renders, does not advise. Embellishment is the named failure mode; transitional framing that introduces substantive claims not in source gets reshaped to structural-only transitions.

8. **Template-trap flag — when applicable.** Where source content was forced into ill-fitting structure, the flag is preserved with adaptation note. Template-trap is the named failure mode.

9. **Confidence per claim-trace.** Each substantive claim's trace-to-source carries a confidence (high for direct quote; lower for paraphrase-with-judgement).

**Mode-specific bloat patterns to cut:**

- **Analyst-trap** — substantive claims not in source.
- **Format mismatch** — requested format's conventions not followed.
- **Silent gap-filling** — format-required content invented because source didn't provide it.
- **Embellishment** — recommendations or conclusions added that aren't in source.
- **Schema drift on passthrough** — visual envelope JSON modified during rendering.
- **mode_context rewriting** — passthrough envelopes' `mode_context` rewritten to `structured-output` instead of preserved.
- **Compression that drops qualifications** — caveats and nuance lost without explicit compression declaration.
- **Template-trap** — source forced into ill-fitting structure without adaptation note.
- **Source-extension** — SO going beyond what source supports; the depth ceiling is set by source.

**What NOT to collapse:**

- **Gap-report entries** — never silently filled; the gap is the load-bearing finding that tells the user what's missing.
- **Visual envelopes** — byte-equivalent passthrough; never regenerated, never edited, `mode_context` preserved.
- **Compression declarations** — explicit notice of what was compressed and at what cost; never smoothed away for cleaner reading.
- **Format adaptations** — when source genuinely doesn't fit the requested format, the adaptation is noted; never silently reshaped.

## VERIFICATION CRITERIA

Verified means: every substantive claim in output traces to source; format follows requested conventions; gaps explicitly flagged; no recommendation added that was not in source; visual envelopes preserved byte-equivalent with `mode_context` from source. The five critical questions are addressed. Silent gap-filling, silent recommendation injection, and silent schema drift on passthrough envelopes are all verification failures. Envelope count must match source (if source has N visuals, output has N visuals).

## OUTPUT FORMAT GUIDANCE

**Note: pipeline architecture applies imperfectly to T21 rendering modes — SO is `passthrough: true` by spec.** The deliverable is the **formatted deliverable in its requested form plus two universal elements (gap report, format notes)**. The deliverable's structure follows the requested format's conventions (memo format for a memo request, report sections for a report request, table columns for a comparison-table request — the mode does not impose analytical-mode shape on rendering outputs).

Place the consolidated-corpus atoms into the following sections (or their format-appropriate equivalents):

1. **Formatted deliverable.** The user-requested artifact, in its native form, rendered faithfully from source. Structure follows the requested format type. Visual envelopes from source are passed through byte-equivalent with `mode_context` preserved (NOT rewritten to `structured-output`).

2. **Gap report.** A short labelled section after the deliverable. Bulleted list. Each: `**Gap:** [what the requested format required that source did not provide]. **What the user could supply:** [...]. **Why this gap was not silently filled:** [...].` At least one entry when source did not fully satisfy the format; explicit `No gaps — source fully satisfied format.` when applicable. The gap report is for PARTIAL shortfalls only — where some source exists but does not fully satisfy the requested format. Total absence of source content is not a gap-report case: per the source-presence gate, emit no skeleton and no table, ask for the source content, and stop.

3. **Format notes.** A short labelled section. Bulleted list. Each: `**Structural choice:** [ordering / compression / section organisation / format adaptation]. **What was done:** [...]. **What it cost:** [if anything was lost or compressed].`

**Per-section conventions:**

- The deliverable (section 1) follows its native format. Analytical-mode templates (the 7-section analytical-mode shape) get reshaped at this layer — they belong to other modes, not SO.
- The gap report (section 2) and format notes (section 3) appear *after* the deliverable, not interleaved. They support audit but do not interrupt the deliverable's natural reading.
- Visual envelopes from source are passed through **byte-equivalent**. Schema drift is a hard failure; `mode_context` is preserved from source (the source mode's name stays, even though SO is doing the rendering).
- Envelope count matches source. If source has N visual envelopes, the output has N visual envelopes.
- Substantive claims in section 1 trace to source. Where SO needed to add structural transitions, the transitions are *structural* (e.g., "First...", "Second...", "In summary...") rather than analytical ("This demonstrates...", "The implication is...").
- Compression declarations appear in section 3 when source content was condensed; what was dropped is named.
- When the user's request actually requires original analysis (not just rendering), the deliverable opens with a sideways-route note: `**Note: this task requires original analysis beyond rendering. Project Mode (T21) is the appropriate sideways-route; SO renders, does not advise. If you want SO to proceed with the rendering portion only and surface the analytical gap, say so explicitly.**`
- When the template-trap flag survived consolidation, section 3 carries: `**Format-adaptation note:** source content did not fit the requested format cleanly. [Adaptation made] — [why this serves the content better than forcing the original format].`
- The depth ceiling is set by source — SO does not deepen content beyond what source supports. Adversarial review at Gear 3 is appropriate for high-stakes rendering; consolidator merging is *not* applied to SO outputs.

---

## DEFAULT GEAR

Gear 2

- **Expected Runtime:** ~1min
- **Context Budget:** conversation_history_soft_ceiling=0.6

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- AGO
- CAF

Mental models (always loaded):
- map-territory
- narrative-instinct
- bertin-visual-variables
- alexander-pattern-language

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[framework, mode, engram]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `requires`, `enables`, `parent`, `child`, `produces`
**Deprioritize:** `analogous-to`, `contradicts`

*Family: execution-output. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
