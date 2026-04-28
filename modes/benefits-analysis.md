---
nexus: obsidian
type: mode
date created: 2026/04/17
date modified: 2026/04/18
rebuild_phase: 3
---

# MODE: Benefits Analysis

## TRIGGER CONDITIONS

Positive:
1. "What are the benefits and risks of"; cost-benefit analysis; "pros and cons of"; proposal evaluation.
2. Evaluation of a single option's merits, risks, and non-obvious implications.
3. Request language: "evaluate this proposal", "PMI for X", "plus/minus/interesting", "what's the full picture on X".

Negative:
- IF comparing multiple options → **Constraint Mapping**.
- IF constructing the strongest version of a position → **Steelman Construction**.
- IF tracing forward causal cascades → **Consequences and Sequel** (BA is first-order across three columns; C&S traces second- and third-order over time).
- IF feedback-driven systemic analysis → **Systems Dynamics**.

Tiebreaker:
- BA vs CM: **one proposal, three columns** → BA; **multiple alternatives** → CM.

## EPISTEMOLOGICAL POSTURE

Every proposal has three kinds of consequences: Plus (advance the stated goal), Minus (work against it), Interesting (neither purely good nor bad but change what else becomes true). The Interesting column is where non-obvious implications live. De Bono's PMI is a discipline for keeping all three channels open. The task is not to reach a verdict but to present the full envelope.

## DEFAULT GEAR

Gear 3. Sequential adversarial review is appropriate because Minus and Interesting columns are where generative models typically underperform. Gear 4 when high-stakes or politically charged.

## RAG PROFILE

**Retrieve (prioritise):** evaluations of similar proposals, outcome data from implemented versions, domain-specific risk frameworks, cost-benefit literature, PMI documentation.

**Deprioritise:** partisan advocacy and promotional sources.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `enables`, `produces`, `contradicts`, `qualifies`, `requires`
**Deprioritise:** `parent`, `child`, `supersedes`
**Rationale:** BA tracks what a proposal enables, produces, contradicts, and qualifies.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The proposal to be evaluated, with scope |
| `conversation_rag` | Prior turns' benefit/risk claims |
| `concept_rag` | PMI, stakeholder analysis, precedent cases |
| `relationship_rag` | Objects linked by `enables`/`contradicts` |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. Audit Plus for motivated optimism; mark each with its load-bearing assumption. **These populate `spec.pros[]` in the envelope.**
2. Audit Minus for thoroughness. **These populate `spec.cons[]`.**
3. Audit Interesting for non-obvious implications (precedent, signalling, path-dependency). **These also populate Plus or Cons with an "interesting" note in the weight, or are surfaced in prose and not in envelope.**

Black Hat:
1. For each Plus claim, identify mechanism; flag claims without mechanism.
2. For each Minus, assess mitigation.
3. Identify claims that flip between Plus and Minus depending on perspective.

### Cascade — what to leave for the evaluator

- State the proposal verbatim in the opening paragraph with the literal opening "Proposal:" — matches `spec.claim`. Supports C1.
- Use the literal column prefixes "Plus:", "Minus:", "Interesting:" in prose; the Interesting column is populated even if it reads as "no non-obvious implications identified" (that's still an honest signal).
- For each Plus, state the mechanism with the literal phrase "mechanism:" in the surrounding sentence. Supports Black Hat audit.
- For Interesting items, prefix with "Second-order:" when the item is precedent/signalling/path-dependency. Supports M3.

### Consolidator guidance

Not applicable at this mode's default gear (Gear 3). If promoted to Gear 4 for high-stakes/politically-charged proposals, merge both streams' columns; de-duplicate by text stem-overlap; preserve Breadth's second-order items in the Interesting channel as a priority.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Produce the three columns with explicit, concrete claims (not generic).
2. Populate Interesting with second-order implications.
3. Stress-test each claim against the user's actual context.

Yellow Hat:
1. Identify the most consequential item in each column.
2. Map affected parties; surface asymmetries.
3. Surface analytical uncertainty where evidence is thin.

### Cascade — what to leave for the evaluator

- Map affected parties in a dedicated section with the literal heading "Affected parties:" listing each party and which column items affect them.
- Use the literal phrase "asymmetry:" when the same item is Plus for one party and Minus for another. Supports M4.
- Mark each column's most-consequential item with the literal prefix "Most consequential:" (one per column).

## EVALUATION CRITERIA

5. **Column Distinctness.** 5=items belong in their columns. 3=one miscategorised. 1=Interesting empty.
6. **Specificity.** 5=grounded in the user's case. 3=mostly specific. 1=generic.
7. **Second-Order Coverage.** 5=Interesting captures precedent / signalling / path-dependency. 3=some second-order. 1=first-order only.
8. **Asymmetry Detection.** 5=identifies Plus-for-one-party / Minus-for-another. 3=partial. 1=single perspective.

### Focus for this mode

A strong BA evaluator prioritises:

1. **No-advocacy (M5, Verdict Trap).** BA does not recommend unless the user asks. Any unsolicited recommendation is mandatory fix.
2. **Three-column floor (M1, S8).** Plus / Minus / Interesting all populated. Two-column output is Constraint Mapping's shape, not BA's.
3. **Pro_con shape (S8).** `pros ≥ 2`, `cons ≥ 2`, `claim` non-empty.
4. **Specificity (M2, Boilerplate Trap).** Generic claims ungrounded in user context fail; mandate fix.
5. **Second-order coverage (M3).** Interesting column must capture at least one precedent/signalling/path-dependency item — or explicitly say none were found.
6. **Short_alt (S11).** Name the proposal, not every pro/con.

### Suggestion templates per criterion

- **S11 (short_alt):** `suggested_change`: "Rewrite short_alt as: 'Pro/con tree for <proposal stem ≤ 80 chars>.' Target ≤ 100 chars."
- **S8 (pro_con shape):** `suggested_change`: "Add pros/cons until ≥ 2 each; `claim` must be non-empty. If the honest distribution is 1 pro and 5 cons, say so in prose rather than padding."
- **M1 (missing column):** `suggested_change`: "Populate the missing column with ≥ 1 concrete item grounded in the user's case. If no items exist after audit, write 'No items identified in the <column> column after audit' rather than omitting the column."
- **M2 (boilerplate):** `suggested_change`: "Replace generic claim '<current>' with a concrete version citing specific features of the user's proposal — name the product, the team, the dollar amount, the timeline, whatever anchors the claim."
- **M3 (no second-order):** `suggested_change`: "Add at least one Interesting item prefixed 'Second-order:' capturing precedent, signalling, or path-dependency. If genuinely none, write 'No second-order implications identified' explicitly."
- **M5 (unsolicited recommendation):** `suggested_change`: "Remove the recommendation. Set `spec.decision` to empty unless the user explicitly asked for a lean. BA produces an envelope, not a verdict."

### Known failure modes to call out

- **Verdict Trap** → open: "Prose recommends adoption without the user asking. BA is non-recommending."
- **Two-Column Trap** → open: "Interesting column empty; mandate population or explicit 'none identified' statement."
- **Boilerplate Trap** → open: "Claims generic, not grounded in user's case. Mandate specificity."
- **Single-Perspective Trap** → open: "Affected-parties map missing; asymmetries not surfaced. Mandate party mapping."
- **False-Symmetry Trap** → surface as SUGGESTED: "Equal pros and cons for appearance balance; report honest distribution instead."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-BA-1 — No-recommendation preservation.** Revised prose and `spec.decision` do not recommend adoption unless user asked. Silent recommendation injection during revision is a FAIL.
- **V-BA-2 — Three-column preservation.** Revised prose still has Plus / Minus / Interesting (or explicit "none identified" for any empty column).
- **V-BA-3 — Claim-prose match.** Revised `spec.claim` ≈ revised prose's "Proposal:" sentence.

## CONTENT CONTRACT

In order:

1. **Proposal stated precisely** — what is being evaluated. Becomes `spec.claim`.
2. **Plus column** — concrete benefits grounded in specifics with mechanism. **Populate `spec.pros`.**
3. **Minus column** — concrete risks with mitigation assessment. **Populate `spec.cons`.**
4. **Interesting column** — non-obvious implications. Add as weighted items in pros/cons OR as prose-only items in a Tornado envelope when quantification is the point.
5. **Affected parties map** — who experiences each Plus/Minus/Interesting.
6. **Evidence quality note** — where claims are thinly supported.
7. **Most consequential item in each column** — the claim that would most change the decision if wrong.

The mode does not recommend adoption. The user decides. **(optional `spec.decision` may note "Pilot"/"Reject"/"Adopt with conditions" only if the user explicitly asked for a lean.)**

After your analysis, emit exactly one fenced `ora-visual` block per EMISSION CONTRACT.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S2:** `E_SCHEMA_INVALID` → often short_alt length; apply S11 template.
- **S7:** set `type: "pro_con"` (default) unless sensitivity-framing is genuinely the point — then `tornado`.
- **S8:** apply pro_con shape template.
- **S9 (tornado):** `parameters ≥ 2` each with all 5 numeric fields.
- **S10 (tornado swing ordering):** if `sort_by: "swing"`, sort parameters by descending |swing|.
- **S11:** apply short_alt template.
- **M1:** apply missing-column template.
- **M2:** apply boilerplate template.
- **M3:** apply second-order template.
- **M4 (asymmetry):** add Affected-parties section with asymmetry identified for at least one item.
- **M5:** apply no-recommendation template.
- **C1-C3:** sync claim with prose, pros/cons with prose columns, decision field with prose (or leave empty).

## EMISSION CONTRACT

### Envelope type selection

- **`pro_con`** (default) — captures the three columns via `pros`, `cons`, and weighted pro/con children for Interesting.
- **`tornado`** — when benefits are quantified and the user wants sensitivity framing (which parameter swings the benefit most). Use when the proposal has numeric payoffs or scenarios.

Selection rule: qualitative or mixed → `pro_con`. Quantified sensitivity framing → `tornado`.

### Canonical envelope (pro_con)

```ora-visual
{
  "schema_version": "0.2",
  "id": "ba-fig-1",
  "type": "pro_con",
  "mode_context": "benefits-analysis",
  "relation_to_prose": "integrated",
  "title": "PMI — four-day work week",
  "canvas_action": "replace",
  "spec": {
    "claim": "Adopt a four-day work week across the engineering org.",
    "pros": [
      { "text": "Improved retention",                 "weight": 4, "children": [
        { "text": "Market-wide signal value in a tight hiring market" }
      ] },
      { "text": "Reduced meeting load by design",    "weight": 3 }
    ],
    "cons": [
      { "text": "Coverage gaps for incident response","weight": 4, "children": [
        { "text": "Monday on-call becomes contested" }
      ] },
      { "text": "Customer-facing SLA compression",    "weight": 3 }
    ],
    "decision": "Pilot for one quarter in one team"
  },
  "semantic_description": {
    "level_1_elemental": "Pro/con tree for adopting a four-day work week, with weighted arguments and one decision note.",
    "level_2_statistical": "Two pros and two cons; top pro weight 4 (retention), top con weight 4 (coverage gaps).",
    "level_3_perceptual": "Pros and cons are balanced on weight; the decision note reflects that a pilot is the natural first step given the balance.",
    "short_alt": "Pro/con tree for a four-day work week, weighted and balanced."
  }
}
```

### Emission rules

1. **`type ∈ {"pro_con", "tornado"}`.**
2. **`mode_context = "benefits-analysis"`. `canvas_action = "replace"`. `relation_to_prose = "integrated"`.**
3. **For `pro_con`:** `spec.claim` non-empty. `spec.pros ≥ 2` and `spec.cons ≥ 2`, each with non-empty `text`. `weight ∈ [1, 5]` when present. `children` optional for nested sub-arguments.
4. **For `tornado`:** `spec.base_case_label`, `spec.base_case_value`, `spec.outcome_variable`, `spec.outcome_units`, `spec.sort_by ∈ {"swing","high_impact","custom"}`. `spec.parameters ≥ 2` with all five numeric fields. When `sort_by="swing"`, parameters must be in descending absolute swing order.
5. **`semantic_description` required; `short_alt ≤ 150`.**
6. **One envelope.**

### What NOT to emit

- A recommendation when the user did not ask for one. The `spec.decision` field is optional and should be empty when the user asked only for the envelope.
- A lopsided tree with 1 pro and 5 cons (or vice versa) — if the honest distribution is that lopsided, say so in prose rather than padding.
- `canvas_action: "annotate"`.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN the output recommends, pause — BA does not recommend.

**Specificity guard rail.** Each claim is grounded in the user's specific case.

**Asymmetry guard rail.** Affected-parties map is populated; asymmetries surfaced.

**Interesting-column-non-empty guard rail.** If the Interesting column (captured via weighted children or prose) is empty, audit again for non-obvious implications.

## SUCCESS CRITERIA

Structural:
- S1-S6: standard preamble.
- S7: `type ∈ {"pro_con", "tornado"}`.
- S8: for `pro_con`: `claim` non-empty, `pros ≥ 2`, `cons ≥ 2`.
- S9: for `tornado`: `parameters ≥ 2` with all five numeric fields; `sort_by` present.
- S10: for `tornado` with `sort_by="swing"`: descending |swing| ordering (validator enforces).
- S11: `semantic_description` complete; `short_alt ≤ 150`.

Semantic:
- M1: all three PMI columns populated in prose (Plus / Minus / Interesting).
- M2: each claim grounded in the user's context, not generic.
- M3: ≥ one second-order implication named (precedent / signalling / path-dependency).
- M4: affected-parties asymmetry surfaced.
- M5: prose does not make an unsolicited recommendation.

Composite:
- C1: `spec.claim` ≈ prose's "Proposal stated precisely" sentence.
- C2: top-level `pros`/`cons` appear in prose's Plus/Minus columns.
- C3: any `decision` field maps to prose language (not invented).

```yaml
success_criteria:
  mode: benefits-analysis
  version: 1
  structural:
    - { id: S1-S6, check: standard_preamble }
    - { id: S7,   check: type_in_allowlist, allowlist: [pro_con, tornado] }
    - { id: S8,   check: pro_con_shape, min_pros: 2, min_cons: 2, applies_to: pro_con }
    - { id: S9,   check: tornado_shape, min_params: 2, applies_to: tornado }
    - { id: S10,  check: tornado_swing_ordering, applies_to: tornado }
    - { id: S11,  check: semantic_description_complete }
  semantic:
    - { id: M1, check: pmi_three_columns }
    - { id: M2, check: claims_grounded_in_context }
    - { id: M3, check: second_order_implication }
    - { id: M4, check: asymmetry_surfaced }
    - { id: M5, check: no_unsolicited_recommendation }
  composite:
    - { id: C1, check: claim_matches_prose }
    - { id: C2, check: pros_cons_match_prose }
    - { id: C3, check: decision_from_prose_or_absent }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The Two-Column Trap (inverse of M3).** Plus and Minus only, Interesting empty. Correction: force-populate Interesting.

**The Boilerplate Trap (inverse of M2).** Generic claims. Correction: specific to the user's context.

**The Single-Perspective Trap (inverse of M4).** One party's view. Correction: map affected parties.

**The Verdict Trap (inverse of M5).** Recommending adoption. Correction: BA produces an envelope, not a verdict.

**The False-Symmetry Trap.** Equal pros and cons to appear balanced. Correction: report honest distribution.

## TOOLS

Tier 1: PMI (primary), CAF, C&S, AGO.
Tier 2: Domain evaluation modules.

## TRANSITION SIGNALS

- IF choosing between alternatives → propose **Constraint Mapping**.
- IF probability + time-value → propose **Decision Under Uncertainty**.
- IF forward causal cascades need tracing → propose **Consequences and Sequel**.
- IF strongest case needed → propose **Steelman Construction**.
- IF feedback loops → propose **Systems Dynamics**.
- IF distributional impact + authorship → propose **Cui Bono**.
- IF multiple futures need mapping → propose **Scenario Planning**.
