---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 2
---

# MODE: Decision Under Uncertainty

## TRIGGER CONDITIONS

Positive (fire the mode):
1. A choice must be made between alternatives with uncertain outcomes.
2. Probabilities matter but are not precisely known; the cost of being wrong is high.
3. Flexibility or optionality has value (the ability to defer, reverse, hedge, or buy information).
4. The decision has temporal dynamics — the cost of delay vs the benefit of learning is part of the question.
5. Decision-shaped request language: "should we act now or wait", "which option has the best expected value", "what's the downside of each option", "is it worth waiting for more information", "walk me through the decision tree".

Negative (route elsewhere):
- IF the user wants to map tradeoffs without incorporating probability or time-value → **Constraint Mapping**.
- IF the user wants to understand which explanation fits the evidence best (not which action to take) → **Competing Hypotheses**.
- IF the user wants to explore multiple possible futures rather than make a specific decision now → **Scenario Planning**.
- IF the question is "what could go wrong" along a causal cascade rather than "which alternative to pick" → **Consequences and Sequel**.

Tiebreakers:
- DUU vs Scenario Planning: **one decision now, uncertainty over outcomes** → DUU; **multiple futures to compare without immediate choice** → SP.
- DUU vs Constraint Mapping: **probabilities + time value matter** → DUU; **tradeoffs are deterministic** → CM.

## EPISTEMOLOGICAL POSTURE

Evidence is input to probability estimation, and uncertainty has formal structure. Three types of uncertainty are distinguished: risk (known probabilities), uncertainty (estimable probability ranges), and deep uncertainty (variables whose probabilities cannot be meaningfully assigned). Decisions have temporal dynamics: the cost of delay vs the benefit of learning. The option to wait and learn has value that must be weighed against the cost of delay. Non-quantifiable factors must be acknowledged alongside formal calculations — utility functions do not capture everything that matters.

## DEFAULT GEAR

Gear 3. Sequential review is sufficient: the Depth model structures the decision and assesses probabilities; the Breadth model challenges whether the framing captures all relevant alternatives, whether probability estimates are well-grounded, and whether non-quantifiable factors have been adequately considered. Gear 4 when the decision has multi-actor dynamics where each model needs independent framing to avoid anchoring.

## RAG PROFILE

**Retrieve (prioritise):** decision theory frameworks (expected utility, minimax regret, robustness analysis), domain-specific risk analyses, base-rate data for probability estimation, case studies of similar decisions. IF financial/investment, retrieve real-options methodology. IF policy, retrieve public decision-making frameworks (precautionary principle, robust decision-making).

**Deprioritise:** advocacy literature — sources should inform probability estimates, not argue for outcomes.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `enables`, `requires`, `contradicts`, `qualifies`
**Deprioritise:** `analogous-to`, `parent`, `child`
**Rationale:** Decision analysis needs dependency chains, constraint identification, and qualification of assumptions.


### RAG PROFILE — INPUT SPEC (context-package fields consumed)

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The stated decision and the alternatives the user is weighing |
| `conversation_rag` | Prior turns' probability estimates, discarded alternatives, updates from new info |
| `concept_rag` | Mental models — EU, real options, minimax regret, robust decision-making, value of information |
| `relationship_rag` | Domain objects with `enables` / `requires` / `contradicts` that gate the alternatives |
| `prior_spatial_representation` | Any decision tree or influence diagram the user drew; preserve branch structure and node ids |
| `spatial_representation` | User's current drawing of the decision landscape |
| `annotations` | User callouts flagging a branch, probability, or payoff as high-confidence or questionable |


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
1. Frame the decision: what are the alternatives (including **defer**, **sequence**, and **hedge** options), what outcomes are possible for each, and what can be deferred? **The alternatives become decision-node `children` in `spec.root` when emitting a decision tree.**
2. Classify the uncertainty type for each critical variable: risk (assignable probability), uncertainty (estimable range), or deep uncertainty (cannot assign meaningful probabilities). **This classification drives the envelope choice — decision_tree only when probabilities are assignable; otherwise prefer influence_diagram or tornado.**
3. For each alternative under each plausible state, assess consequences. Quantify where possible (`payoff` on terminal nodes); characterise qualitatively where quantification would be misleading.

Black Hat directives:
1. Challenge probability estimates. Are they grounded in base rates or anchored to initial assumptions? IF no base rate exists, state this explicitly — an estimate without a base rate is a guess.
2. Assess downside exposure for each alternative. What is the worst plausible outcome, and how bad is it? This informs the `payoff` on the worst-case terminal.
3. Evaluate whether the decision framing artificially constrains the alternatives. Can the user create new alternatives, sequence decisions, or buy information before committing? These become additional `decision`-kind nodes in the tree.

### Cascade — what to leave for the evaluator

Explicit structural cues the Depth analyst must leave so the evaluator can mechanically verify:

- Classify each critical variable in the "Uncertainty identification" paragraph with the literal labels `risk` / `uncertainty` / `deep uncertainty`. Supports M1.
- State `utility_units` verbatim in the "Consequence analysis" section (e.g. "USD millions (3-year NPV)") before the envelope — supports C4.
- Write probabilities as decimals (0.45, 0.40) in prose and envelope; never mix percentage and decimal forms within one analysis.
- For each `decision_tree` branch, state the expected value arithmetic in prose in the form `EV = Σ(p_i · payoff_i) = <number>`. Supports C1 and `level_2_statistical`.
- State the recommendation verbatim as "Recommendation: <first-level branch label>" so C1 traces.
- **short_alt discipline — IMPORTANT (Phase 5 iteration).** Emit `spec.semantic_description.short_alt` in Cesal form: for `decision_tree` — `"Decision tree comparing <alt1>, <alt2>, <alt3>."`; for `influence_diagram` — `"Influence diagram of <decision>."`; for `tornado` — `"Tornado chart of <outcome> sensitivity to <N> parameters."`. TARGET ≤ 100 chars. HARD MAX 150 chars — exceeding rejects the envelope with `E_SCHEMA_INVALID`. Do NOT enumerate every branch, probability, or payoff inside short_alt. Good: `"Decision tree comparing Launch, Pilot, Do-nothing."` (50 chars). Bad: `"Decision tree with three first-level branches (Launch, Pilot, Do nothing); Launch fans into three chance outcomes, Pilot into two, Do nothing is terminal..."` (180+ chars — rejected).

### Consolidator guidance

Not applicable at this mode's default gear (Gear 3). If promoted to Gear 4 — typically when multi-actor dynamics require independent framing — use Depth's decision-tree structure as reference frame for the envelope; present Breadth's additional alternatives (information-gathering, hedging, sequencing) as additional first-level branches added to Depth's tree rather than as a parallel tree. Reconcile probability disagreements by emitting both estimates in prose as a range and taking the midpoint to `spec`; flag as `uncertainty` in the classification.

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. Identify alternatives the framing may have excluded. Can alternatives be sequenced rather than chosen exclusively? Can options be created that preserve flexibility?
2. Conduct value-of-information analysis: what additional information would most reduce uncertainty? What would it cost to obtain? Is the expected value of that information greater than the cost of delay?
3. Identify hedging strategies — actions that reduce downside exposure without forfeiting upside potential.

Yellow Hat directives:
1. Identify robust alternatives — choices that perform acceptably across multiple plausible states rather than optimally in one. Tornado is the natural envelope when robustness-vs-parameter-swing is the question.
2. Assess what the user gains from each decision framework applied — does expected value analysis, minimax regret, or robustness analysis best serve this particular decision?
3. Identify reversibility — which alternatives can be undone or adjusted if conditions change, and what is the cost of reversal?

### Cascade — what to leave for the evaluator

Explicit structural cues the Breadth analyst must leave so the evaluator can mechanically verify:

- Use the literal phrase "value of information" at least once in the VOI section. Supports M2.
- When proposing a defer/pilot/hedge alternative, label it explicitly (`Defer:`, `Pilot first:`, `Hedge by:`). Supports decision framing rubric #6.
- For non-quantifiable factors, use the literal heading "Non-quantifiable factors" exactly as specified in content contract clause 6. Supports M3.
- When recommending a `tornado` or `influence_diagram` over `decision_tree`, state the rationale with the literal phrase "sensitivity is the core question" or "dependency structure dominates" — supports M4 envelope-match check.

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Uncertainty Classification.** 5=each critical variable classified as risk, uncertainty, or deep uncertainty with reasoning. 3=classification attempted but one variable miscategorised. 1=all variables treated as either risk or complete ignorance without distinction.
6. **Decision Framing Quality.** 5=alternatives include sequencing, information-gathering, and hedging options alongside direct choices. 3=standard alternatives identified but no creative framing. 1=decision presented as binary when alternatives exist.
7. **Value-of-Information Assessment.** 5=specific information identified that would most reduce uncertainty, with cost of obtaining it vs cost of delay assessed. 3=information needs identified but cost-benefit not assessed. 1=no value-of-information analysis performed.
8. **Envelope Match.** 5=envelope type matches the decision structure (tree for sequential, influence_diagram for dependency-driven, tornado for sensitivity). 3=envelope used but one structural feature is suppressed or overstated. 1=envelope type contradicts the decision framing.

### Focus for this mode

A strong DUU evaluator prioritises in this order:

1. **Envelope-match first (M4, S3).** Using `decision_tree` for a pure sensitivity question, or `tornado` for a sequential choice, invalidates the structural framing — mandate fix before semantic critique.
2. **Probability-sum (S8).** Non-summing chance-node children are rejected by validator; mandate arithmetic fix.
3. **Two-value-nodes trap (S9).** Influence diagram with > 1 `value` node is rejected; mandate merge.
4. **Utility-units consistency (C4).** Silent unit drift between prose and `spec.utility_units` is a composite failure; mandate sync.
5. **Missing-defer (Decision Framing rubric).** Binary framing when wait-and-learn is feasible is a suggestion, not a fix, unless the content contract required defer explicitly.
6. **Short_alt discipline (S12).** Name the dominant branch's comparison, not every branch.

### Suggestion templates per criterion

- **S12 (short_alt):** `suggested_change`: "Rewrite short_alt as: 'Decision tree comparing <alt1>, <alt2>, <alt3> with probabilistic payoffs.' (or equivalent for influence_diagram / tornado). Do not enumerate every branch or probability. Target ≤ 100 chars."  `criterion_it_would_move`: `S12`.
- **S8 (probability sum):** `suggested_change`: "At chance node '<label>', children probabilities sum to <current_sum>, must equal 1.0 ± 1e-6. Adjust probabilities to sum to 1.0 — distribute delta across the most-uncertain branch or name the missing branch explicitly."  `criterion_it_would_move`: `S8`.
- **S9 (multiple value nodes):** `suggested_change`: "Merge to exactly one `value` node. Option A: combine multi-outcome into a weighted utility. Option B: promote the secondary outcome to a `chance` or `decision` node with the primary as its functional child."  `criterion_it_would_move`: `S9`.
- **M4 (wrong envelope):** `suggested_change`: "Switch envelope type — current type <X> does not fit the framing. Rule: sequential choice under assignable probabilities ⇒ `decision_tree`; dependency structure dominates ⇒ `influence_diagram`; parameter-swing-is-the-question ⇒ `tornado`."  `criterion_it_would_move`: `M4`.
- **C4 (units drift):** `suggested_change`: "Align `spec.utility_units` with the prose's consequence-analysis units verbatim. If prose says 'millions of USD (3-year NPV)', `utility_units` must be the exact string."  `criterion_it_would_move`: `C4`.
- **Defer alternative missing:** `suggested_change`: "Add a `Do nothing / defer` or `Run pilot first` first-level branch when feasible; value-of-information analysis is structurally required for decisions with >N months of reversibility."  `criterion_it_would_move`: Decision Framing rubric.

### Known failure modes to call out

Dispatch rule:

- **Wrong-Envelope Trap** → open: "Envelope type <X> does not match the framing <Y>. This is a structural failure."
- **Probability-Sum Trap** → open: "Chance node <label>'s children sum to <N>, not 1.0. Mandatory arithmetic fix."
- **Two-Value-Nodes Trap** → open: "Influence diagram has <N> value nodes; exactly one required. Mandate merge."
- **Silent-Probability Trap** → surface as fix (C3): "Envelope contains probability <p> for <outcome> not grounded in prose. Either derive in prose or remove."
- **Unit-Drift Trap** → surface as fix (C4) per template.
- **Missing-Defer Trap, Analysis-Paralysis Trap** → surface as SUGGESTED IMPROVEMENT with the Defer template.
- **False Precision Trap** → surface as SUGGESTED: "Replace point probability <0.17> with a range or a qualitative band when no base rate grounds the precision."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-DUU-1 — Probability-sum preservation.** Every `chance` node's children in the revised envelope sum to 1.0 ± 1e-6. Silent re-weighting during revision is a FAIL.
- **V-DUU-2 — Utility-units persistence.** `spec.utility_units` in revised envelope equals the prose's consequence-analysis units string verbatim.
- **V-DUU-3 — Recommendation-branch trace.** The revised prose's "Recommendation:" line names a first-level branch that exists in revised `spec.root.children`.
- **V-DUU-4 — Envelope type stability.** If the reviser changed envelope type (e.g. `decision_tree` → `tornado`), the CHANGELOG names the change with explicit rationale; silent type-change is a FAIL.

## CONTENT CONTRACT

The prose is complete when it contains, in order:

1. **Decision framing** — what is the decision, what are the alternatives (including defer, sequence, and hedge options), what can be deferred. **When emitting a `decision_tree`, the decision-node labels in the tree derive from this section.**
2. **Uncertainty identification** — what is known vs unknown, the uncertainty type for each critical variable, whether probabilities can be meaningfully assigned. **This determines whether the chosen envelope carries probabilities.**
3. **Consequence analysis** — for each alternative under each plausible state, the outcomes (quantified where appropriate, characterised qualitatively otherwise). Quantified outcomes become `payoff` on terminal nodes.
4. **Value-of-information analysis** — what information would most reduce uncertainty, what it is worth, whether to decide now or learn more first.
5. **Recommendation** — with explicit risk characterisation, stated confidence level, and conditions under which the recommendation should be revisited. The recommendation must be identifiable in the envelope (highest-EV branch for `decision_tree`; robust alternative for `tornado` under deep uncertainty; the value-maximising policy for `influence_diagram`).
6. **Non-quantifiable factors** — ethics, relationships, morale, identity, reputation — presented alongside the quantitative framework, not as footnotes.

After your analysis, emit exactly one fenced `ora-visual` block conforming to the EMISSION CONTRACT below as the final block of the response.

### Reviser guidance per criterion

When the evaluator's output mandates a fix:

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S2 (schema):** first error code guides: `E_PROB_SUM` → S8 template. `E_GRAPH_CYCLE` on functional arcs → restructure the influence-diagram DAG; most often a functional arc runs backward and should be reversed or retyped as `informational`.
- **S6 (relation):** set `envelope.relation_to_prose = "integrated"` — DUU envelope complements, not replaces, the prose argument.
- **S7 (decision-tree shape):** if `mode: "decision"`, every terminal must have numeric `payoff` and `spec.utility_units` must be present; root must be `decision` or `chance` kind.
- **S8 (probability sum):** apply S8 template.
- **S9 (influence-diagram shape):** apply S9 template; also ensure ≥ 1 `decision` + ≥ 1 `chance` + exactly 1 `value`.
- **S10 (tornado shape):** if `sort_by: "swing"`, re-sort parameters by descending absolute swing; every parameter needs all 5 numeric fields.
- **S12 (short_alt):** apply S12 template.
- **M1 (uncertainty not classified):** add classification labels to the "Uncertainty identification" section using the literal `risk` / `uncertainty` / `deep uncertainty` vocabulary.
- **M2 (VOI missing):** add a one-paragraph VOI section using the literal phrase "value of information".
- **M3 (non-quantifiable factors not acknowledged):** add the "Non-quantifiable factors" content-contract section.
- **M4 (envelope mismatch):** apply M4 template — switch envelope type to match framing.
- **M5 (recommendation conditions):** add one sentence to the recommendation paragraph naming what would change it.
- **C1 (recommendation not traceable):** align recommendation paragraph's branch name with a first-level branch `edge_label` in the envelope.
- **C2 (alternatives coverage):** add any prose alternative missing from the envelope as a first-level branch; or document explicit exclusion in prose.
- **C3 (silent probability):** either derive the probability in prose or remove it from the envelope.
- **C4 (units drift):** apply C4 template.

## EMISSION CONTRACT

Decision Under Uncertainty produces a response containing BOTH prose (the six content-contract sections above) AND exactly one fenced `ora-visual` block. The prose arrives first; the envelope is the final block of the response.

### Envelope type selection (three alternatives)

- **`decision_tree`** (default) — when the decision is sequential: an ordered cascade of decision and chance nodes, each with discrete branches and (for chance nodes) assignable probabilities. Use `mode: "decision"` with a declared `utility_units` when payoffs are quantified; `mode: "probability"` when only the probability tree matters and payoffs are elsewhere.
- **`influence_diagram`** — when dependency structure matters more than sequence: multiple decision and chance nodes feeding into exactly one value node, with `informational`, `functional`, and `relevance` arcs capturing what knows what. Use when the user is reasoning about which variable depends on which before worrying about sequence.
- **`tornado`** — when the question is "which input parameter dominates the outcome": base-case value + parameters swept between `low_value` and `high_value` with resulting `outcome_at_low` / `outcome_at_high`. Use for sensitivity analysis and robustness framing under deep uncertainty.

Selection rule:
- **If** a sequential choice under assignable probabilities is the core → `decision_tree`.
- **Else if** dependency structure dominates (e.g. "what does the decision depend on; what does the chance node depend on") → `influence_diagram`.
- **Else if** the user is asking which assumption swings the answer → `tornado`.
- Default when unclear: `decision_tree` with `mode: "decision"`.

`relation_to_prose: "integrated"` for all three — the envelope complements the prose; it is not the whole argument.

### Canonical envelope (decision_tree, mode=decision)

```ora-visual
{
  "schema_version": "0.2",
  "id": "duu-fig-1",
  "type": "decision_tree",
  "mode_context": "decision-under-uncertainty",
  "relation_to_prose": "integrated",
  "title": "Launch decision — expected payoff rollback",
  "canvas_action": "replace",
  "spec": {
    "mode": "decision",
    "utility_units": "USD millions (3-year NPV)",
    "root": {
      "kind": "decision",
      "label": "Launch now?",
      "children": [
        {
          "edge_label": "Launch",
          "node": {
            "kind": "chance",
            "label": "Market reception",
            "children": [
              { "edge_label": "Strong",    "probability": 0.45,
                "node": { "kind": "terminal", "label": "Strong uptake", "payoff": 18 } },
              { "edge_label": "Moderate",  "probability": 0.40,
                "node": { "kind": "terminal", "label": "Meets plan",    "payoff": 5  } },
              { "edge_label": "Weak",      "probability": 0.15,
                "node": { "kind": "terminal", "label": "Write-down",    "payoff": -7 } }
            ]
          }
        },
        {
          "edge_label": "Run 3-month pilot first",
          "node": {
            "kind": "chance",
            "label": "Pilot signal",
            "children": [
              { "edge_label": "Green light", "probability": 0.55,
                "node": { "kind": "terminal", "label": "Launch delayed but informed", "payoff": 9 } },
              { "edge_label": "Red flag",    "probability": 0.45,
                "node": { "kind": "terminal", "label": "Cancel, pilot cost sunk",     "payoff": -1 } }
            ]
          }
        },
        {
          "edge_label": "Do nothing",
          "node": { "kind": "terminal", "label": "Status quo", "payoff": 0 }
        }
      ]
    }
  },
  "semantic_description": {
    "level_1_elemental": "Decision tree with three first-level branches (Launch, Pilot, Do nothing); Launch fans into three chance outcomes, Pilot into two, Do nothing is terminal.",
    "level_2_statistical": "Expected payoffs: Launch = 0.45·18 + 0.40·5 + 0.15·(-7) = 9.05; Pilot = 0.55·9 + 0.45·(-1) = 4.50; Do nothing = 0. Launch dominates on EV.",
    "level_3_perceptual": "Launch has the highest EV but the widest downside range (-7 to 18); Pilot is narrower but lower-EV; Do nothing is risk-free zero.",
    "short_alt": "Decision tree comparing Launch, Pilot-first, and Do-nothing with probabilistic payoffs."
  }
}
```

### Emission rules (decision_tree)

1. **`mode_context` must be `"decision-under-uncertainty"`** (hyphens).
2. **`relation_to_prose` must be `"integrated"`.**
3. **`canvas_action` must be `"replace"`.**
4. **`spec.mode ∈ {"decision", "probability"}`.** If `decision`, `spec.utility_units` is required and every `terminal` node must carry a `payoff`.
5. **`spec.root.kind` must be `"decision"` or `"chance"`** — root terminals are not decisions.
6. **Every `chance` node's children probabilities must sum to 1.0** (± 1e-6). The validator rejects mismatches with `E_PROB_SUM`.
7. **Decision-node children must not carry `probability`** — only chance-node edges do. The validator rejects decision-edge probabilities with `E_PROB_SUM`.
8. **Every `terminal` must have a `payoff` (number) when `mode: "decision"`.**
9. **Decision nodes must have at least one child.** A leaf decision is a missing branch.
10. **`semantic_description` includes all four required fields**, with `short_alt ≤ 150 chars`. Level 2 should state the EV arithmetic so the comparison is traceable.

### Emission rules (influence_diagram — alternative)

When dependency structure matters more than sequence, emit `type: "influence_diagram"` with:

- `spec.nodes` — at least one each of `decision`, `chance`, and `value` kinds; exactly one `value` node (validator enforces).
- `spec.arcs` — each with `type ∈ {"informational", "functional", "relevance"}`. `informational` into decision means the decision knows the variable; `functional` means the variable is a deterministic function of its parents; `relevance` is a soft probabilistic dependency.
- `spec.temporal_order` — an ordered list of node ids. No arc may run from a later-decided node into an earlier-decided decision (temporal consistency).
- The functional subgraph must be acyclic; the validator rejects cycles with `E_GRAPH_CYCLE`.

### Emission rules (tornado — alternative)

When sensitivity is the question, emit `type: "tornado"` with:

- `spec.base_case_label`, `spec.base_case_value` (number), `spec.outcome_variable`, `spec.outcome_units` — all non-empty.
- `spec.parameters` — at least 2 entries; each with `label`, `low_value`, `high_value`, `outcome_at_low`, `outcome_at_high` (all numbers).
- `spec.sort_by ∈ {"swing", "high_impact", "custom"}`. When `sort_by = "swing"`, parameters must be ordered by descending absolute swing; the validator enforces this.
- Tornado is QUANT-family; the Tufte T-rule layer applies (no 3D marks, no pie, banking for time_series doesn't apply).

### What NOT to emit

- **Do not** set `canvas_action: "annotate"` — that is Spatial Reasoning's mode.
- **Do not** emit a decision tree with chance-node probabilities that don't sum to 1.0.
- **Do not** emit two value nodes in an influence diagram (exactly one required).
- **Do not** emit a tornado with parameters unsorted by swing when `sort_by="swing"`.
- **Do not** put `probability` on a decision-node edge — the validator flags this with `E_PROB_SUM`.

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN a recommendation is presented, THEN verify it accounts for what the analysis does not know. A confident recommendation under deep uncertainty requires explicit justification.

**Humility guard rail.** State what the analysis assumes, what it does not know, and what would change the recommendation. Every recommendation is conditional — state the conditions.

**Non-quantifiable factors guard rail.** Before finalising, ask: are there factors that matter but resist quantification? IF so, present them alongside the quantitative framework, not as footnotes.

**Probability-sum guard rail.** WHEN a chance node has children, THEN verify their probabilities sum to 1.0 (± 1e-6) before emitting. The validator rejects otherwise.

**Envelope-match guard rail.** WHEN choosing envelope type, THEN check: sequential choice ⇒ decision_tree; dependency structure ⇒ influence_diagram; parameter-swing ⇒ tornado. A mismatch between framing and envelope is a structural error.

**Temporal consistency guard rail (influence_diagram).** WHEN declaring a `temporal_order`, THEN verify no arc runs from a later-decided node into an earlier decision. The validator catches this, but the guard is to think about it BEFORE emitting.

## SUCCESS CRITERIA

### Structural (machine-checkable)

- **S1 — Envelope presence.** Exactly one `ora-visual` fence, parseable JSON.
- **S2 — Schema validity.** Passes `validate_envelope` with zero errors.
- **S3 — Mode-correct type.** `envelope.type ∈ {"decision_tree", "influence_diagram", "tornado"}`.
- **S4 — Mode context.** `envelope.mode_context == "decision-under-uncertainty"`.
- **S5 — Canvas action.** `envelope.canvas_action == "replace"`.
- **S6 — Relation to prose.** `envelope.relation_to_prose == "integrated"`.
- **S7 — Decision-tree shape (if type=decision_tree).** `spec.mode ∈ {"decision","probability"}`; root is `decision` or `chance`; if `mode: "decision"` then `utility_units` present and every terminal has `payoff`.
- **S8 — Probability sums (if type=decision_tree).** Every `chance` node's children probabilities sum to 1.0 ± 1e-6.
- **S9 — Influence-diagram shape (if type=influence_diagram).** Exactly one `value` node; at least one `decision` and one `chance`; every arc has a valid `type`.
- **S10 — Tornado shape (if type=tornado).** `parameters` ≥ 2; every parameter has all 5 numeric fields; if `sort_by=swing`, parameters are descending-by-swing.
- **S11 — Acyclicity (influence_diagram).** Functional-arc subgraph is a DAG.
- **S12 — Semantic description complete.** All four required fields non-empty; `short_alt ≤ 150 chars`.

### Semantic (LLM-reviewer)

- **M1 — Uncertainty classification in prose.** Each critical variable classified risk / uncertainty / deep uncertainty with reasoning.
- **M2 — Value-of-information treatment.** Prose addresses whether to decide now or buy information first.
- **M3 — Non-quantifiable factors acknowledged.** At least one non-quantifiable factor named and weighted, not just footnoted.
- **M4 — Envelope match.** The chosen envelope matches the framing (sequential / dependency / sensitivity) — if the model is using a decision tree for a pure sensitivity question, M4 fails.
- **M5 — Recommendation conditions stated.** The recommendation paragraph names what would change it.

### Composite (prose + envelope)

- **C1 — Recommendation traceability (decision_tree).** Prose recommendation names one of the decision-tree's first-level branches, and its EV is highest (or robustness is explicitly invoked for a lower-EV branch).
- **C2 — Alternatives coverage.** Every alternative in prose appears as a first-level branch in `spec.root.children` (for decision_tree) or a decision node (for influence_diagram) or an excluded-alternative note.
- **C3 — Probability plausibility.** Every probability on the envelope appears either as a number, a range, or a qualitative band in prose; no silent fabrication.
- **C4 — Units agreement.** When `mode: "decision"`, prose's consequence analysis uses the same units string as `spec.utility_units`.

### Machine-readable summary

```yaml
success_criteria:
  mode: decision-under-uncertainty
  version: 1
  structural:
    - { id: S1,  check: envelope_present }
    - { id: S2,  check: envelope_schema_valid }
    - { id: S3,  check: type_in_allowlist, allowlist: [decision_tree, influence_diagram, tornado] }
    - { id: S4,  check: mode_context_equals, value: decision-under-uncertainty }
    - { id: S5,  check: canvas_action_equals, value: replace }
    - { id: S6,  check: relation_to_prose_equals, value: integrated }
    - { id: S7,  check: decision_tree_shape, applies_to: decision_tree }
    - { id: S8,  check: chance_probabilities_sum_to_one, applies_to: decision_tree }
    - { id: S9,  check: influence_diagram_shape, applies_to: influence_diagram }
    - { id: S10, check: tornado_shape, applies_to: tornado }
    - { id: S11, check: functional_arc_dag, applies_to: influence_diagram }
    - { id: S12, check: semantic_description_complete }
  semantic:
    - { id: M1, check: uncertainty_classified_in_prose }
    - { id: M2, check: voi_addressed }
    - { id: M3, check: nonquantifiable_factors_acknowledged }
    - { id: M4, check: envelope_matches_framing }
    - { id: M5, check: recommendation_conditions_stated }
  composite:
    - { id: C1, check: recommendation_maps_to_branch }
    - { id: C2, check: alternatives_coverage }
    - { id: C3, check: probabilities_match_prose }
    - { id: C4, check: units_agreement, applies_to: decision_tree_mode_decision }
  acceptance:
    tier_a_threshold: 0.9
    structural_must_all_pass: true
    semantic_min_pass: 0.8
    composite_min_pass: 0.75
```

## KNOWN FAILURE MODES

**The False Precision Trap (inverse of M1).** Assigning specific probabilities ("17% chance") when genuine uncertainty makes such precision misleading. Correction: Use probability ranges rather than point estimates for uncertain variables; state the basis for every estimate.

**The Analysis-Paralysis Trap (inverse of M2).** Real options theory can rationalise indefinite delay because the option to wait always has positive value. Correction: Assess the cost of delay explicitly. IF the cost of delay exceeds the value of information from waiting, decide now.

**The Quantification Trap (inverse of M3).** Reducing all factors to utility functions when some factors resist meaningful quantification — ethics, relationships, morale, identity. Correction: Acknowledge non-quantifiable factors explicitly.

**The Anchoring Trap.** Initial probability estimates anchor subsequent analysis regardless of evidence. Correction: Generate estimates independently before comparing them. IF using Gear 4, independent estimation is architectural.

**The Probability-Sum Trap (inverse of S8).** Chance-node children probabilities don't sum to 1.0. Correction: Check arithmetic before emitting; use cumulative rounding instead of independent rounding.

**The Two-Value-Nodes Trap (inverse of S9).** Emitting an influence diagram with more than one value node. Correction: Exactly one value node; if two outcomes matter, merge them into a weighted value or declare one as a functional input to the other.

**The Wrong-Envelope Trap (inverse of M4).** Using a decision tree when the question is sensitivity (should be tornado), or a tornado when the question is sequence (should be decision_tree). Correction: Run the envelope selection rule against the question's shape before emitting.

**The Silent-Probability Trap (inverse of C3).** Introducing a probability in the envelope that was never discussed in prose. Correction: Every probability in `spec` is justified by at least a qualitative band in prose.

**The Unit-Drift Trap (inverse of C4).** Prose talks in millions USD; envelope talks in NPV-years-3. Correction: `utility_units` must match the consequence-analysis units verbatim.

**The Missing-Defer Trap (inverse of Decision Framing rubric).** Decision framed as binary (A or B) when "wait and learn" or "buy information" is a real alternative. Correction: Add a `Do nothing / defer` branch or a `Run pilot first` branch when feasible.

## TOOLS

Tier 1: C&S (consequences across time horizons for each alternative), PMI (evaluate each alternative's plus/minus/interesting), FIP (identify which uncertainties matter most), CAF (identify all factors including non-quantifiable ones).

Tier 2: Module 7 — Evaluation. Engineering and Technical Analysis Module for technical risk assessment.

## TRANSITION SIGNALS

- IF the decision requires exploring multiple possible futures → propose **Scenario Planning** to develop the states first.
- IF the decision involves institutional interests shaping the alternatives → propose **Cui Bono**.
- IF the user selects an alternative and wants to execute → propose **Project Mode**.
- IF the alternatives rest on unexamined assumptions → propose **Paradigm Suspension**.
- IF the user wants the strongest case for an alternative before deciding → propose **Steelman Construction**.
- IF the decision involves a system with feedback loops where interventions produce counterintuitive effects → propose **Systems Dynamics**.
