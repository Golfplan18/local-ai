---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 3
---

# MODE: Constraint Mapping

## TRIGGER CONDITIONS

Positive:
1. Multiple viable options exist; "which should I choose".
2. Tradeoff analysis, C&S output showing consequences in opposite directions.
3. The user frames the question as a choice between alternatives rather than a search for the right answer.
4. Request language: "compare alternatives", "map the tradeoffs", "what are the pros and cons of each option".

Negative:
- IF the user is questioning the framework within which alternatives exist → **Paradigm Suspension**.
- IF the user wants to trace who benefits → **Cui Bono**.
- IF the question is about which explanation fits evidence → **Competing Hypotheses**.
- IF probability and time-value are central → **Decision Under Uncertainty**.

Tiebreakers:
- CM vs DUU: **deterministic tradeoffs** → CM; **probabilities matter** → DUU.
- CM vs Benefits Analysis: **comparing multiple alternatives** → CM; **evaluating one proposal** → BA.

## EPISTEMOLOGICAL POSTURE

Operate within the accepted framework rather than questioning it. All candidate alternatives are treated as potentially viable — the task is not to determine which is "right" but to map the conditions under which each succeeds and fails. Value judgements embedded in each alternative are surfaced, not resolved — resolution is the user's prerogative.

## DEFAULT GEAR

Gear 3. Sequential adversarial review is sufficient.

## RAG PROFILE

**Retrieve (prioritise):** case studies, comparative analyses, decision frameworks, domain-specific tradeoff literature, historical precedents.

**Deprioritise:** advocacy sources that argue for one position.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `requires`, `enables`, `contradicts`, `qualifies`
**Deprioritise:** `analogous-to`, `precedes`
**Rationale:** Constraints are dependencies and enablers; contradictions reveal tradeoffs.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The alternatives the user is comparing |
| `conversation_rag` | Prior turns' alternatives + discarded ones |
| `concept_rag` | Tradeoff frameworks |
| `relationship_rag` | Objects linked by `requires`/`enables` |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. For each alternative, identify success conditions (what must be true). **These become items placed in quadrants or pro_con children in the envelope.**
2. For each alternative, identify failure conditions.
3. Quantify gains and forfeitures where possible.

Black Hat:
1. Test success conditions for realism — are they plausible or best-case?
2. Identify hidden dependencies.
3. Identify at minimum one alternative the Breadth model may have omitted.

### Cascade — what to leave for the evaluator

- Label each alternative with `Alternative A:`, `Alternative B:`, etc. in prose; use the same labels in envelope `items[].label` or `pro_con` subclaims.
- Prefix success conditions with `Success condition:` and failure conditions with `Failure condition:`. Supports M2.
- State the two selected criteria for `quadrant_matrix` axes with the literal phrase "axes independence rationale:". Supports S9.
- For `pro_con` envelopes, use the literal phrase "Claim:" to introduce `spec.claim` in prose.

### Consolidator guidance

Not applicable at this mode's default gear (Gear 3). If promoted to Gear 4, merge alternatives from both streams into the envelope's `items` list; Depth's per-alternative placement on the 2×2 is reference unless Breadth can argue a different positioning with evidence.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Map all candidate alternatives, including any the user has not named. At minimum three.
2. For each alternative, generate conditions under which it would be the clearly best choice.
3. Identify hybrid options or sequencing strategies.

Yellow Hat:
1. For each alternative, identify what is uniquely gained.
2. Identify what is forfeited.
3. Surface "no-lose" elements valuable regardless of choice.

### Cascade — what to leave for the evaluator

- Use the literal phrase "No-lose element:" in prose when naming an action valuable regardless of choice. Supports M3.
- For each alternative, use the literal phrases "uniquely gained" and "forfeited" at least once.
- When recommending a hybrid or sequencing strategy, use the literal phrase "Hybrid:" or "Sequence:".

## EVALUATION CRITERIA

5. **Alternative Coverage.** 5=all viable alternatives mapped + ≥1 beyond user's list. 3=only user-named alternatives. 1=missing alternatives.
6. **Condition Specificity.** 5=conditions as testable propositions. 3=vague. 1=missing.
7. **Gain/Forfeit Balance.** 5=identified for every alternative with uniqueness. 3=present but not differentiated. 1=missing.

### Focus for this mode

A strong CM evaluator prioritises:

1. **Subtype match (S7).** `quadrant_matrix` must carry `subtype = "strategic_2x2"` — NOT `scenario_planning`. Mandate.
2. **Three-alternative floor (S8, M1).** At least 3 items (or 2-alternative `pro_con`); false dichotomies get mandatory expansion.
3. **Pro-con shape (S10).** If `pro_con`: `pros ≥ 2`, `cons ≥ 2`, both with text.
4. **Axes independence (M4).** Pearson |r| between items' x and y should be ≤ 0.7; correlated axes fail the mode.
5. **No-advocacy (M5).** Symmetric analytical depth across alternatives.
6. **Short_alt (S11).** Name the comparison axis, not every alternative.

### Suggestion templates per criterion

- **S11 (short_alt):** `suggested_change`: "Rewrite short_alt as: 'Strategic 2×2 of <N> <options> plotted by <criterion1> vs <criterion2>.' (or 'Pro/con of <claim>' for pro_con). Target ≤ 100 chars."
- **S7 (wrong subtype):** `suggested_change`: "Set `spec.subtype = 'strategic_2x2'`. `'scenario_planning'` belongs to Scenario Planning, not Constraint Mapping."
- **S8 (< 3 items):** `suggested_change`: "Add alternatives until ≥ 3 items. False dichotomies (only 2 alternatives) mask option space; use `pro_con` if the choice is genuinely binary."
- **S10 (pro_con shape):** `suggested_change`: "Ensure `pros ≥ 2` and `cons ≥ 2`, each with non-empty `text`. `claim` must be non-empty."
- **M4 (correlated axes):** `suggested_change`: "Axes X and Y correlate (items cluster along a diagonal). Either (a) redesign axes to orthogonal criteria, or (b) drop to `pro_con` form if the choice is better expressed as binary."
- **M5 (advocacy asymmetry):** `suggested_change`: "Equalise analytical depth across alternatives. Every alternative should have the same sections: Success conditions, Failure conditions, Uniquely gained, Forfeited."

### Known failure modes to call out

- **Wrong-Subtype Trap** → open: "`subtype = 'scenario_planning'` in CM. Mandate `'strategic_2x2'`."
- **False Dichotomy Trap** → open: "Only two alternatives; CM requires ≥ 3 or switches to pro_con."
- **Advocacy Trap** → open: "Asymmetric depth favours alternative X. Mandate equalisation."
- **Correlated-Axes Trap** → open: "Items correlate along diagonal; axes are not independent. Mandate redesign or drop to pro_con."
- **Abstraction Trap** → surface as fix: "Conditions stated as abstractions, not testable propositions. Rewrite as statements with specific thresholds or observables."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-CM-1 — Subtype stability.** Revised `spec.subtype == "strategic_2x2"` (or envelope is `pro_con`). Silent subtype switch is a FAIL.
- **V-CM-2 — Alternative-count floor preservation.** Revised `quadrant_matrix` has ≥ 3 items OR envelope is `pro_con`.
- **V-CM-3 — Axes-item consistency.** Revised envelope's `items` (x, y) positions are consistent with revised prose's per-alternative analysis.

## CONTENT CONTRACT

In order:

1. **Decision context** — what the choice is and what constraints bound it.
2. **Alternatives** — at minimum three, with short names. Each alternative becomes an item in the envelope (for `quadrant_matrix`) or a structured pro_con block (for `pro_con` when comparing 2 alternatives).
3. **Per-alternative analysis** — conditions for success, conditions for failure, gains, forfeitures. For each alternative.
4. **Cross-alternative comparison** — where they overlap, diverge; critical differentiating factors.
5. **No-lose elements** — actions valuable regardless of which alternative is chosen.

After your analysis, emit exactly one fenced `ora-visual` block per EMISSION CONTRACT.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S2:** `E_SCHEMA_INVALID` → most often an item's x or y outside [0, 1]; clip to range.
- **S7:** apply subtype template.
- **S8:** add items until ≥ 3 OR switch to `pro_con`.
- **S9 (rationale empty):** fill `axes_independence_rationale`.
- **S10:** apply pro_con shape template.
- **S11:** apply short_alt template.
- **M1:** add alternatives until ≥ 3 named in prose.
- **M2:** apply testable-propositions template.
- **M3:** add No-lose elements section.
- **M4:** apply correlated-axes template.
- **M5:** apply advocacy-equalisation template.
- **C1-C3:** sync prose alternatives with envelope items, positions with prose claims, axis labels with prose criteria.

## EMISSION CONTRACT

### Envelope type selection

- **`quadrant_matrix`** with `subtype: "strategic_2x2"` — when the decision decomposes onto two orthogonal criteria (e.g. cost × reversibility) and alternatives can be placed at (x, y) points in [0,1]². Default for ≥ 3 alternatives.
- **`pro_con`** — when the choice is binary (adopt vs don't adopt; X vs Y) and the tree of arguments is what the user needs. Use for 2-alternative comparisons.

Selection rule: if alternatives ≥ 3 AND two clear criteria exist → `quadrant_matrix`. Otherwise → `pro_con`.

### Canonical envelope (quadrant_matrix strategic_2x2)

```ora-visual
{
  "schema_version": "0.2",
  "id": "cm-fig-1",
  "type": "quadrant_matrix",
  "mode_context": "constraint-mapping",
  "relation_to_prose": "integrated",
  "title": "Database migration options — cost vs reversibility",
  "canvas_action": "replace",
  "spec": {
    "subtype": "strategic_2x2",
    "x_axis": {
      "label": "Migration cost",
      "low_label": "Low",
      "high_label": "High"
    },
    "y_axis": {
      "label": "Reversibility",
      "low_label": "Irreversible",
      "high_label": "Easily reversible"
    },
    "quadrants": {
      "TL": { "name": "Cheap & reversible",   "narrative": "Pilot territory — experiment without commitment." },
      "TR": { "name": "Expensive & reversible","narrative": "Worth it if confidence is high; cost bounds exposure." },
      "BL": { "name": "Cheap & irreversible", "narrative": "Decide fast — low cost, but the door closes." },
      "BR": { "name": "Expensive & irreversible","narrative": "Do not enter without strong confidence."}
    },
    "items": [
      { "label": "A: Postgres → pgvector extension", "x": 0.25, "y": 0.75 },
      { "label": "B: Postgres → Pinecone (managed)", "x": 0.6,  "y": 0.55 },
      { "label": "C: Postgres → self-hosted Qdrant", "x": 0.8,  "y": 0.3  }
    ],
    "axes_independence_rationale": "Migration cost depends on engineering effort; reversibility depends on data gravity and integration depth — these dimensions historically decorrelate."
  },
  "semantic_description": {
    "level_1_elemental": "2×2 strategic matrix with migration cost on x and reversibility on y; three alternatives placed as items.",
    "level_2_statistical": "Alternative A (0.25, 0.75) sits in 'Cheap & reversible'; B near centre-right; C in 'Expensive & nearly-irreversible'.",
    "level_3_perceptual": "The alternatives span a diagonal from pilot-territory (A) to commitment-territory (C); B is a middle-ground hybrid.",
    "short_alt": "Strategic 2×2 of three migration options plotted by cost vs reversibility."
  }
}
```

### Emission rules

1. **`type ∈ {"quadrant_matrix", "pro_con"}`.**
2. **`mode_context = "constraint-mapping"`. `canvas_action = "replace"`. `relation_to_prose = "integrated"`.**
3. **For `quadrant_matrix`:** `subtype = "strategic_2x2"` (do NOT use `scenario_planning` — that's Scenario Planning's shape). Quadrants have `name` (narrative optional but recommended). `items` required: at least 3, each with `label`, `x∈[0,1]`, `y∈[0,1]`. `axes_independence_rationale` non-empty.
4. **For `pro_con`:** `spec.claim` is the framing statement. `pros` and `cons` each have ≥ 2 items with non-empty `text`. `decision` optional.
5. **`semantic_description` required; `short_alt ≤ 150`.**
6. **No `items` outside [0, 1]²** — the validator rejects with schema error.
7. **Pearson |r| between items' x and y should be ≤ 0.7** — adversarial layer flags correlated axes with `W_AXES_DEPENDENT`.
8. **One envelope.**

### What NOT to emit

- `subtype: "scenario_planning"` from this mode — that's Scenario Planning's territory.
- A quadrant_matrix with fewer than 3 items.
- Items whose x or y are outside [0, 1].
- `canvas_action: "annotate"`.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN recommending one alternative, verify: did the user ask for a recommendation? CM maps choice terrain; it does not make the choice.

**Symmetry guard rail.** Identical analytical rigour for every alternative.

**Pre-mortem guard rail.** For each alternative, imagine failure; surface what went wrong.

**Axes independence guard rail.** Before emitting `quadrant_matrix`, verify axes decorrelate; if item points correlate, reconsider axes or drop to prose.

## SUCCESS CRITERIA

Structural:
- S1-S6: standard preamble (fence, schema, type in allowlist, mode_context, canvas_action=replace, relation_to_prose=integrated).
- S7: if `quadrant_matrix`: `subtype == "strategic_2x2"` (NOT "scenario_planning").
- S8: if `quadrant_matrix`: `len(items) ≥ 3`, each with `label`, `x`, `y` in [0, 1].
- S9: if `quadrant_matrix`: `axes_independence_rationale` non-empty.
- S10: if `pro_con`: `claim` non-empty; `pros ≥ 2` and `cons ≥ 2` with non-empty text.
- S11: `semantic_description` complete; `short_alt ≤ 150`.

Semantic:
- M1: ≥ 3 alternatives mapped in prose (matches or exceeds envelope items count).
- M2: success + failure conditions stated as testable propositions for each alternative.
- M3: no-lose elements explicitly called out in prose.
- M4: if `quadrant_matrix`: axes independence rationale is substantive (not just "they're different").
- M5: prose does not make the final choice for the user.

Composite:
- C1: every alternative named in prose corresponds to an `item` in the envelope (for `quadrant_matrix`) or to a tree subclaim (for `pro_con`).
- C2: item (x, y) positions in the envelope are consistent with prose claims about cost / reversibility / selected criteria.
- C3: axis labels match prose criteria.

```yaml
success_criteria:
  mode: constraint-mapping
  version: 1
  structural:
    - { id: S1-S6, check: standard_preamble }
    - { id: S7,  check: subtype_equals, value: strategic_2x2, applies_to: quadrant_matrix }
    - { id: S8,  check: min_items_in_unit_square, min: 3, applies_to: quadrant_matrix }
    - { id: S9,  check: axes_independence_rationale_nonempty, applies_to: quadrant_matrix }
    - { id: S10, check: pro_con_shape, min_pros: 2, min_cons: 2, applies_to: pro_con }
    - { id: S11, check: semantic_description_complete }
  semantic:
    - { id: M1, check: three_alternatives_in_prose }
    - { id: M2, check: success_and_failure_conditions }
    - { id: M3, check: no_lose_elements_called_out }
    - { id: M4, check: axes_independence_substantive }
    - { id: M5, check: prose_does_not_choose }
  composite:
    - { id: C1, check: alternatives_match_envelope }
    - { id: C2, check: item_positions_consistent_with_prose }
    - { id: C3, check: axis_labels_match_criteria }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The False Dichotomy Trap (inverse of M1).** Only two alternatives. Correction: generate ≥ 3.

**The Advocacy Trap (inverse of M5).** Asymmetric analytical depth favouring one alternative. Correction: equalise.

**The Abstraction Trap (inverse of M2).** Conditions too vague. Correction: state as testable propositions.

**The Wrong-Subtype Trap (inverse of S7).** Using `scenario_planning` subtype in CM. Correction: CM is `strategic_2x2`; SP is `scenario_planning`.

**The Correlated-Axes Trap (inverse of M4).** Axes that aren't independent. Correction: redesign or drop to `pro_con`.

## TOOLS

Tier 1: C&S, PMI, KVI, FIP, OPV.
Tier 2: Module 7 — Evaluation.

## TRANSITION SIGNALS

- IF the user selects an alternative → propose **Project Mode**.
- IF alternatives reveal the framework needs questioning → propose **Paradigm Suspension**.
- IF formal probability assessment required → propose **Decision Under Uncertainty**.
- IF alternatives involve institutional interests → propose **Cui Bono**.
