---
nexus: obsidian
type: mode
date created: 2026/04/17
date modified: 2026/04/18
rebuild_phase: 3
---

# MODE: Consequences and Sequel

## TRIGGER CONDITIONS

Positive:
1. "What would happen if", "what are the downstream effects", "second-order consequences".
2. Policy change impact analysis; "if we do X then what".
3. Requests for causal chain tracing beyond first-order effects.
4. Cascading implications of a decision or event; temporal evolution of effects.
5. Request language: "consequences", "sequel", "second-order", "cascade forward", "what does this lead to".

Negative:
- IF tracing backward from symptoms → **Root Cause Analysis**.
- IF circular feedback is the defining structure → **Systems Dynamics**.
- IF exploring multiple plausible futures under uncertainty → **Scenario Planning**.
- IF evaluating a single proposal's benefit/risk envelope → **Benefits Analysis**.

Tiebreakers:
- C&S vs RCA: **forward from action** → C&S; **backward from symptom** → RCA.
- C&S vs Systems Dynamics: **linear cascades (may fork but not loop)** → C&S; **feedback loops** → SD.

## EPISTEMOLOGICAL POSTURE

Effects propagate forward in time, and each effect becomes a cause of further effects. The important consequences are usually not the first-order ones but the second- and third-order ones. The analytical discipline is holding the cascade open long enough — not stopping at the first layer — and distinguishing effects by time horizon, confidence, and whether they are reinforcing (amplifying) or counteracting (dampening). Linear cascades are the object; when feedback loops appear, they are signals to transition to Systems Dynamics.

## DEFAULT GEAR

Gear 3. Sequential adversarial is the standard. Gear 4 when the cascade crosses multiple domains.

## RAG PROFILE

**Retrieve (prioritise):** historical cases of similar decisions and their actual downstream effects, outcome data for analogous policy changes, second-order effects documented in literature for the domain, de Bono's C&S framework.

**Deprioritise:** first-order-only analyses, promotional materials, short-horizon assessments.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `produces`, `enables`, `precedes`, `requires`, `contradicts`
**Deprioritise:** `parent`, `child`
**Rationale:** Forward cascades depend on what actions produce, what they enable, what must precede or follow.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The action or event to cascade from |
| `conversation_rag` | Prior turns' cascade attempts |
| `concept_rag` | C&S mental models, stakeholder frameworks |
| `relationship_rag` | Domain objects linked by `produces`/`precedes` |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. Audit each causal link for logical soundness with a stated mechanism.
2. Distinguish causally linked consequences from co-occurrences.
3. Identify where the cascade has been stopped prematurely — continue to second or third order.

Black Hat:
1. For each consequence, identify the specific condition under which it would NOT follow.
2. Identify feedback loops — if present, flag for SD transition; C&S is wrong tool for cycles.
3. Challenge the time-horizon distribution.

### Cascade — what to leave for the evaluator

- State the starting action with the literal opening `Action:` in prose — matches `focal_exposure`. Supports C1.
- For each consequence, prefix with `First-order:`, `Second-order:`, or `Third-order:` labels in prose. Supports chain depth rubric.
- For each link, state the mechanism with the literal phrase "mechanism:" in the surrounding sentence. Supports M1.
- Tag each consequence with a time-horizon label `[immediate]` / `[short]` / `[medium]` / `[long]`. Supports M2.
- If a feedback loop is detected, use the literal phrase "feedback loop detected — transitioning to Systems Dynamics" and suppress the envelope. Supports M5.
- **short_alt discipline — IMPORTANT (Phase 5 iteration).** Emit `spec.semantic_description.short_alt` in Cesal form: `"Causal DAG from <action ≤ 30 chars> to <primary outcome ≤ 30 chars>."` (or `"Flowchart of <action stem>."` for flowchart). TARGET ≤ 100 chars. HARD MAX 150 chars — exceeding rejects the envelope with `E_SCHEMA_INVALID`. Do NOT enumerate intermediate nodes, paths, or time horizons inside short_alt — that content lives in `level_1_elemental`. Good: `"Causal DAG from minimum-wage raise to urban prices."` (50 chars). Bad: `"Causal DAG cascading from a 40% price increase through demand, churn, brand perception, and operational shifts to long-horizon customer loyalty and margin compression..."` (185+ chars — rejected).
- **Envelope-as-final-block emphasis (Phase 5 iter-2).** The fenced `ora-visual` block MUST be the FINAL block of your response. Do not emit prose, citations, or caveats after it. Do not omit it — if you hit token budget, truncate the prose sections BEFORE the envelope, not the envelope itself. S1 (envelope absence) is the dominant residual failure at this mode; it surfaces when the model drifts into prose after writing the envelope intro or runs out of tokens in a long cascade. Emit the envelope DEFINITIVELY as your last act.

### Consolidator guidance

Not applicable at this mode's default gear (Gear 3). If promoted to Gear 4 — typically when the cascade crosses multiple domains — use Depth's cascade structure as reference frame; merge Breadth stream's cross-domain branches as additional subpaths in the causal_dag DSL.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Trace the causal cascade forward. Each effect becomes a cause. **First-order effects become direct `->` children of the action node in the causal_dag DSL; second-order effects cascade off those.**
2. Classify each link by time horizon: immediate / short / medium / long.
3. Identify unintended consequences.

Yellow Hat:
1. Identify reinforcing vs counteracting branches.
2. Identify cross-domain crossings.
3. Identify leading indicators for the most consequential distant effects.

### Cascade — what to leave for the evaluator

- Label each branch as `Reinforcing:` (amplifying) or `Counteracting:` (dampening). Supports M4.
- Use the literal phrase "unintended consequence:" for each effect outside the stated goal. Supports M3.
- Use the literal heading `Leading indicators:` for the leading-indicators section. Supports content contract clause 9.
- For cross-domain effects, prefix with `Cross-domain [<from domain> → <to domain>]:`.

## EVALUATION CRITERIA

5. **Chain Depth.** 5=third-order reached. 3=second-order but premature stop. 1=first-order only.
6. **Link Quality.** 5=every link has a mechanism. 3=one assumed without mechanism. 1=association only.
7. **Time-Horizon Distribution.** 5=immediate / short / medium / long all represented. 3=one horizon missing. 1=single horizon.
8. **Unintended Consequence Identification.** 5=surfaced and distinguished. 3=one missed. 1=intended only.

### Focus for this mode

A strong C&S evaluator prioritises:

1. **Acyclicity (S8).** DAG with a cycle is rejected; mandate SD transition.
2. **Chain depth (S10).** ≥ 1 path of length ≥ 3 (third-order reached).
3. **Node count (S9).** ≥ 5 distinct cascade nodes.
4. **Mechanism per link (M1).** Every link states a mechanism — association-only links fail.
5. **Time-horizon distribution (M2).** ≥ 3 of (immediate, short, medium, long) represented.
6. **Unintended consequences (M3).** At least one outside the stated goal.
7. **Short_alt (S11).** Name the cascade's start → dominant-path → end, not every node.

### Suggestion templates per criterion

- **S11 (short_alt):** `suggested_change`: "Rewrite short_alt as: 'Causal DAG cascading from <action stem> through <key intermediaries ≤ 40 chars> to <outcome>.' Target ≤ 100 chars."
- **S8 (cycle in DAG):** `suggested_change`: "Cycle detected between <A, B, C>. Either (a) remove one edge and document which edge is less defensible, or (b) suppress the envelope and propose transition to Systems Dynamics (cycles are not C&S's territory)."
- **S9 (< 5 nodes):** `suggested_change`: "Cascade has < 5 nodes. Add intermediate nodes representing second-order and third-order effects; a short cascade is not a cascade."
- **S10 (< 3-deep path):** `suggested_change`: "No path reaches third order. Extend at least one branch by asking: each effect becomes a cause — what does <second-order effect> then cause?"
- **M1 (association without mechanism):** `suggested_change`: "Link <A → B> has no stated mechanism in prose. Add a mechanism sentence: 'A causes B because <mechanism>' OR flag as speculative."
- **M3 (no unintended consequence):** `suggested_change`: "Add at least one unintended consequence — an effect outside the proposer's stated goal — prefixed 'unintended consequence:' in prose."

### Known failure modes to call out

- **Feedback-Loop Collapse** → open: "Cascade contains a cycle. Mandate SD transition or DAG edge-removal with rationale."
- **First-Order Trap** → open: "Cascade stops at immediate effects. Mandate extension to second and third order."
- **Association Trap** → open: "Links assert association without mechanism. Mandate mechanism per link."
- **Single-Horizon Trap** → open: "All effects in one time horizon. Mandate distribution across ≥ 3 horizons."
- **Intended-Effects-Only Trap** → open: "Only the proposer's stated goals traced. Mandate at least one unintended consequence."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-CS-1 — Acyclicity preservation.** Revised envelope is acyclic.
- **V-CS-2 — Focal-pair preservation.** Revised `focal_exposure` and `focal_outcome` match prose's Action and dominant outcome.
- **V-CS-3 — Third-order preservation.** ≥ 1 path of length ≥ 3 in revised envelope.
- **V-CS-4 — Mechanism-per-link preservation.** Every link in revised envelope has a corresponding mechanism sentence in revised prose.

## CONTENT CONTRACT

In order:

1. **Action / event** — the starting point, stated precisely. Becomes `focal_exposure` in the envelope.
2. **First-order consequences** — immediate direct effects with mechanism.
3. **Second-order consequences** — each with the causal link identified.
4. **Third-order consequences where tractable.**
5. **Time-horizon classification** — each effect tagged immediate / short / medium / long.
6. **Reinforcing and counteracting branches** — amplification vs offset.
7. **Cross-domain effects** — where the cascade traverses domains.
8. **Unintended consequences** — effects outside the stated goal.
9. **Leading indicators** — near-term signals for distant effects.
10. **Feedback-loop flag** — if any link returns to an earlier node, flag and propose SD transition.

After your analysis, emit exactly one fenced `ora-visual` block per EMISSION CONTRACT.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S2:** `E_GRAPH_CYCLE` → apply cycle template. `E_SCHEMA_INVALID` → often short_alt; apply S11.
- **S7:** pick envelope type — pure forward cascade → `causal_dag`; branching with decision points → `flowchart`.
- **S8:** apply cycle template for `causal_dag`; verify Mermaid syntax for `flowchart`.
- **S9:** apply < 5 nodes template.
- **S10:** apply third-order template.
- **S11:** apply short_alt template.
- **M1:** apply association-without-mechanism template.
- **M2:** redistribute consequences across time horizons using `[immediate]`/`[short]`/`[medium]`/`[long]` tags.
- **M3:** apply unintended-consequence template.
- **M4:** add both reinforcing and counteracting branches; label each.
- **M5 (feedback):** suppress envelope and transition to SD if a cycle is discovered during revision.
- **C1-C3:** sync focal_exposure, focal_outcome, and node names between prose and envelope.

## EMISSION CONTRACT

### Envelope type selection

- **`causal_dag`** (default) — forward cascade as a DAGitty DSL, with `focal_exposure` = the action and `focal_outcome` = the most consequential distant effect. DAG acyclicity is the structural guarantee — C&S cannot emit a cycle.
- **`flowchart`** — when the cascade has branching with decision points (IF X then Y else Z), a Mermaid flowchart is clearer than a DAG.

Selection rule: pure forward causal cascade → `causal_dag`; branching/conditional cascade → `flowchart`.

### Canonical envelope (causal_dag)

```ora-visual
{
  "schema_version": "0.2",
  "id": "cs-fig-1",
  "type": "causal_dag",
  "mode_context": "consequences-and-sequel",
  "relation_to_prose": "integrated",
  "title": "Cascade — raise minimum wage to $22/hr in urban centres",
  "canvas_action": "replace",
  "spec": {
    "dsl": "dag { wage [exposure]; prices [outcome]; small_biz; automation; labor_supply; migration; housing; wage -> prices; wage -> small_biz; small_biz -> automation; automation -> prices; wage -> labor_supply; labor_supply -> migration; migration -> housing; housing -> prices }",
    "focal_exposure": "wage",
    "focal_outcome": "prices"
  },
  "semantic_description": {
    "level_1_elemental": "Causal DAG tracing the effects of raising urban minimum wage on prices, with intermediate nodes for small business effects, automation, labor supply, migration, and housing.",
    "level_2_statistical": "Two forward paths from wage to prices — a direct path and an indirect path via small business automation; one longer path via labor supply, migration, and housing.",
    "level_3_perceptual": "The cascade has a short-horizon direct path (wage → prices) and longer-horizon indirect paths — second-order effects dominate the long-horizon structure.",
    "short_alt": "Causal DAG cascading from a minimum-wage raise through small business, labor supply, migration, and housing to prices."
  }
}
```

### Emission rules

1. **`type ∈ {"causal_dag", "flowchart"}`.**
2. **`mode_context = "consequences-and-sequel"`. `canvas_action = "replace"`. `relation_to_prose = "integrated"`.**
3. **For `causal_dag`:** `spec.dsl` parses as DAGitty; `focal_exposure` = the action; `focal_outcome` = the most consequential distant effect; graph is acyclic (validator enforces).
4. **For `flowchart`:** Mermaid flowchart syntax; decision nodes `{like this}` for forking points.
5. **At least 5 nodes in the cascade** — third-order effects require ≥ 5 nodes typically.
6. **If any cycle appears in the analysis, suppress the envelope and route to Systems Dynamics** — do NOT emit a cycle masquerading as a DAG.
7. **`semantic_description` required; `short_alt ≤ 150`.**
8. **One envelope.**

### What NOT to emit

- A DAG with a cycle (validator rejects with `E_GRAPH_CYCLE`; transition to SD instead).
- A cascade with only first-order effects (nodes adjacent to `focal_exposure` and no depth beyond).
- `canvas_action: "annotate"`.

## GUARD RAILS

**Solution Announcement Trigger.** WHEN the cascade supports a recommendation, verify the recommendation is about the action being analysed.

**Mechanism guard rail.** Every link has a mechanism.

**Feedback-detection guard rail.** If the cascade has a returning link, flag as feedback loop and route to SD.

**Third-order guard rail.** Before marking complete, verify ≥1 branch reaches third order.

## SUCCESS CRITERIA

Structural:
- S1-S6: standard preamble.
- S7: `type ∈ {"causal_dag", "flowchart"}`.
- S8: for `causal_dag`: acyclic (validator enforces), `focal_exposure` and `focal_outcome` declared in DSL.
- S9: ≥ 5 distinct nodes in the cascade.
- S10: at least one path has length ≥ 3 (third-order reached).
- S11: `semantic_description` complete; `short_alt ≤ 150`.

Semantic:
- M1: every link has a mechanism stated in prose.
- M2: time horizons distributed across ≥ 3 of (immediate, short, medium, long).
- M3: ≥ 1 unintended consequence explicitly named.
- M4: ≥ 1 reinforcing branch AND ≥ 1 counteracting branch named.
- M5: if feedback appears, flagged and SD proposed; envelope is suppressed or type changed.

Composite:
- C1: `focal_exposure` in envelope matches the "Action / event" named in prose.
- C2: `focal_outcome` corresponds to the most consequential distant effect named in prose.
- C3: every node in the DSL appears in prose (by label or equivalent phrase).

```yaml
success_criteria:
  mode: consequences-and-sequel
  version: 1
  structural:
    - { id: S1-S6, check: standard_preamble }
    - { id: S7,  check: type_in_allowlist, allowlist: [causal_dag, flowchart] }
    - { id: S8,  check: causal_dag_acyclic_with_focals, applies_to: causal_dag }
    - { id: S9,  check: min_nodes_in_cascade, min: 5 }
    - { id: S10, check: longest_path_at_least, len: 3 }
    - { id: S11, check: semantic_description_complete }
  semantic:
    - { id: M1, check: mechanism_per_link }
    - { id: M2, check: time_horizons_distributed }
    - { id: M3, check: unintended_consequence_named }
    - { id: M4, check: reinforcing_and_counteracting_branches }
    - { id: M5, check: feedback_handled_via_transition }
  composite:
    - { id: C1, check: focal_exposure_matches_prose }
    - { id: C2, check: focal_outcome_matches_prose }
    - { id: C3, check: all_dsl_nodes_in_prose }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The First-Order Trap (inverse of Chain Depth rubric, S10).** Stopping at immediate effects. Correction: continue each to ≥ second order; ≥ 1 branch to third.

**The Association Trap (inverse of M1).** Asserting X → Y without mechanism. Correction: state the mechanism or flag as speculative.

**The Feedback-Loop Collapse (inverse of M5).** Treating circular causation as linear. Correction: transition to SD.

**The Single-Horizon Trap (inverse of M2).** Only one time horizon. Correction: distribute across immediate / short / medium / long.

**The Intended-Effects-Only Trap (inverse of M3).** Tracing only the proposer's stated goals. Correction: actively search for unintended effects.

## TOOLS

Tier 1: C&S (primary), CAF, Challenge, AGO.
Tier 2: Domain modules as applicable (Political/Social, Engineering, Economic, Ecological).

## TRANSITION SIGNALS

- IF circular causation appears → propose **Systems Dynamics**.
- IF evaluating benefit/risk envelope at first order → propose **Benefits Analysis**.
- IF choosing between actions given the cascade → propose **Constraint Mapping** or **Decision Under Uncertainty**.
- IF exploring multiple futures → propose **Scenario Planning**.
- IF cascade reveals structural interests → propose **Cui Bono**.
- IF tracing backward to root cause → propose **Root Cause Analysis**.
- IF strategic interaction shapes the cascade → propose **Strategic Interaction**.
