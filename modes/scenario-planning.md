---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 3
---

# MODE: Scenario Planning

## TRIGGER CONDITIONS

Positive:
1. A decision depends on future conditions that are genuinely uncertain.
2. Strategic planning over a horizon exceeding one year.
3. "What could happen", "how should we prepare", "what if the environment changes".
4. The analysis defaults to a single "official future" that needs challenging.
5. Request language: "scenarios", "2×2 scenario matrix", "possible futures", "what-if matrix".

Negative:
- IF the user wants present-state tradeoffs → **Constraint Mapping**.
- IF the user wants to trace a failure backward → **Root Cause Analysis**.
- IF the user wants to choose between options on probability + payoff → **Decision Under Uncertainty**.

Tiebreakers:
- SP vs DUU: **multiple futures to prepare for** → SP; **one decision under uncertainty now** → DUU.
- SP vs Paradigm Suspension: **multiple plausible futures under the same frame** → SP; **questioning the frame itself** → PS.

## EPISTEMOLOGICAL POSTURE

The future is fundamentally uncertain and multiple. Multiple plausible futures are simultaneously valid — no single scenario is designated "most likely". Single-point forecasting is rejected. The "official future" — the straight-line extrapolation of current trends — is the specific target of challenge. Uncertainty is treated as a structuring device, not an impediment. The purpose is not to predict but to modify decision-makers' mental models and prepare for contingencies.

## DEFAULT GEAR

Gear 4. Independent scenario generation is the minimum. IF the Depth model sees the Breadth model's scenarios before developing its own, scenarios converge rather than spanning the possibility space.

## RAG PROFILE

**Retrieve (prioritise):** strategic foresight literature, trend analyses, weak-signal reports, historical analogues of structural change; STEEP driving forces (Social, Technological, Economic, Environmental, Political).

**Deprioritise:** forecasts and predictions — these are single-point estimates SP is designed to transcend.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `enables`, `requires`, `produces`, `precedes`, `qualifies`
**Deprioritise:** `parent`, `child`
**Rationale:** Scenario construction needs causal chains, sequencing, and qualification under different conditions.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The focal decision and the horizon |
| `conversation_rag` | Prior-turn driving-force analyses |
| `concept_rag` | Scenario-planning mental models (Shell method, 2×2 axes, wild cards) |
| `relationship_rag` | Domain objects linked by `enables`/`produces` |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. Identify the focal question / strategic decision. State it precisely. Becomes `focus_question` context in prose; the envelope's quadrants operationalise it.
2. Map all driving forces. Classify each as **predetermined** (will happen regardless) or **critical uncertainty** (could go either way).
3. For each critical uncertainty, assess the range of plausible outcomes and identify leading indicators.

Black Hat:
1. Evaluate scenarios for internal consistency — does each scenario's causal logic hold?
2. Test whether scenarios are genuinely structurally distinct or variations of the same future with different magnitudes.
3. Stress-test proposed strategies against each scenario.

### Cascade — what to leave for the evaluator

- Classify every driving force with a literal `Predetermined:` or `Critical uncertainty:` prefix in prose. Supports M1.
- State axes selection rationale with the literal phrase "axes independence rationale:" before the envelope. Supports S10.
- Name each scenario with an identity phrase (not a magnitude label); use quadrant keys TL/TR/BL/BR explicitly in prose. Supports M2 and C1.
- Generate the wild-card scenario in prose with the literal prefix "Wild card:". Supports M3.

### Consolidator guidance

Applies at this mode's default gear (Gear 4). Both streams' independently-generated scenarios are the core signal.

- **Reference frame for the envelope:** the four scenarios agreed-upon (Depth + Breadth convergence). If they disagree on axis selection, emit Depth's axes and preserve Breadth's axes in prose as "Alternative framing considered:".
- **Scenario name disagreement:** if both streams produce the same structural scenario with different names, combine: `<Depth name> / <Breadth name>` in `quadrants.X.name`.
- **Wild-card reconciliation:** emit both streams' wild-cards in prose (not in envelope); each preserves its originator's framing.
- **Do not designate any scenario as "most likely"** — this is M5, a mode-critical invariant.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. From the **two most critical uncertainties**, construct a 2×2 with **four structurally distinct scenarios**. Each scenario occupies one quadrant. **These become `spec.quadrants.TL/TR/BL/BR` with `subtype: "scenario_planning"`.**
2. Develop each scenario with a narrative: a name, a coherent causal logic, key characteristics.
3. Generate at minimum one wild-card scenario outside the 2×2 — noted in prose, not in the envelope.

Yellow Hat:
1. For each scenario, identify opportunities.
2. Identify **robust strategies** (work across scenarios) vs **scenario-dependent strategies**.
3. Identify **contingent actions** tied to leading indicators.

### Cascade — what to leave for the evaluator

- Generate at least two leading indicators per scenario with the literal prefix `Leading indicator:` in the Leading Indicators section.
- Label every strategy as `Robust strategy:` or `Scenario-dependent strategy:` in prose. Supports M4.
- Generate at least one `Contingent action:` tied to a specific leading indicator.

## EVALUATION CRITERIA

5. **Scenario Distinctiveness.** 5=structurally different futures with distinct causal logic. 3=two share significant overlap. 1=variations in magnitude only.
6. **Uncertainty/Predetermined Separation.** 5=clean distinction with reasoning. 3=one miscategorised. 1=no distinction.
7. **Strategic Actionability.** 5=leading indicators for each scenario, robust vs scenario-dependent strategies, contingent actions. 3=some missing. 1=no strategic translation.
8. **Axes Independence.** 5=the two selected uncertainties are genuinely independent; the `axes_independence_rationale` is non-trivial. 3=independence rationale thin. 1=axes correlate.

### Focus for this mode

A strong SP evaluator prioritises:

1. **Subtype match (S7).** Must be `scenario_planning`, not `strategic_2x2` (that's Constraint Mapping). Mandate.
2. **Four-quadrant populated (S8).** All of TL/TR/BL/BR have `name` and `narrative`. Partial matrix is invalid.
3. **Axes independence rationale (S10, M4).** Must actually argue decoupling, not just declare it. ≥ 40 chars floor.
4. **No-most-likely invariant (M5).** SP does not predict; any scenario labelled "most likely" is mandatory fix.
5. **Scenarios structurally distinct (M2).** Good/bad/medium trio fails the mode.
6. **Short_alt (S12).** Name the axes, not the scenarios.

### Suggestion templates per criterion

- **S12 (short_alt):** `suggested_change`: "Rewrite short_alt as: 'Scenario matrix for <x-axis> × <y-axis> with four named futures.' Target ≤ 100 chars."
- **S7 (wrong subtype):** `suggested_change`: "Set `spec.subtype = 'scenario_planning'`; `'strategic_2x2'` is Constraint Mapping's territory."
- **S8 (partial quadrants):** `suggested_change`: "Populate all four quadrants TL/TR/BL/BR with non-empty `name` and `narrative`. A scenario matrix with fewer than four is not a matrix."
- **S10 (thin rationale):** `suggested_change`: "Expand `axes_independence_rationale` to argue why the two uncertainties decouple — reference distinct drivers, historical decorrelation, or orthogonal dependencies. ≥ 40 chars required."
- **M2 (magnitude labels):** `suggested_change`: "Rewrite scenario names to reflect distinct causal logic, not optimistic/pessimistic/baseline. Name each by its defining mechanism (e.g. 'Constrained boom', 'Wild west')."
- **M5 (most-likely label):** `suggested_change`: "Remove the 'most likely' designation. SP does not predict; each scenario receives equal standing regardless of subjective probability."

### Known failure modes to call out

- **Good/Bad/Medium Trap** → open: "Scenarios labelled by magnitude, not distinct causal logic. Mandate rewrite."
- **Official Future Trap** → open: "One scenario labelled 'most likely'. Mandate removal — SP does not predict."
- **Story Without Strategy Trap** → surface as fix: "Quadrants lack `action` or `indicators`. Add both."
- **Certainty Masquerade Trap** → surface as fix: "Driving force X classified as 'predetermined' when it could go either way. Reclassify or defend."
- **Correlated-Axes Trap** → open: "Items cluster along a diagonal (Pearson |r| > 0.7); axes are not independent. Mandate redesign."

### Verifier checks for this mode

Universal V1-V8 (V2/V3/V6 N/A for Gear 4-only but SP is Gear 4 so these apply); then:

- **V-SP-1 — Four-quadrant preservation.** Revised envelope has all four quadrants with non-empty `name` and `narrative`.
- **V-SP-2 — Subtype stability.** Revised `spec.subtype == "scenario_planning"`; silent switch is a FAIL.
- **V-SP-3 — No-most-likely preservation.** Revised prose does not designate any scenario as "most likely" or "highest-probability".
- **V-SP-4 — Axes-independence preservation.** Revised `axes_independence_rationale` ≥ 40 chars.

## CONTENT CONTRACT

In order:

1. **Focal question** — the strategic decision.
2. **Driving forces** — classified predetermined vs critical uncertainty.
3. **Critical uncertainties** — the two forming the scenario axes, with reasoning for their selection. **These become `spec.x_axis` and `spec.y_axis`.**
4. **Scenario matrix** — four scenarios, each with name, narrative, and causal logic. **Populate `spec.quadrants.TL/TR/BL/BR` with `name` + `narrative`.**
5. **Leading indicators** — at minimum two per scenario. **Populate `spec.quadrants.*.indicators`.**
6. **Strategic implications** — robust strategies, fragile strategies, contingent actions. **Optional `spec.quadrants.*.action`.**
7. **Wild card** — at minimum one plausible future outside the 2×2 (prose-only; not in envelope).

After your analysis, emit exactly one fenced `ora-visual` block per EMISSION CONTRACT.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S2:** `E_UNRESOLVED_REF` → most often an empty quadrant narrative for `scenario_planning` subtype; populate all four.
- **S7:** apply subtype template.
- **S8:** apply four-quadrant template.
- **S9 (per-quadrant indicators):** add at least one indicator per quadrant.
- **S10:** apply rationale-expansion template.
- **S11 (axes shape):** fill `label`, `low_label`, `high_label` on both x_axis and y_axis.
- **S12:** apply short_alt template.
- **M1:** add predetermined/critical-uncertainty prefixes.
- **M2:** apply magnitude-label rewrite template.
- **M3 (wild card):** add Wild-card paragraph if missing.
- **M4:** label strategies as robust/scenario-dependent and add contingent action.
- **M5:** apply most-likely removal template.
- **C1-C3:** sync quadrant names, indicators, and axis labels between prose and envelope.

## EMISSION CONTRACT

### Envelope type

- **`quadrant_matrix`** with `subtype: "scenario_planning"`. Only this envelope type is emitted by this mode.

### Canonical envelope

```ora-visual
{
  "schema_version": "0.2",
  "id": "sp-fig-1",
  "type": "quadrant_matrix",
  "mode_context": "scenario-planning",
  "relation_to_prose": "integrated",
  "title": "Scenarios for AI capability × regulation",
  "canvas_action": "replace",
  "spec": {
    "subtype": "scenario_planning",
    "x_axis": {
      "label": "AI capability growth",
      "low_label": "Stalls",
      "high_label": "Accelerates"
    },
    "y_axis": {
      "label": "Regulatory posture",
      "low_label": "Laissez-faire",
      "high_label": "Strict"
    },
    "quadrants": {
      "TL": { "name": "Soft landing",      "narrative": "Capability plateaus while regulators tighten; incumbents entrench.", "action": "Position as a compliance-first provider.", "indicators": ["Plateau in benchmark gains", "EU AI Act enforcement begins"] },
      "TR": { "name": "Constrained boom",  "narrative": "Rapid capability growth under strict regulation; friction slows shipping but sorts serious from frivolous players.", "action": "Invest in compliance infrastructure early.", "indicators": ["Capability jumps + new federal rulemaking"] },
      "BL": { "name": "Stall",             "narrative": "Capability plateau with laissez-faire regulation; incumbents consolidate quietly.", "action": "Pivot to deployment + integration.", "indicators": ["Training cost > $1B per run; no regulatory action"] },
      "BR": { "name": "Wild west",         "narrative": "Rapid capability growth with minimal regulation; safety incidents accumulate.", "action": "Build self-regulation and insurance.", "indicators": ["Major capability jump + incident without regulatory response"] }
    },
    "axes_independence_rationale": "Regulatory stance depends on political economy and public opinion; capability growth depends on research throughput and capital — historically these have not moved in lockstep."
  },
  "semantic_description": {
    "level_1_elemental": "2×2 scenario matrix with AI capability growth on x-axis and regulatory posture on y-axis; four named scenarios.",
    "level_2_statistical": "Each quadrant has a narrative, an action, and at least one leading indicator.",
    "level_3_perceptual": "The matrix surfaces that 'strict regulation + stalled capability' (Soft landing) and 'loose regulation + fast growth' (Wild west) are opposite-corner extremes; the diagonal is where most tension concentrates.",
    "short_alt": "Scenario matrix for AI capability × regulation with four named futures."
  }
}
```

### Emission rules

1. **`type = "quadrant_matrix"`. `spec.subtype = "scenario_planning"` (mandatory).**
2. **`mode_context = "scenario-planning"`. `canvas_action = "replace"`. `relation_to_prose = "integrated"`.**
3. **All four quadrants (TL/TR/BL/BR) must have `name` and non-empty `narrative`** (the validator rejects empty narratives for `scenario_planning` subtype with `E_UNRESOLVED_REF`).
4. **Each quadrant should have ≥1 `indicators`** (the leading indicators from the prose).
5. **`axes_independence_rationale` must be non-empty and non-trivial** — the validator enforces presence; the rationale must actually address why the two uncertainties move independently.
6. **Axes (`x_axis`, `y_axis`) each have `label`, `low_label`, `high_label`.**
7. **No `items` in the envelope** unless the user has placed specific anchors (e.g. "EU trajectory at (0.3, 0.8)"). When present, each item has `label`, `x`, `y` in [0, 1].
8. **`semantic_description` required fields; `short_alt ≤ 150`.**
9. **One envelope.**

### What NOT to emit

- A good/bad/medium trio — scenarios must be structurally distinct, not value-tagged magnitudes.
- An envelope without all four quadrants populated.
- `subtype: "strategic_2x2"` — that's Constraint Mapping's shape, not Scenario Planning's.
- `canvas_action: "annotate"`.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN the analysis endorses one scenario as most likely, pause — SP does not predict.

**Structural distinctiveness guard rail.** Before emitting, verify: if I remove value-laden adjectives (good, bad), are these scenarios still distinguishable by causal logic?

**Strategy translation guard rail.** Do not emit scenarios without `action` / `indicators`.

**Axes independence guard rail.** Verify the `axes_independence_rationale` actually argues independence, not just asserts it.

## SUCCESS CRITERIA

Structural:
- S1-S6: envelope, schema, `type=quadrant_matrix`, `mode_context=scenario-planning`, `canvas_action=replace`, `relation_to_prose=integrated`.
- S7: `subtype == "scenario_planning"`.
- S8: all four quadrants present with non-empty `name` and `narrative`.
- S9: each quadrant has ≥1 `indicators`.
- S10: `axes_independence_rationale` non-empty (≥ 40 chars).
- S11: `x_axis` and `y_axis` each have `label`, `low_label`, `high_label`.
- S12: `semantic_description` complete, `short_alt ≤ 150`.

Semantic:
- M1: predetermined vs critical-uncertainty classification in prose.
- M2: scenarios are structurally distinct (not optimistic/pessimistic/baseline).
- M3: ≥ one wild-card scenario in prose.
- M4: ≥ one robust strategy vs ≥ one scenario-dependent strategy distinguished in prose.
- M5: no scenario is labelled "most likely".

Composite:
- C1: every quadrant name appears in prose.
- C2: each quadrant's `indicators` appear in prose's Leading Indicators section.
- C3: prose's axis labels match the envelope's `x_axis.label` / `y_axis.label`.

```yaml
success_criteria:
  mode: scenario-planning
  version: 1
  structural:
    - { id: S1-S6, check: standard_preamble }
    - { id: S7,    check: subtype_equals, value: scenario_planning }
    - { id: S8,    check: four_quadrants_with_narrative }
    - { id: S9,    check: each_quadrant_has_indicators, min: 1 }
    - { id: S10,   check: axes_independence_rationale_nontrivial, min_chars: 40 }
    - { id: S11,   check: axes_shape_complete }
    - { id: S12,   check: semantic_description_complete }
  semantic:
    - { id: M1, check: predetermined_vs_uncertain_in_prose }
    - { id: M2, check: scenarios_structurally_distinct }
    - { id: M3, check: wild_card_in_prose }
    - { id: M4, check: robust_vs_scenario_dependent }
    - { id: M5, check: no_most_likely_label }
  composite:
    - { id: C1, check: quadrant_names_in_prose }
    - { id: C2, check: indicators_in_leading_section }
    - { id: C3, check: axis_labels_match }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The Good/Bad/Medium Trap (inverse of M2).** Scenarios as optimistic/pessimistic/baseline. Correction: each scenario needs its own causal logic, not a magnitude label.

**The Official Future Trap (inverse of M5).** Labelling one scenario "most likely". Correction: no scenario receives a probability designation.

**The Story Without Strategy Trap.** Narratives without strategic implications. Correction: every quadrant needs `action` and `indicators`.

**The Certainty Masquerade Trap (inverse of M1).** Classifying a genuine uncertainty as predetermined. Correction: test each "predetermined" by asking what would make it avoidable.

**The Correlated-Axes Trap (inverse of S10).** Axes that move together — not independent. Correction: strengthen or replace; the rationale must argue decoupling.

## TOOLS

Tier 1: C&S, CAF, FIP, OPV.
Tier 2: Political and Social Analysis Module for geopolitical scenarios.

## TRANSITION SIGNALS

- IF the user wants to choose between strategies → propose **Decision Under Uncertainty** or **Constraint Mapping**.
- IF scenarios reveal institutional interests shaping driving forces → propose **Cui Bono**.
- IF the user begins a deliverable → propose **Project Mode**.
- IF the scenarios expose a foundational assumption → propose **Paradigm Suspension**.
- IF the driving forces involve feedback loops → propose **Systems Dynamics**.
